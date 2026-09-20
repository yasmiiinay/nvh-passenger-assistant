"""Interaction log and the minimal escalation record (Architecture Freeze
v1.1 4.10).

Both are JSONL files under outputs/logs/. The event log holds what an
evaluation or a debugging session needs and nothing a passenger would not
expect to be kept: no audio, no image, no transcript text by default. A
ticket is a real record with a reference number that the passenger can
quote at the contact route the KB names; it is not a live hand-over and
the interface says so.
"""
from __future__ import annotations

import json
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path

from configs.settings import SETTINGS

LOG_DIR = SETTINGS.outputs_dir / "logs"
EVENTS_PATH = LOG_DIR / "events.jsonl"
TICKETS_PATH = LOG_DIR / "tickets.jsonl"
ASSISTANCE_LINE = "Airport assistance line +00 000 0000 (synthetic)"


def _append(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def event_from_outcome(outcome, session_id: str, turn_index: int, latency_s: float) -> dict:
    """The log row for one turn. Scores and ids only; the words the passenger
    typed are not stored (a transcript never is)."""
    text = outcome.text
    vision = outcome.vision
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "session_id": session_id,
        "turn_index": turn_index,
        "modalities": list(outcome.modalities),
        "route": outcome.route,
        "decision": outcome.decision,
        "record_id": outcome.matched_record_id,
        "candidates": list(outcome.candidates),
        "band": outcome.band,
        "score": outcome.score,
        "intent": text.intent if text is not None else None,
        "stage": text.stage if text is not None else None,
        "image_category": outcome.image_category,
        "image_out_of_scope": bool(vision.out_of_scope) if vision is not None else None,
        "audio_ok": bool(outcome.speech.check.ok) if outcome.speech is not None else None,
        "conflict": outcome.conflict,
        "flags": list(outcome.flags),
        "error": outcome.error,
        "latency_s": round(latency_s, 3),
    }


def log_event(event: dict, path: Path | None = None) -> None:
    _append(path or EVENTS_PATH, event)


def contact_route(outcome, gaz) -> str:
    """The official contact the KB names for this situation: the matched
    record's assistance contact, else the information desk of the terminal
    the passenger mentioned, else the assistance line."""
    if outcome.matched_record_id and outcome.matched_record_id in gaz.records:
        contact = gaz.records[outcome.matched_record_id].get("assistance_contact")
        if contact:
            return contact
    terminal = outcome.text.entities.get("terminal") if outcome.text is not None else None
    if terminal:
        for record in gaz.records.values():
            if record["category"] == "information" and record.get("volatility") != "high" and record["terminal"] == terminal:
                return f"{record['name']} ({record['terminal']})"
    return ASSISTANCE_LINE


def open_ticket(outcome, gaz, session_id: str, note: str = "", path: Path | None = None) -> dict:
    """Write an escalation record and return it. The reference is what the
    passenger quotes; the note is the passenger's own words, kept only here."""
    ticket = {
        "reference": "NVH-" + secrets.token_hex(3).upper(),
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "session_id": session_id,
        "decision": outcome.decision,
        "record_id": outcome.matched_record_id,
        "candidates": list(outcome.candidates),
        "conflict": outcome.conflict,
        "contact_route": contact_route(outcome, gaz),
        "note": note.strip()[:500],
    }
    _append(path or TICKETS_PATH, ticket)
    return ticket


def new_session_id() -> str:
    return f"{int(time.time())}-{secrets.token_hex(2)}"
