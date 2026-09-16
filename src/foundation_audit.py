"""Consistency audit across KB, controlled vocabulary and the seed query set.

Every check returns a list of problem strings; an empty list means pass.
Used by scripts/audit_foundation.py (human report) and tests/ (CI-style gate).
No models, no network.
"""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

from src.kb import load_kb, records_by_id

REQUIRED_FIELDS = [
    "record_id", "name", "category", "aliases", "terminal", "level", "zone",
    "identifiers", "identifier_ranges", "description", "directions",
    "opening_hours", "availability_note", "accessibility", "related_records",
    "assistance_contact", "source", "verification_status", "last_verified",
    "volatility", "retrieval_text",
]
ACCESSIBILITY_FIELDS = ["step_free", "accessible_toilet_nearby", "induction_loop",
                        "assistance_point_record", "notes"]
RETRIEVAL_TEXT_MAX_WORDS = 40  # comfortably below MiniLM's 256 word-piece truncation


def load_vocabulary(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_queries(path: str | Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


# ---------------- KB checks ----------------

def check_required_fields(kb: dict) -> list[str]:
    problems = []
    for r in kb["records"]:
        for f in REQUIRED_FIELDS:
            if f not in r:
                problems.append(f"{r.get('record_id','?')}: missing field '{f}'")
        acc = r.get("accessibility", {})
        for f in ACCESSIBILITY_FIELDS:
            if f not in acc:
                problems.append(f"{r.get('record_id','?')}: accessibility missing '{f}'")
    return problems


def check_unique_ids(kb: dict) -> list[str]:
    counts = Counter(r["record_id"] for r in kb["records"])
    return [f"duplicate record_id: {rid} (x{n})" for rid, n in counts.items() if n > 1]


def check_related_refs(kb: dict) -> list[str]:
    ids = set(records_by_id(kb))
    problems = []
    for r in kb["records"]:
        for ref in r["related_records"]:
            if ref not in ids:
                problems.append(f"{r['record_id']}: related_records -> unknown id '{ref}'")
        ap = r["accessibility"].get("assistance_point_record")
        if ap not in ids:
            problems.append(f"{r['record_id']}: assistance_point_record -> unknown id '{ap}'")
    return problems


def check_categories(kb: dict, vocab: dict) -> list[str]:
    valid = set(vocab["categories"])
    return [f"{r['record_id']}: category '{r['category']}' not in controlled vocabulary"
            for r in kb["records"] if r["category"] not in valid]


def check_terminal_scope(kb: dict, vocab: dict) -> list[str]:
    """serves_terminals, when given, names known terminals and includes the
    record's own; the loader fills the default for records without it."""
    known = set(vocab["entities"]["terminal"]["values"])
    problems = []
    for r in kb["records"]:
        scope = r.get("serves_terminals")
        if scope is None:
            continue
        if not isinstance(scope, list) or not set(scope) <= known:
            problems.append(f"{r['record_id']}: serves_terminals {scope!r} not a list of known terminals")
        elif r["terminal"] not in scope:
            problems.append(f"{r['record_id']}: serves_terminals does not include its own terminal")
    return problems


def check_volatility(kb: dict, vocab: dict) -> list[str]:
    valid = set(vocab["volatility_values"])
    return [f"{r['record_id']}: volatility '{r['volatility']}' invalid"
            for r in kb["records"] if r["volatility"] not in valid]


def check_identifier_collisions(kb: dict) -> list[str]:
    owner: dict[str, str] = {}
    problems = []
    for r in kb["records"]:
        for tok in r["_expanded_identifiers"]:
            if tok in owner:
                problems.append(f"identifier '{tok}' owned by both {owner[tok]} and {r['record_id']}")
            owner[tok] = r["record_id"]
    return problems


def check_alias_conflicts(kb: dict) -> list[str]:
    owner: dict[str, str] = {}
    problems = []
    for r in kb["records"]:
        for alias in [a.lower().strip() for a in r["aliases"]]:
            if alias in owner and owner[alias] != r["record_id"]:
                problems.append(f"alias '{alias}' claimed by both {owner[alias]} and {r['record_id']}")
            owner[alias] = r["record_id"]
    return problems


def check_synthetic_provenance(kb: dict) -> list[str]:
    return [f"{r['record_id']}: source/verification_status must both be 'synthetic'"
            for r in kb["records"]
            if r["source"] != "synthetic" or r["verification_status"] != "synthetic"]


def check_retrieval_text(kb: dict) -> list[str]:
    problems = []
    for r in kb["records"]:
        n = len(r["retrieval_text"].split())
        if n == 0:
            problems.append(f"{r['record_id']}: empty retrieval_text")
        elif n > RETRIEVAL_TEXT_MAX_WORDS:
            problems.append(f"{r['record_id']}: retrieval_text {n} words > {RETRIEVAL_TEXT_MAX_WORDS}")
        if r["retrieval_text"] == r["description"]:
            problems.append(f"{r['record_id']}: retrieval_text identical to description")
    return problems


# ---------------- query-set checks ----------------

def check_queries(queries: list[dict], kb: dict, vocab: dict) -> list[str]:
    problems = []
    ids = set(records_by_id(kb))
    intents = set(vocab["intents"]) | {"none"}
    qtypes = set(vocab["query_types"])
    outcomes = set(vocab["decision_outcomes"])
    seen = Counter(q["query_id"] for q in queries)
    problems += [f"duplicate query_id {qid}" for qid, n in seen.items() if n > 1]
    for q in queries:
        qid = q["query_id"]
        if q["intent"] not in intents:
            problems.append(f"{qid}: intent '{q['intent']}' not in vocabulary")
        if q["query_type"] not in qtypes:
            problems.append(f"{qid}: query_type '{q['query_type']}' invalid")
        if q["expected_behaviour"] not in outcomes:
            problems.append(f"{qid}: expected_behaviour '{q['expected_behaviour']}' invalid")
        if q["target_kb_id"] and q["target_kb_id"] not in ids:
            problems.append(f"{qid}: target_kb_id '{q['target_kb_id']}' not in KB")
        if not q["target_kb_id"] and q["expected_behaviour"] == "answer":
            problems.append(f"{qid}: expected 'answer' but no target_kb_id")
        try:
            json.loads(q["entities_json"] or "{}")
        except json.JSONDecodeError:
            problems.append(f"{qid}: entities_json is not valid JSON")
    return problems


def check_intent_kb_coverage(queries: list[dict], vocab: dict) -> list[str]:
    """Every non-deictic intent should have at least one seed query."""
    covered = {q["intent"] for q in queries}
    return [f"intent '{i}' has no seed query" for i in vocab["intents"] if i not in covered]


def run_all(kb_path, vocab_path, queries_path) -> dict[str, list[str]]:
    kb = load_kb(kb_path)
    vocab = load_vocabulary(vocab_path)
    queries = load_queries(queries_path)
    return {
        "required_fields": check_required_fields(kb),
        "unique_ids": check_unique_ids(kb),
        "related_refs": check_related_refs(kb),
        "categories": check_categories(kb, vocab),
        "volatility": check_volatility(kb, vocab),
        "terminal_scope": check_terminal_scope(kb, vocab),
        "identifier_collisions": check_identifier_collisions(kb),
        "alias_conflicts": check_alias_conflicts(kb),
        "synthetic_provenance": check_synthetic_provenance(kb),
        "retrieval_text": check_retrieval_text(kb),
        "queries": check_queries(queries, kb, vocab),
        "intent_coverage": check_intent_kb_coverage(queries, vocab),
    }
