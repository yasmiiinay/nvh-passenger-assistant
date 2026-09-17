"""One-time final blind evaluation of the frozen system.

Reads the four frozen blind files at the repository root (text, images,
audio, multimodal), runs each case exactly once through the unchanged
pipelines and writes per-case results and a machine-readable summary to
docs/report/final_blind_evaluation/. Evaluation code only: nothing here
touches thresholds, retrieval, routing, templates, assets or labels.

The expected_route vocabulary of the blind multimodal manifest is the
author's, not the router's; the mapping used to score routing is written
down in ROUTE_EXPECTATION and reported next to the raw values.
"""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from configs.settings import SETTINGS, REPO_ROOT
from evaluation.multimodal_metrics import judge_scenario
from evaluation.speech_metrics import wer_l2
from src.entities import extract, load_gazetteers
from src.responses import render_outcome
from src.retrieval import build_text_index
from src.router import build_context, image_evidence, route
from src.vision import analyse_image

OUT_DIR = REPO_ROOT / "docs" / "report" / "final_blind_evaluation"
SAFE_DECISIONS = ("clarify", "abstain", "redirect", "conflict")

ROUTE_EXPECTATION = {
    # author's label -> what the router must have done
    "fuse_consistent": lambda o: o.route in ("text_leads", "voice_leads", "image_leads") and not o.conflict,
    "flag_cross_modal_conflict": lambda o: o.conflict,
    "image_resolves_deictic": lambda o: o.route == "image_leads",
    "image_only": lambda o: o.route == "image_only",
    "voice_only": lambda o: o.route == "voice_only",
}


def read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def candidate_categories(out, gaz) -> set[str]:
    cats = {gaz.records[r]["category"] for r in out.candidates if r in gaz.records}
    if out.matched_record_id:
        cats.add(gaz.records[out.matched_record_id]["category"])
    return cats


def actual_category(out, gaz) -> str:
    if out.matched_record_id:
        return gaz.records[out.matched_record_id]["category"]
    if out.image_category and out.route in ("image_only", "image_leads"):
        return out.image_category
    cats = sorted(candidate_categories(out, gaz))
    return "|".join(cats)


def safety_note(expected_decision: str, out, verdict: str) -> str:
    if verdict == "wrong_confident":
        return "confident answer where none or another record was expected"
    if verdict == "wrong_redirect":
        return "redirected without a live-information request"
    if expected_decision in SAFE_DECISIONS and out.decision in SAFE_DECISIONS and verdict != "correct":
        return "safe: a different safe decision than expected"
    if verdict == "over_cautious":
        return "safe: asked or declined where an answer was expected"
    if "grounded_negative" in out.flags:
        return "grounded negative given"
    return ""


def judge(expected_decision, expected_record, expected_category, expected_conflict, out, gaz) -> str:
    return judge_scenario(expected_decision, expected_record or "", expected_category or "",
                          expected_conflict, out.decision, out.matched_record_id,
                          candidate_categories(out, gaz), out.conflict)


def evidence(out) -> str:
    bits = []
    if out.text is not None:
        t = out.text
        bits.append(f"stage={t.stage}")
        if t.match_score is not None:
            bits.append(f"text_score={t.match_score:.3f} margin={t.margin:.3f}")
        if t.intent:
            bits.append(f"intent={t.intent}({t.intent_score})")
    if out.vision is not None and out.vision.category_ranking:
        v = out.vision
        bits.append("image=" + ",".join(f"{c}:{s:.3f}" for c, s in v.category_ranking) +
                    f" margin={v.category_margin:.3f} band={v.band} anchor={v.best_anchor[0]}:{v.best_anchor[1]:.3f}")
    if out.speech is not None:
        bits.append(f"audio_ok={out.speech.check.ok}")
    return "; ".join(bits)


def load_results() -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    """The per-case files of the single run, with the boolean columns restored."""
    def fix(rows):
        for r in rows:
            for k, v in r.items():
                if v in ("True", "False"):
                    r[k] = v == "True"
        return rows
    return tuple(fix(read_csv(OUT_DIR / f"final_blind_{n}_results.csv")) for n in ("text", "image", "audio", "multimodal"))


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=REPO_ROOT).stdout.strip()
    summary_only = "--summary-only" in sys.argv
    gaz = load_gazetteers(SETTINGS.kb_path, SETTINGS.vocabulary_path)
    ctx = None if summary_only else build_context(gaz, build_text_index(gaz, SETTINGS.intent_exemplars_path))

    text_cases = read_csv(REPO_ROOT / "final_blind_text.csv")
    image_cases = read_csv(REPO_ROOT / "final_blind_images_manifest.csv")
    audio_cases = read_csv(REPO_ROOT / "final_blind_audio_manifest.csv")
    mm_cases = read_csv(REPO_ROOT / "final_blind_multimodal.csv")
    assets = {"text": "final_blind_text.csv", "images": "final_blind_images_manifest.csv",
              "audio": "final_blind_audio_manifest.csv", "multimodal": "final_blind_multimodal.csv"}
    hashes = {name: sha256(REPO_ROOT / name) for name in list(assets.values()) +
              [f"IMG_B{i:02d}.png" for i in range(1, 9)] + [f"AUD_B{i:02d}.wav" for i in range(1, 7)]}

    if summary_only:
        text_rows, image_rows, audio_rows, mm_rows = load_results()
        text_cases = image_cases = audio_cases = mm_cases = []

    # ---- text ----
    text_rows = [] if not summary_only else text_rows
    for c in text_cases:
        out = route(c["query"], None, None, ctx)
        verdict = judge(c["expected_decision"], c["expected_record_id"], c["expected_category"], False, out, gaz)
        text_rows.append({
            "blind_id": c["blind_id"], "query": c["query"],
            "expected_decision": c["expected_decision"], "actual_decision": out.decision,
            "expected_category": c["expected_category"], "actual_category": actual_category(out, gaz),
            "expected_record_id": c["expected_record_id"], "actual_record_id": out.matched_record_id or "",
            "candidates": "|".join(out.candidates), "stage": out.text.stage if out.text else "",
            "match_score": out.text.match_score if out.text and out.text.match_score is not None else "",
            "band": out.band or "", "route": out.route, "flags": "|".join(out.flags),
            "verdict": verdict, "correct": verdict == "correct",
            "safety_note": safety_note(c["expected_decision"], out, verdict),
            "final_response": render_outcome(out, gaz).replace("\n", " // "),
        })
    if not summary_only:
        write_csv(OUT_DIR / "final_blind_text_results.csv", text_rows)

    # ---- images ----
    image_rows = [] if not summary_only else image_rows
    for c in image_cases:
        path = REPO_ROOT / f"{c['image_id']}.png"
        vision = analyse_image(path, ctx.vision_index, ctx.vision_thresholds)
        out = route(None, path, None, ctx)
        verdict = judge(c["expected_decision"], c["expected_record_id"], c["expected_category"], False, out, gaz)
        ranking = vision.category_ranking
        image_rows.append({
            "image_id": c["image_id"], "quality_stratum": c["quality_stratum"],
            "expected_decision": c["expected_decision"], "actual_decision": out.decision,
            "expected_category": c["expected_category"],
            "top1_category": ranking[0][0] if ranking else "", "top1_similarity": f"{ranking[0][1]:.4f}" if ranking else "",
            "top2": f"{ranking[1][0]}:{ranking[1][1]:.4f}" if len(ranking) > 1 else "",
            "top3": f"{ranking[2][0]}:{ranking[2][1]:.4f}" if len(ranking) > 2 else "",
            "category_margin": f"{vision.category_margin:.4f}", "band": vision.band or "",
            "out_of_scope_flag": vision.out_of_scope, "closest_anchor": f"{vision.best_anchor[0]}:{vision.best_anchor[1]:.4f}",
            "quality_flags": "|".join(vision.check.flags),
            "expected_record_id": c["expected_record_id"], "actual_record_id": out.matched_record_id or "",
            "candidates": "|".join(out.candidates),
            "top1_correct": bool(c["expected_category"]) and ranking and ranking[0][0] == c["expected_category"],
            "top3_contains": bool(c["expected_category"]) and c["expected_category"] in [r for r, _ in ranking],
            "verdict": verdict, "correct": verdict == "correct",
            "safety_note": safety_note(c["expected_decision"], out, verdict),
            "final_response": render_outcome(out, gaz).replace("\n", " // "),
        })
    if not summary_only:
        write_csv(OUT_DIR / "final_blind_image_results.csv", image_rows)

    # ---- audio ----
    audio_rows = [] if not summary_only else audio_rows
    for c in audio_cases:
        path = REPO_ROOT / f"{c['audio_id']}.wav"
        out = route(None, None, path, ctx)
        sp = out.speech
        transcript = sp.transcript_raw or "" if sp else ""
        wer = wer_l2([c["spoken_text"]], [transcript])["wer"] if transcript else 1.0
        ref_ids = [e.value for e in extract(c["spoken_text"], gaz).entities if e.type in ("gate_id", "desk_id", "belt_id")]
        found_ids = list(sp.identifiers) if sp and sp.identifiers else []
        ident = "n/a" if not ref_ids else ("correct" if set(ref_ids) == set(found_ids) else "incorrect")
        verdict = judge(c["expected_decision"], c["expected_record_id"], c["expected_category"], False, out, gaz)
        audio_rows.append({
            "audio_id": c["audio_id"], "audio_condition": c["audio_condition"], "reference_text": c["spoken_text"],
            "asr_transcript": transcript, "normalized_transcript": sp.transcript_l2 if sp and sp.transcript_l2 else "",
            "audio_accepted": sp.check.ok if sp else "", "wer": f"{wer:.3f}",
            "reference_identifiers": "|".join(ref_ids), "found_identifiers": "|".join(found_ids), "identifier": ident,
            "expected_decision": c["expected_decision"], "actual_decision": out.decision,
            "expected_category": c["expected_category"], "actual_category": actual_category(out, gaz),
            "expected_record_id": c["expected_record_id"], "actual_record_id": out.matched_record_id or "",
            "stage": out.text.stage if out.text else "", "flags": "|".join(out.flags),
            "verdict": verdict, "correct": verdict == "correct",
            "safety_note": safety_note(c["expected_decision"], out, verdict),
            "final_response": render_outcome(out, gaz).replace("\n", " // "),
        })
    if not summary_only:
        write_csv(OUT_DIR / "final_blind_audio_results.csv", audio_rows)

    # ---- multimodal ----
    mm_rows = [] if not summary_only else mm_rows
    for c in mm_cases:
        image_path = REPO_ROOT / f"{c['image_id']}.png" if c["image_id"] else None
        audio_path = REPO_ROOT / f"{c['audio_id']}.wav" if c["audio_id"] else None
        out = route(c["text"] or None, image_path, audio_path, ctx)
        expected_conflict = c["expected_decision"] == "conflict"
        verdict = judge(c["expected_decision"], c["expected_record_id"], c["expected_category"], expected_conflict, out, gaz)
        route_ok = ROUTE_EXPECTATION[c["expected_route"]](out)
        mm_rows.append({
            "scenario_id": c["scenario_id"], "modality": c["modality"], "text": c["text"],
            "image_id": c["image_id"], "audio_id": c["audio_id"],
            "expected_decision": c["expected_decision"], "actual_decision": out.decision,
            "expected_category": c["expected_category"], "actual_category": actual_category(out, gaz),
            "expected_record_id": c["expected_record_id"], "actual_record_id": out.matched_record_id or "",
            "expected_route": c["expected_route"], "actual_route": out.route, "route_ok": route_ok,
            "conflict_expected": expected_conflict, "conflict_detected": out.conflict,
            "transcript": out.speech.transcript_raw if out.speech and out.speech.transcript_raw else "",
            "evidence": evidence(out), "band": out.band or "", "flags": "|".join(out.flags),
            "verdict": verdict, "correct": verdict == "correct",
            "safety_note": safety_note(c["expected_decision"], out, verdict),
            "final_response": render_outcome(out, gaz).replace("\n", " // "),
        })
    if not summary_only:
        write_csv(OUT_DIR / "final_blind_multimodal_results.csv", mm_rows)

    # ---- summary ----
    def counts(rows):
        return dict(Counter(r["verdict"] for r in rows))

    def rate(n, d):
        return {"count": n, "of": d, "rate": round(n / d, 3) if d else None}

    text_answer_expected = [r for r in text_rows if r["expected_decision"] == "answer" and r["expected_record_id"]]
    mm_answer_expected = [r for r in mm_rows if r["expected_decision"] == "answer" and r["expected_record_id"]]
    conf_tp = sum(1 for r in mm_rows if r["conflict_expected"] and r["conflict_detected"])
    conf_fp = sum(1 for r in mm_rows if not r["conflict_expected"] and r["conflict_detected"])
    conf_fn = sum(1 for r in mm_rows if r["conflict_expected"] and not r["conflict_detected"])
    strata = sorted({r["quality_stratum"] for r in image_rows})
    in_scope = [r for r in image_rows if r["expected_category"]]
    oos = [r for r in image_rows if not r["expected_category"]]
    summary = {
        "commit": commit, "date": date.today().isoformat(),
        "sizes": {"text": len(text_rows), "images": len(image_rows), "audio": len(audio_rows), "multimodal": len(mm_rows)},
        "asset_sha256": hashes,
        "thresholds": SETTINGS.thresholds() | (SETTINGS.vision_thresholds() or {}),
        "text": {
            "verdicts": counts(text_rows),
            "decision_accuracy": rate(sum(r["actual_decision"] == r["expected_decision"] for r in text_rows), len(text_rows)),
            "category_accuracy": rate(sum(bool(r["expected_category"]) and r["expected_category"] in str(r["actual_category"]).split("|") for r in text_rows),
                                      sum(1 for r in text_rows if r["expected_category"])),
            "record_accuracy": rate(sum(r["actual_record_id"] == r["expected_record_id"] for r in text_answer_expected), len(text_answer_expected)),
            "wrong_record_answers": [r["blind_id"] for r in text_rows if r["actual_decision"] == "answer" and r["actual_record_id"] and r["actual_record_id"] != r["expected_record_id"]],
            "wrong_confident": [r["blind_id"] for r in text_rows if r["verdict"] == "wrong_confident"],
            "clarify_answer_mismatches": [r["blind_id"] for r in text_rows if {r["expected_decision"], r["actual_decision"]} == {"clarify", "answer"}],
            "abstain_failures": [r["blind_id"] for r in text_rows if r["expected_decision"] == "abstain" and r["actual_decision"] != "abstain"],
            "incorrect_redirects": [r["blind_id"] for r in text_rows if r["actual_decision"] == "redirect" and r["expected_decision"] != "redirect"],
            "missed_redirects": [r["blind_id"] for r in text_rows if r["expected_decision"] == "redirect" and r["actual_decision"] != "redirect"],
            "false_grounded_negatives": [r["blind_id"] for r in text_rows if "grounded_negative" in r["flags"] and r["verdict"] != "correct"],
            "safe_outcome_rate": rate(sum(r["verdict"] not in ("wrong_confident", "wrong_redirect") for r in text_rows), len(text_rows)),
        },
        "images": {
            "verdicts": counts(image_rows),
            "top1_category_accuracy": rate(sum(bool(r["top1_correct"]) for r in in_scope), len(in_scope)),
            "top3_inclusion": rate(sum(bool(r["top3_contains"]) for r in in_scope), len(in_scope)),
            "by_stratum": {s: rate(sum(r["verdict"] == "correct" for r in image_rows if r["quality_stratum"] == s),
                                   sum(1 for r in image_rows if r["quality_stratum"] == s)) for s in strata},
            "in_scope_outcome_accuracy": rate(sum(r["verdict"] == "correct" for r in in_scope), len(in_scope)),
            "oos_safe_detection": rate(sum(r["actual_decision"] in SAFE_DECISIONS for r in oos), len(oos)),
            "oos_abstained": rate(sum(r["actual_decision"] == "abstain" for r in oos), len(oos)),
            "wrong_confident": [r["image_id"] for r in image_rows if r["verdict"] == "wrong_confident"],
        },
        "audio": {
            "verdicts": counts(audio_rows),
            "mean_wer": round(sum(float(r["wer"]) for r in audio_rows) / len(audio_rows), 3),
            "wer_by_condition": {r["audio_condition"]: float(r["wer"]) for r in audio_rows},
            "identifier_accuracy": rate(sum(r["identifier"] == "correct" for r in audio_rows if r["identifier"] != "n/a"),
                                        sum(1 for r in audio_rows if r["identifier"] != "n/a")),
            "decision_accuracy": rate(sum(r["actual_decision"] == r["expected_decision"] for r in audio_rows), len(audio_rows)),
            "record_accuracy": rate(sum(r["actual_record_id"] == r["expected_record_id"] for r in audio_rows), len(audio_rows)),
            "asr_errors_changing_outcome": [r["audio_id"] for r in audio_rows if float(r["wer"]) > 0 and r["verdict"] != "correct"],
            "asr_errors_absorbed": [r["audio_id"] for r in audio_rows if float(r["wer"]) > 0 and r["verdict"] == "correct"],
        },
        "multimodal": {
            "verdicts": counts(mm_rows),
            "decision_accuracy": rate(sum(r["actual_decision"] == r["expected_decision"] for r in mm_rows), len(mm_rows)),
            "record_accuracy": rate(sum(r["actual_record_id"] == r["expected_record_id"] for r in mm_answer_expected), len(mm_answer_expected)),
            "routing_accuracy": rate(sum(bool(r["route_ok"]) for r in mm_rows), len(mm_rows)),
            "conflict": {"tp": conf_tp, "fp": conf_fp, "fn": conf_fn,
                         "precision": round(conf_tp / (conf_tp + conf_fp), 3) if conf_tp + conf_fp else None,
                         "recall": round(conf_tp / (conf_tp + conf_fn), 3) if conf_tp + conf_fn else None},
            "wrong_confident": [r["scenario_id"] for r in mm_rows if r["verdict"] == "wrong_confident"],
            "unsafe_answers": [r["scenario_id"] for r in mm_rows if r["actual_decision"] == "answer" and r["expected_decision"] != "answer"],
            "safe_clarify_or_abstain": [r["scenario_id"] for r in mm_rows if r["actual_decision"] in ("clarify", "abstain")],
            "consistent_vs_conflicting": {
                "consistent": rate(sum(r["verdict"] == "correct" for r in mm_rows if not r["conflict_expected"]), sum(1 for r in mm_rows if not r["conflict_expected"])),
                "conflicting": rate(sum(r["verdict"] == "correct" for r in mm_rows if r["conflict_expected"]), sum(1 for r in mm_rows if r["conflict_expected"])),
            },
        },
    }
    (OUT_DIR / "final_blind_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    for name, rows in (("text", text_rows), ("images", image_rows), ("audio", audio_rows), ("multimodal", mm_rows)):
        print(f"== {name}")
        for r in rows:
            key = next(iter(r.values()))
            print(f"  {key:8s} expected={r['expected_decision']:8s} actual={r['actual_decision']:8s} "
                  f"record={r['actual_record_id'] or '-':22s} {r['verdict']}")
    print(json.dumps({k: summary[k] for k in ("text", "images", "audio", "multimodal")}, indent=1, default=str))
    print("written to", OUT_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
