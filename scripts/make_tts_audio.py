"""Produce the synthetic-speech stratum with the macOS built-in voices.

Reads data/audio/tts_utterances.csv (query_id, text), speaks each line with
every requested voice through `say`, converts to 16 kHz mono WAV with
`afconvert`, and appends one manifest row per clip with speaker_id
`tts_<voice>`. Reference transcripts are the utterance texts themselves, so
WER on this stratum measures the recogniser, not a human transcriber.

macOS only (both tools ship with the system). Run on the MacBook:
    python scripts/make_tts_audio.py --voices Daniel Samantha Karen Moira Rishi
`say -v ?` lists the installed voices; voices that are not installed are
skipped with a message.
"""
from __future__ import annotations

import argparse
import csv
import json
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
UTTERANCES = AUDIO_DIR / "tts_utterances.csv"


def installed_voices() -> set[str]:
    out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, check=True).stdout
    return {line.split()[0] for line in out.splitlines() if line.strip()}


def query_lookup() -> dict[str, dict]:
    rows = load_queries(SETTINGS.queries_seed_path) + load_queries(SETTINGS.queries_heldout_path)
    return {r["query_id"]: r for r in rows}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--voices", nargs="+", required=True)
    parser.add_argument("--rate", type=int, default=175, help="words per minute for say")
    args = parser.parse_args()
    if not (shutil.which("say") and shutil.which("afconvert")):
        raise SystemExit("say/afconvert not found: this script runs on macOS only")
    available = installed_voices()
    voices = [v for v in args.voices if v in available]
    for missing in set(args.voices) - set(voices):
        print(f"voice not installed, skipped: {missing}")

    gaz = load_gazetteers(SETTINGS.kb_path, SETTINGS.vocabulary_path)
    queries = query_lookup()
    with open(MANIFEST, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames
        existing = list(reader)
    known = {(r["query_id"], r["speaker_id"]) for r in existing}
    number = max([int(r["audio_id"].split("_")[1]) for r in existing], default=0) + 1
    files_dir = AUDIO_DIR / "files"
    files_dir.mkdir(exist_ok=True)

    added = []
    with open(UTTERANCES, encoding="utf-8", newline="") as fh:
        utterances = list(csv.DictReader(fh))
    for voice in voices:
        speaker = f"tts_{voice.lower()}"
        for utt in utterances:
            if (utt["query_id"], speaker) in known:
                continue
            audio_id = f"aud_{number:03d}"
            aiff = files_dir / f"{audio_id}.aiff"
            wav = files_dir / f"{audio_id}.wav"
            subprocess.run(["say", "-v", voice, "-r", str(args.rate), "-o", str(aiff), utt["text"]], check=True)
            subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", str(aiff), str(wav)], check=True)
            aiff.unlink()
            identifiers = [e.value for e in extract(utt["text"], gaz).entities
                           if e.type in ("gate_id", "desk_id", "belt_id")]
            query = queries.get(utt["query_id"], {})
            added.append({
                "audio_id": audio_id, "query_id": utt["query_id"], "speaker_id": speaker,
                "reference_transcript": utt["text"], "environment": "quiet", "noise_condition": "clean",
                "expected_identifiers": ";".join(identifiers), "target_kb_id": query.get("target_kb_id", ""),
                "split": query.get("split", "dev"), "file": f"files/{wav.name}",
            })
            number += 1
            print(f"{audio_id} {speaker}: {utt['text']}")

    with open(MANIFEST, "a", encoding="utf-8", newline="") as fh:
        csv.DictWriter(fh, fieldnames=fieldnames).writerows(added)
    print(f"added {len(added)} clips; voices used: {json.dumps(voices)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
