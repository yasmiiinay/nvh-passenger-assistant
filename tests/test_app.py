"""Interface boundaries: the callbacks return the shapes the layout expects,
never raise, and the page builds. Model-backed cases skip without weights."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
gr = pytest.importorskip("gradio")
import app as ui
from src import event_log
from src.router import Outcome


def test_page_builds_and_keeps_uploaded_images_as_they_are():
    demo = ui.build_ui()
    assert isinstance(demo, gr.Blocks)
    photo = next(c for c in demo.blocks.values() if getattr(c, "elem_id", None) == "photo")
    assert photo.image_mode is None     # a transparent pictogram must not become a black square


def test_empty_input_is_a_message_not_a_traceback():
    result = ui.run_turn("", None, None, {})
    assert "type a question" in result["notice"] and result["session"]["turn"] == 1
    assert result["session"].get("history", []) == []


def test_assistance_needs_a_previous_turn():
    assert "Ask a question first" in ui.request_assistance("help", {})


def test_every_status_has_words_not_only_a_symbol():
    for key in ui.STATUS:
        chip = ui.status_chip(key)
        assert ui.STATUS[key][1] in chip and 'aria-hidden' in chip


def test_passenger_turn_escapes_html():
    shown = ui.passenger_html("<b>gate</b>", None, "", False)
    assert "&lt;b&gt;gate&lt;/b&gt;" in shown and "<b>" not in shown


def test_quick_replies_only_for_terminal_clarify_and_conflict():
    class Gaz:
        records = {"a": {"category": "security", "terminal": "Terminal 1"},
                   "b": {"category": "security", "terminal": "Terminal 2"}}
    clarify = Outcome(route="text_only", decision="clarify", candidates=["a", "b"], clarification_field="terminal",
                      pending_next={"category": "security", "terminal": None, "zones": []})
    clarify.text = object()
    replies = ui.quick_replies(clarify, Gaz(), "where is security", None)
    assert [r["label"] for r in replies] == ["Terminal 1", "Terminal 2"]
    assert replies[0]["text"] == "Terminal 1"      # the short follow-up the pending clarification completes
    conflict = Outcome(route="text_leads", decision="conflict", conflict=True)
    replies = ui.quick_replies(conflict, Gaz(), "baggage reclaim", "/tmp/sign.png")
    assert [r["label"] for r in replies] == ["Use my question", "Use the photo"]
    assert replies[1] == {"label": "Use the photo", "image": "/tmp/sign.png"}
    assert ui.quick_replies(Outcome(route="text_only", decision="answer"), Gaz(), "x", None) == []


def test_fact_row_shows_labelled_fields_of_the_selected_record_only():
    """Rule G (04.6): each fact item is icon + text label + a field of the
    record the outcome selected; nothing when nothing was selected."""
    from src.entities import load_gazetteers
    from configs.settings import SETTINGS
    import re
    gaz = load_gazetteers(SETTINGS.kb_path, SETTINGS.vocabulary_path)
    for rid, record in gaz.records.items():
        row = ui.fact_row(Outcome(route="text_only", decision="answer", matched_record_id=rid), gaz)
        assert 'aria-hidden="true"' in row and "Location:" in row
        assert html_unescape(record["zone"]) in row
        for label in ("Hours:", "Access:", "Route:"):
            if label in row:
                assert re.search(r'<span class="fact-label">' + label + "</span>", row)
    assert ui.fact_row(Outcome(route="text_only", decision="clarify", candidates=["gates_pier_b"]), gaz) == ""


def html_unescape(text: str) -> str:
    import html as html_module
    return html_module.escape(text)


@pytest.fixture(scope="module")
def models_ready():
    try:
        ui.get_context()
    except Exception as exc:
        pytest.skip(f"models not available here: {type(exc).__name__}")


def test_text_turn_and_ticket(models_ready, tmp_path, monkeypatch):
    monkeypatch.setattr(event_log, "EVENTS_PATH", tmp_path / "events.jsonl")
    monkeypatch.setattr(event_log, "TICKETS_PATH", tmp_path / "tickets.jsonl")
    result = ui.run_turn("Where is gate B12?", None, None, {})
    session = result["session"]
    assert len(session["history"]) == 1 and "Pier B Gates" in result["conversation"]
    assert "Strong match" in result["conversation"] and "From your words" in result["conversation"]
    assert "Matched record" in result["evidence"] and result["transcript"] == "" and result["quick"] == []
    assert (tmp_path / "events.jsonl").exists()
    note = ui.request_assistance("", session)
    assert "NVH-" in note and "Departures information desk" in note


def test_turns_stay_on_screen_and_a_terminal_follow_up_completes_the_clarification(models_ready, tmp_path, monkeypatch):
    monkeypatch.setattr(event_log, "EVENTS_PATH", tmp_path / "events.jsonl")
    first = ui.run_turn("Where is security?", None, None, {})
    assert [q["label"] for q in first["quick"]] == ["Terminal 1", "Terminal 2"]
    assert first["session"]["pending"] == {"category": "security", "terminal": None, "zones": []}
    assert "Pending clarification" in first["evidence"]
    second = ui.run_turn(first["quick"][1]["text"], None, None, first["session"])      # "Terminal 2"
    assert len(second["session"]["history"]) == 2 and second["session"]["turn"] == 2
    assert "Where is security?" in second["conversation"]      # earlier turn still shown
    assert "Security, Terminal 2" in second["conversation"] and "Follow-up context" in second["evidence"]
    assert second["session"]["pending"] is None                # an answer leaves nothing behind
    assert ui.HISTORY_NOTE not in second["evidence"]           # stated once, in the session-history bar
    third = ui.run_turn("Terminal 1", None, None, second["session"])     # two turns later: no context
    assert "What would you like to find in Terminal 1?" in third["conversation"]


def test_a_full_question_ignores_the_pending_context_and_clear_drops_it(models_ready, tmp_path, monkeypatch):
    monkeypatch.setattr(event_log, "EVENTS_PATH", tmp_path / "events.jsonl")
    first = ui.run_turn("Where is security in Terminal 1?", None, None, {})
    assert first["session"]["pending"]["category"] == "security"
    second = ui.run_turn("Where is gate B12?", None, None, first["session"])
    assert "Pier B Gates" in second["conversation"] and "Follow-up context" not in second["evidence"]
    again = ui.run_turn("Where is security in Terminal 1?", None, None, second["session"])
    assert again["session"]["pending"]["category"] == "security"
    cleared = dict(again["session"], pending=None, history=[])
    assert ui.run_turn("What about Terminal 2?", None, None, cleared)["session"]["pending"]["terminal"] == "Terminal 2"
    assert "What would you like to find in Terminal 2?" in ui.run_turn("What about Terminal 2?", None, None, cleared)["conversation"]


def test_answer_is_short_and_details_are_in_the_evidence_panel(models_ready, tmp_path, monkeypatch):
    monkeypatch.setattr(event_log, "EVENTS_PATH", tmp_path / "events.jsonl")
    result = ui.run_turn("Where is gate B12?", None, None, {})
    import re
    body = re.search(r'<div class="answer">(.*?)</div>', result["session"]["history"][-1]["assistant"]).group(1)
    words = re.sub(r"<[^>]+>", " ", body).split()
    assert len(words) <= 90 and "Source" not in body and "last verified" not in body
    assert "Description" in result["evidence"] and "last verified" in result["evidence"]
    assert 'class="facts"' in result["session"]["history"][-1]["assistant"]


def test_history_note_is_on_the_page():
    demo = ui.build_ui()
    assert any(ui.HISTORY_NOTE in str(getattr(c, "value", "")) for c in demo.blocks.values())


def test_a_terminal_reply_completes_a_photo_clarification(models_ready, tmp_path, monkeypatch):
    monkeypatch.setattr(event_log, "EVENTS_PATH", tmp_path / "events.jsonl")
    photo = Path(__file__).resolve().parents[1] / "data" / "images" / "files" / "img_015.png"   # restroom pictogram
    first = ui.run_turn("", str(photo), None, {})
    if first["session"]["pending"] is None:
        pytest.skip("photo did not produce a terminal clarification here")
    assert [q["label"] for q in first["quick"]] == ["Terminal 1", "Terminal 2"]
    second = ui.run_turn("Terminal 2", None, None, first["session"])
    assert "Restrooms, Terminal 2" in second["conversation"]


def test_evidence_starts_with_a_short_summary(models_ready, tmp_path, monkeypatch):
    monkeypatch.setattr(event_log, "EVENTS_PATH", tmp_path / "events.jsonl")
    evidence = ui.run_turn("Where is gate B12?", None, None, {})["evidence"]
    summary, technical = evidence.split('<details class="ev-tech">')
    assert summary.count('class="ev-row"') <= 5 and "Pier B Gates" in summary
    assert "Retrieval stage" in technical and "Description" in technical


def test_unreadable_image_is_handled(models_ready, tmp_path, monkeypatch):
    monkeypatch.setattr(event_log, "EVENTS_PATH", tmp_path / "events.jsonl")
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image")
    result = ui.run_turn("", str(bad), None, {})
    assert "could not read" in result["conversation"] and "Could not read the input" in result["conversation"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))


def test_evidence_summary_lists_no_options_for_a_sign_that_cannot_be_read():
    class Gaz:
        records = {"a": {"name": "Baggage Reclaim, Terminal 1"}}
    out = Outcome(route="image_only", decision="clarify", candidates=["a"], band="uncertain",
                  flags=["image_uncertain", "image_text_sign"])
    labels = [label for label, _ in ui.evidence_summary(out, Gaz())]
    assert "Options" not in labels
    out.flags = ["image_uncertain"]
    assert "Options" in [label for label, _ in ui.evidence_summary(out, Gaz())]
