"""Unit tests for src/entities.py against the real KB and vocabulary."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from configs.settings import SETTINGS
from src.entities import extract, load_gazetteers


@pytest.fixture(scope="module")
def gaz():
    return load_gazetteers(SETTINGS.kb_path, SETTINGS.vocabulary_path)


def values(ex, entity_type):
    return [e.value for e in ex.entities if e.type == entity_type]


def test_gazetteers_are_kb_derived(gaz):
    # 12+18+10 gates, 60+30 desks, 6+3 belts, P1
    assert len(gaz.identifier_index) == 140
    assert gaz.identifier_index["B12"] == "gates_pier_b"
    assert gaz.identifier_index["BELT 8"] == "baggage_reclaim_t2"
    assert gaz.identifier_index["DESK 145"] == "checkin_t1"
    assert "B21" not in gaz.identifier_index
    assert gaz.alias_index["lost and found"] == "lost_property_t1"
    assert gaz.alias_index["terminal 1 check in"] == "checkin_t1"   # alias normalised like queries
    assert set(gaz.volatile_phrases.values()) == {"flight_information"}
    assert "flight" not in gaz.category_cues   # volatile record contributes no cues
    assert gaz.category_cues["lounge"] == "lounge"
    assert "terminal" not in gaz.category_cues  # spans categories -> excluded
    assert "a" not in gaz.category_cues         # function word -> excluded


@pytest.mark.parametrize("text,gate,exists", [
    ("Where is gate B12?", "B12", True),
    ("gate c3?", "C3", True),
    ("How do I get to A7", "A7", True),
    ("gate bee twelve", "B12", True),
    ("Where is gate B21?", "B21", False),
    ("gate D4", None, None),                  # D is not a pier letter
])
def test_gate_ids(gaz, text, gate, exists):
    ex = extract(text, gaz)
    gates = [e for e in ex.entities if e.type == "gate_id"]
    if gate is None:
        assert gates == []
    else:
        assert gates[0].value == gate and gates[0].exists is exists


@pytest.mark.parametrize("text", [
    "I have a 12 o'clock flight", "it will be 12 minutes", "a 7 hour layover",
])
def test_gate_ids_not_hallucinated(gaz, text):
    assert values(extract(text, gaz), "gate_id") == []


def test_desk_and_belt(gaz):
    assert values(extract("Where is desk 145?", gaz), "desk_id") == ["DESK 145"]
    assert values(extract("carousel 8", gaz), "belt_id") == ["BELT 8"]
    assert values(extract("belt eight", gaz), "belt_id") == ["BELT 8"]
    desk = extract("desk 999", gaz).entities[0]
    assert desk.type == "desk_id" and desk.exists is False


def test_terminal_closed_set(gaz):
    ex = extract("How do I get from Terminal 1 to T2?", gaz)
    assert values(ex, "terminal") == ["Terminal 1", "Terminal 2"]
    t3 = extract("terminal 3", gaz).entities[0]
    assert t3.type == "terminal" and t3.exists is False


@pytest.mark.parametrize("text,ref", [
    ("Is my flight NH123 delayed?", "NH 123"),
    ("What gate is flight XY456 leaving from?", "XY 456"),
    ("flight ba 2490", "BA 2490"),              # spoken form directly after 'flight'
    ("Is LH2004 boarding yet?", "LH 2004"),      # no 'flight' word, but four digits cannot be a gate
])
def test_flight_ref(gaz, text, ref):
    assert values(extract(text, gaz), "flight_ref") == [ref]


@pytest.mark.parametrize("text", ["meet at 10 am", "the shop is open until 22 tonight",
                                  "Where is KP12?"])   # ASR-damaged gate id in flight-code shape
def test_flight_ref_not_from_plain_numbers(gaz, text):
    assert values(extract(text, gaz), "flight_ref") == []


def test_service_alias_longest_first_no_overlap(gaz):
    ex = extract("accessible toilet terminal 2", gaz)
    assert values(ex, "service") == ["accessible toilet terminal 2"]
    assert values(ex, "terminal") == ["Terminal 2"]
    ex = extract("Skyline restaurant opening hours", gaz)
    assert [e.record_ids for e in ex.entities if e.type == "service"] == [("restaurant_skyline",)]


def test_time_and_deictic(gaz):
    ex = extract("Is the lounge open right now?", gaz)
    assert values(ex, "time") == ["right now"]
    assert values(ex, "service") == ["the lounge"]
    assert values(extract("Can you book me a taxi for 6pm?", gaz), "time") == ["6pm"]
    assert values(extract("What does this sign mean?", gaz), "deictic_ref") == ["this sign"]


def test_category_cues_outside_consumed_spans(gaz):
    ex = extract("Is there a lounge in Terminal 2?", gaz)
    assert ex.category_cues == [("lounge", "lounge")]
    ex = extract("I left my bag on the plane", gaz)
    assert sorted(c for _, c in ex.category_cues) == ["baggage", "lost_property"]


def test_as_json_dict_matches_seed_shape(gaz):
    assert extract("Where is belt 8?", gaz).as_json_dict() == {"belt_id": "BELT 8"}


def test_l1_only_mode(gaz):
    assert values(extract("gate bee twelve", gaz, domain_rules=False), "gate_id") == []
    assert values(extract("gate bee twelve", gaz, domain_rules=True), "gate_id") == ["B12"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))


# ---- QA 04.5 change 2: deictic phrases with a generic noun ----

@pytest.mark.parametrize("text,phrase", [
    ("What is this place used for?", "this place"),
    ("Can you tell me what these signs mean?", "these signs"),
    ("Where does that symbol lead?", "that symbol"),
    ("What do I do here?", "here"),
])
def test_deictic_phrase_with_generic_noun(gaz, text, phrase):
    ex = extract(text, gaz)
    assert values(ex, "deictic_ref") == [phrase]
    assert not ex.category_cues       # the generic noun is not read as a category cue


def test_deictic_does_not_fire_inside_a_time_phrase(gaz):
    ex = extract("is the cafe open this evening", gaz)
    assert values(ex, "deictic_ref") == [] and values(ex, "time") == ["this evening"]


def test_explicit_service_words_still_give_cues_next_to_a_deictic(gaz):
    ex = extract("what does this baggage sign mean", gaz)
    assert values(ex, "deictic_ref") == ["this"]
    assert ("baggage", "baggage") in ex.category_cues
