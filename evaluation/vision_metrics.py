"""Vision pipeline metrics (RQ1). Pure aggregation; predictions arrive in the pipeline phase."""
from __future__ import annotations
from collections import Counter


def top_k_accuracy(gold: list[str], ranked_predictions: list[list[str]], k: int) -> dict:
    """gold[i] is the true label; ranked_predictions[i] is the ranked label list."""
    if len(gold) != len(ranked_predictions):
        raise ValueError("gold and predictions must align")
    hits = sum(1 for g, ranked in zip(gold, ranked_predictions) if g in ranked[:k])
    return {"k": k, "n": len(gold), "accuracy": hits / len(gold) if gold else 0.0}


def confusion_counts(gold: list[str], top1: list[str]) -> dict:
    """Sparse confusion matrix as {(gold, predicted): count}; CSV-ready."""
    return {"pairs": Counter(zip(gold, top1)), "n": len(gold)}


def score_distribution(scores: list[float], correct: list[bool]) -> dict:
    """Similarity scores split by correctness, for the RQ1 distribution plot."""
    return {
        "correct_scores": [s for s, c in zip(scores, correct) if c],
        "incorrect_scores": [s for s, c in zip(scores, correct) if not c],
    }


def oos_anchor_abstention(in_scope_abstained: list[bool], oos_abstained: list[bool]) -> dict:
    """Anchor ablation table: abstention rate on in-scope vs out-of-scope images.

    Run once with anchors enabled and once disabled; the two dicts form the
    ablation table (v1.1 4.1).
    """
    def rate(flags): return sum(flags) / len(flags) if flags else 0.0
    return {"false_abstain_rate_in_scope": rate(in_scope_abstained),
            "abstain_rate_out_of_scope": rate(oos_abstained),
            "n_in_scope": len(in_scope_abstained), "n_oos": len(oos_abstained)}


def write_artifacts(*args, **kwargs):
    raise NotImplementedError("TODO(evaluation phase): persist tables to outputs/evaluation/vision/")
