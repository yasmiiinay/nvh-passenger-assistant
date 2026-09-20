"""Evaluate the Whisper speech pipeline on the audio manifest (RQ2).

Writes to outputs/checkpoint_03_3/speech/<split>_<speakers>/. With no
matching manifest rows the script writes STATUS.md saying BLOCKED BY DATA and
stops. Otherwise, per split and speaker group:

  per_clip.csv     gate result, raw transcript, L1/L2 transcripts, identifiers
                   expected vs found, retrieval outcome from the transcript
                   and from the typed reference, latency
  summary.json     WER L1 and L2 (per speaker stratum and overall),
                   identifier-token accuracy L1 and L2, the three-way
                   propagation breakdown, latency, failure types

Propagation is reported in three steps for every clip:
  typed_ok          the reference transcript, typed, reaches the expected outcome
  transcript_changed  the L2 transcript differs from the L2 reference
  asr_ok            the ASR transcript reaches the expected outcome
so "typed_ok and not asr_ok" is the loss attributable to transcription.
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
from evaluation.retrieval_metrics import judge_outcome
from evaluation.speech_metrics import identifier_token_accuracy, propagation_gap, wer_l1, wer_l2
from src.entities import load_gazetteers
from src.foundation_audit import load_queries
from src.normalizer import normalize_l2
from src.retrieval import build_text_index, resolve
from src.speech import SpeechResult, check_audio, load_audio, load_whisper, process_transcript, transcribe

OUT_ROOT = SETTINGS.outputs_dir / "checkpoint_03_3" / "speech"
AUDIO_DIR = SETTINGS.kb_path.parents[1] / "audio"


def blocked(out_dir: Path, reason: str) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "STATUS.md").write_text(f"BLOCKED BY DATA\n\n{reason}\n", encoding="utf-8")
    print("BLOCKED BY DATA:", reason)
    return 0


def speaker_selected(row: dict, speakers: str) -> bool:
    synthetic = row["speaker_id"].startswith("tts_")
    return speakers == "all" or (speakers == "tts") == synthetic


def warm_up() -> float:
    """Load Whisper and run it once on a short clip so that per-clip latency
    below measures transcription, not the first-load cost (which the
    benchmark script reports separately)."""
    import numpy as np
    start = time.perf_counter()
    load_whisper()
    transcribe(np.zeros(SETTINGS.audio_sample_rate, dtype="float32"), SETTINGS.audio_sample_rate)
    return round(time.perf_counter() - start, 2)


def outcome_ok(query: dict, retrieval: dict) -> bool:
    verdict, _ = judge_outcome(query["expected_behaviour"], query["target_kb_id"] or None,
                               retrieval["decision"], retrieval["matched_record_id"],
                               retrieval["candidates"], retrieval["flags"])
    return verdict == "correct"


def failure_type(reference_l2: str, hypothesis_l2: str, expected_ids: list[str], found_ids: list[str]) -> str:
    if reference_l2 == hypothesis_l2:
        return "none"
    if expected_ids and set(expected_ids) != set(found_ids):
        return "identifier_changed"
    ref_words, hyp_words = reference_l2.split(), hypothesis_l2.split()
    if len(hyp_words) < len(ref_words):
        return "words_dropped"
    if len(hyp_words) > len(ref_words):
        return "words_inserted"
    return "word_substituted"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["dev", "heldout", "all"], default="dev")
    parser.add_argument("--speakers", default="tts", choices=["tts", "human", "all"],
                        help="synthetic voices (speaker ids starting with tts_), human recordings, or both")
    args = parser.parse_args()
    out_dir = OUT_ROOT / f"{args.split}_{args.speakers}"
    with open(AUDIO_DIR / "audio_manifest.csv", encoding="utf-8", newline="") as fh:
        rows = [r for r in csv.DictReader(fh)
                if args.split in ("all", r["split"]) and speaker_selected(r, args.speakers)]
    if not rows:
        return blocked(out_dir, f"audio_manifest.csv has no {args.speakers} rows for split '{args.split}'. "
                       "Record clips or run scripts/make_tts_audio.py on the MacBook first.")
    out_dir.mkdir(parents=True, exist_ok=True)
    warm_up_seconds = warm_up()
    gaz = load_gazetteers(SETTINGS.kb_path, SETTINGS.vocabulary_path)
    index = build_text_index(gaz, SETTINGS.intent_exemplars_path)
    thresholds = SETTINGS.thresholds()
    queries = {q["query_id"]: q for path in (SETTINGS.queries_seed_path, SETTINGS.queries_heldout_path, SETTINGS.queries_spoken_path)
               for q in load_queries(path)}

    per_clip, refs, hyps, ref_ids, latencies = [], [], [], [], []
    for row in rows:
        query = queries[row["query_id"]]
        samples, rate = load_audio(AUDIO_DIR / row["file"])
        check = check_audio(samples, rate)
        result = SpeechResult(row["file"], check)
        record = {"audio_id": row["audio_id"], "speaker": row["speaker_id"], "query_id": row["query_id"],
                  "reference": row["reference_transcript"], "gate_ok": check.ok, "gate_problem": check.problem or ""}
        if not check.ok:
            per_clip.append(record)
            continue
        start = time.perf_counter()
        text = transcribe(samples, rate)
        latency = time.perf_counter() - start
        process_transcript(result, text, gaz, index, thresholds)
        typed = resolve(row["reference_transcript"], gaz, index, thresholds).as_dict()
        expected_ids = [i for i in row["expected_identifiers"].split(";") if i]
        reference_l2 = normalize_l2(row["reference_transcript"])
        record.update({
            "transcript_raw": text, "transcript_l1": result.transcript_l1, "transcript_l2": result.transcript_l2,
            "expected_identifiers": ";".join(expected_ids), "found_identifiers": ";".join(result.identifiers),
            "identifiers_ok": set(expected_ids) <= set(result.identifiers),
            "typed_decision": typed["decision"], "typed_record": typed["matched_record_id"] or "",
            "typed_ok": outcome_ok(query, typed),
            "transcript_changed": reference_l2 != result.transcript_l2,
            "asr_decision": result.retrieval["decision"], "asr_record": result.retrieval["matched_record_id"] or "",
            "asr_ok": outcome_ok(query, result.retrieval),
            "failure_type": failure_type(reference_l2, result.transcript_l2, expected_ids, result.identifiers),
            "seconds": check.seconds, "latency_s": round(latency, 3),
        })
        per_clip.append(record)
        refs.append(row["reference_transcript"])
        hyps.append(text)
        ref_ids.append(expected_ids)
        latencies.append(latency)

    with open(out_dir / "per_clip.csv", "w", newline="", encoding="utf-8") as fh:
        fields = sorted({k for r in per_clip for k in r}, key=lambda k: (k != "audio_id", k))
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(per_clip)

    scored = [r for r in per_clip if r["gate_ok"]]
    by_speaker = defaultdict(lambda: {"refs": [], "hyps": []})
    for r in scored:
        by_speaker[r["speaker"]]["refs"].append(r["reference"])
        by_speaker[r["speaker"]]["hyps"].append(r["transcript_raw"])
    typed_ok = sum(r["typed_ok"] for r in scored)
    asr_ok = sum(r["asr_ok"] for r in scored)
    summary = {
        "split": args.split, "speakers": args.speakers, "n_clips": len(rows), "n_gate_rejected": len(rows) - len(scored),
        "wer_l1": wer_l1(refs, hyps) if refs else None,
        "wer_l2": wer_l2(refs, hyps) if refs else None,
        "wer_by_speaker": {s: {"n": len(v["refs"]), "wer_l1": wer_l1(v["refs"], v["hyps"])["wer"],
                               "wer_l2": wer_l2(v["refs"], v["hyps"])["wer"]} for s, v in sorted(by_speaker.items())},
        "identifier_token_accuracy_l1": identifier_token_accuracy(ref_ids, hyps, gaz, "L1") if refs else None,
        "identifier_token_accuracy_l2": identifier_token_accuracy(ref_ids, hyps, gaz, "L2") if refs else None,
        "propagation": {
            "typed_ok": typed_ok, "asr_ok": asr_ok, "n": len(scored),
            "transcript_changed": sum(r["transcript_changed"] for r in scored),
            "changed_but_outcome_kept": sum(r["transcript_changed"] and r["asr_ok"] for r in scored),
            "lost_to_transcription": sum(r["typed_ok"] and not r["asr_ok"] for r in scored),
            "gap": propagation_gap(typed_ok / len(scored), asr_ok / len(scored), len(scored)) if scored else None,
        },
        "latency_s": {"median": round(sorted(latencies)[len(latencies) // 2], 3) if latencies else None,
                      "max": round(max(latencies), 3) if latencies else None,
                      "warm_up": warm_up_seconds},
        "failure_types": dict(Counter(r["failure_type"] for r in scored)),
        "device": "cpu", "whisper_model": SETTINGS.whisper_model_id,
        "audio_min_seconds": SETTINGS.audio_min_seconds,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("n_clips", "n_gate_rejected", "wer_l1", "wer_l2", "propagation", "failure_types", "latency_s")}, indent=1, default=str))
    print(f"written to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
