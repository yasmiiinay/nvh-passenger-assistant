"""Speech pipeline: the gate, loading, the shared normaliser on transcripts
and the hand-off into the text cascade (always run, with generated audio and
a stand-in transcriber), plus Whisper itself when the weights exist."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from configs.settings import SETTINGS
from src.entities import load_gazetteers
from src import speech
from src.speech import SpeechResult, check_audio, load_audio, process_transcript, rms_dbfs

RATE = 16000


def tone(seconds: float, amplitude: float = 0.1, rate: int = RATE) -> np.ndarray:
    t = np.arange(int(seconds * rate)) / rate
    return (amplitude * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def write_wav(path, samples, rate=RATE):
    import soundfile as sf
    sf.write(str(path), samples, rate)


@pytest.fixture(scope="module")
def gaz():
    return load_gazetteers(SETTINGS.kb_path, SETTINGS.vocabulary_path)


# ---- always run ----

def test_duration_gate():
    assert not check_audio(tone(0.4), RATE).ok
    assert "too short" in check_audio(tone(0.4), RATE).problem
    assert check_audio(tone(0.9), RATE).ok      # a three-word query lasts under a second
    assert check_audio(tone(3.0), RATE).ok
    assert "too long" in check_audio(tone(SETTINGS.audio_max_seconds + 5), RATE).problem


def test_rms_gate():
    assert rms_dbfs(np.zeros(RATE, dtype=np.float32)) == -120.0
    assert check_audio(np.zeros(RATE * 2, dtype=np.float32), RATE).problem.startswith("too quiet")
    assert check_audio(tone(2.0, amplitude=0.002), RATE).problem.startswith("too quiet")
    assert check_audio(tone(2.0, amplitude=0.05), RATE).ok


def test_load_audio_mono_and_resampled(tmp_path):
    stereo = np.stack([tone(2.0, rate=44100), tone(2.0, rate=44100)], axis=1)
    path = tmp_path / "stereo44.wav"
    write_wav(path, stereo, 44100)
    samples, rate = load_audio(path)
    assert rate == RATE and samples.ndim == 1
    assert abs(len(samples) / rate - 2.0) < 0.01
    assert check_audio(samples, rate).ok


def test_load_audio_errors(tmp_path):
    with pytest.raises(ValueError, match="not found"):
        load_audio(tmp_path / "missing.wav")
    bad = tmp_path / "bad.wav"
    bad.write_bytes(b"not audio")
    with pytest.raises(ValueError, match="cannot read"):
        load_audio(bad)


def test_transcript_uses_the_shared_normaliser_and_keeps_identifiers(gaz):
    result = SpeechResult("x.wav", check_audio(tone(2.0), RATE))
    process_transcript(result, "Where is gate bee twelve, near Terminal one?", gaz, None, None,
                       run_retrieval=False)
    assert result.transcript_l1 == "where is gate bee 12 near terminal 1"
    assert result.transcript_l2 == "where is gate b12 near terminal 1"
    assert result.identifiers == ["B12"]
    result = SpeechResult("y.wav", check_audio(tone(2.0), RATE))
    process_transcript(result, "desk one forty five and belt eight", gaz, None, None, run_retrieval=False)
    assert result.identifiers == ["DESK 145", "BELT 8"]


def test_handoff_reaches_the_text_cascade_with_a_stand_in_transcriber(gaz, tmp_path, monkeypatch):
    path = tmp_path / "gate.wav"
    write_wav(path, tone(2.0))
    monkeypatch.setattr(speech, "transcribe", lambda samples, rate: "Where is gate B12?")
    result = speech.process_audio(path, gaz, None, SETTINGS.thresholds())
    assert result.check.ok and result.transcript_raw == "Where is gate B12?"
    assert result.retrieval["decision"] == "answer"
    assert result.retrieval["matched_record_id"] == "gates_pier_b"
    assert result.retrieval["stage"] == "exact_identifier"


def test_failed_gate_skips_transcription(gaz, tmp_path, monkeypatch):
    path = tmp_path / "silence.wav"
    write_wav(path, np.zeros(RATE * 2, dtype=np.float32))
    def boom(samples, rate):
        raise AssertionError("transcriber called on a rejected clip")
    monkeypatch.setattr(speech, "transcribe", boom)
    result = speech.process_audio(path, gaz, None, SETTINGS.thresholds())
    assert not result.check.ok and result.transcript_raw is None and result.retrieval is None
    assert set(result.as_dict()) >= {"check", "transcript_raw", "transcript_l2", "identifiers", "retrieval"}


def test_non_speech_transcript_is_rejected_after_the_gate(gaz, tmp_path, monkeypatch):
    """A tone passes the loudness gate; Whisper answers with dots. That must
    end as a rejected clip, not as a query to the text cascade."""
    path = tmp_path / "tone.wav"
    write_wav(path, tone(2.0))
    monkeypatch.setattr(speech, "transcribe", lambda samples, rate: "........")
    result = speech.process_audio(path, gaz, None, SETTINGS.thresholds())
    assert not result.check.ok and result.check.problem == "no speech recognised"
    assert result.retrieval is None
    assert speech.has_speech_text("Where is gate B12?") and not speech.has_speech_text("... --- ...")


# ---- Whisper needed ----

@pytest.fixture(scope="module")
def asr():
    pytest.importorskip("transformers")
    try:
        return speech.load_whisper()
    except Exception as exc:
        pytest.skip(f"Whisper not available here: {type(exc).__name__}")


def test_whisper_tone_is_bounded_and_not_speech(asr):
    import time
    start = time.perf_counter()
    text = speech.transcribe(tone(2.0), RATE)
    assert time.perf_counter() - start < 30            # the token cap keeps non-speech decoding short
    assert isinstance(text, str) and not speech.has_speech_text(text)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
