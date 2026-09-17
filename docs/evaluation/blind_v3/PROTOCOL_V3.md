# Blind evaluation v3: pre-registered protocol

Written on 17 September 2026, before any v3 case exists. This file fixes what
will be evaluated, how, and what happens afterwards, so that none of it can
be chosen after seeing results.

## 1. What is evaluated

Behavioural freeze: commit `2d05b1c` ("Uncertain photos leave no follow-up
context; no options listed for an unreadable sign"), the end of usability
hardening 04.6.

The later commits `d6225b0` (single-row composer) and `194b83d` (drop a photo
onto the composer), and the commit that adds this protocol, change only the
Gradio page (`app/app.py`), its tests, documentation and evaluation tooling.
`git diff 2d05b1c <evaluated commit> -- src configs data evaluation requirements.txt`
must be empty at the run; the runner calls `src.router.route` directly and
never loads the page. The deployed build therefore has the same answering
behaviour as the evaluated one.

Thresholds in force are those of v1.1 and 04.6: `tau_high` 0.50, `tau_low`
0.25, margin 0.10, `tau_intent` 0.30, `tau_intent_answer` 0.40, vision bands
0.30 / 0.24 with margin 0.015, audio gate −45 dBFS. Whisper-base, CLIP and
MiniLM as frozen.

This build is not the system measured by blind v1 or v2. v3 results describe
the final usability-hardened deployment build only; v1 and v2 results stay
evidence for the earlier builds and are not rerun or relabelled.

## 2. How the set is made

- Author: a separate chat with no access to this project, given only
  `docs/airport_spec.md`, `data/kb/airport_kb.json` and
  `AUTHOR_BRIEF_V3.md`. The developer (this repository's author) and any
  session that has seen the code, the rules, earlier blind sets or results
  do not write, edit or pre-screen cases.
- Assets: images sourced or drawn from the author's descriptions and saved as
  PNG; audio made by the author's TTS script or read verbatim by a person.
  Each file is made once; only a technical fault (clipping, silence, a corrupt
  file) justifies redoing it, judged without running the chatbot.
- Shape (so the runner reads it unchanged): 20 text, 8 images, 6 audio clips,
  12 multimodal scenarios, file names and columns as in the brief.

## 3. Freeze

1. The author's files are copied to the repository root unchanged, with
   `SELF_CHECK_V3.txt`, the three `blind_v3_*_sha256.txt` files and, if used,
   `generate_blind_v3_audio.sh`.
2. `python scripts/verify_blind_set.py --set v3` must print `OK`. It checks
   counts, columns, allowed values, that every record id and category exists,
   that asset names match, that every hash matches and that no v3 result
   folder exists. It runs no model.
3. One commit, "Freeze independent blind evaluation v3", adds exactly those
   files. Its hash is the dataset freeze.
4. If verification fails for a formatting reason, the author fixes the file
   and re-hashes before this commit. After the commit nothing in the set
   changes.

## 4. The run

Once, at the freeze commit:

```
python scripts/verify_blind_set.py --set v3      # must print OK first
python scripts/run_final_blind.py --set v3
```

Outputs go to `docs/report/final_blind_evaluation_v3/`: four per-case CSVs
and `final_blind_v3_summary.json`. Each case is routed once, single-turn, with
no clarification context. A crash, a missing model file or an interrupted run
before any result is written may be rerun unchanged; any rerun is recorded.

## 5. Measures (fixed now)

Computed by the existing runner and `evaluation/multimodal_metrics.judge_scenario`,
the same definitions as v1 and v2:

- per case verdict: correct, wrong_confident, over_cautious, safe_mismatch,
  wrong_redirect;
- text: correct verdict rate, decision as expected, category as expected,
  expected record answered, wrong-confident answers, missed and incorrect
  redirects, safe-outcome rate;
- vision: top-1 and top-3 category over in-scope images, in-scope outcome
  correct, out-of-scope handled safely, wrong-confident image answers, by
  stratum;
- speech: mean WER, exact transcriptions, WER by condition, identifier
  accuracy, decision and record as expected, ASR errors that changed the
  outcome;
- multimodal: verdicts, route as expected (runner mapping), conflicts
  detected, wrong-confident answers.

The primary safety measure is the count of wrong-confident answers across all
modalities. With 20 / 8 / 6 / 12 cases every rate is reported with its counts;
no significance claim is made and differences from v1/v2 are not tested,
because the sets and the builds differ.

## 6. After the run

- No change to `src/`, `configs/`, `data/` or the thresholds because of v3
  results, before or after deployment. The deployed build is the evaluated
  build.
- Failures are reported and analysed (likely cause, class, whether 04.6 was
  meant to cover it), not fixed.
- The summary states the freeze hashes, the dataset hash, the evaluated
  commit, and quotes this protocol for anything that deviated from it.
- Deployment (Chat 05) follows the run whatever the result.
