"""Text-only regression queries (data/text/queries_qa.csv, split `regression`).

These sentences were written after a defect was seen, with their expected
outcome and flags recorded before the run; they are neither development nor
held-out evidence. Each row is judged like the seed set, and its
`expected_flags` (|-separated; a leading ! means the flag must be absent)
are checked separately so that a rule can be shown to fire, or not, on the
case it was written for.

Writes outputs/checkpoint_03_2/regression/cascade_results.csv and summary.json.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from configs.settings import SETTINGS
from evaluation.retrieval_metrics import clarify_type, judge_outcome
from src.entities import load_gazetteers
from src.foundation_audit import load_queries
from src.retrieval import build_text_index, resolve

OUT_DIR = SETTINGS.outputs_dir / "checkpoint_03_2" / "regression"


def flags_ok(expected: str, flags: list[str]) -> bool | str:
    if not expected:
        return ""
    for item in expected.split("|"):
        present = item.lstrip("!") in flags
        if item.startswith("!") == present:
            return False
    return True


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    gaz = load_gazetteers(SETTINGS.kb_path, SETTINGS.vocabulary_path)
    index = build_text_index(gaz, SETTINGS.intent_exemplars_path)
    queries = [q for q in load_queries(SETTINGS.queries_qa_path) if q["split"] == "regression"]
    rows = []
    for q in queries:
        r = resolve(q["query"], gaz, index, SETTINGS.thresholds())
        verdict, detail = judge_outcome(q["expected_behaviour"], q["target_kb_id"] or None,
                                        r.decision, r.matched_record_id, r.candidates, r.flags)
        rows.append({"query_id": q["query_id"], "query": q["query"], "expected_behaviour": q["expected_behaviour"],
                     "target_kb_id": q["target_kb_id"], "stage": r.stage, "decision": r.decision,
                     "matched_record_id": r.matched_record_id or "", "candidates": "|".join(r.candidates),
                     "clarify_type": clarify_type(r.decision, r.clarification_field, r.candidates, r.flags) or "",
                     "flags": "|".join(r.flags), "expected_flags": q.get("expected_flags", ""),
                     "flags_ok": flags_ok(q.get("expected_flags", ""), r.flags),
                     "verdict": verdict, "verdict_detail": detail, "reason": r.reason})
        print(f"{q['query_id']} {r.decision:8s} {(r.matched_record_id or '-'):20s} {verdict:8s} flags_ok={rows[-1]['flags_ok']}")
    with open(OUT_DIR / "cascade_results.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    summary = {"n": len(rows), "verdicts": dict(Counter(r["verdict"] for r in rows)),
               "flag_checks": {"n": sum(1 for r in rows if r["expected_flags"]),
                               "ok": sum(1 for r in rows if r["flags_ok"] is True)},
               "grounded_negative_answers": [r["query_id"] for r in rows if "grounded_negative" in r["flags"]]}
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("written to", OUT_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
