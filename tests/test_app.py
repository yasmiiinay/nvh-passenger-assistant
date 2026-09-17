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
    clarify = Outcome(route="text_only", decision="clarify", candidates=["a", "b"], clarification_field="terminal")
    clarify.text = object()
    replies = ui.quick_replies(clarify, Gaz(), "where is security", None)
    assert [r["label"] for r in replies] == ["Terminal 1", "Terminal 2"]
    assert replies[0]["text"] == "security in Terminal 1"      # the same example the answer text gives
    conflict = Outcome(route="text_leads", decision="conflict", conflict=True)
    replies = ui.quick_replies(conflict, Gaz(), "baggage reclaim", "/tmp/sign.png")
    assert [r["label"] for r in replies] == ["Use my question", "Use the photo"]
    assert replies[1] == {"label": "Use the photo", "image": "/tmp/sign.png"}
    assert ui.quick_replies(Outcome(route="text_only", decision="answer"), Gaz(), "x", None) == []


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


def test_turns_are_independent_but_stay_on_screen(models_ready, tmp_path, monkeypatch):
    monkeypatch.setattr(event_log, "EVENTS_PATH", tmp_path / "events.jsonl")
    first = ui.run_turn("Where is security?", None, None, {})
    assert [q["label"] for q in first["quick"]] == ["Terminal 1", "Terminal 2"]
    second = ui.run_turn(first["quick"][0]["text"], None, None, first["session"])
    assert len(second["session"]["history"]) == 2 and second["session"]["turn"] == 2
    assert "Where is security?" in second["conversation"]      # earlier turn still shown
    assert "Terminal 1" in second["session"]["history"][-1]["passenger"]
    assert ui.HISTORY_NOTE in second["evidence"]


def test_unreadable_image_is_handled(models_ready, tmp_path, monkeypatch):
    monkeypatch.setattr(event_log, "EVENTS_PATH", tmp_path / "events.jsonl")
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image")
    result = ui.run_turn("", str(bad), None, {})
    assert "could not read" in result["conversation"] and "Could not read the input" in result["conversation"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
