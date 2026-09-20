"""Unit tests for src/normalizer.py. Every case is a (in, out) pair so the
table doubles as the report's evidence that each rule does what it claims,
including the cases where a rule must NOT fire."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.normalizer import RULES, normalize, normalize_l1, normalize_l2, rule_table_markdown

L1_CASES = [
    ("Where is gate B12?", "where is gate b12"),
    ("Check-in desks Terminal 2", "check in desks terminal 2"),
    ("What's the wifi password?", "what is the wifi password"),
    ("I can't find belt 3", "i cannot find belt 3"),
    ("terminal two", "terminal 2"),
    ("desk one forty five", "desk 145"),
    ("desk one hundred and forty five", "desk 145"),
    ("belt eight", "belt 8"),
    ("twenty one", "21"),
    ("first aid", "first aid"),               # ordinal untouched
    ("one and two", "1 and 2"),               # 'and' is not a number joiner here
    ("gate  b12   please", "gate b12 please"),
    ("Gate B12 — Pier B", "gate b12 pier b"),
    ("", ""),
    (None, ""),
]

L2_CASES = [
    ("gate bee twelve", "gate b12"),
    ("gate be twelve", "gate b12"),           # 'be' only after a gate keyword
    ("it will be 12 minutes", "it will be 12 minutes"),
    ("I have a 12 o'clock flight", "i have a 12 oclock flight"),  # bare 'a' never collapses
    ("gate a 7", "gate a7"),
    ("Bravo 7", "b7"),
    ("B 12", "b12"),
    ("b-12", "b12"),
    ("T2 security", "terminal 2 security"),
    ("t 1 check-in", "terminal 1 check in"),
    ("terminal1", "terminal 1"),
    ("checkin desks", "check in desks"),
    ("wi fi password", "wifi password"),
    ("lost in found", "lost and found"),
    ("gait b12", "gate b12"),
    ("is the launch open", "is the lounge open"),
    ("nearest toilette", "nearest toilet"),
    ("where is desk145", "where is desk 145"),
    ("i parked in p 1", "i parked in p1"),          # observed: Whisper on aud_110
    ("where is disk 145", "where is desk 145"),      # observed: Whisper on aud_053
    ("a disk of 145 mm", "a disk of 145 mm"),        # only the desk-number shape is touched
    ("the p 12 bus", "the p 12 bus"),                # car parks have one digit
]

STOP_WORDS_MUST_SURVIVE = [
    "where is the gate", "how do i get to a7", "is there a lounge in terminal 2",
]


@pytest.mark.parametrize("text,expected", L1_CASES)
def test_l1(text, expected):
    assert normalize_l1(text) == expected


@pytest.mark.parametrize("text,expected", L2_CASES)
def test_l2(text, expected):
    assert normalize_l2(text) == expected


def test_pipeline_entry_is_l1_then_l2():
    assert normalize("Gate Bee Twelve, T1") == "gate b12 terminal 1"


@pytest.mark.parametrize("text", STOP_WORDS_MUST_SURVIVE)
def test_no_stop_word_removal(text):
    assert normalize(text).split() == text.split()


def test_idempotent():
    for text, _ in L1_CASES + L2_CASES:
        once = normalize(text)
        assert normalize(once) == once


def test_rule_table_lists_every_rule():
    table = rule_table_markdown()
    for rule in RULES:
        assert f"`{rule.name}`" in table
        assert rule.provenance in ("design", "anticipated", "observed")


def test_rule_examples_hold():
    """Each rule's documented example must actually be produced by that rule."""
    for rule in RULES:
        assert rule.apply(rule.example_in) == rule.example_out, rule.name


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
