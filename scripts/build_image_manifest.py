"""Append image rows to data/images/images_manifest.csv from a labelled folder.

The labels come from a small CSV you write by hand (one row per file):
    filename,category,split,quality_stratum,optional_identifier,notes
`category` is a visual vocabulary category or `out_of_scope`. Licence fields
are fixed per source so they cannot be typed inconsistently; the wording
follows Evidence Pack 02B2 section A1.

Usage:
    python scripts/build_image_manifest.py --source commons --folder data/images/raw/aiga --labels data/images/labels_aiga.csv
    python scripts/build_image_manifest.py --source own_photo --folder data/images/raw/own --labels data/images/labels_own.csv

Out-of-scope rows carry a note starting with `generic:` (a symbol with no
airport meaning), `airport_adjacent:` (an airport symbol outside the
vocabulary) or `photo:` (an ordinary photograph, the wrong-upload case),
which the vision evaluation reports separately.
Files are copied unmodified to data/images/files/<image_id>.<ext>.
"""
from __future__ import annotations

import argparse
import csv
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from configs.settings import REPO_ROOT
from src.foundation_audit import load_vocabulary

SOURCES = {
    "aiga_dot": {
        "licence": "copyright-free (AIGA/DOT symbol signs)",
        "licence_url": "https://www.aiga.org/resources/symbol-signs",
        "attribution": "AIGA and the US Department of Transportation symbol signs, made available free of charge and described by AIGA as copyright-free",
        "source_type": "clean_icon",
        "default_stratum": "clean",
        "modified": "no",
    },
    "commons": {
        "licence": "public domain / CC0 (AIGA/DOT symbol signs, per-file licence in data/images/provenance_commons.csv)",
        "licence_url": "https://commons.wikimedia.org/wiki/Category:AIGA_symbol_signs",
        "attribution": "AIGA and the US Department of Transportation symbol signs, files from Wikimedia Commons rendered server-side as 512 px PNG",
        "source_type": "clean_icon",
        "default_stratum": "clean",
        "modified": "yes",
    },
    "own_photo": {
        "licence": "own work",
        "licence_url": "",
        "attribution": "photograph by the project author",
        "source_type": "photo_signage",
        "default_stratum": "real_good_light",
        "modified": "yes",   # single symbols are cropped out of the photographs
    },
}
IMAGES_DIR = REPO_ROOT / "data" / "images"
MANIFEST = IMAGES_DIR / "images_manifest.csv"


def next_image_number(rows: list[dict]) -> int:
    numbers = [int(r["image_id"].split("_")[1]) for r in rows if r["image_id"].startswith("img_")]
    return max(numbers, default=0) + 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, choices=sorted(SOURCES))
    parser.add_argument("--folder", required=True)
    parser.add_argument("--labels", required=True)
    args = parser.parse_args()
    preset = SOURCES[args.source]
    vocabulary = load_vocabulary(REPO_ROOT / "data" / "vocabulary.json")
    visual = {c for c, v in vocabulary["categories"].items() if v["visual_class"]} | {"out_of_scope"}

    with open(MANIFEST, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames
        existing = list(reader)
    known_files = {r["file"] for r in existing}
    number = next_image_number(existing)
    (IMAGES_DIR / "files").mkdir(exist_ok=True)

    added = []
    with open(args.labels, encoding="utf-8", newline="") as fh:
        for label in csv.DictReader(fh):
            if label["category"] not in visual:
                raise SystemExit(f"{label['filename']}: category '{label['category']}' is not a visual category")
            src = Path(args.folder) / label["filename"]
            if not src.is_file():
                raise SystemExit(f"missing file: {src}")
            image_id = f"img_{number:03d}"
            dest = IMAGES_DIR / "files" / f"{image_id}{src.suffix.lower()}"
            rel = f"files/{dest.name}"
            if rel in known_files:
                continue
            shutil.copyfile(src, dest)
            added.append({
                "image_id": image_id, "category": label["category"], "source": args.source,
                "licence": preset["licence"], "licence_url": preset["licence_url"],
                "attribution": preset["attribution"], "modified": preset["modified"],
                "source_type": preset["source_type"],
                "quality_stratum": label.get("quality_stratum") or preset["default_stratum"],
                "split": label.get("split") or "dev", "expected_label": label["category"],
                "optional_identifier": label.get("optional_identifier", ""),
                "notes": label.get("notes", ""), "file": rel,
            })
            number += 1

    with open(MANIFEST, "a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writerows(added)
    print(f"added {len(added)} rows to {MANIFEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
