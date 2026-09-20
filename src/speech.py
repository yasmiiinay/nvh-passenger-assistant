"""Speech pipeline: audio quality gate, Whisper-base transcription, hand-off
to the text cascade (Architecture Freeze v1.1 4.2).

The transcript goes through exactly the normaliser and entity extractor the
typed path uses; there is no speech-specific text handling. What the speech
layer adds is the gate in front (duration and loudness) and the record of
what Whisper produced before normalisation, so that the evaluation can
separate transcription errors from retrieval errors.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path

import numpy as np

from configs.settings import SETTINGS
from src.entities import extract
from src.normalizer import normalize_l1, normalize_l2
from src.retrieval import resolve


# ---------------------------------------------------------------------------
# audio loading and the quality gate
# ---------------------------------------------------------------------------

@dataclass
class AudioCheck:
    seconds: float
    rms_dbfs: float
    sample_rate: int
    ok: bool
    problem: str | None = None


def load_audio(path: str | Path, target_rate: int = SETTINGS.audio_sample_rate) -> tuple[np.ndarray, int]:
    """Mono float32 samples at the target rate. Raises ValueError on
    unreadable files."""
    import soundfile as sf
    from scipy.signal import resample_poly
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"audio file not found: {path}")
    try:
        samples, rate = sf.read(str(path), dtype="float32", always_2d=True)
    except (RuntimeError, sf.LibsndfileError) as exc:
        raise ValueError(f"cannot read audio {path.name}: {exc}") from exc
    mono = samples.mean(axis=1)
    if rate != target_rate:
        gcd = np.gcd(rate, target_rate)
        mono = resample_poly(mono, target_rate // gcd, rate // gcd).astype(np.float32)
    return mono, target_rate


def rms_dbfs(samples: np.ndarray) -> float:
    rms = float(np.sqrt(np.mean(np.square(samples)))) if len(samples) else 0.0
    return float(20 * np.log10(rms)) if rms > 0 else -120.0


def check_audio(samples: np.ndarray, rate: int,
                min_seconds: float = SETTINGS.audio_min_seconds,
                max_seconds: float = SETTINGS.audio_max_seconds,
                min_rms_dbfs: float = SETTINGS.audio_min_rms_dbfs) -> AudioCheck:
    """Duration bounds and a loudness floor. A clip that fails is not
    transcribed; the passenger is asked to re-record or type."""
    seconds = len(samples) / rate
    loudness = rms_dbfs(samples)
    check = AudioCheck(round(seconds, 2), round(loudness, 1), rate, ok=True)
    if seconds < min_seconds:
        check.ok, check.problem = False, f"too short ({seconds:.1f} s)"
    elif seconds > max_seconds:
        check.ok, check.problem = False, f"too long ({seconds:.0f} s)"
    elif loudness < min_rms_dbfs:
        check.ok, check.problem = False, f"too quiet ({loudness:.0f} dBFS)"
    return check


# ---------------------------------------------------------------------------
# Whisper, loaded on first use
# ---------------------------------------------------------------------------

_asr = None


def load_whisper():
    global _asr
    if _asr is None:
        from transformers import pipeline
        local_copy = SETTINGS.models_dir / SETTINGS.whisper_model_id.split("/")[-1]
        source = str(local_copy) if local_copy.exists() else SETTINGS.whisper_model_id
        _asr = pipeline("automatic-speech-recognition", model=source, device="cpu")
    return _asr


MAX_NEW_TOKENS = 64   # a passenger query is a sentence or two; see the docstring below


def transcribe(samples: np.ndarray, rate: int) -> str:
    """Raw Whisper text, English forced so that a non-English utterance is
    transcribed as best-effort English rather than translated or skipped.

    Decoding is capped at MAX_NEW_TOKENS. Measured on this project's CPU
    environment, a pure tone that passes the loudness gate made Whisper-base
    emit punctuation until its 448-token limit (about 31 s); the cap bounds
    that to a few seconds without touching real queries, which are far
    shorter than 64 tokens."""
    asr = load_whisper()
    out = asr({"raw": samples, "sampling_rate": rate},
              generate_kwargs={"language": "english", "task": "transcribe",
                               "max_new_tokens": MAX_NEW_TOKENS})
    return out["text"].strip()


def has_speech_text(text: str) -> bool:
    """Whisper emits runs of dots or dashes for non-speech input; a transcript
    with no letters is treated as no speech."""
    return any(ch.isalpha() for ch in text)


# ---------------------------------------------------------------------------
# hand-off into the text cascade
# ---------------------------------------------------------------------------

@dataclass
class SpeechResult:
    path: str
    check: AudioCheck
    transcript_raw: str | None = None
    transcript_l1: str | None = None
    transcript_l2: str | None = None
    identifiers: list[str] = field(default_factory=list)   # canonical identifiers found after L2
    retrieval: dict | None = None                            # RetrievalResult.as_dict(), if run

    def as_dict(self) -> dict:
        return asdict(self)


def process_transcript(result: SpeechResult, text: str, gaz, index, thresholds: dict,
                       run_retrieval: bool = True) -> SpeechResult:
    """Everything after Whisper: the two normalisation levels, the
    identifiers the L2 text yields, and the frozen text cascade."""
    result.transcript_raw = text
    result.transcript_l1 = normalize_l1(text)
    result.transcript_l2 = normalize_l2(text)
    result.identifiers = [e.value for e in extract(text, gaz).entities
                          if e.type in ("gate_id", "desk_id", "belt_id")]
    if run_retrieval:
        result.retrieval = resolve(text, gaz, index, thresholds).as_dict()
    return result


def process_audio(path: str | Path, gaz, index, thresholds: dict) -> SpeechResult:
    samples, rate = load_audio(path)
    check = check_audio(samples, rate)
    result = SpeechResult(path=str(path), check=check)
    if not check.ok:
        return result
    text = transcribe(samples, rate)
    if not has_speech_text(text):
        result.transcript_raw = text
        result.check.ok, result.check.problem = False, "no speech recognised"
        return result
    return process_transcript(result, text, gaz, index, thresholds)
