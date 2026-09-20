"""Download the files of a Wikimedia Commons category as PNG images.

Used for the AIGA/DOT symbol signs (public domain), which are the pictogram
stratum of the image dataset. Every file is fetched as a PNG rendering at
the requested width, so SVG originals need no local converter. A
provenance CSV (Commons title, page URL, licence text from the file's
extended metadata) is written next to the images for the data section of
the report.

Usage:
    python scripts/fetch_wikimedia_category.py --category "AIGA symbol signs" --out data/images/raw/aiga
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "nvh-passenger-assistant dataset builder (MSc project; contact via GitHub yasmiiinay)"


def api_get(params: dict) -> dict:
    query = urllib.parse.urlencode({**params, "format": "json"})
    request = urllib.request.Request(f"{API}?{query}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def category_files(category: str, width: int) -> list[dict]:
    """Title, page URL, PNG rendering URL and licence for every file in the category."""
    files, params = [], {
        "action": "query", "generator": "categorymembers", "gcmtitle": f"Category:{category}",
        "gcmtype": "file", "gcmlimit": "50", "prop": "imageinfo",
        "iiprop": "url|mime|extmetadata", "iiurlwidth": str(width),
    }
    while True:
        data = api_get(params)
        for page in data.get("query", {}).get("pages", {}).values():
            info = page["imageinfo"][0]
            meta = info.get("extmetadata", {})
            files.append({
                "title": page["title"], "page_url": info["descriptionurl"],
                "download_url": info.get("thumburl") or info["url"], "mime": info["mime"],
                "licence": meta.get("LicenseShortName", {}).get("value", ""),
                "credit": re.sub(r"<[^>]+>", "", meta.get("Credit", {}).get("value", "")),
            })
        if "continue" not in data:
            return files
        params.update(data["continue"])


def safe_name(title: str) -> str:
    stem = Path(title.removeprefix("File:")).stem
    return re.sub(r"[^a-z0-9]+", "_", stem.lower()).strip("_") + ".png"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", required=True, help='Commons category name without the "Category:" prefix')
    parser.add_argument("--out", required=True)
    parser.add_argument("--width", type=int, default=512)
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    files = category_files(args.category, args.width)
    print(f"{len(files)} files in Category:{args.category}")
    rows = []
    for f in files:
        name = safe_name(f["title"])
        target = out / name
        if not target.exists():
            request = urllib.request.Request(f["download_url"], headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=60) as response:
                target.write_bytes(response.read())
            time.sleep(0.5)          # polite to the Commons servers
        rows.append({"file": name, **f})
        print(f"{name:45s} {f['licence']}")
    with open(out / "provenance.csv", "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["file", "title", "page_url", "download_url", "mime", "licence", "credit"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"written to {out} (provenance.csv alongside)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
