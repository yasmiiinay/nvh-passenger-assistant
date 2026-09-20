# Smart Airport Passenger Assistance Multimodal Chatbot (AI7016)

A multimodal (image / voice / text) assistant for a **fictional** airport,
Nordhaven International (NVH), answering passenger questions from a structured,
fully synthetic knowledge base. MSc set exercise, proof of concept.

Deployed prototype: https://huggingface.co/spaces/yasmincinar/nvh-assistant

This repository is the submission snapshot of the final system: source code,
datasets, tests, evaluation code and the evidence the report relies on. The
development history, including earlier builds and the commits that record the
order of the final blind evaluation, is kept in a private archive retained by
the author.

## System

Core stack (frozen, nothing is fine-tuned): CLIP ViT-B/32 (zero-shot image
labelling with out-of-scope anchors) · Whisper-base (ASR) + airport text
normaliser · all-MiniLM-L6-v2 sentence embeddings for intent-by-similarity and
semantic KB retrieval · deterministic retrieval cascade (official redirect for
live-status requests → exact identifier → alias → category and terminal cues →
category-filtered semantic → full semantic → answer / clarify / abstain /
redirect) · deterministic multimodal router (rules R0 to R6, scores are never
averaged, a fifth outcome reports a conflict between modalities) · template
responses grounded in KB records · Gradio Blocks UI. No generative model
anywhere; EasyOCR is an optional, flag-gated enhancement that is switched off.

Supported inputs: text, voice, image, image + text, image + voice. English only.
An architecture diagram is in
`docs/report/evidence/architecture_multimodal_pipeline.png`.

## Supported visual scope

The photo path recognises the **kind** of airport sign in an image: its
category (restroom, security, transport, …) from CLIP similarity to the
category prompts, with out-of-scope anchors and a similarity band. It does
**not** read text: desk numbers, gate identifiers, terminal names or any
text-only sign content are invisible to it (`enable_ocr = False`). A photo of a
"C7" gate marker is therefore a gate-category sign at best, never gate C7.

## Final blind evaluation (v3)

Blind v3 was run once after the behavioural freeze under a pre-registered
protocol. The 46 cases were authored separately from implementation work,
without access to the code, earlier blind results, known failure classes or
current metrics. The image and audio assets were produced by the developer from
the authored descriptions. No tuning followed the run.

| Modality | Cases | Final Blind v3 result |
|---|---:|---|
| Text | 20 | decision 17/20; safe outcome 18/20; expected record 8/11; 2 wrong-confident |
| Vision | 8 | top-1 category 5/6; top-3 6/6; in-scope outcome 3/6; OOS safe 2/2; 0 wrong-confident |
| Speech | 6 | mean WER 0.015; decision 6/6; expected record 6/6 |
| Multimodal | 12 | decision 9/12; routing 11/12; conflict precision 1.00, recall 0.50; 0 wrong-confident |

Overall verdict counts were **34 correct, 5 over-cautious, 5 safe mismatch
and 2 wrong-confident**. Per-case results and the summary are under
`docs/report/final_blind_evaluation_v3/`; the protocol and the authoring brief
are under `docs/evaluation/blind_v3/`. The frozen manifests
(`final_blind_v3_*.csv`), the stimuli (`IMG3_B*.png`, `AUD3_B*.wav`),
`SELF_CHECK_V3.txt` and the SHA-256 files (`blind_v3_*_sha256.txt`) sit at the
repository root, where the scripts expect them.

```bash
python scripts/verify_blind_set.py --set v3   # checks completeness and hashes; runs no model
```

`python scripts/run_final_blind.py --set v3` repeats the evaluation and
overwrites the result files in the working copy; the committed files are the
single frozen run.

Two earlier blind iterations (v1 and v2) were run on earlier builds with
different items. The final build followed a usability hardening pass made after
the second iteration, and v3 is the only blind evaluation of the final build.
The earlier iterations are retained unchanged in the private development
archive and are not treated as directly comparable with v3.

## Scope and limitations

The prototype answers from a static, synthetic knowledge base and has no
connection to any live airport system. Flight status, gate changes, queue
times and same-day exceptions to opening hours are outside what it can know,
and it does not attempt to infer them.

"Request assistance" writes a structured escalation record with a reference
number to `outputs/logs/tickets.jsonl` and shows the synthetic contact route
held in the knowledge base. Nothing is transmitted to any service, and the
interface states that the assistant cannot connect the passenger to a person:
there is no human hand-over in this build.

Nordhaven International (NVH) is fictional. The system is a proof of concept
built for an MSc set exercise (AI7016) and evaluated as one. It is not an
operational passenger service, and the blind sets are small enough (20, 8, 6
and 12 cases) that the rates above should be read as indicative rather than
as precise performance estimates.

## Repository layout

| Path | Responsibility (one sentence) |
|---|---|
| `app/` | The passenger assistant interface (`gr.Blocks`): text, photo and voice inputs, answer, match band, evidence panel, assistance request. |
| `configs/` | The single `Settings` dataclass every script reads; thresholds live here and nowhere else. |
| `src/` | Pipeline code: `kb.py` (KB loading, identifier expansion), `foundation_audit.py`, `normalizer.py` (L1/L2 text normalisation), `entities.py` (regex + KB-derived gazetteers), `text_encoder.py` (MiniLM, loaded on first use), `intent.py` (intent by nearest exemplar), `retrieval.py` (the full text cascade), `responses.py` (template answers from record fields), `router.py` (the deterministic multimodal routing rules and conflict surfacing), `event_log.py` (JSONL event log and the escalation record), `vision.py` (image checks, CLIP zero-shot ranking), `speech.py` (audio gate, Whisper-base transcription into the same text cascade). |
| `data/kb/` | The synthetic knowledge base (`airport_kb.json`, 32 records). |
| `data/images/`, `data/audio/`, `data/multimodal/` | Datasets per `docs/dataset_schemas.md`: 101 labelled images (64 AIGA/DOT pictograms from Wikimedia Commons, 30 symbols cropped from screen photographs, 7 unrelated photographs), 125 audio clips (120 synthetic from five macOS voices, 5 human) plus 4 derived low-quality clips, and 68 evaluation multimodal scenarios plus 13 QA regression cases. |
| `data/text/` | Seed query set (`queries_seed.csv`, 43 rows, dev), the held-out set (`queries_heldout.csv`, 36 rows, frozen before any run), spoken and QA queries, and the dev-only intent exemplars (`intent_exemplars.csv`, 95 phrasings for the 15 intents). |
| `data/vocabulary.json` | Controlled vocabulary shared by image labels, intents, entities, KB categories and routing. |
| `evaluation/` | Metric modules (pure functions). |
| `scripts/` | Runnable utilities: `smoke_test.py`, `audit_foundation.py`, `benchmark_env.py`, the evaluation runners (`run_deterministic_seed.py`, `run_text_pipeline_seed.py`, `run_text_regression.py`, `run_vision_eval.py`, `run_speech_eval.py`, `run_multimodal_eval.py`), the blind-set tools (`verify_blind_set.py`, `run_final_blind.py`) and the dataset helpers (`build_image_manifest.py`, `fetch_wikimedia_category.py`, `make_tts_audio.py`, `add_recordings.py`). |
| `tests/` | Consistency gate plus unit tests per module (`python -m pytest tests`). |
| `docs/` | `airport_spec.md`, `dataset_schemas.md`, the Blind v3 protocol (`docs/evaluation/blind_v3/`), the evidence used by the report (`docs/report/evidence/`: data exploration, preprocessing, deployment, structured deployment scenarios, ethics), the manual usability diagnostics and the Blind v3 results (`docs/report/final_blind_evaluation_v3/`). |
| repository root | Frozen Blind v3 manifests, stimuli, self check and hash files; `generate_blind_v3_audio.sh` (how the synthetic Blind v3 clips were made); requirements files. |
| `outputs/` | Everything generated (benchmarks, evaluation artefacts, logs); git-ignored except `.gitkeep`. |
| `models/` | Local model copies (git-ignored). A local copy is used when present; otherwise the hub id from `configs/settings.py` is fetched on first use. |

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # runtime
pip install -r requirements-dev.txt      # + evaluation/dev extras (sklearn, matplotlib, pytest, faiss dev-check)
# EasyOCR only if the OCR enhancement is enabled:
# pip install -r requirements-ocr.txt
python scripts/smoke_test.py             # must print SMOKE TEST: PASS
python scripts/audit_foundation.py       # must print ALL CHECKS PASS
```

Evaluation was run locally on macOS with Python 3.14; the hosted Space runs
Python 3.12 with the same pins. Model weights are not committed and are
downloaded from the Hugging Face Hub on first use of each modality.

## Running the assistant and the evaluations

```bash
python app/app.py                                        # local interface at http://127.0.0.1:7860
python -m pytest tests                                   # the MiniLM tests skip if the model is unavailable
python scripts/run_deterministic_seed.py                 # deterministic stages only
python scripts/run_text_pipeline_seed.py                 # full text cascade on the development queries
python scripts/run_text_pipeline_seed.py --set heldout   # same pipeline on the held-out set
python scripts/run_text_regression.py                    # QA regression queries (data/text/queries_qa.csv)
python scripts/run_vision_eval.py --split dev            # CLIP on the labelled images
python scripts/run_speech_eval.py --split dev            # Whisper on the synthetic development clips
python scripts/run_speech_eval.py --split heldout
python scripts/run_speech_eval.py --split dev --speakers human
python scripts/run_multimodal_eval.py --split dev        # 35 development scenarios
python scripts/run_multimodal_eval.py --split heldout    # 33 held-out scenarios
python scripts/run_multimodal_eval.py --split regression # 13 QA regression cases, reported separately
```

Results are written under `outputs/`. Development and held-out results are
diagnostic: those sets were rerun during development and are not blind.

Models load on the first question. Each turn appends one line to
`outputs/logs/events.jsonl` (ids, decision, band, scores, flags, latency;
no words, no media); an assistance request appends a ticket with a
reference number to `outputs/logs/tickets.jsonl`.

The page shows the session as a conversation. Each request is routed from
the current text, photo and audio; the one thing carried over is the
previous turn's unresolved clarification (its category, terminal and zone),
which a short follow-up such as "What about Terminal 2?" completes. The
answer is two to four sentences about what was asked with a compact fact row
drawn from the selected record; every field of the record, the retrieval route
and the similarity numbers sit under "Evidence & details", where the numbers
are described as retrieval distances, not probabilities. The status next to
every answer is a symbol plus words, so colour is never the only signal.

Decision thresholds live in `configs/settings.py`. The text thresholds were
chosen on the 43-query development split by the coarse grid in
`run_text_pipeline_seed.py` and the vision thresholds on the development
images; held-out and blind data were not used for them. Displayed scores are
cosine similarities, not probabilities.

## Deployment

The final build is deployed at
https://huggingface.co/spaces/yasmincinar/nvh-assistant (Gradio SDK, ZeroGPU
hardware; inference runs on CPU). The Space is a separate repository holding a
deployment-only subset: `app/`, `src/`, `configs/`, `requirements.txt`, a
README and the `data/` files the application loads at run time. Evaluation
media, scripts, tests and all blind-set material are not published there. The
deployment record, the smoke test and the live-microphone checks are in
`docs/report/evidence/deployment_smoke_test.md`; that record is dated and its
commit identifiers refer to the private development archive.

## Provenance and privacy

The operational knowledge base and authored evaluation/query data are synthetic
or project-created; no real airport operational data was copied. The visual
dataset also includes externally sourced AIGA/DOT pictograms, with per-file
provenance and licensing recorded in `data/images/provenance_commons.csv`.
The five human speech recordings use pseudonymous speaker codes.

The application event log stores structured decision metadata rather than raw
passenger words, transcripts, images or audio. Uploaded media is still processed
by the hosted pipeline, and thumbnails/transcripts can remain in session state.
Platform temporary files and logs were not assessed. The prototype has no
formal privacy notice, consent workflow, retention period or deletion routine;
these remain documented limitations rather than compliance claims.
