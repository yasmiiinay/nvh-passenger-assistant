"""Environment smoke test. Run AFTER `pip install -r requirements.txt`.

Verifies imports and reports versions/devices. Downloads nothing, loads no
model weights. Exit code: 0 = all required imports OK, 1 = something missing.
EasyOCR is checked only when configs.settings.SETTINGS.enable_ocr is True.
"""
import importlib
import importlib.metadata
import platform
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from configs.settings import SETTINGS

REQUIRED = ["torch", "torchvision", "transformers", "sentence_transformers",
            "numpy", "pandas", "cv2", "gradio", "jiwer", "psutil", "soundfile"]


def try_import(name: str):
    try:
        module = importlib.import_module(name)
        version = getattr(module, "__version__", None)
        if version is None:  # e.g. jiwer exposes no __version__ attribute
            try:
                version = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                version = "?"
        return True, version
    except Exception as exc:  # noqa: BLE001 - report anything, crash on nothing
        return False, f"{type(exc).__name__}: {exc}"


def main() -> int:
    print(f"python              {platform.python_version()}  ({platform.machine()}, {platform.system()})")
    failures = 0
    for name in REQUIRED:
        ok, info = try_import(name)
        print(f"{name:20s} {'OK  ' if ok else 'MISS'} {info}")
        failures += 0 if ok else 1

    ok, info = try_import("torch")
    if ok:
        import torch
        mps = getattr(torch.backends, "mps", None)
        device = "mps" if (mps and torch.backends.mps.is_available()) else "cpu"
        print(f"{'device':20s} {device}")

    if SETTINGS.enable_ocr:
        ok, info = try_import("easyocr")
        print(f"{'easyocr':20s} {'OK  ' if ok else 'MISS'} {info}  (enable_ocr=True)")
        failures += 0 if ok else 1
    else:
        print(f"{'easyocr':20s} SKIP (enable_ocr=False)")

    print("\nSMOKE TEST:", "PASS" if failures == 0 else f"FAIL ({failures} missing)")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
