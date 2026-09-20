"""Text/intent/entity metrics. sklearn is a dev-only dependency by design."""
from __future__ import annotations
from collections import Counter


def intent_prf(gold: list[str], predicted: list[str]) -> dict:
    """Per-intent precision/recall/F1 + macro average (dev-only sklearn)."""
    from sklearn.metrics import precision_recall_fscore_support  # dev dep
    labels = sorted(set(gold) | set(predicted))
    p, r, f, s = precision_recall_fscore_support(gold, predicted, labels=labels, zero_division=0)
    per_label = {lab: {"precision": float(pi), "recall": float(ri), "f1": float(fi), "support": int(si)}
                 for lab, pi, ri, fi, si in zip(labels, p, r, f, s)}
    macro_f1 = sum(v["f1"] for v in per_label.values()) / len(per_label) if per_label else 0.0
    return {"per_intent": per_label, "macro_f1": macro_f1, "n": len(gold)}


def intent_confusion(gold: list[str], predicted: list[str]) -> dict:
    return {"pairs": Counter(zip(gold, predicted)), "n": len(gold)}


def entity_extraction_accuracy(gold_entities: list[dict], predicted_entities: list[dict]) -> dict:
    """Exact-match per entity field, micro-averaged. Pure comparison; runnable
    as soon as the extractor exists (pipeline phase)."""
    total = correct = 0
    for g, p in zip(gold_entities, predicted_entities):
        for key, value in g.items():
            total += 1
            correct += int(p.get(key) == value)
    return {"micro_accuracy": correct / total if total else 0.0, "n_fields": total}


def write_artifacts(*args, **kwargs):
    raise NotImplementedError("TODO(evaluation phase): persist to outputs/evaluation/text/")
