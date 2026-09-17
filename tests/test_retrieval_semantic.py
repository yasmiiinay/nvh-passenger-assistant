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
from src.retrieval import (STAGE_CATEGORY, STAGE_FULL_KB, RetrievalResult, candidate_records, decide, has_flight_context,
                           offered_candidates, tied_by_terminal,
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
    assert "unsupported_service" in r.flags      # named service the KB does not hold (04.6)
    r = resolve("Where can I get my shoes repaired?", gaz, index, SETTINGS.thresholds())
    assert r.decision == "abstain" and r.matched_record_id is None
    assert r.match_score < SETTINGS.tau_low


def test_vague_query_clarifies_with_candidates(gaz, index):
    r = resolve("Where is security?", gaz, index, SETTINGS.thresholds())
    assert r.decision == "clarify" and r.stage == STAGE_CATEGORY
    # three checkpoints of one category within the margin across both terminals:
    # the question asks for the terminal, no record name is offered
    assert r.clarification_field == "terminal"
    assert set(r.candidates) == {"security_t1_north", "security_t1_south", "security_t2"}
    assert len(r.ranked) == 3


def test_terminal_in_the_text_narrows_before_asking(gaz, index):
    r = resolve("Is there a second security checkpoint in terminal 1?", gaz, index, SETTINGS.thresholds())
    assert r.decision == "clarify" and r.clarification_field is None
    assert set(r.candidates) == {"security_t1_north", "security_t1_south"}


def test_mixed_category_candidates_are_listed_not_asked_by_terminal(gaz, index):
    r = resolve("information desk in the departures hall or arrivals", gaz, index, SETTINGS.thresholds())
    assert r.decision == "clarify" and r.clarification_field is None
    assert len(r.candidates) == 2
    # "arrivals" alone is a journey-stage zone and narrows to the arrivals desk (04.6)
    r = resolve("information desk arrivals", gaz, index, SETTINGS.thresholds())
    assert r.candidates == ["info_desk_t1_arrivals"]


def test_tied_by_terminal_rule():
    class Gaz:
        records = {"a": {"category": "x", "terminal": "Terminal 1"}, "b": {"category": "x", "terminal": "Terminal 2"},
                   "c": {"category": "y", "terminal": "Terminal 2"}, "d": {"category": "x", "terminal": "Terminal 1"}}
    assert tied_by_terminal([("a", 0.50), ("b", 0.48), ("c", 0.30)], 0.1, Gaz) == ["a", "b"]
    assert tied_by_terminal([("a", 0.50), ("c", 0.48)], 0.1, Gaz) == []        # two categories
    assert tied_by_terminal([("a", 0.50), ("d", 0.48)], 0.1, Gaz) == []        # one terminal
    assert tied_by_terminal([("a", 0.50), ("b", 0.35)], 0.1, Gaz) == []        # runner-up outside the margin


def test_offered_candidates_follow_the_margin_rule():
    assert offered_candidates([("a", 0.49), ("b", 0.46), ("c", 0.41)], 0.1) == ["a", "b"]   # runner-up within margin
    assert offered_candidates([("a", 0.56), ("b", 0.32), ("c", 0.30)], 0.1) == ["a"]        # clear leader, low score
    assert offered_candidates([("a", 0.37)], 0.1) == ["a"]


def test_assistance_policy_answers(gaz, index):
    # with a terminal the nearest designated point is answered, not asked about
    r = resolve("I need wheelchair assistance in terminal 1", gaz, index, SETTINGS.thresholds())
    assert r.decision == "answer" and "assist_policy" in r.flags
    assert gaz.records[r.matched_record_id]["category"] == "accessibility"
    # without any location the terminal is the one thing asked (04.6)
    r = resolve("I need wheelchair assistance", gaz, index, SETTINGS.thresholds())
    assert r.decision == "clarify" and r.clarification_field == "terminal"
    assert {gaz.records[rid]["category"] for rid in r.candidates} == {"accessibility"}


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


def test_similarity_alone_does_not_answer_without_a_recognised_intent(gaz, index):
    # "baby changing facilities" resembles a restroom record above tau_high
    # but matches no intent well; the top record is offered, not asserted
    r = resolve("Baby changing facilities?", gaz, index, SETTINGS.thresholds())
    assert r.decision == "clarify" and "intent_weak" in r.flags and len(r.candidates) == 1
    # a single-record cue is confirmed by the semantic stage, not answered outright
    r = resolve("Is there a lounge?", gaz, index, SETTINGS.thresholds())
    assert r.decision == "answer" and r.matched_record_id == "lounge_aurora" and r.match_score >= SETTINGS.tau_high
    r = resolve("Check-in desks Terminal 2", gaz, index, SETTINGS.thresholds())
    assert r.decision == "answer" and r.matched_record_id == "checkin_t2"
    # a confident intent keeps its semantic answer once the terminal is known
    r = resolve("my mother needs a wheelchair, we are in terminal 1", gaz, index, SETTINGS.thresholds())
    assert r.decision == "answer" and r.matched_record_id == "prm_point_t1_entrance"


# ---- QA 04.5 change 1: a semantic flight-status redirect needs flight words ----

@pytest.mark.parametrize("query", ["What time is the last shuttle bus tonight?",
                                   "Does the first train leave before six in the morning?",
                                   "Until when do the buses keep running?"])
def test_timetable_wording_without_flight_words_is_not_redirected(gaz, index, query):
    r = resolve(query, gaz, index, SETTINGS.thresholds())
    assert r.decision != "redirect" and "volatile" not in r.flags
    assert r.matched_record_id != "flight_information"


@pytest.mark.parametrize("query", ["is my plane delayed tonight", "has boarding begun for the evening departures",
                                   "my flight got cancelled what now"])
def test_flight_status_wording_still_redirects(gaz, index, query):
    r = resolve(query, gaz, index, SETTINGS.thresholds())
    assert r.decision == "redirect" and "volatile" in r.flags


def test_flight_context_words():
    r = RetrievalResult(query="", normalized="when do the buses run", entities={}, resolved=False)
    assert not has_flight_context(r)
    r.normalized = "is the plane late"
    assert has_flight_context(r)
    r = RetrievalResult(query="", normalized="", entities={"flight_ref": "NH 123"}, resolved=False)
    assert has_flight_context(r)


# ---- QA 04.5 change 3: a small coherent cue set is kept as the candidate set ----

def test_small_cue_set_is_scored_on_its_own_when_the_intent_agrees(gaz, index):
    r = resolve("Which way to the security checkpoints in Terminal 1?", gaz, index, SETTINGS.thresholds())
    assert r.decision == "clarify" and set(r.candidates) == {"security_t1_north", "security_t1_south"}
    assert r.clarification_field is None      # both in one terminal: the two names are listed


def test_small_cue_set_across_terminals_still_asks_for_the_terminal(gaz, index):
    r = resolve("how do I get to security", gaz, index, SETTINGS.thresholds())
    assert r.decision == "clarify" and r.clarification_field == "terminal"


def test_cue_set_and_disagreeing_intent_are_searched_together(gaz):
    handoff = {"cue_records": ["info_desk_t2"], "category_hints": ["information"], "terminal": ["Terminal 2"]}
    allowed, stage = candidate_records("find_check_in", handoff, gaz, "intent")
    assert "info_desk_t2" in allowed and "checkin_t2" in allowed and stage == STAGE_CATEGORY
    allowed, _ = candidate_records("find_information", handoff, gaz, "intent")
    assert allowed == ["info_desk_t2"]


def test_large_cue_sets_stay_category_hints(gaz):
    r = resolve_deterministic("how do I get to the transport options", gaz)
    assert r.handoff.get("cue_records") == []   # five transport records: a hint, not a candidate set
