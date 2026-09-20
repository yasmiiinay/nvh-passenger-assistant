"""The speech metric definitions, exercised on hand-written string pairs.

These are NOT speech results: no audio exists yet. They prove that the two
WER levels and identifier-token accuracy compute what Evidence Pack A4
defines, so that the speech evaluation can drop real transcripts in without touching the
metric code."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from configs.settings import SETTINGS
from evaluation.speech_metrics import identifier_token_accuracy, propagation_gap, wer_l1, wer_l2
from src.entities import load_gazetteers

jiwer = pytest.importorskip("jiwer")

REFS = ["Where is gate B12?", "Check-in desks Terminal 2", "where is belt eight"]
HYPS = ["where is gate bee twelve", "check in desks t2", "where is belt 8"]


def test_l2_wer_never_exceeds_l1_on_domain_repairs():
    l1, l2 = wer_l1(REFS, HYPS), wer_l2(REFS, HYPS)
    assert l1["n_utterances"] == l2["n_utterances"] == 3
    assert l1["wer"] > 0.0          # 'bee twelve' and 't2' are errors at L1
    assert l2["wer"] == 0.0         # and repaired at L2
    assert wer_l1(REFS, REFS)["wer"] == 0.0


def test_wer_rejects_misaligned_or_empty_input():
    with pytest.raises(ValueError):
        wer_l1(["a"], ["a", "b"])
    with pytest.raises(ValueError):
        wer_l1(["?!"], ["anything"])


def test_identifier_token_accuracy_levels():
    gaz = load_gazetteers(SETTINGS.kb_path, SETTINGS.vocabulary_path)
    ids = [["B12"], [], ["BELT 8"]]
    l1 = identifier_token_accuracy(ids, HYPS, gaz, level="L1")
    l2 = identifier_token_accuracy(ids, HYPS, gaz, level="L2")
    assert l1["n"] == l2["n"] == 2          # the utterance without identifiers is excluded
    assert l1["accuracy"] == 0.5 and l1["errors"][0]["reference"] == ["B12"]
    assert l2["accuracy"] == 1.0 and l2["errors"] == []
    assert identifier_token_accuracy([[], []], ["x", "y"], gaz)["accuracy"] is None


def test_propagation_gap():
    assert propagation_gap(0.9, 0.7, 10)["gap"] == pytest.approx(0.2)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
