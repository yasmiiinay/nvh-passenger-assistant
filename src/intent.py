"""Intent by nearest labelled exemplar.

No classifier is trained. Each intent has a handful of authored example
phrasings (data/text/intent_exemplars.csv); a query takes the intent of
the exemplar it is most similar to. The matched exemplar is returned so
every prediction can be inspected and explained.
"""
from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

NO_INTENT = "none"


def load_exemplars(path: str | Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise ValueError(f"no exemplars in {path}")
    return rows


def predict_intent(query_vec: np.ndarray, exemplar_vecs: np.ndarray,
                   exemplars: list[dict], floor: float) -> dict:
    """Nearest exemplar wins. Below `floor` the query is treated as having no
    known intent, which is how out-of-scope requests reach the abstain path.
    The margin is measured against the best exemplar of a different intent."""
    sims = exemplar_vecs @ query_vec
    order = np.argsort(-sims)
    best = int(order[0])
    best_intent = exemplars[best]["intent"]
    runner_up_score = 0.0
    runner_up_intent = None
    for i in order[1:]:
        if exemplars[int(i)]["intent"] != best_intent:
            runner_up_score = float(sims[int(i)])
            runner_up_intent = exemplars[int(i)]["intent"]
            break
    score = float(sims[best])
    return {
        "intent": best_intent if score >= floor else NO_INTENT,
        "score": round(score, 4),
        "exemplar": exemplars[best]["exemplar"],
        "nearest_intent": best_intent,
        "runner_up_intent": runner_up_intent,
        "runner_up_score": round(runner_up_score, 4),
        "margin": round(score - runner_up_score, 4),
    }
