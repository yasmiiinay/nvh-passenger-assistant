"""Pre-run check of an independently authored blind set.

Verifies that the frozen files are complete, well-formed and unchanged since
their hashes were recorded. It never runs the chatbot and prints no model
output, so it can be used before the single evaluation run without looking
at any result.

    python scripts/verify_blind_set.py --set v3
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# the shape every later set follows, so the unchanged runner can read it
COUNTS = {"text": 20, "images": 8, "audio": 6, "multimodal": 12}
COLUMNS = {
    "text": ["blind_id", "query", "expected_decision", "expected_category", "expected_record_id", "reason"],
    "images": ["image_id", "image_description", "expected_decision", "expected_category", "expected_record_id",
               "quality_stratum", "reason"],
    "audio": ["audio_id", "spoken_text", "expected_decision", "expected_category", "expected_record_id",
              "audio_condition", "recording_source", "reason"],
    "multimodal": ["scenario_id", "modality", "text", "image_id", "audio_id", "expected_decision",
                   "expected_category", "expected_record_id", "expected_route", "reason"],
}
DECISIONS = {"answer", "clarify", "abstain", "redirect"}
MULTIMODAL_DECISIONS = DECISIONS | {"conflict"}
STRATA = {"clean", "photographed", "angled", "blurred", "out_of_scope"}
AUDIO_CONDITIONS = {"clean", "fast_natural", "identifier", "mild_noise", "terminal_specific"}
SOURCES = {"TTS", "human"}
MODALITIES = {"image-only", "voice-only", "text+image", "voice+image"}
ROUTES = {"fuse_consistent", "flag_cross_modal_conflict", "image_resolves_deictic", "image_only", "voice_only"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path: Path) -> tuple[list[str], list[dict]]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        return list(reader.fieldnames or []), list(reader)


def check_hash_file(hash_file: Path, problems: list[str]) -> int:
    if not hash_file.exists():
        problems.append(f"missing hash file {hash_file.name}")
        return 0
    checked = 0
    for line in hash_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, name = line.split(maxsplit=1)
        target = REPO_ROOT / name.strip().lstrip("*")
        if not target.exists():
            problems.append(f"{hash_file.name}: {target.name} missing")
        elif sha256(target) != digest:
            problems.append(f"{hash_file.name}: {target.name} does not match its recorded hash")
        checked += 1
    return checked


def main() -> int:
    set_name = sys.argv[sys.argv.index("--set") + 1] if "--set" in sys.argv else "v3"
    n = set_name.lstrip("v")
    prefix = f"final_blind_{set_name}"
    files = {"text": f"{prefix}_text.csv", "images": f"{prefix}_images_manifest.csv",
             "audio": f"{prefix}_audio_manifest.csv", "multimodal": f"{prefix}_multimodal.csv"}
    kb = json.loads((REPO_ROOT / "data" / "kb" / "airport_kb.json").read_text(encoding="utf-8"))
    record_ids = {r["record_id"] for r in kb["records"]}
    categories = set(json.loads((REPO_ROOT / "data" / "vocabulary.json").read_text(encoding="utf-8"))["categories"])
    problems: list[str] = []
    rows: dict[str, list[dict]] = {}

    for kind, name in files.items():
        path = REPO_ROOT / name
        if not path.exists():
            problems.append(f"missing {name}")
            continue
        header, rows[kind] = read_csv(path)
        if header != COLUMNS[kind]:
            problems.append(f"{name}: columns {header} differ from {COLUMNS[kind]}")
        if len(rows[kind]) != COUNTS[kind]:
            problems.append(f"{name}: {len(rows[kind])} rows, expected {COUNTS[kind]}")
        allowed = MULTIMODAL_DECISIONS if kind == "multimodal" else DECISIONS
        for row in rows[kind]:
            case = next(iter(row.values()))
            if row.get("expected_decision") not in allowed:
                problems.append(f"{name} {case}: decision {row.get('expected_decision')!r} not allowed")
            if row.get("expected_category") and row["expected_category"] not in categories:
                problems.append(f"{name} {case}: unknown category {row['expected_category']!r}")
            if row.get("expected_record_id") and row["expected_record_id"] not in record_ids:
                problems.append(f"{name} {case}: unknown record {row['expected_record_id']!r}")
            if row.get("expected_decision") == "answer" and not row.get("expected_record_id") and kind == "text":
                problems.append(f"{name} {case}: an answer needs an expected record")
            if not row.get("reason", "").strip():
                problems.append(f"{name} {case}: empty reason")
        for row in rows[kind]:
            case = next(iter(row.values()))
            if kind == "images" and row["quality_stratum"] not in STRATA:
                problems.append(f"{name} {case}: stratum {row['quality_stratum']!r} not allowed")
            if kind == "audio":
                if row["audio_condition"] not in AUDIO_CONDITIONS:
                    problems.append(f"{name} {case}: condition {row['audio_condition']!r} not allowed")
                if row["recording_source"] not in SOURCES:
                    problems.append(f"{name} {case}: source {row['recording_source']!r} not allowed")
            if kind == "multimodal":
                if row["modality"] not in MODALITIES:
                    problems.append(f"{name} {case}: modality {row['modality']!r} not allowed")
                if row["expected_route"] not in ROUTES:
                    problems.append(f"{name} {case}: route {row['expected_route']!r} not allowed")

    expected_images = [f"IMG{n}_B{i:02d}.png" for i in range(1, COUNTS["images"] + 1)]
    expected_audio = [f"AUD{n}_B{i:02d}.wav" for i in range(1, COUNTS["audio"] + 1)]
    for asset in expected_images + expected_audio:
        if not (REPO_ROOT / asset).exists():
            problems.append(f"missing asset {asset}")
    if "images" in rows and [r["image_id"] for r in rows["images"]] != [a[:-4] for a in expected_images]:
        problems.append("image ids do not match the asset names IMG{n}_B01…B08")
    if "audio" in rows and [r["audio_id"] for r in rows["audio"]] != [a[:-4] for a in expected_audio]:
        problems.append("audio ids do not match the asset names AUD{n}_B01…B06")
    if "multimodal" in rows:
        known_images = {a[:-4] for a in expected_images}
        known_audio = {a[:-4] for a in expected_audio}
        for row in rows["multimodal"]:
            if row["image_id"] and row["image_id"] not in known_images:
                problems.append(f"multimodal {row['scenario_id']}: unknown image {row['image_id']}")
            if row["audio_id"] and row["audio_id"] not in known_audio:
                problems.append(f"multimodal {row['scenario_id']}: unknown audio {row['audio_id']}")

    if not (REPO_ROOT / f"SELF_CHECK_{set_name.upper()}.txt").exists():
        problems.append(f"missing SELF_CHECK_{set_name.upper()}.txt")
    checked = sum(check_hash_file(REPO_ROOT / f"blind_{set_name}_{part}_sha256.txt", problems)
                  for part in ("manifests", "images", "audio"))
    if (REPO_ROOT / "docs" / "report" / f"final_blind_evaluation_{set_name}").exists():
        problems.append(f"docs/report/final_blind_evaluation_{set_name} already exists: the set may have been run")

    counts = ", ".join(f"{k} {len(v)}" for k, v in rows.items())
    print(f"blind set {set_name}: {counts}; {checked} hashes checked")
    for p in problems:
        print("PROBLEM:", p)
    print("OK" if not problems else f"{len(problems)} problem(s): do not run the evaluation")
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
