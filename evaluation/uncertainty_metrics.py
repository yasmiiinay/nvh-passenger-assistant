"""Uncertainty/abstention metrics (RQ4). Final metric set frozen in Evidence
Pack section A7: abstention P/R, risk-coverage, threshold sensitivity,
dev-vs-heldout gap, accuracy per match-score band. Deliberately NO reliability
diagram and NO calibration (see A7 for the argument)."""
from __future__ import annotations


def abstention_precision_recall(should_abstain: list[bool], did_abstain: list[bool]) -> dict:
    tp = sum(1 for s, d in zip(should_abstain, did_abstain) if s and d)
    fp = sum(1 for s, d in zip(should_abstain, did_abstain) if not s and d)
    fn = sum(1 for s, d in zip(should_abstain, did_abstain) if s and not d)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    return {"precision": precision, "recall": recall, "tp": tp, "fp": fp, "fn": fn,
            "n": len(should_abstain)}


def risk_coverage_curve(scores: list[float], correct: list[bool],
                        thresholds: list[float]) -> list[dict]:
    """Selective-prediction curve (Geifman & El-Yaniv 2017): for each threshold,
    coverage = share answered (score >= t), risk = error rate among answered."""
    curve = []
    n = len(scores)
    for t in thresholds:
        answered = [(s, c) for s, c in zip(scores, correct) if s >= t]
        coverage = len(answered) / n if n else 0.0
        risk = (sum(1 for _, c in answered if not c) / len(answered)) if answered else 0.0
        curve.append({"threshold": t, "coverage": coverage, "risk": risk,
                      "n_answered": len(answered)})
    return curve


def band_table(scores: list[float], correct: list[bool],
               tau_low: float, tau_high: float) -> dict:
    """Accuracy/error per match-score band, the table that replaced the
    reliability diagram (Evidence Pack A7). Band edges are the operational
    thresholds, so the label and the behaviour cannot drift apart."""
    bands = {"strong": [], "uncertain": [], "abstain": []}
    for s, c in zip(scores, correct):
        key = "strong" if s >= tau_high else ("uncertain" if s >= tau_low else "abstain")
        bands[key].append(c)
    return {band: {"n": len(items),
                   "accuracy": (sum(items) / len(items)) if items else None,
                   "error_rate": (1 - sum(items) / len(items)) if items else None}
            for band, items in bands.items()}


def dev_heldout_gap(dev_metric: float, heldout_metric: float, name: str) -> dict:
    return {"metric": name, "dev": dev_metric, "heldout": heldout_metric,
            "gap": dev_metric - heldout_metric}


def threshold_sensitivity(scores: list[float], correct: list[bool],
                          grid: list[float]) -> list[dict]:
    """Coarse-grid sensitivity (v1.1: report sensitivity, never an 'optimum')."""
    return risk_coverage_curve(scores, correct, grid)


def write_artifacts(*args, **kwargs):
    raise NotImplementedError("TODO(evaluation phase): persist to outputs/evaluation/uncertainty/")
