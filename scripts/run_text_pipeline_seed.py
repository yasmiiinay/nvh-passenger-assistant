"""Evaluate the full text cascade (deterministic + semantic) on a query set.

Checkpoint 03.2 evidence. Loads MiniLM once, encodes every query once, then
reuses the vectors for every experiment below. `--set dev` (default) runs
the 43 seed queries and also the threshold grid and the category-cue
experiment; `--set heldout` runs the frozen held-out file with the same
thresholds and no tuning of any kind. Writes to outputs/checkpoint_03_2/
(dev) or outputs/checkpoint_03_2/heldout/:

  intent_results.csv      predicted vs gold intent per query, with the matched exemplar
  intent_report.json      precision / recall / F1 per intent, macro F1, confusion pairs
  baseline_tfidf_lr.json  TF-IDF + logistic regression on the same exemplars and queries
  cascade_results.csv     one row per query: stage, decision, record, score, margin, verdict
  cascade_summary.json    stage counts, decision counts, accuracy by query type,
                          deterministic-only vs full pipeline
  threshold_grid.csv      correct decisions on the 21 unresolved queries per setting
  cue_experiment.csv      intent filter vs lexical cue filter vs whole KB

Thresholds come from configs/settings.py in both modes.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from itertools import product
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from configs.settings import SETTINGS
from evaluation.retrieval_metrics import (clarify_type, decision_rates, judge_outcome, outcome_accuracy_by_type,
                                          retrieval_accuracy_by_type, stage_firing_counts)
from evaluation.text_metrics import intent_confusion, intent_prf
from src.entities import load_gazetteers
from src.foundation_audit import load_queries
from src.intent import NO_INTENT, predict_intent
from src.retrieval import build_text_index, resolve_deterministic, resolve_semantic
from src.text_encoder import encode

DIFFICULT = ["q009", "q013", "q015", "q017", "q026", "q027", "q031", "q034",
             "q037", "q038", "q039", "q040", "q043"]

# coarse, explainable grid; each value is a round number on the cosine scale
GRID = {
    "tau_high": [0.40, 0.45, 0.50, 0.55],
    "tau_low": [0.20, 0.25, 0.30],
    "margin_delta": [0.03, 0.05, 0.10],
}
TAU_INTENT_GRID = [0.0, 0.30, 0.40, 0.50]


def write_csv(path: Path, rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run_cascade(queries, vectors, gaz, index, thresholds, filter_mode="intent"):
    """Deterministic first; semantic only for the unresolved ones."""
    results = []
    for q, vec in zip(queries, vectors):
        r = resolve_deterministic(q["query"], gaz)
        if not r.resolved:
            r = resolve_semantic(r, gaz, index, thresholds, filter_mode, query_vec=vec)
        results.append(r)
    return results


def count_correct(queries, results, only_ids=None) -> int:
    n = 0
    for q, r in zip(queries, results):
        if only_ids is not None and q["query_id"] not in only_ids:
            continue
        verdict, _ = judge_outcome(q["expected_behaviour"], q["target_kb_id"] or None,
                                   r.decision, r.matched_record_id, r.candidates, r.flags)
        n += verdict == "correct"
    return n


def intent_evaluation(queries, vectors, index, tau_intent):
    gold, predicted, rows = [], [], []
    for q, vec in zip(queries, vectors):
        p = predict_intent(vec, index.exemplar_vecs, index.exemplars, tau_intent)
        gold.append(q["intent"])
        predicted.append(p["intent"])
        rows.append({"query_id": q["query_id"], "query": q["query"], "gold_intent": q["intent"],
                     "predicted_intent": p["intent"], "score": p["score"], "margin": p["margin"],
                     "matched_exemplar": p["exemplar"], "runner_up_intent": p["runner_up_intent"],
                     "correct": q["intent"] == p["intent"]})
    report = intent_prf(gold, predicted)
    confusion = intent_confusion(gold, predicted)
    report["confusions"] = [{"gold": g, "predicted": p, "count": c}
                            for (g, p), c in sorted(confusion["pairs"].items()) if g != p]
    report["accuracy"] = sum(r["correct"] for r in rows) / len(rows)
    report["tau_intent"] = tau_intent
    return rows, report


def tfidf_baseline(index, queries):
    """TF-IDF + logistic regression trained on the exemplars only, scored on
    the 40 seed queries that have one of the 15 intents. The baseline cannot
    say "none", so the three out-of-scope queries are excluded for both
    methods in this comparison."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from src.normalizer import normalize
    train_x = [normalize(e["exemplar"]) for e in index.exemplars]
    train_y = [e["intent"] for e in index.exemplars]
    scored = [q for q in queries if q["intent"] != NO_INTENT]
    vectoriser = TfidfVectorizer(ngram_range=(1, 2), min_df=1)
    clf = LogisticRegression(max_iter=1000, C=10.0, random_state=SETTINGS.seed)
    clf.fit(vectoriser.fit_transform(train_x), train_y)
    predicted = list(clf.predict(vectoriser.transform([normalize(q["query"]) for q in scored])))
    gold = [q["intent"] for q in scored]
    return {"n": len(scored), "accuracy": sum(g == p for g, p in zip(gold, predicted)) / len(gold),
            "macro_f1": intent_prf(gold, predicted)["macro_f1"],
            "features": "tf-idf word 1-2 grams over normalised text",
            "classifier": "logistic regression, C=10, max_iter=1000"}


def minilm_on_same_split(queries, vectors, index):
    scored = [(q, v) for q, v in zip(queries, vectors) if q["intent"] != NO_INTENT]
    gold = [q["intent"] for q, _ in scored]
    predicted = [predict_intent(v, index.exemplar_vecs, index.exemplars, 0.0)["intent"] for _, v in scored]
    return {"n": len(gold), "accuracy": sum(g == p for g, p in zip(gold, predicted)) / len(gold),
            "macro_f1": intent_prf(gold, predicted)["macro_f1"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--set", choices=["dev", "heldout"], default="dev")
    args = parser.parse_args()
    tuning = args.set == "dev"
    OUT_DIR = SETTINGS.outputs_dir / "checkpoint_03_2" / ("" if tuning else "heldout")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    gaz = load_gazetteers(SETTINGS.kb_path, SETTINGS.vocabulary_path)
    index = build_text_index(gaz, SETTINGS.intent_exemplars_path)
    queries = load_queries(SETTINGS.queries_seed_path if tuning else SETTINGS.queries_heldout_path)
    vectors = encode([resolve_deterministic(q["query"], gaz).normalized for q in queries])
    thresholds = SETTINGS.thresholds()

    # ---- intent ----
    intent_rows, intent_report = intent_evaluation(queries, vectors, index, thresholds["tau_intent"])
    intent_report["tau_intent_sweep"] = [
        {"tau_intent": t, "accuracy_43": intent_evaluation(queries, vectors, index, t)[1]["accuracy"]}
        for t in TAU_INTENT_GRID]
    write_csv(OUT_DIR / "intent_results.csv", intent_rows)
    (OUT_DIR / "intent_report.json").write_text(json.dumps(intent_report, indent=2), encoding="utf-8")

    # ---- baseline on the same split ----
    baseline = {"tfidf_lr": tfidf_baseline(index, queries),
                "minilm_nearest_exemplar": minilm_on_same_split(queries, vectors, index)}
    (OUT_DIR / "baseline_tfidf_lr.json").write_text(json.dumps(baseline, indent=2), encoding="utf-8")

    # ---- full cascade with the chosen thresholds ----
    results = run_cascade(queries, vectors, gaz, index, thresholds)
    rows = []
    for q, r in zip(queries, results):
        verdict, detail = judge_outcome(q["expected_behaviour"], q["target_kb_id"] or None,
                                        r.decision, r.matched_record_id, r.candidates, r.flags)
        rows.append({"query_id": q["query_id"], "query": q["query"], "query_type": q["query_type"],
                     "expected_behaviour": q["expected_behaviour"], "target_kb_id": q["target_kb_id"],
                     "stage": r.stage, "decision": r.decision, "matched_record_id": r.matched_record_id or "",
                     "candidates": "|".join(r.candidates),
                     "clarify_type": clarify_type(r.decision, r.clarification_field, r.candidates, r.flags) or "",
                     "intent": r.intent or "",
                     "intent_score": r.intent_score if r.intent_score is not None else "",
                     "match_score": r.match_score if r.match_score is not None else "",
                     "margin": r.margin if r.margin is not None else "",
                     "flags": "|".join(r.flags), "reason": r.reason,
                     "verdict": verdict, "verdict_detail": detail})
    write_csv(OUT_DIR / "cascade_results.csv", rows)

    deterministic_only = [resolve_deterministic(q["query"], gaz) for q in queries]
    unresolved_ids = {q["query_id"] for q, r in zip(queries, deterministic_only) if not r.resolved}
    semantic_rows = [row for row in rows if row["query_id"] in unresolved_ids]
    summary = {
        "thresholds": thresholds,
        "stage_counts": stage_firing_counts([r.stage for r in results]),
        "decision_counts": {k: v for k, v in decision_rates([r.decision for r in results]).items() if k != "n"},
        "semantic_stage_decisions": dict(Counter(row["decision"] for row in semantic_rows)),
        "verdicts_all": dict(Counter(row["verdict"] for row in rows)),
        "clarify_types": dict(Counter(row["clarify_type"] for row in rows if row["clarify_type"])),
        "verdicts_semantic_workload": dict(Counter(row["verdict"] for row in semantic_rows)),
        "record_accuracy_by_query_type": retrieval_accuracy_by_type(
            [q["query_type"] for q in queries], [q["target_kb_id"] for q in queries],
            [r.matched_record_id or "" for r in results]),
        "outcome_accuracy_by_query_type": outcome_accuracy_by_type(
            [q["query_type"] for q in queries], [row["verdict"] for row in rows]),
        "deterministic_only_correct": count_correct(queries, deterministic_only),
        "full_pipeline_correct": count_correct(queries, results),
        "n_queries": len(queries), "query_set": args.set,
        "n_semantic_workload": len(unresolved_ids),
        "wrong_record_answers": sum(1 for row in rows if row["decision"] == "answer"
                                    and row["matched_record_id"]
                                    and row["matched_record_id"] != row["target_kb_id"]),
        "out_of_scope_answers": [row["query_id"] for row in rows
                                 if row["query_type"] == "out_of_scope" and row["decision"] == "answer"],
        "grounded_negative_answers": [row["query_id"] for row in rows
                                      if row["decision"] == "answer" and "grounded_negative" in row["flags"]],
        "semantic_failures": [{"query_id": row["query_id"], "decision": row["decision"],
                               "matched": row["matched_record_id"], "detail": row["verdict_detail"]}
                              for row in semantic_rows if row["verdict"] != "correct"],
    }
    (OUT_DIR / "cascade_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    # ---- threshold sensitivity (dev split only) ----
    grid_rows = []
    for tau_high, tau_low, margin_delta in (product(*GRID.values()) if tuning else []):
        if tau_low >= tau_high:
            continue
        trial = dict(thresholds, tau_high=tau_high, tau_low=tau_low, margin_delta=margin_delta)
        trial_results = run_cascade(queries, vectors, gaz, index, trial)
        decisions = Counter(r.decision for q, r in zip(queries, trial_results) if q["query_id"] in unresolved_ids)
        grid_rows.append({"tau_high": tau_high, "tau_low": tau_low, "margin_delta": margin_delta,
                          "correct_of_unresolved": count_correct(queries, trial_results, unresolved_ids),
                          "answer": decisions["answer"], "clarify": decisions["clarify"],
                          "abstain": decisions["abstain"], "redirect": decisions["redirect"],
                          "wrong_record_answers": sum(
                              1 for q, r in zip(queries, trial_results)
                              if q["query_id"] in unresolved_ids and r.decision == "answer"
                              and r.matched_record_id != (q["target_kb_id"] or None))})
    if grid_rows:
        write_csv(OUT_DIR / "threshold_grid.csv", grid_rows)

    # ---- category cues: intent filter (frozen) vs cue filter vs no filter ----
    cue_rows = []
    for mode in (("intent", "cues", "none") if tuning else ()):
        mode_results = run_cascade(queries, vectors, gaz, index, thresholds, filter_mode=mode)
        top1_hits = sum(1 for q, r in zip(queries, mode_results)
                        if q["query_id"] in unresolved_ids and q["target_kb_id"]
                        and r.ranked and r.ranked[0][0] == q["target_kb_id"])
        cue_rows.append({"filter_mode": mode,
                         "correct_of_unresolved": count_correct(queries, mode_results, unresolved_ids),
                         "top1_is_target": top1_hits,
                         "q015_top1": next(r.ranked[0][0] if r.ranked else "" for q, r in zip(queries, mode_results)
                                           if q["query_id"] == "q015")})
    if cue_rows:
        write_csv(OUT_DIR / "cue_experiment.csv", cue_rows)

    # ---- console ----
    print(f"intent: accuracy {intent_report['accuracy']:.3f}  macro F1 {intent_report['macro_f1']:.3f}  "
          f"(tau_intent {thresholds['tau_intent']})")
    for c in intent_report["confusions"]:
        print(f"  confusion {c['gold']} -> {c['predicted']} x{c['count']}")
    print("baseline:", json.dumps(baseline))
    print("\nstage counts:", summary["stage_counts"])
    print("decisions:", summary["decision_counts"])
    print("verdicts all:", summary["verdicts_all"], " semantic workload:", summary["verdicts_semantic_workload"])
    print(f"deterministic-only correct {summary['deterministic_only_correct']}/{len(queries)}, "
          f"full pipeline correct {summary['full_pipeline_correct']}/{len(queries)}")
    print("\nsemantic workload:")
    for row in semantic_rows:
        print(f"  {row['query_id']} {row['stage']:25} {row['decision']:8} {row['matched_record_id'] or '-':24} "
              f"s={row['match_score'] or '-'} m={row['margin'] or '-'} intent={row['intent']} "
              f"{row['verdict']} {row['verdict_detail']}")
    print("\ncue experiment:")
    for row in cue_rows:
        print(" ", row)
    print("\nthreshold grid (top 6):")
    for row in sorted(grid_rows, key=lambda r: (-r["correct_of_unresolved"], r["wrong_record_answers"]))[:6]:
        print(" ", row)
    print(f"\nwritten to {OUT_DIR}")
