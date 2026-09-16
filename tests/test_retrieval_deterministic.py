"""Unit tests for the deterministic stages of src/retrieval.py.

Two properties matter more than any single case:
  1. a deterministic decision is never wrong on the seed set (false resolution
     is the failure class this stage exists to avoid);
  2. unresolved queries hand on their evidence rather than silently dropping it.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from configs.settings import SETTINGS
from evaluation.retrieval_metrics import STAGES, stage_firing_counts
from src.entities import load_gazetteers
from src.foundation_audit import load_queries
from src.retrieval import resolve_deterministic


@pytest.fixture(scope="module")
def gaz():
    return load_gazetteers(SETTINGS.kb_path, SETTINGS.vocabulary_path)


def test_exact_identifier_wins(gaz):
    r = resolve_deterministic("Where is gate B12?", gaz)
    assert (r.stage, r.decision, r.matched_record_id) == ("exact_identifier", "answer", "gates_pier_b")
    r = resolve_deterministic("Where is belt 8?", gaz)
    assert r.matched_record_id == "baggage_reclaim_t2"
    r = resolve_deterministic("desk one forty five", gaz)
    assert r.matched_record_id == "checkin_t1"


def test_volatile_redirect_precedes_identifier(gaz):
    r = resolve_deterministic("Is flight NH123 boarding at gate B12 yet?", gaz)
    assert r.decision == "redirect" and r.stage == "no_retrieval"
    assert r.matched_record_id == "flight_information" and "volatile" in r.flags
    r = resolve_deterministic("where are the departure boards", gaz)
    assert r.decision == "redirect"


def test_grounded_negative_identifier(gaz):
    r = resolve_deterministic("Where is gate B21?", gaz)
    assert r.decision == "abstain" and r.stage == "exact_identifier"
    assert "grounded_negative" in r.flags and r.candidates == ["gates_pier_b"]
    assert "B1 to B18" in r.reason
    r = resolve_deterministic("lounge in terminal 3", gaz)
    assert r.decision == "abstain" and "Terminal 3" in r.reason


def test_grounded_negative_category_in_terminal(gaz):
    r = resolve_deterministic("Is there a lounge in Terminal 2?", gaz)
    assert r.decision == "answer" and r.matched_record_id is None
    assert "grounded_negative" in r.flags and r.candidates == ["lounge_aurora"]


def test_terminal_scope_separates_location_from_service(gaz):
    # the shuttle sits in Terminal 1 but serves both; "no transport in
    # Terminal 2" was the false grounded negative found on the held-out set
    r = resolve_deterministic("How often does the shuttle to terminal 2 run?", gaz)
    assert "grounded_negative" not in r.flags
    assert "shuttle_t1_t2" in (r.candidates or r.handoff.get("candidates", []))
    # a terminal-specific service still gives the grounded negative
    r = resolve_deterministic("Does Terminal 2 have a lounge?", gaz)
    assert "grounded_negative" in r.flags and r.candidates == ["lounge_aurora"]
    # an airport-level service reached by alias says it serves the terminal asked about
    r = resolve_deterministic("Is there a first aid room in Terminal 2?", gaz)
    assert r.matched_record_id == "first_aid_t1" and "cross_terminal_service" in r.flags
    assert "terminal_mismatch" not in r.flags
    # a record that is genuinely elsewhere keeps the mismatch flag
    r = resolve_deterministic("Is there lost property in terminal 2?", gaz)
    assert "terminal_mismatch" in r.flags and "cross_terminal_service" not in r.flags


def test_live_information_record_does_not_count_as_a_desk(gaz):
    # the flight boards serve both terminals but only ever redirect; they must
    # not stop "help desk in terminal 2" narrowing to the one Terminal 2 desk
    r = resolve_deterministic("help desk in terminal 2", gaz)
    assert not r.resolved and r.handoff["cue_single_record"] == "info_desk_t2"


def test_serves_terminals_defaults_to_the_record_terminal(gaz):
    assert gaz.records["checkin_t2"]["serves_terminals"] == ["Terminal 2"]
    assert gaz.serves("shuttle_t1_t2", "Terminal 2") and not gaz.serves("lounge_aurora", "Terminal 2")


def test_conflicting_identifiers_surface_both(gaz):
    r = resolve_deterministic("is it gate B12 or C3?", gaz)
    assert r.decision == "clarify" and r.candidates == ["gates_pier_b", "gates_pier_c"]


def test_alias_and_terminal_narrowing(gaz):
    assert resolve_deterministic("lost and found", gaz).matched_record_id == "lost_property_t1"
    r = resolve_deterministic("Check-in desks Terminal 2", gaz)   # cue + terminal: one record, confirmed semantically
    assert not r.resolved and r.handoff["cue_single_record"] == "checkin_t2"
    r = resolve_deterministic("Is there lost property in terminal 2?", gaz)
    assert r.matched_record_id == "lost_property_t1" and "terminal_mismatch" in r.flags


def test_single_record_category_is_handed_over_not_answered(gaz):
    # a cue narrows to the one lounge record; the semantic stage confirms it
    r = resolve_deterministic("Is there a lounge?", gaz)
    assert not r.resolved and r.handoff["cue_single_record"] == "lounge_aurora"


def test_multi_record_category_does_not_resolve(gaz):
    r = resolve_deterministic("Where is security?", gaz)
    assert not r.resolved and r.stage is None and r.decision is None
    assert r.handoff["category_hints"] == ["security"]
    assert len(r.handoff["candidates"]) == 3


def test_time_flag(gaz):
    r = resolve_deterministic("Is the lounge open right now?", gaz)
    assert r.matched_record_id == "lounge_aurora" and "time_reference_no_clock" in r.flags


def test_deictic_without_evidence_clarifies(gaz):
    r = resolve_deterministic("What does this sign mean?", gaz)
    assert r.decision == "clarify" and "deictic" in r.flags
    # deictic word with real evidence is not the deictic branch
    r = resolve_deterministic("is this gate B12?", gaz)
    assert r.decision == "answer"


def test_unresolved_keeps_evidence(gaz):
    r = resolve_deterministic("I left my bag on the plane", gaz)
    assert not r.resolved
    assert sorted(r.handoff["category_hints"]) == ["baggage", "lost_property"]
    r = resolve_deterministic("Kayip esya ofisi nerede?", gaz)
    assert not r.resolved and r.handoff["category_hints"] == []


def test_empty_input(gaz):
    r = resolve_deterministic("", gaz)
    assert not r.resolved and r.entities == {}


def test_seed_set_no_false_resolution(gaz):
    """Every deterministic decision on the seed set must match the seed's
    expected behaviour and target. Unresolved queries are allowed."""
    wrong = []
    stages = []
    for q in load_queries(SETTINGS.queries_seed_path):
        r = resolve_deterministic(q["query"], gaz)
        if not r.resolved:
            continue
        stages.append(r.stage)
        target = q["target_kb_id"] or None
        record_ok = (r.matched_record_id == target
                     or ("grounded_negative" in r.flags and target in r.candidates)
                     or (target is None and r.matched_record_id is None))
        if not record_ok or r.decision != q["expected_behaviour"]:
            wrong.append((q["query_id"], r.decision, r.matched_record_id, q["expected_behaviour"], target))
    assert wrong == [], wrong
    counts = stage_firing_counts(stages)   # also proves the stage names are the frozen ones
    assert set(counts) <= set(STAGES)
    assert counts["exact_identifier"] >= 5 and counts["alias_lookup"] >= 10


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))


# ---- QA 04.4 item 3: aliases against the terminal asked about ----

def test_alias_retargets_to_the_same_kind_of_record_in_the_asked_terminal(gaz):
    r = resolve_deterministic("Where is the check-in hall in Terminal 2?", gaz)
    assert r.matched_record_id == "checkin_t2" and "terminal_retargeted" in r.flags
    # nothing of that kind serves Terminal 2: the mismatch answer stands
    r = resolve_deterministic("lost property office in terminal 2", gaz)
    assert r.matched_record_id == "lost_property_t1" and "terminal_mismatch" in r.flags
    # an airport-level service is not retargeted, it serves the terminal itself
    r = resolve_deterministic("taxi rank at terminal 2", gaz)
    assert r.matched_record_id == "taxi_rank_t1" and "cross_terminal_service" in r.flags


def test_two_word_aliases_match_in_either_order(gaz):
    assert resolve_deterministic("security north", gaz).matched_record_id == "security_t1_north"
    assert resolve_deterministic("north security", gaz).matched_record_id == "security_t1_north"
    assert "security north" in gaz.alias_index and gaz.alias_index["security north"] == "security_t1_north"
