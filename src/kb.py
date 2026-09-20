"""Knowledge-base loading and identifier expansion.

Foundation-stage code: pure data handling, no models. The identifier_ranges
extension ({prefix, from, to, spaced}) is expanded here at load time so the
rest of the system only ever sees flat identifier lists.
"""
from __future__ import annotations

import json
from pathlib import Path


def expand_identifier_ranges(record: dict) -> list[str]:
    """Return the record's full exact-match token list.

    'identifiers' are taken verbatim; each identifier_range expands to
    PREFIX+N (spaced=False, e.g. gates 'A1'..'A12') or 'PREFIX N' with the
    prefix's own trailing space (spaced=True, e.g. 'BELT 1'..'BELT 6').
    """
    tokens = list(record.get("identifiers", []))
    for rng in record.get("identifier_ranges", []):
        prefix = rng["prefix"]
        for n in range(int(rng["from"]), int(rng["to"]) + 1):
            tokens.append(f"{prefix}{n}")
    return tokens


def load_kb(path: str | Path) -> dict:
    """Load the KB and attach the expanded token list to every record."""
    with open(path, encoding="utf-8") as fh:
        kb = json.load(fh)
    for record in kb["records"]:
        record["_expanded_identifiers"] = expand_identifier_ranges(record)
        # `terminal` says where a record is; `serves_terminals` says whose
        # passengers it is for. Airport-level services (ground transport,
        # flight boards, first aid) list both terminals; everything else
        # serves only the terminal it sits in.
        record.setdefault("serves_terminals", [record["terminal"]])
    return kb


def records_by_id(kb: dict) -> dict[str, dict]:
    return {r["record_id"]: r for r in kb["records"]}


LANDSIDE_MARKERS = ("arrivals", "check-in hall", "forecourt", "entrance", "car park", "rail station",
                    "opposite terminal", "below terminal", "p1")


def zone_tags(record: dict) -> set[str]:
    """Journey-stage tags read from the record's own level and zone fields:
    "airside" (airside levels and the piers), "landside", "arrivals",
    "departures". A record can carry several (the Terminal 1 departures
    restrooms span the check-in hall and the airside plaza). No facts are
    added: a tag is present only when the field text says so (04.6)."""
    text = f"{record.get('level', '')} {record.get('zone', '')}".lower()
    tags = set()
    if "airside" in text or "pier" in text:
        tags.add("airside")
    if any(marker in text for marker in LANDSIDE_MARKERS):
        tags.add("landside")
    if "arrival" in text:
        tags.add("arrivals")
    if "departure" in text:
        tags.add("departures")
        if "airside" not in tags:
            tags.add("landside")     # a departures area that is not airside is the check-in side
    return tags
