"""Append human recordings to data/audio/audio_manifest.csv.

Put the recordings in a folder named `<query_id>__<speaker>.<ext>`, for
example `q001__spk_01.m4a` or `h004__spk_02.wav` (the query id is matched
case-insensitively). A sentence the speaker chose that is not in the seed
or held-out set goes into data/text/queries_spoken.csv first, with an
`s###` id, so that the reference transcript and expected outcome are
declared before the clip is scored. The reference transcript
is the query text from the seed or held-out file, so speak it as written.
Non-WAV files are converted with afconvert (macOS) to 16 kHz mono WAV;
on other systems provide WAV files directly.

Usage:
    python scripts/add_recordings.py --folder data/audio/raw/own --environment quiet --noise clean
"""
from __future__ import annotations

import argparse
import csv
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from configs.settings import REPO_ROOT, SETTINGS
from src.entities import extract, load_gazetteers
from src.foundation_audit import load_queries

AUDIO_DIR = REPO_ROOT / "data" / "audio"
MANIFEST = AUDIO_DIR / "audio_manifest.csv"


def to_wav(src: Path, dest: Path) -> None:
    if src.suffix.lower() == ".wav":
        shutil.copyfile(src, dest)
        return
    if not shutil.which("afconvert"):
        raise SystemExit(f"{src.name}: only WAV input is supported on this system (afconvert not found)")
    subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", str(src), str(dest)], check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", required=True)
    parser.add_argument("--environment", default="quiet", choices=["quiet", "cafe_noise", "announcement_noise"])
    parser.add_argument("--noise", default="clean", choices=["clean", "moderate", "heavy"])
    args = parser.parse_args()
    gaz = load_gazetteers(SETTINGS.kb_path, SETTINGS.vocabulary_path)
    queries = {q["query_id"]: q for path in (SETTINGS.queries_seed_path, SETTINGS.queries_heldout_path, SETTINGS.queries_spoken_path)
               for q in load_queries(path)}
    with open(MANIFEST, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames
        existing = list(reader)
    known = {(r["query_id"], r["speaker_id"], r["environment"]) for r in existing}
    number = max([int(r["audio_id"].split("_")[1]) for r in existing], default=0) + 1
    (AUDIO_DIR / "files").mkdir(exist_ok=True)

    added = []
    for src in sorted(Path(args.folder).iterdir()):
        if src.suffix.lower() not in (".wav", ".m4a", ".aiff", ".aif", ".mp3", ".caf") or "__" not in src.stem:
            continue
        query_id, speaker = src.stem.split("__", 1)
        query_id = query_id.lower()          # recorder apps tend to capitalise the first letter
        if query_id not in queries:
            raise SystemExit(f"{src.name}: unknown query id {query_id}")
        if (query_id, speaker, args.environment) in known:
            continue
        audio_id = f"aud_{number:03d}"
        dest = AUDIO_DIR / "files" / f"{audio_id}.wav"
        to_wav(src, dest)
        text = queries[query_id]["query"]
        identifiers = [e.value for e in extract(text, gaz).entities if e.type in ("gate_id", "desk_id", "belt_id")]
        added.append({
            "audio_id": audio_id, "query_id": query_id, "speaker_id": speaker, "reference_transcript": text,
            "environment": args.environment, "noise_condition": args.noise,
            "expected_identifiers": ";".join(identifiers), "target_kb_id": queries[query_id]["target_kb_id"],
            "split": queries[query_id]["split"], "file": f"files/{dest.name}",
        })
        number += 1
        print(f"{audio_id} {speaker}: {text}")

    with open(MANIFEST, "a", encoding="utf-8", newline="") as fh:
        csv.DictWriter(fh, fieldnames=fieldnames).writerows(added)
    print(f"added {len(added)} recordings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
