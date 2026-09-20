"""Run the deterministic retrieval stages over the seed query set and record
what they decide, what they hand on, and where they are wrong.

Checkpoint 03.1 evidence. No model is loaded. Writes to outputs/checkpoint_03_1/:
  seed_results.csv        one row per query: stage, decision, record, verdict
  stage_counts.csv        how often each stage produced the final decision
  category_cues.csv       the derived cue table (token -> category)
  normaliser_rules.csv    the rule table (also printable as markdown)
  summary.json            the counts quoted in the checkpoint report

Verdicts:
  correct              deterministic decision matches the seed expectation
  wrong                deterministic stage decided, and the decision or the
                       record differs from the seed expectation (a false
                       resolution, the failure class this stage must avoid)
  handed_to_semantic   not decided here; by design for paraphrase/vague/
                       out-of-scope queries, not counted as a failure
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from configs.settings import SETTINGS
from evaluation.retrieval_metrics import decision_rates, judge_outcome, stage_firing_counts
from src.entities import load_gazetteers
from src.foundation_audit import load_queries
from src.normalizer import rule_table_markdown, rule_table_rows
from src.retrieval import resolve_deterministic

DIFFICULT = ["q009", "q013", "q015", "q019", "q023", "q036", "q041", "q042", "q043"]


def verdict(row: dict, result, gaz) -> tuple[str, str]:
    target = row["target_kb_id"] or None
    expected = row["expected_behaviour"]
    if not result.resolved:
        hints = result.handoff
        target_cat = None
        if target:
            target_cat = gaz.records[target]["category"]
        note = []
        if target and target in hints.get("candidates", []):
            note.append("target in candidates")
        if hints.get("category_hints"):
            if target_cat:
                note.append("hint " + ("matches" if target_cat in hints["category_hints"] else "misses")
                            + f" target category ({target_cat})")
            else:
                note.append(f"hints {hints['category_hints']} (no target record; expected {expected})")
        return "handed_to_semantic", "; ".join(note) or "no hints"
    return judge_outcome(expected, target, result.decision, result.matched_record_id,
                         result.candidates, result.flags)


if __name__ == "__main__":
    out_dir = SETTINGS.outputs_dir / "checkpoint_03_1"
    out_dir.mkdir(parents=True, exist_ok=True)
    gaz = load_gazetteers(SETTINGS.kb_path, SETTINGS.vocabulary_path)
    queries = load_queries(SETTINGS.queries_seed_path)

    rows, results = [], []
    for q in queries:
        r = resolve_deterministic(q["query"], gaz)
        v, detail = verdict(q, r, gaz)
        results.append(r)
        rows.append({
            "query_id": q["query_id"], "query": q["query"], "normalized": r.normalized,
            "query_type": q["query_type"], "expected_behaviour": q["expected_behaviour"],
            "target_kb_id": q["target_kb_id"], "entities": json.dumps(r.entities),
            "stage": r.stage or "", "decision": r.decision or "",
            "matched_record_id": r.matched_record_id or "",
            "candidates": "|".join(r.candidates), "flags": "|".join(r.flags),
            "reason": r.reason, "handoff": json.dumps(r.handoff) if r.handoff else "",
            "verdict": v, "verdict_detail": detail,
        })

    with open(out_dir / "seed_results.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    resolved = [r for r in results if r.resolved]
    stages = stage_firing_counts([r.stage for r in resolved])
    decisions = decision_rates([r.decision for r in resolved])
    verdicts = Counter(row["verdict"] for row in rows)
    with open(out_dir / "stage_counts.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["stage", "count"])
        for stage, n in sorted(stages.items()):
            w.writerow([stage, n])
        w.writerow(["unresolved (semantic workload)", len(results) - len(resolved)])
    with open(out_dir / "category_cues.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["token", "category"])
        w.writeheader()
        w.writerows(gaz.cue_table_rows())
    with open(out_dir / "normaliser_rules.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["name", "level", "provenance", "example_in", "example_out"])
        w.writeheader()
        w.writerows(rule_table_rows())
    (out_dir / "normaliser_rules.md").write_text(rule_table_markdown() + "\n", encoding="utf-8")

    summary = {
        "n_queries": len(results), "n_resolved": len(resolved),
        "n_unresolved": len(results) - len(resolved),
        "stage_counts": stages, "decision_rates": decisions, "verdicts": dict(verdicts),
        "unresolved_ids": [row["query_id"] for row in rows if row["verdict"] == "handed_to_semantic"],
        "wrong_ids": [row["query_id"] for row in rows if row["verdict"] == "wrong"],
        "gazetteer_sizes": {"identifiers": len(gaz.identifier_index), "aliases": len(gaz.alias_index),
                            "volatile_phrases": len(gaz.volatile_phrases),
                            "category_cues": len(gaz.category_cues)},
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"{'id':5} {'stage':17} {'decision':9} {'record':24} {'verdict':19} detail")
    for row in rows:
        print(f"{row['query_id']:5} {row['stage'] or '-':17} {row['decision'] or '-':9} "
              f"{row['matched_record_id'] or '-':24} {row['verdict']:19} {row['verdict_detail']}")
    print("\nstage counts:", stages)
    print("decision rates:", {k: v for k, v in decisions.items() if k != 'n'})
    print("verdicts:", dict(verdicts))
    print("\nDIFFICULT CASES")
    for row in rows:
        if row["query_id"] in DIFFICULT:
            print(f"- {row['query_id']} {row['query']!r}\n    stage={row['stage'] or 'unresolved'} "
                  f"decision={row['decision'] or '-'} record={row['matched_record_id'] or '-'} "
                  f"flags={row['flags'] or '-'}\n    reason: {row['reason']}\n    verdict: {row['verdict']} "
                  f"{row['verdict_detail']} {row['handoff']}")
    print(f"\nwritten to {out_dir}")
