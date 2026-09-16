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
from src.responses import asks_live_status, is_action_request, render
from src.retrieval import resolve_deterministic

FORBIDDEN = ["is open now", "is closed now", "currently open", "currently closed",
             "minutes wait", "minute wait", "queue is", "on time", "delayed by"]


@pytest.fixture(scope="module")
def gaz():
    return load_gazetteers(SETTINGS.kb_path, SETTINGS.vocabulary_path)


def no_forbidden_claims(text: str) -> bool:
    lower = text.lower()
    return not any(phrase in lower for phrase in FORBIDDEN)


def test_answer_contains_every_non_empty_record_field(gaz):
    r = resolve_deterministic("Where is gate B12?", gaz)
    text = render(r, gaz)
    record = gaz.records["gates_pier_b"]
    for field in ("name", "description", "directions", "terminal", "level", "zone", "assistance_contact"):
        assert record[field] in text, field
    for value in record["opening_hours"].values():
        assert value in text
    assert record["accessibility"]["notes"] in text
    assert "record gates_pier_b" in text and "last verified" in text
    assert "not a probability" not in text            # deterministic match has no score
    assert "Matched by exact identifier" in text


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
    assert text.startswith("Car Park P1 is in Terminal 1 and also serves Terminal 2.")
    text = render(resolve_deterministic("Is there lost property in terminal 2?", gaz), gaz)
    assert text.startswith("Lost Property Office is not at Terminal 2; it is at Terminal 1.")


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


def test_security_answer_carries_availability_note(gaz):
    r = resolve_deterministic("north security", gaz)
    assert r.matched_record_id == "security_t1_north"
    text = render(r, gaz)
    assert "Live queue times are not available" in text


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


def test_semantic_answer_names_the_band_not_the_number(gaz, index):
    """The raw cosine reads like a low percentage to a passenger; the answer
    carries the band and the evidence panel carries the number."""
    r = retrieval.resolve("taxi?", gaz, index, SETTINGS.thresholds())
    assert r.decision == "answer"
    text = render(r, gaz)
    assert "Matched by similarity: strong match" in text and f"{r.match_score:.2f}" not in text


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
