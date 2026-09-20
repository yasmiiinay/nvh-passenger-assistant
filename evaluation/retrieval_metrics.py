"""KB retrieval metrics, stratified by query type; stage-firing evidence table."""
from __future__ import annotations
from collections import Counter, defaultdict

STAGES = ["exact_identifier", "alias_lookup", "category_filter_semantic",
          "semantic_full_kb", "no_retrieval"]


def retrieval_accuracy_by_type(query_types: list[str], gold_ids: list[str],
                               predicted_ids: list[str]) -> dict:
    per_type = defaultdict(lambda: {"n": 0, "correct": 0})
    for qt, g, p in zip(query_types, gold_ids, predicted_ids):
        per_type[qt]["n"] += 1
        per_type[qt]["correct"] += int(bool(g) and g == p)
    return {qt: {"n": v["n"], "accuracy": v["correct"] / v["n"]} for qt, v in per_type.items()}


def outcome_accuracy_by_type(query_types: list[str], verdicts: list[str]) -> dict:
    """Share of queries per type whose decision AND record matched the
    expectation (verdict == "correct"). Unlike retrieval_accuracy_by_type
    this credits a correct clarify or abstain."""
    per_type = defaultdict(lambda: {"n": 0, "correct": 0})
    for qt, v in zip(query_types, verdicts):
        per_type[qt]["n"] += 1
        per_type[qt]["correct"] += int(v == "correct")
    return {qt: {"n": v["n"], "accuracy": v["correct"] / v["n"]} for qt, v in per_type.items()}


def stage_firing_counts(stages_fired: list[str]) -> dict:
    """How often each cascade stage produced the final candidate set (v1.1 4.4:
    the counter table showing the deterministic stages doing the work)."""
    unknown = [s for s in stages_fired if s not in STAGES]
    if unknown:
        raise ValueError(f"unknown stage names: {sorted(set(unknown))}")
    return dict(Counter(stages_fired))


def decision_rates(decisions: list[str]) -> dict:
    """answer/clarify/abstain/redirect shares over a query set."""
    counts = Counter(decisions)
    n = len(decisions)
    return {d: {"count": c, "rate": c / n} for d, c in counts.items()} | {"n": n}


def judge_outcome(expected_behaviour: str, target_id: str | None, decision: str | None,
                  matched_id: str | None, candidates: list[str], flags: list[str]) -> tuple[str, str]:
    """Compare one cascade outcome with the seed row's expectation.

    Returns (verdict, detail): "correct", "wrong" (decided but not as
    expected) or "unresolved" (no decision yet). A grounded negative counts
    as correct when the target record is among the alternatives it offers."""
    if decision is None:
        return "unresolved", ""
    if expected_behaviour in ("abstain", "clarify"):
        # no record is required; the seed target on such rows only documents
        # what the query was about (e.g. the non-English case)
        record_ok = matched_id is None or matched_id == target_id
    else:
        record_ok = (matched_id == target_id
                     or ("grounded_negative" in flags and target_id in candidates))
    decision_ok = decision == expected_behaviour
    if record_ok and decision_ok:
        return "correct", ""
    detail = []
    if not decision_ok:
        detail.append(f"decision {decision} != expected {expected_behaviour}")
    if not record_ok:
        detail.append(f"record {matched_id} != target {target_id}")
    return "wrong", "; ".join(detail)


def clarify_type(decision: str | None, clarification_field: str | None, candidates: list[str], flags: list[str]) -> str | None:
    """How a clarify was put to the passenger: a targeted question for a KB
    field (terminal), a single-record confirmation, a list of record names,
    a request for a photo (deictic), or an open question. None when the
    decision is not clarify. Counted in the runners; the judge ignores it."""
    if decision != "clarify":
        return None
    if clarification_field:
        return "targeted_" + clarification_field
    if "deictic" in flags:
        return "deictic"
    if len(candidates) == 1:
        return "confirm_one"
    if candidates:
        return "list"
    return "open"


def write_artifacts(*args, **kwargs):
    raise NotImplementedError("TODO(evaluation phase): persist to outputs/evaluation/retrieval/")
