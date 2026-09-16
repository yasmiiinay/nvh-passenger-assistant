"""Multimodal fusion metrics (RQ3): condition x query-type grid, conflicts,
cascade vs weighted-fusion comparison. Aggregation only; conditions come from
the multimodal manifest, outcomes from the pipeline."""
from __future__ import annotations
from collections import defaultdict

CONDITIONS = ["image_only", "text_only", "voice_only",
              "image_text_consistent", "image_text_conflict", "voice_image"]
SAFE_DECISIONS = ("clarify", "abstain", "redirect", "conflict")


def judge_scenario(expected_decision: str, target_kb_id: str, target_category: str, expected_conflict: bool,
                   decision: str, record_id: str | None, candidate_categories: set[str], conflict: bool) -> str:
    """One label per scenario, wrong-confident kept apart from over-cautious.

    correct          decision as expected; the record (answer) or the category
                     (clarify) as expected; the conflict flag as expected
    wrong_confident  an answer was given that should not have been, or the
                     wrong record
    over_cautious    an answer was expected but a safe decision came back
    safe_mismatch    a safe decision was expected and a different safe decision
                     came back, or the right decision with the wrong category
    wrong_redirect   redirected when no redirect was expected
    """
    if decision == "answer":
        if expected_decision == "answer" and record_id == target_kb_id and conflict == expected_conflict:
            return "correct"
        return "wrong_confident"
    if decision == "redirect":
        return "correct" if expected_decision == "redirect" else "wrong_redirect"
    if expected_decision == "answer":
        return "over_cautious"
    if decision != expected_decision or conflict != expected_conflict:
        return "safe_mismatch"
    if decision == "clarify" and target_category and target_category not in candidate_categories:
        return "safe_mismatch"
    return "correct"


def accuracy_by_condition(conditions: list[str], query_types: list[str],
                          gold_ids: list[str], predicted_ids: list[str]) -> dict:
    grid = defaultdict(lambda: {"n": 0, "correct": 0})
    for c, qt, g, p in zip(conditions, query_types, gold_ids, predicted_ids):
        if c not in CONDITIONS:
            raise ValueError(f"unknown condition '{c}'")
        cell = grid[(c, qt)]
        cell["n"] += 1
        cell["correct"] += int(bool(g) and g == p)
    return {f"{c}|{qt}": {"n": v["n"], "accuracy": v["correct"] / v["n"]}
            for (c, qt), v in grid.items()}


def conflict_detection(conflict_present: list[bool], conflict_flagged: list[bool]) -> dict:
    tp = sum(1 for p, f in zip(conflict_present, conflict_flagged) if p and f)
    fp = sum(1 for p, f in zip(conflict_present, conflict_flagged) if not p and f)
    fn = sum(1 for p, f in zip(conflict_present, conflict_flagged) if p and not f)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    return {"precision": precision, "recall": recall, "tp": tp, "fp": fp, "fn": fn,
            "n": len(conflict_present)}


def rates(verdicts: list[str]) -> dict:
    n = len(verdicts)
    counts = {v: verdicts.count(v) for v in sorted(set(verdicts))}
    return {"n": n, "counts": counts,
            "correct_rate": counts.get("correct", 0) / n if n else 0.0,
            "wrong_confident_rate": counts.get("wrong_confident", 0) / n if n else 0.0,
            "over_cautious_rate": counts.get("over_cautious", 0) / n if n else 0.0}

