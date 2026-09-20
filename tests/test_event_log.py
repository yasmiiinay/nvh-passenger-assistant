"""Event log and escalation record: what is written, and what is not."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from configs.settings import SETTINGS
from src.entities import load_gazetteers
from src.event_log import event_from_outcome, log_event, new_session_id, open_ticket
from src.retrieval import RetrievalResult
from src.router import Outcome
from src.speech import AudioCheck, SpeechResult


@pytest.fixture(scope="module")
def gaz():
    return load_gazetteers(SETTINGS.kb_path, SETTINGS.vocabulary_path)


def sample_outcome():
    text = RetrievalResult(query="Where is gate B12? my name is Alex", normalized="where is gate b12 my name is alex",
                           entities={"gate_id": "B12"}, resolved=True, stage="exact_identifier", decision="answer",
                           matched_record_id="gates_pier_b", intent=None)
    speech = SpeechResult("clip.wav", AudioCheck(2.0, -20.0, 16000, True), transcript_raw="Where is gate B12? my name is Alex")
    return Outcome(route="voice_only", decision="answer", matched_record_id="gates_pier_b", band="strong match",
                   modalities=["voice"], text=text, speech=speech, flags=["image_agrees"])


def test_event_holds_ids_and_scores_but_no_words(tmp_path):
    event = event_from_outcome(sample_outcome(), "s1", 3, 0.42)
    assert event["record_id"] == "gates_pier_b" and event["route"] == "voice_only" and event["audio_ok"] is True
    assert event["latency_s"] == 0.42 and event["turn_index"] == 3
    serialised = json.dumps(event)
    assert "Alex" not in serialised and "gate b12" not in serialised   # neither the query nor the transcript
    path = tmp_path / "events.jsonl"
    log_event(event, path)
    log_event(event, path)
    assert len(path.read_text().splitlines()) == 2


def test_ticket_has_reference_and_kb_contact(tmp_path, gaz):
    ticket = open_ticket(sample_outcome(), gaz, "s1", "lift out of order", tmp_path / "tickets.jsonl")
    assert ticket["reference"].startswith("NVH-") and len(ticket["reference"]) == 10
    assert ticket["contact_route"] == "Departures information desk, Terminal 1"
    assert ticket["note"] == "lift out of order"
    stored = json.loads((tmp_path / "tickets.jsonl").read_text().splitlines()[0])
    assert stored["reference"] == ticket["reference"]


def test_session_ids_differ():
    assert new_session_id() != new_session_id()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
