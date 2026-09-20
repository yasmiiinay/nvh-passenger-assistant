"""Exemplar file validity and nearest-exemplar prediction (no model needed)."""
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from configs.settings import SETTINGS
from src.foundation_audit import load_queries, load_vocabulary
from src.intent import NO_INTENT, load_exemplars, predict_intent
from src.normalizer import normalize


@pytest.fixture(scope="module")
def exemplars():
    return load_exemplars(SETTINGS.intent_exemplars_path)


def test_every_frozen_intent_has_5_to_8_exemplars(exemplars):
    vocabulary = load_vocabulary(SETTINGS.vocabulary_path)
    counts = Counter(e["intent"] for e in exemplars)
    assert set(counts) == set(vocabulary["intents"])
    assert all(5 <= n <= 8 for n in counts.values()), counts
    assert all(e["split"] == "dev" for e in exemplars)


def test_exemplars_do_not_copy_seed_queries(exemplars):
    seed = {normalize(q["query"]) for q in load_queries(SETTINGS.queries_seed_path)}
    copied = [e["exemplar"] for e in exemplars if normalize(e["exemplar"]) in seed]
    assert copied == []
    assert len({normalize(e["exemplar"]) for e in exemplars}) == len(exemplars)


def unit(v):
    v = np.asarray(v, dtype=np.float32)
    return v / np.linalg.norm(v)


def test_nearest_exemplar_and_margin_against_other_intent():
    rows = [{"intent": "a", "exemplar": "a1"}, {"intent": "a", "exemplar": "a2"},
            {"intent": "b", "exemplar": "b1"}]
    vecs = np.stack([unit([1, 0]), unit([0.9, 0.1]), unit([0, 1])])
    p = predict_intent(unit([1, 0.05]), vecs, rows, floor=0.0)
    assert p["intent"] == "a" and p["exemplar"] == "a1"
    assert p["runner_up_intent"] == "b"           # not the second 'a' exemplar
    assert p["margin"] == pytest.approx(p["score"] - p["runner_up_score"], abs=1e-3)   # rounded fields


def test_floor_gives_no_intent():
    rows = [{"intent": "a", "exemplar": "a1"}]
    vecs = np.stack([unit([1, 0])])
    assert predict_intent(unit([0, 1]), vecs, rows, floor=0.3)["intent"] == NO_INTENT
    assert predict_intent(unit([1, 0]), vecs, rows, floor=0.3)["intent"] == "a"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
