"""Semantic stages of the cascade.

The first group needs no model and always runs. The second group loads
MiniLM (local copy under models/ or the hub) and is skipped when neither is
available, so the suite still passes on a machine without the weights.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from configs.settings import SETTINGS
from evaluation.retrieval_metrics import judge_outcome
from src.entities import load_gazetteers
from src.foundation_audit import load_queries
from src import retrieval
from src.retrieval import (STAGE_CATEGORY, STAGE_FULL_KB, candidate_records, decide, offered_candidates,
                           resolve, resolve_deterministic)


@pytest.fixture(scope="module")
def gaz():
    return load_gazetteers(SETTINGS.kb_path, SETTINGS.vocabulary_path)


# ---- no model needed ----

def test_decide_rules():
    assert decide([("a", 0.7), ("b", 0.4)], 0.5, 0.25, 0.1)[0] == "answer"
    assert decide([("a", 0.7), ("b", 0.65)], 0.5, 0.25, 0.1)[0] == "clarify"   # margin too small
    assert decide([("a", 0.4), ("b", 0.1)], 0.5, 0.25, 0.1)[0] == "clarify"    # score too low to answer
    assert decide([("a", 0.2), ("b", 0.1)], 0.5, 0.25, 0.1)[0] == "abstain"
    decision, score, margin = decide([("only", 0.6)], 0.5, 0.25, 0.1)
    assert decision == "answer" and margin == score                         # single candidate


def test_candidate_filter_modes(gaz):
    allowed, stage = candidate_records("find_lounge", {}, gaz, "intent")
    assert allowed == ["lounge_aurora"] and stage == STAGE_CATEGORY
    allowed, _ = candidate_records("find_restroom", {"terminal": ["Terminal 2"]}, gaz, "intent")
    assert allowed == ["restrooms_t2"]
    allowed, stage = candidate_records("none", {}, gaz, "intent")
    assert len(allowed) == 32 and stage == STAGE_FULL_KB
    allowed, _ = candidate_records("find_security", {"category_hints": ["baggage"]}, gaz, "cues")
    assert {gaz.records[r]["category"] for r in allowed} == {"baggage"}
    allowed, _ = candidate_records("find_security", {}, gaz, "cues")   # no hints: falls back to intent
    assert {gaz.records[r]["category"] for r in allowed} == {"security"}


def test_deterministic_matches_never_reach_the_encoder(gaz, monkeypatch):
    def boom(texts):
        raise AssertionError("encoder called for a deterministic query")
    monkeypatch.setattr(retrieval, "encode", boom)
    r = resolve("Where is gate B12?", gaz, index=None, thresholds=SETTINGS.thresholds())
    assert r.matched_record_id == "gates_pier_b" and r.stage == "exact_identifier"
    r = resolve("Is my flight NH123 delayed?", gaz, index=None, thresholds=SETTINGS.thresholds())
    assert r.decision == "redirect"


def test_thresholds_must_be_set():
    from configs.settings import Settings
    with pytest.raises(ValueError):
        Settings(tau_high=None).thresholds()


# ---- model needed ----

@pytest.fixture(scope="module")
def index(gaz):
    pytest.importorskip("sentence_transformers")
    try:
        return retrieval.build_text_index(gaz, SETTINGS.intent_exemplars_path)
    except Exception as exc:  # no local copy and no network
        pytest.skip(f"MiniLM not available here: {type(exc).__name__}")


def test_volatile_intent_redirects(gaz, index):
    r = resolve("when does boarding start", gaz, index, SETTINGS.thresholds())
    assert r.decision == "redirect" and r.intent == "ask_flight_status"
    assert r.matched_record_id == "flight_information" and r.stage == "no_retrieval"


def test_out_of_scope_abstains(gaz, index):
    r = resolve("What is the wifi password?", gaz, index, SETTINGS.thresholds())
    assert r.decision == "abstain" and r.matched_record_id is None
    assert r.match_score < SETTINGS.tau_low


def test_vague_query_clarifies_with_candidates(gaz, index):
    r = resolve("Where is security?", gaz, index, SETTINGS.thresholds())
    assert r.decision == "clarify" and r.stage == STAGE_CATEGORY
    # three checkpoints score within 0.002 of each other; only the leader and the
    # runner-up are offered, the third stays in the ranking for the evidence panel
    assert len(r.candidates) == 2 and set(r.candidates) <= {"security_t1_north", "security_t1_south", "security_t2"}
    assert len(r.ranked) == 3


def test_offered_candidates_follow_the_margin_rule():
    assert offered_candidates([("a", 0.49), ("b", 0.46), ("c", 0.41)], 0.1) == ["a", "b"]   # runner-up within margin
    assert offered_candidates([("a", 0.56), ("b", 0.32), ("c", 0.30)], 0.1) == ["a"]        # clear leader, low score
    assert offered_candidates([("a", 0.37)], 0.1) == ["a"]


def test_assistance_policy_answers(gaz, index):
    r = resolve("I need wheelchair assistance", gaz, index, SETTINGS.thresholds())
    assert r.decision == "answer" and "assist_policy" in r.flags
    assert gaz.records[r.matched_record_id]["category"] == "accessibility"


def test_live_information_record_is_never_an_answer(gaz, index):
    """Found on the held-out set: a query about flight connections ranked the
    flight_information record first. That record only carries the redirect."""
    r = resolve("Where can I ask about flight connections?", gaz, index, SETTINGS.thresholds())
    assert r.decision != "answer" or r.matched_record_id != "flight_information"
    if r.matched_record_id == "flight_information":
        assert r.decision == "redirect" and "volatile" in r.flags


# q004 "Where do I board my flight?" is answered with gates_pier_b since the
# declared exemplar revision: the intent became right (find_gate), the three
# gate records are near-identical and pier B wins by a margin above 0.10.
# Recorded here so that any further wrong-record answer fails the test and
# so that fixing q004 is noticed too.
KNOWN_WRONG_RECORD_ANSWERS = {"q004"}


def test_semantic_workload_wrong_record_answers_are_exactly_the_known_ones(gaz, index):
    thresholds = SETTINGS.thresholds()
    wrong = set()
    for q in load_queries(SETTINGS.queries_seed_path):
        if resolve_deterministic(q["query"], gaz).resolved:
            continue
        r = resolve(q["query"], gaz, index, thresholds)
        if r.decision == "answer" and r.matched_record_id != q["target_kb_id"]:
            wrong.add(q["query_id"])
    assert wrong == KNOWN_WRONG_RECORD_ANSWERS


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
