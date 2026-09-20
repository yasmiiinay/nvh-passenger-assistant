"""Evaluate the CLIP vision pipeline on the labelled image manifest (RQ1).

Writes to outputs/checkpoint_03_3/vision/. If the manifest has no rows the
script writes STATUS.md saying BLOCKED BY DATA and stops; no number is
produced without images. With rows it reports, on the requested split:

  per_image.csv        top-3 categories, top-3 records, margins, anchor, flags
  summary.json         top-1 / top-3 accuracy overall, by category and by
                       stratum; correct vs incorrect similarity distributions;
                       margin behaviour; out-of-scope detection; anchor ablation
  confusion.csv        gold category x predicted category

Prompt revisions are made on the dev split only and are logged in
data/vision_prompts.json under _meta.revisions.
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from configs.settings import SETTINGS
from evaluation.vision_metrics import confusion_counts, oos_anchor_abstention, score_distribution, top_k_accuracy
from src.entities import load_gazetteers
from src.vision import VisionIndex, analyse_vector, build_vision_index, check_image, embed_images, load_image, load_prompts

OUT_DIR = SETTINGS.outputs_dir / "checkpoint_03_3" / "vision"
IMAGES_DIR = SETTINGS.kb_path.parents[1] / "images"


def load_manifest(split: str) -> list[dict]:
    with open(IMAGES_DIR / "images_manifest.csv", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    return [r for r in rows if r["split"] == split]


def blocked(reason: str) -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "STATUS.md").write_text(f"BLOCKED BY DATA\n\n{reason}\n", encoding="utf-8")
    print("BLOCKED BY DATA:", reason)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["dev", "heldout"], default="dev")
    args = parser.parse_args()
    rows = load_manifest(args.split)
    if not rows:
        return blocked(f"images_manifest.csv has no rows for split '{args.split}'. "
                       "Add labelled images with scripts/build_image_manifest.py first.")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    gaz = load_gazetteers(SETTINGS.kb_path, SETTINGS.vocabulary_path)
    index = build_vision_index(gaz, load_prompts(SETTINGS.vision_prompts_path))
    thresholds = SETTINGS.vision_thresholds()

    per_image, gold, ranked_cats, scores, correct_flags, strata = [], [], [], [], [], []
    oos_flags_with, oos_flags_without, oos_kind = [], [], []
    for row in rows:
        try:
            image = load_image(IMAGES_DIR / row["file"])
        except ValueError as exc:
            per_image.append({"image_id": row["image_id"], "error": str(exc)})
            continue
        vec = embed_images([image])[0]
        r = analyse_vector(row["file"], check_image(image), vec, index, thresholds)
        no_anchor_index = VisionIndex(index.categories, index.category_vecs, [], index.anchor_vecs[:0],
                                      index.record_ids, index.record_vecs)
        r_no_anchor = analyse_vector(row["file"], r.check, vec, no_anchor_index, thresholds)
        predicted = "out_of_scope" if r.out_of_scope else r.category_ranking[0][0]
        is_correct = predicted == row["expected_label"]
        gold.append(row["expected_label"])
        ranked_cats.append(["out_of_scope"] if r.out_of_scope else [c for c, _ in r.category_ranking])
        scores.append(r.category_ranking[0][1])
        correct_flags.append(is_correct)
        strata.append(row["quality_stratum"])
        if row["expected_label"] == "out_of_scope":
            oos_flags_with.append(r.out_of_scope)
            oos_kind.append(row["notes"].split(":")[0] if ":" in row["notes"] else "unspecified")
        else:
            oos_flags_without.append(r.out_of_scope)
        per_image.append({
            "image_id": row["image_id"], "file": row["file"], "expected": row["expected_label"],
            "stratum": row["quality_stratum"], "predicted": predicted, "correct": is_correct,
            "top3_categories": "|".join(f"{c}:{s}" for c, s in r.category_ranking),
            "category_margin": r.category_margin, "best_anchor": f"{r.best_anchor[0]}:{r.best_anchor[1]}",
            "out_of_scope": r.out_of_scope, "out_of_scope_without_anchors": r_no_anchor.out_of_scope,
            "records_in_top_category": "|".join(f"{c}:{s}" for c, s in r.record_ranking),
            "record_margin": r.record_margin, "band": r.band or "",
            "blur_score": round(r.check.blur_score, 1), "brightness": round(r.check.brightness, 1),
            "flags": "|".join(r.check.flags),
        })

    with open(OUT_DIR / "per_image.csv", "w", newline="", encoding="utf-8") as fh:
        fields = sorted({k for row in per_image for k in row}, key=lambda k: (k != "image_id", k))
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(per_image)

    in_scope = [i for i, g in enumerate(gold) if g != "out_of_scope"]
    by_category, by_stratum = {}, {}
    for i in in_scope:
        by_category.setdefault(gold[i], []).append(correct_flags[i])
        by_stratum.setdefault(strata[i], []).append(correct_flags[i])
    margins = [r["category_margin"] for r in per_image if "category_margin" in r]
    summary = {
        "split": args.split, "n_images": len(rows), "n_in_scope": len(in_scope),
        "n_out_of_scope": len(rows) - len(in_scope),
        "top1": top_k_accuracy([gold[i] for i in in_scope], [ranked_cats[i] for i in in_scope], 1),
        "top3": top_k_accuracy([gold[i] for i in in_scope], [ranked_cats[i] for i in in_scope], 3),
        "by_category": {c: {"n": len(v), "top1": sum(v) / len(v)} for c, v in sorted(by_category.items())},
        "by_stratum": {s: {"n": len(v), "top1": sum(v) / len(v)} for s, v in sorted(by_stratum.items())},
        "score_distribution": score_distribution(scores, correct_flags),
        "margin": {"median_correct": statistics.median([m for m, c in zip(margins, correct_flags) if c] or [0]),
                   "median_incorrect": statistics.median([m for m, c in zip(margins, correct_flags) if not c] or [0])},
        "out_of_scope_detection": oos_anchor_abstention(oos_flags_without, oos_flags_with),
        "out_of_scope_detection_by_kind": {
            k: {"n": sum(1 for kk in oos_kind if kk == k),
                "detected": sum(1 for kk, f in zip(oos_kind, oos_flags_with) if kk == k and f)}
            for k in sorted(set(oos_kind))},
        "anchor_ablation_without_anchors": {
            "abstain_rate_out_of_scope": 0.0, "false_abstain_rate_in_scope": 0.0,
            "note": "without anchors nothing can be marked out of scope by construction; the band floor is the only remaining guard"},
        "bands": dict(Counter(r.get("band", "") for r in per_image)),
        "thresholds": thresholds,
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    pairs = confusion_counts(gold, [c[0] for c in ranked_cats])["pairs"]
    with open(OUT_DIR / "confusion.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["gold", "predicted", "count"])
        for (g, p), n in sorted(pairs.items()):
            writer.writerow([g, p, n])
    print(json.dumps({k: summary[k] for k in ("n_images", "top1", "top3", "by_category", "by_stratum", "out_of_scope_detection", "out_of_scope_detection_by_kind", "bands")}, indent=1))
    print(f"written to {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
