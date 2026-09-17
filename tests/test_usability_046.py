"""Usability regression set from hardening pass 04.6.

These are acceptance checks written after manual usability testing of the
v1.1 build, NOT a blind evaluation: the diagnostic sentences were seen when
the general rules were designed, so every rule also carries at least one
paraphrase that was not among them, and a false-positive check where the
rule could over-fire. Nothing here feeds the blind result files.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from configs.settings import SETTINGS
from src.entities import extract, load_gazetteers
from src.retrieval import build_text_index, pending_context, resolve


@pytest.fixture(scope="module")
def gaz():
    return load_gazetteers(SETTINGS.kb_path, SETTINGS.vocabulary_path)


@pytest.fixture(scope="module")
def index(gaz):
    pytest.importorskip("sentence_transformers")
    try:
        return build_text_index(gaz, SETTINGS.intent_exemplars_path)
    except Exception as exc:
        pytest.skip(f"MiniLM not available here: {type(exc).__name__}")


def ask(q, gaz, index, pending=None):
    return resolve(q, gaz, index, SETTINGS.thresholds(), pending=pending)


# ---------------------------------------------------------------------------
# the sixteen text acceptance cases (section I of the brief)
# ---------------------------------------------------------------------------

ACCEPTANCE = [
    ("Where is gate B17?", "answer", "gates_pier_b"),
    ("My check-in desk is 225. Where do I go?", "answer", "checkin_t2"),
    ("Is Security South open at 8:30 pm?", "answer", "security_t1_south"),
    ("I just landed in Terminal 2. Where do I collect my bag?", "answer", "baggage_reclaim_t2"),
    ("I lost my headphones. Where should I go?", "answer", "lost_property_t1"),
    ("I just arrived in Terminal 1 and want a coffee.", "answer", "cafe_harbour"),
    ("I've passed security in Terminal 1 and want a sit-down meal.", "answer", "restaurant_skyline"),
    ("I need a bathroom after security in Terminal 1.", "answer", "restrooms_t1_departures"),
    ("I need wheelchair assistance in Terminal 2.", "answer", "prm_point_t2"),
    ("I feel sick near Security North. Where can I get medical help?", "answer", "first_aid_t1"),
    ("How do I get from Terminal 1 to Terminal 2?", "answer", "shuttle_t1_t2"),
    ("What time is the last train from the airport?", "answer", "rail_station"),
    ("Has flight NV402 landed yet?", "redirect", "flight_information"),
]


@pytest.mark.parametrize("query,decision,record", ACCEPTANCE)
def test_acceptance_answers(gaz, index, query, decision, record):
    r = ask(query, gaz, index)
    assert r.decision == decision and r.matched_record_id == record, (r.decision, r.matched_record_id, r.reason)


def test_acceptance_security_terminal_1_clarifies_north_or_south(gaz, index):
    r = ask("Where is security in Terminal 1?", gaz, index)
    assert r.decision == "clarify" and set(r.candidates) == {"security_t1_north", "security_t1_south"}


def test_acceptance_generic_special_assistance_asks_for_the_terminal_not_first_aid(gaz, index):
    r = ask("I need special assistance. Where should I go?", gaz, index)
    assert r.decision == "clarify" and r.clarification_field == "terminal"
    assert {gaz.records[rid]["category"] for rid in r.candidates} == {"accessibility"}


def test_acceptance_baggage_lockers_are_refused_not_mapped_to_reclaim(gaz, index):
    r = ask("Are there baggage lockers in Terminal 2?", gaz, index)
    assert r.decision == "abstain" and "unsupported_service" in r.flags and r.matched_record_id is None


def test_acceptance_explicit_time_is_interpreted(gaz):
    ex = extract("Is Security South open at 8:30 pm?", gaz)
    assert [e.value for e in ex.of_type("clock_time")] == ["20:30"]


# ---------------------------------------------------------------------------
# follow-up: one-turn pending clarification context (section D)
# ---------------------------------------------------------------------------

def test_followup_completes_the_pending_security_clarification(gaz, index):
    first = ask("Where is security in Terminal 1?", gaz, index)
    pending = pending_context(first, gaz)
    assert pending == {"category": "security", "terminal": "Terminal 1", "zones": []}
    second = ask("What about Terminal 2?", gaz, index, pending)
    assert second.decision == "answer" and second.matched_record_id == "security_t2"
    assert "followup_context" in second.flags and pending_context(second, gaz) is None


def test_followup_restroom_terminal(gaz, index):
    pending = pending_context(ask("I need a toilet", gaz, index), gaz)
    assert pending["category"] == "restroom"
    r = ask("Terminal 2", gaz, index, pending)
    assert r.decision == "answer" and r.matched_record_id == "restrooms_t2"
    r = ask("And Terminal 1?", gaz, index, pending)         # two T1 restroom records remain
    assert r.decision == "clarify" and set(r.candidates) == {"restrooms_t1_arrivals", "restrooms_t1_departures"}


def test_followup_does_not_leak_into_a_full_question(gaz, index):
    pending = pending_context(ask("Where is security in Terminal 1?", gaz, index), gaz)
    r = ask("Where is gate B12?", gaz, index, pending)
    assert r.matched_record_id == "gates_pier_b" and "followup_context" not in r.flags
    r = ask("Where can I get a coffee in Terminal 2?", gaz, index, pending)
    assert r.matched_record_id == "cafe_pier_c" and "followup_context" not in r.flags


def test_followup_context_only_comes_from_a_clarification(gaz, index):
    assert pending_context(ask("Where is gate B12?", gaz, index), gaz) is None
    assert pending_context(ask("Has flight NV402 landed yet?", gaz, index), gaz) is None
    assert pending_context(ask("Are there baggage lockers here?", gaz, index), gaz) is None


def test_fragment_without_context_asks_for_the_service(gaz, index):
    for fragment in ("What about Terminal 2?", "And Terminal 1?", "where is terminal 2", "What about arrivals?"):
        r = ask(fragment, gaz, index)
        assert r.decision == "clarify" and "fragment" in r.flags, fragment
        assert r.clarification_field == "service" and not r.candidates and r.matched_record_id is None
    # "the other terminal" is transfer wording, so it resolves like "how do I change terminal"
    r = ask("The other terminal?", gaz, index)
    assert r.matched_record_id == "shuttle_t1_t2" and "terminal_transfer" in r.flags


# ---------------------------------------------------------------------------
# voice transcripts (text-level; Whisper itself is frozen)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("transcript,decision,record", [
    ("Where is Gate B17?", "answer", "gates_pier_b"),
    ("My chicken desk is 225. Where do I go?", "answer", "checkin_t2"),
    ("I just landed in Terminal 2, where do I collect my bag?", "answer", "baggage_reclaim_t2"),
    ("I feel sick near security north. Where can I get medical help?", "answer", "first_aid_t1"),
    ("How do I get from terminal 1 to terminal 2?", "answer", "shuttle_t1_t2"),
    ("has flight NV402 landed yet", "redirect", "flight_information"),
])
def test_voice_transcripts(gaz, index, transcript, decision, record):
    r = ask(transcript, gaz, index)
    assert r.decision == decision and r.matched_record_id == record


def test_voice_transcript_security_terminal_one(gaz, index):
    r = ask("Various Security Terminal 1", gaz, index)
    assert r.decision == "clarify" and set(r.candidates) == {"security_t1_north", "security_t1_south"}


# ---------------------------------------------------------------------------
# generalisation: paraphrases that were not diagnostic sentences
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("query,record", [
    ("I have a headache near the check-in hall, is there a nurse?", "first_aid_t1"),     # other landmark + medical
    ("Something hurts and I'm standing by Pier B. Where is first aid?", "first_aid_t1"),
    ("counter 118, is that terminal 1?", "checkin_t1"),                                   # other desk syntax
    ("my desk number is 210", "checkin_t2"),
    ("carousel number 3", "baggage_reclaim_t1"),
    ("which belt is number 8", "baggage_reclaim_t2"),
    ("where can I find a toilet once I'm through security in terminal 1", "restrooms_t1_departures"),
    ("somewhere to eat airside in terminal 1", "restaurant_skyline"),                     # other after-security wording
    ("How do I change terminals?", "shuttle_t1_t2"),                                      # other transfer wording
    ("I need to get to the other terminal", "shuttle_t1_t2"),
    ("from T2 to T1", "shuttle_t1_t2"),
    ("shuttle between the terminals", "shuttle_t1_t2"),
    ("I use a wheelchair, where do I get help in terminal 1?", "prm_point_t1_entrance"),
    ("I feel faint, where is the medical room", "first_aid_t1"),
    ("How do I get from the rail station up to departures?", "rail_station"),            # landmark is the topic
    ("How long is the queue at security north?", "security_t1_north"),
])
def test_paraphrases_resolve(gaz, index, query, record):
    r = ask(query, gaz, index)
    assert r.decision == "answer" and r.matched_record_id == record, (r.decision, r.matched_record_id, r.reason)


def test_paraphrase_special_assistance_wording(gaz, index):
    r = ask("reduced mobility assistance", gaz, index)
    assert r.decision == "clarify" and {gaz.records[rid]["category"] for rid in r.candidates} == {"accessibility"}


def test_landmark_record_is_not_the_answer_when_another_service_is_asked_for(gaz, index):
    r = ask("I'm at the taxi rank, where is the bus?", gaz, index)
    assert r.matched_record_id != "taxi_rank_t1" and "taxi_rank_t1" not in r.candidates
    r = ask("Standing next to the Aurora Lounge, where are the toilets?", gaz, index)
    assert r.matched_record_id == "restrooms_t1_departures"


@pytest.mark.parametrize("query,term", [
    ("Is there somewhere to leave my luggage in a locker?", "locker"),
    ("cash machine", "cash machine"),
    ("where can I exchange money", "exchange money"),
    ("is there a pharmacy in terminal 2", "pharmacy"),
    ("duty free shops", "duty free"),
])
def test_unsupported_services_are_refused(gaz, index, query, term):
    r = ask(query, gaz, index)
    assert r.decision == "abstain" and "unsupported_service" in r.flags and r.entities["unsupported_service"] == term


@pytest.mark.parametrize("query,record", [
    ("is the lounge open at 20:30", "lounge_aurora"),
    ("is first aid open at 11 pm", "first_aid_t1"),
])
def test_other_explicit_times(gaz, index, query, record):
    r = ask(query, gaz, index)
    assert r.matched_record_id == record and "time_explicit" in r.flags and r.entities["clock_time"] in ("20:30", "23:00")


# ---------------------------------------------------------------------------
# false positives: where the new rules could over-fire
# ---------------------------------------------------------------------------

def test_supported_services_are_not_refused(gaz, index):
    for q, rid in (("where is baggage reclaim in terminal 1", "baggage_reclaim_t1"),
                   ("left luggage enquiries", "lost_property_t1"),
                   ("coffee shop arrivals", "cafe_harbour")):
        r = ask(q, gaz, index)
        assert "unsupported_service" not in r.flags and r.matched_record_id == rid, q


def test_an_unsupported_place_used_as_a_landmark_does_not_block_the_request(gaz, index):
    r = ask("Toilets after passport control", gaz, index)
    assert "unsupported_service" not in r.flags
    assert r.decision == "clarify" and {gaz.records[rid]["category"] for rid in r.candidates} == {"restroom"}


def test_medical_queries_do_not_become_prm_and_prm_queries_do_not_become_medical(gaz, index):
    r = ask("I feel ill, is there a doctor in terminal 2?", gaz, index)
    assert gaz.records[r.matched_record_id or r.candidates[0]]["category"] == "medical"
    r = ask("I need special assistance in terminal 1", gaz, index)
    assert gaz.records[r.matched_record_id or r.candidates[0]]["category"] == "accessibility"


def test_a_destination_zone_is_not_a_constraint(gaz):
    ex = extract("how do I get up to departures", gaz)
    assert ex.destination == "departures" and ex.zones == []
    ex = extract("I have just landed and need departures", gaz)
    assert "arrivals" in ex.zones


def test_a_single_terminal_and_a_bus_terminal_are_not_transfers(gaz, index):
    ex = extract("where is the bus terminal", gaz)
    assert not ex.transfer
    r = ask("where is the bus terminal", gaz, index)
    assert r.matched_record_id == "bus_terminal"


def test_empty_and_greeting_inputs_are_not_fragments(gaz):
    assert not extract("", gaz).fragment
    assert not extract("hello", gaz).fragment


def test_action_requests_are_refused_with_a_pointer(gaz, index):
    r = ask("Can you book me a taxi for 6pm?", gaz, index)
    assert r.decision == "abstain" and "action_request" in r.flags and r.candidates == ["taxi_rank_t1"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
