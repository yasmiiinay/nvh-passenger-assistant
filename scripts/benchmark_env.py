"""Model load-time / memory / latency benchmark harness (Evidence Pack section A2).

Warm-up runs are separated from measured runs; median, min and max are
reported with the process RSS before and after. Loaders are added as the
models enter the pipeline; entries still set to None raise
NotImplementedError. NEVER report a timing that was not produced by running
this script on the machine in question (the row records python, machine
and device).

Usage:
    python scripts/benchmark_env.py --model noop
    python scripts/benchmark_env.py --model minilm --warmup 1 --runs 3
    python scripts/benchmark_env.py --model minilm_encode --warmup 1 --runs 5
    python scripts/benchmark_env.py --model clip --warmup 1 --runs 3
    python scripts/benchmark_env.py --model clip_encode --warmup 1 --runs 5
    python scripts/benchmark_env.py --model whisper --warmup 1 --runs 3
    python scripts/benchmark_env.py --model whisper_transcribe --warmup 1 --runs 5
Output: appends one row to outputs/env_benchmark.csv
"""
from __future__ import annotations

import argparse
import csv
import platform
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from configs.settings import SETTINGS

try:
    import psutil
    _PROC = psutil.Process()

    def peak_rss_mb() -> float:
        return _PROC.memory_info().rss / (1024 ** 2)
except ImportError:  # harness still usable before pip install
    import resource

    def peak_rss_mb() -> float:
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def _load_noop():
    """Baseline loader proving the harness works: trivial deterministic work."""
    return sum(i * i for i in range(200_000))


def _load_minilm():
    """Cold load of the sentence encoder: a fresh object every run, so the
    timing is load time, not cache time. Uses the local copy under models/
    when present, otherwise the hub id."""
    from sentence_transformers import SentenceTransformer
    local_copy = SETTINGS.models_dir / SETTINGS.sentence_model_id.split("/")[-1]
    source = str(local_copy) if local_copy.exists() else SETTINGS.sentence_model_id
    return SentenceTransformer(source, device="cpu")


ENCODE_PROBES = ["where is gate b12", "i left my bag on the plane",
                 "is there a lounge in terminal 2"]


def _encode_minilm():
    """Inference latency of the shared encoder on three fixed queries
    (the warm-up run absorbs the one-off load)."""
    from src.text_encoder import encode
    return encode(ENCODE_PROBES)


def _local_or_hub(model_id: str) -> str:
    local_copy = SETTINGS.models_dir / model_id.split("/")[-1]
    return str(local_copy) if local_copy.exists() else model_id


def _load_clip():
    """Cold load of CLIP model and processor, a fresh object every run."""
    from transformers import CLIPModel, CLIPProcessor
    source = _local_or_hub(SETTINGS.clip_model_id)
    return CLIPModel.from_pretrained(source).eval(), CLIPProcessor.from_pretrained(source)


def _encode_clip():
    """Warm inference: one 224x224 synthetic image plus the category prompts
    through the shared encoder (the warm-up run absorbs the load)."""
    import numpy as np
    from PIL import Image
    from src.vision import embed_images, embed_texts, load_prompts
    image = Image.fromarray((np.random.default_rng(0).random((224, 224, 3)) * 255).astype("uint8"))
    prompts = load_prompts(SETTINGS.vision_prompts_path)
    embed_texts([p for ps in prompts["categories"].values() for p in ps])
    return embed_images([image])


def _load_whisper():
    """Cold load of the Whisper-base ASR pipeline, a fresh object every run."""
    from transformers import pipeline
    return pipeline("automatic-speech-recognition", model=_local_or_hub(SETTINGS.whisper_model_id), device="cpu")


def _transcribe_whisper():
    """Warm inference on a fixed probe: data/audio/probe.wav if present,
    otherwise three seconds of a quiet tone (timing only; the text is
    meaningless for a tone and is discarded)."""
    import numpy as np
    from src.speech import load_audio, transcribe
    probe = SETTINGS.kb_path.parents[1] / "audio" / "probe.wav"
    if probe.exists():
        samples, rate = load_audio(probe)
    else:
        rate = SETTINGS.audio_sample_rate
        samples = (0.05 * np.sin(np.arange(3 * rate) / 10)).astype(np.float32)
    return transcribe(samples, rate)


# easyocr -> easyocr.Reader(['en'], gpu=False), only if the OCR enhancement is enabled
LOADERS = {
    "noop": _load_noop,
    "minilm": _load_minilm,
    "minilm_encode": _encode_minilm,
    "clip": _load_clip,
    "clip_encode": _encode_clip,
    "whisper": _load_whisper,
    "whisper_transcribe": _transcribe_whisper,
    "easyocr": None,
}


# every loader below runs on the CPU on purpose (the Space has no GPU and the
# MacBook's MPS path is not part of the design); the row records both what
# torch could use and what the loader actually used
DEVICE_USED = "cpu"


def detect_device() -> str:
    try:
        import torch
        mps = getattr(torch.backends, "mps", None)
        return "mps" if (mps and torch.backends.mps.is_available()) else "cpu"
    except ImportError:
        return "no-torch"


def benchmark(name: str, warmup: int, runs: int) -> dict:
    loader = LOADERS.get(name)
    if loader is None:
        raise NotImplementedError(f"Loader '{name}' is not implemented yet.")
    rss_before = peak_rss_mb()
    warmup_timings = []
    for _ in range(max(0, warmup)):
        start = time.perf_counter()
        loader()
        warmup_timings.append(time.perf_counter() - start)
    timings = []
    for _ in range(max(1, runs)):
        start = time.perf_counter()
        loader()
        timings.append(time.perf_counter() - start)
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": name,
        "device_available": detect_device(),
        "device_used": DEVICE_USED,
        "python": platform.python_version(),
        "machine": platform.machine(),
        "warmup_runs": warmup,
        "first_warmup_seconds": round(warmup_timings[0], 4) if warmup_timings else None,  # cold path
        "measured_runs": runs,
        "median_seconds": round(statistics.median(timings), 4),
        "min_seconds": round(min(timings), 4),
        "max_seconds": round(max(timings), 4),
        "rss_before_mb": round(rss_before, 1),
        "rss_after_mb": round(peak_rss_mb(), 1),
    }


def append_row(row: dict, csv_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not csv_path.exists()
    with open(csv_path, "a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(row))
        if new_file:
            writer.writeheader()
        writer.writerow(row)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, choices=sorted(LOADERS))
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--runs", type=int, default=5)
    args = parser.parse_args()
    row = benchmark(args.model, args.warmup, args.runs)
    out = SETTINGS.outputs_dir / "env_benchmark.csv"
    append_row(row, out)
    for k, v in row.items():
        print(f"{k:16s} {v}")
    print(f"\nappended to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
