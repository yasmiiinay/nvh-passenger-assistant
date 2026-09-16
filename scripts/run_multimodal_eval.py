"""End-to-end multimodal evaluation on data/multimodal/multimodal_manifest.csv.

Every scenario is routed through src.router.route with the real modality
pipelines (typed text, image file, audio file). Expectations were written
into the manifest before the first run and are not edited afterwards.

The `regression` split holds scenarios written after a defect was seen in
the interface (Chat 04 QA); they are not development or held-out evidence
and are reported on their own.

Writes to outputs/checkpoint_03_4/multimodal/<split>[_confirm]/:
  per_scenario.csv   expected vs observed route, decision, record, conflict,
                     verdict, single-modality outcomes, latency
  summary.json       routing accuracy, verdict rates (wrong-confident and
                     over-cautious kept apart), conflict detection precision
                     and recall, per scenario type, modality contribution

--confirm-image-only evaluates the conservative variant in which an image
alone never answers, only asks for confirmation (checkpoint 03.4 section B).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from configs.settings import SETTINGS
from evaluation.multimodal_metrics import conflict_detection, judge_scenario, rates
from evaluation.retrieval_metrics import clarify_type
from src.entities import load_gazetteers
from src.foundation_audit import load_queries
from src.retrieval import build_text_index
from src.router import apply_rules, build_context, image_evidence, route, speech_evidence, text_evidence

DATA = SETTINGS.kb_path.parents[1]
OUT_ROOT = SETTINGS.outputs_dir / "checkpoint_03_4" / "multimodal"


def load_rows(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["dev", "heldout", "regression", "all"], default="dev")
    parser.add_argument("--confirm-image-only", action="store_true")
    args = parser.parse_args()
    out_dir = OUT_ROOT / (args.split + ("_confirm" if args.confirm_image_only else ""))
    out_dir.mkdir(parents=True, exist_ok=True)

    scenarios = [r for r in load_rows(DATA / "multimodal" / "multimodal_manifest.csv")
                 if args.split in ("all", r["split"])]
    queries = {q["query_id"]: q["query"] for path in (SETTINGS.queries_seed_path, SETTINGS.queries_heldout_path,
                                                      SETTINGS.queries_spoken_path, SETTINGS.queries_qa_path)
               for q in load_queries(path)}
    images = {r["image_id"]: r["file"] for r in load_rows(DATA / "images" / "images_manifest.csv")}
    audio = {r["audio_id"]: r["file"] for r in load_rows(DATA / "audio" / "audio_manifest.csv")
             + load_rows(DATA / "audio" / "derived_manifest.csv")}

    gaz = load_gazetteers(SETTINGS.kb_path, SETTINGS.vocabulary_path)
    ctx = build_context(gaz, build_text_index(gaz, SETTINGS.intent_exemplars_path),
                        confirm_image_only_answers=args.confirm_image_only)
    # warm the models so per-scenario latency measures the turn, not the first load
    text_evidence("where is gate b12", ctx)
    image_evidence(DATA / "images" / images["img_001"], ctx)
    speech_evidence(DATA / "audio" / audio["aud_025"], ctx)

    results = []
    for sc in scenarios:
        text = queries.get(sc["query_id"]) if sc["query_id"] else None
        image_path = DATA / "images" / images[sc["image_id"]] if sc["image_id"] else None
        audio_path = DATA / "audio" / audio[sc["audio_id"]] if sc["audio_id"] else None
        start = time.perf_counter()
        out = route(text, image_path, audio_path, ctx)
        latency = time.perf_counter() - start
        cand_cats = {gaz.records[rid]["category"] for rid in out.candidates if rid in gaz.records}
        if out.matched_record_id:
            cand_cats.add(gaz.records[out.matched_record_id]["category"])
        verdict = judge_scenario(sc["expected_decision"], sc["target_kb_id"], sc["target_category"],
                                 sc["expected_conflict"] == "true", out.decision, out.matched_record_id,
                                 cand_cats, out.conflict)
        # what each modality would have done alone (contribution analysis)
        alone = {}
        if text and sc["image_id"]:
            t = apply_rules(out.text, None, None, ctx)
            alone["text_alone"] = judge_scenario(sc["expected_decision"], sc["target_kb_id"], sc["target_category"], False,
                                                 t.decision, t.matched_record_id,
                                                 {gaz.records[r]["category"] for r in t.candidates}, False)
        if out.vision is not None and (text or sc["audio_id"]):
            v = apply_rules(None, out.vision, None, ctx)
            vc = {gaz.records[r]["category"] for r in v.candidates}
            if v.matched_record_id:
                vc.add(gaz.records[v.matched_record_id]["category"])
            alone["image_alone"] = judge_scenario(sc["expected_decision"], sc["target_kb_id"], sc["target_category"], False,
                                                  v.decision, v.matched_record_id, vc, False)
        results.append({
            "sample_id": sc["sample_id"], "scenario_type": sc["scenario_type"], "split": sc["split"],
            "expected_route": sc["expected_route"], "route": out.route, "route_ok": out.route == sc["expected_route"],
            "expected_decision": sc["expected_decision"], "decision": out.decision,
            "target_kb_id": sc["target_kb_id"], "record_id": out.matched_record_id or "",
            "candidates": "|".join(out.candidates), "expected_conflict": sc["expected_conflict"] == "true",
            "clarify_type": clarify_type(out.decision, out.clarification_field, out.candidates, out.flags) or "",
            "expected_clarification_field": sc.get("expected_clarification_field", ""),
            "clarification_field_ok": ((out.clarification_field or "none") == sc["expected_clarification_field"]
                                       if sc.get("expected_clarification_field") else ""),
            "conflict": out.conflict, "band": out.band or "", "score": out.score if out.score is not None else "",
            "verdict": verdict, "text_alone": alone.get("text_alone", ""), "image_alone": alone.get("image_alone", ""),
            "transcript": out.speech.transcript_raw if out.speech is not None and out.speech.transcript_raw else "",
            "flags": "|".join(out.flags), "reason": out.reason, "error": out.error or "",
            "latency_s": round(latency, 3),
        })
        print(f"{sc['sample_id']} {sc['scenario_type']:24s} {out.route:12s} {out.decision:9s} "
              f"{(out.matched_record_id or ''):22s} {verdict}")

    with open(out_dir / "per_scenario.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)

    verdicts = [r["verdict"] for r in results]
    by_type = defaultdict(list)
    for r in results:
        by_type[r["scenario_type"]].append(r["verdict"])
    combined = [r for r in results if r["text_alone"] or r["image_alone"]]
    contribution = {
        "n_combined": len(combined),
        "combined_correct": sum(r["verdict"] == "correct" for r in combined),
        "text_alone_correct": sum(r["text_alone"] == "correct" for r in combined if r["text_alone"]),
        "text_alone_n": sum(1 for r in combined if r["text_alone"]),
        "image_alone_correct": sum(r["image_alone"] == "correct" for r in combined if r["image_alone"]),
        "image_alone_n": sum(1 for r in combined if r["image_alone"]),
        "rescued_by_combination": [r["sample_id"] for r in combined if r["verdict"] == "correct"
                                   and r["text_alone"] != "correct" and r["image_alone"] != "correct"],
        "lost_by_combination": [r["sample_id"] for r in combined if r["verdict"] != "correct"
                                and (r["text_alone"] == "correct" or r["image_alone"] == "correct")],
    }
    latencies = sorted(r["latency_s"] for r in results)
    summary = {
        "split": args.split, "confirm_image_only": args.confirm_image_only, "n": len(results),
        "clarify_types": dict(Counter(r["clarify_type"] for r in results if r["clarify_type"])),
        "clarification_field_checks": {"n": sum(1 for r in results if r["expected_clarification_field"]),
                                       "ok": sum(1 for r in results if r["clarification_field_ok"] is True)},
        "routing_accuracy": sum(r["route_ok"] for r in results) / len(results),
        "verdicts": rates(verdicts),
        "safe_rate_when_not_answering_expected": (
            sum(1 for r in results if r["expected_decision"] != "answer" and r["decision"] != "answer")
            / max(1, sum(1 for r in results if r["expected_decision"] != "answer"))),
        "conflict_detection": conflict_detection([r["expected_conflict"] for r in results],
                                                 [r["conflict"] for r in results]),
        "by_scenario_type": {t: rates(v) for t, v in sorted(by_type.items())},
        "modality_contribution": contribution,
        "latency_s": {"median": latencies[len(latencies) // 2], "max": latencies[-1]},
        "decisions": dict(Counter(r["decision"] for r in results)),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("n", "routing_accuracy", "verdicts", "conflict_detection",
                                              "modality_contribution", "latency_s")}, indent=1))
    print(f"written to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
