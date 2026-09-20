"""Response assembly: every rendered value comes from the KB, flags become
text, and the system never claims to act or to know live status.

Deterministic cases render without the model; the last two tests need
MiniLM and skip when it is unavailable.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from configs.settings import SETTINGS
from src.entities import load_gazetteers
from src import retrieval
from src.responses import (asks_live_status, compact_facts, hours_verdict, is_action_request, record_details,
                           render)
from src.retrieval import resolve_deterministic

FORBIDDEN = ["is open now", "is closed now", "currently open", "currently closed",
             "minutes wait", "minute wait", "queue is", "on time", "delayed by"]


@pytest.fixture(scope="module")
def gaz():
    return load_gazetteers(SETTINGS.kb_path, SETTINGS.vocabulary_path)


def no_forbidden_claims(text: str) -> bool:
    lower = text.lower()
    return not any(phrase in lower for phrase in FORBIDDEN)


def test_where_answer_is_short_and_the_details_hold_every_field(gaz):
    """04.6: the answer says where and gives one direction; every non-empty
    record field is still available through record_details."""
    r = resolve_deterministic("Where is gate B12?", gaz)
    text = render(r, gaz)
    record = gaz.records["gates_pier_b"]
    assert text.startswith("Pier B Gates (B1–B18) is in Terminal 1, Pier B (Airside, Level 2).")
    assert len(text.split()) <= 90 and text.count("\n") <= 3
    assert "Source:" not in text and "last verified" not in text     # provenance lives in the evidence panel
    details = dict(record_details(record, gaz))
    for field, label in (("description", "Description"), ("directions", "Directions"),
                         ("assistance_contact", "Help")):
        assert record[field] in details[label], field
    for value in record["opening_hours"].values():
        assert value in details["Opening hours"]
    assert record["accessibility"]["notes"] in details["Accessibility"]
    assert "gates_pier_b" in details["Record"] and "last verified" in details["Source"]


def test_compact_facts_come_only_from_the_selected_record(gaz):
    """Rule G (04.6): a fact item may show a field of the selected record
    even when the short answer does not repeat it; never anything else."""
    for rid, record in gaz.records.items():
        facts = compact_facts(record)
        assert 1 <= len(facts) <= 4
        for icon, label, value in facts:
            assert icon and label                       # icon never stands alone
            if label == "Location":
                assert value == f"{record['terminal']} · {record['zone']}"
            elif label == "Hours":
                assert value.replace("–", "-") in " ".join(record["opening_hours"].values()) or \
                    all(v in value for v in record["opening_hours"].values())
            elif label == "Access":
                assert record["accessibility"]["step_free"] or record["accessibility"].get("induction_loop") \
                    or record["accessibility"].get("accessible_toilet_nearby")
            elif label == "Route":
                assert value.rstrip(".") in record["directions"]


def test_explicit_clock_time_is_compared_with_listed_hours(gaz):
    """E (04.6): a time the passenger gives is used; "now" still is not."""
    record = gaz.records["security_t1_south"]                 # 04:30-21:00
    assert hours_verdict(record, "20:30").startswith("Yes.")
    assert hours_verdict(record, "21:00").startswith("No.")
    assert hours_verdict(gaz.records["gates_pier_b"], "00:30").startswith("Yes.")   # 04:00-01:00 wraps midnight
    assert hours_verdict(gaz.records["restrooms_t1_arrivals"], "03:00") is None     # "always open" does not parse
    text = render(resolve_deterministic("Is Security South open at 8:30 pm?", gaz), gaz)
    assert "scheduled to be open at 20:30" in text and "04:30–21:00" in text
    assert "cannot see the current time" not in text
    text = render(resolve_deterministic("Is Security South open now?", gaz), gaz)
    assert "cannot see the current time" in text and no_forbidden_claims(text)


def test_first_aid_is_not_an_hours_question(gaz):
    """"first" in "first aid" must not switch the answer to the hours aspect (Chrome QA, 04.6)."""
    text = render(resolve_deterministic("I'm beside Security South and I need first aid.", gaz), gaz)
    assert text.startswith("First Aid Room is in Terminal 1") and "listed hours" not in text


def test_time_reference_gives_hours_but_no_open_closed_claim(gaz):
    r = resolve_deterministic("Is the lounge open right now?", gaz)
    text = render(r, gaz)
    assert "05:00-22:00" in text
    assert "cannot see the current time" in text
    assert no_forbidden_claims(text)


def test_redirect_never_answers_from_kb(gaz):
    r = resolve_deterministic("What gate is flight XY456 leaving from?", gaz)
    text = render(r, gaz)
    assert "do not hold live flight" in text
    assert "official channels" in text
    assert "Pier" not in text and no_forbidden_claims(text)


def test_grounded_negative_and_terminal_mismatch_wording(gaz):
    text = render(resolve_deterministic("Is there a lounge in Terminal 2?", gaz), gaz)
    assert text.startswith("There is no lounge in Terminal 2.")
    assert "Aurora Lounge (Terminal 1)" in text
    text = render(resolve_deterministic("Where is gate B21?", gaz), gaz)
    assert "outside the known range (B1 to B18)" in text and "boarding pass" in text
    text = render(resolve_deterministic("Is there parking at terminal 2?", gaz), gaz)
    assert text.startswith("Car Park P1 also serves Terminal 2.")
    text = render(resolve_deterministic("Is there lost property in terminal 2?", gaz), gaz)
    assert text.startswith("Lost Property Office is not in Terminal 2; it is in Terminal 1.")


def test_action_and_live_status_guards():
    assert is_action_request("can you book me a taxi for 6pm")
    assert is_action_request("please print my boarding pass")
    assert not is_action_request("where is the taxi rank")
    assert asks_live_status("how long is the queue at security north")
    assert not asks_live_status("where is security north")


def test_queue_question_never_invents_queue_information(gaz):
    r = resolve_deterministic("How long is the queue at security north?", gaz)
    r.stage, r.decision, r.candidates = "category_filter_semantic", "clarify", ["security_t1_north", "security_t1_south"]
    text = render(r, gaz)
    assert "do not have live queue" in text and no_forbidden_claims(text)
    assert "live_status_request" in r.flags


def test_security_answer_keeps_the_queue_note_in_the_details(gaz):
    r = resolve_deterministic("north security", gaz)
    assert r.matched_record_id == "security_t1_north"
    text = render(r, gaz)
    assert no_forbidden_claims(text) and len(text.split()) <= 60
    assert "Live queue times are not available" in dict(record_details(gaz.records["security_t1_north"], gaz))["Availability"]


# ---- model needed ----

@pytest.fixture(scope="module")
def index(gaz):
    pytest.importorskip("sentence_transformers")
    try:
        return retrieval.build_text_index(gaz, SETTINGS.intent_exemplars_path)
    except Exception as exc:
        pytest.skip(f"MiniLM not available here: {type(exc).__name__}")


def test_booking_request_states_it_cannot_act(gaz, index):
    r = retrieval.resolve("Can you book me a taxi for 6pm?", gaz, index, SETTINGS.thresholds())
    text = render(r, gaz)
    assert text.startswith("I cannot book, reserve, print or arrange anything")
    assert "action_request" in r.flags
    assert "booked" not in text.lower() and no_forbidden_claims(text)


def test_answer_text_never_carries_a_score(gaz, index):
    """The raw cosine reads like a low percentage to a passenger; the answer
    carries no number at all and the evidence panel carries it (04.6)."""
    r = retrieval.resolve("Where can I collect my luggage in terminal 2?", gaz, index, SETTINGS.thresholds())
    assert r.decision == "answer" and r.match_score is not None
    text = render(r, gaz)
    assert f"{r.match_score:.2f}" not in text and "similarity" not in text.lower()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))


def test_terminal_question_names_terminals_not_records(gaz):
    r = resolve_deterministic("Where is security?", gaz)
    r.stage, r.decision = "category_filter_semantic", "clarify"
    r.candidates, r.clarification_field = ["security_t1_south", "security_t1_north", "security_t2"], "terminal"
    text = render(r, gaz)
    assert "Are you in Terminal 1 or Terminal 2?" in text
    assert "Security South" not in text and "Security North" not in text
    assert no_forbidden_claims(text)


# ---- QA 04.4 item 5: action requests never read as done ----

@pytest.mark.parametrize("query", ["Can you book me a taxi for 6pm?", "please print my boarding pass",
                                   "reserve a table at the restaurant", "cancel my parking"])
def test_action_requests_always_carry_the_refusal_and_never_claim_action(gaz, query):
    r = resolve_deterministic(query, gaz)
    if not r.resolved:      # semantic stage not run here: stand in for it
        r.resolved, r.stage, r.decision, r.candidates = True, "category_filter_semantic", "clarify", ["taxi_rank_t1"]
        r = retrieval._apply_action_policy(r)
    assert r.decision == "abstain" and "action_request" in r.flags      # 04.6: refused, never answered
    text = render(r, gaz)
    assert text.startswith("I cannot book, reserve, print or arrange anything")
    assert not any(w in text.lower() for w in ("booked", "reserved", "printed", "arranged", "cancelled", "done"))
