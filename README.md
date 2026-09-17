---
title: NVH Assistant
emoji: ✈️
colorFrom: blue
colorTo: gray
sdk: gradio
sdk_version: 5.50.0
python_version: '3.12'
app_file: app/app.py
pinned: false
license: mit
short_description: Multimodal airport passenger assistant (AI7016, fictional NVH airport)
---

# Smart Airport Passenger Assistance Multimodal Chatbot (AI7016)

A multimodal (image / voice / text) assistant for a **fictional** airport,
Nordhaven International (NVH), answering passenger questions from a structured,
fully synthetic knowledge base. MSc set exercise; the design is fixed in
`Architecture Freeze v1.1` and evidenced in `Evidence Pack 02B2` (project docs).

Core stack (frozen): CLIP ViT-B/32 (zero-shot image labelling with
out-of-scope anchors) · Whisper-base (ASR) + airport text normaliser ·
MiniLM sentence embeddings for intent-by-similarity and semantic KB retrieval ·
deterministic retrieval cascade (exact identifier → alias → category-filtered
semantic → full semantic → answer/clarify/abstain/redirect) · template
responses grounded in KB records · Gradio Blocks UI. No generative model
anywhere; EasyOCR is an optional, flag-gated enhancement.

## Supported visual scope (v1.1, stated after Blind Evaluation v1)

The photo path recognises the **kind** of airport sign in an image: its
category (restroom, security, transport, …) from CLIP similarity to the
category prompts, with out-of-scope anchors and a similarity band. It does
**not** read text: desk numbers, gate identifiers, terminal names or any
text-only sign content are invisible to it, because EasyOCR is a gated
enhancement that is switched off (`enable_ocr = False`). A photo of a "C7"
gate marker is therefore a gate-category sign at best, never gate C7.
Blind Evaluation v1 (`docs/report/final_blind_evaluation/`) contained
several text-dependent image cases; their results are kept unchanged, and
this paragraph records the scope they exposed rather than moving them.

## Repository layout

| Path | Responsibility (one sentence) |
|---|---|
| `app/` | The passenger assistant interface (`gr.Blocks`): text, photo and voice inputs, answer, match band, evidence panel, assistance request. |
| `configs/` | The single `Settings` dataclass every script reads; thresholds live here and nowhere else. |
| `data/kb/` | The synthetic knowledge base (`airport_kb.json`, 32 records). |
| `data/images/`, `data/audio/`, `data/multimodal/` | Datasets per `docs/dataset_schemas.md`: 101 labelled images (64 AIGA/DOT pictograms from Wikimedia Commons, 30 symbols cropped from screen photographs, 7 unrelated photographs), 125 audio clips (120 synthetic from five macOS voices, 5 human) plus 4 derived low-quality clips, and 68 authored multimodal scenarios. |
| `data/text/` | Seed query set (`queries_seed.csv`, 43 rows, dev), the held-out set (`queries_heldout.csv`, 36 rows, frozen before any run) and the dev-only intent exemplars (`intent_exemplars.csv`, 95 phrasings for the 15 intents). |
| `data/vocabulary.json` | Frozen controlled vocabulary shared by image labels, intents, entities, KB categories and routing. |
| `docs/` | Airport specification, dataset schemas, and project documents. |
| `evaluation/` | Metric modules (pure functions now; model outputs plug in from the pipeline phase). |
| `outputs/` | Everything generated (benchmarks, evaluation artefacts); git-ignored except `.gitkeep`. |
| `scripts/` | Runnable utilities: `smoke_test.py`, `benchmark_env.py`, `audit_foundation.py`, `run_deterministic_seed.py` (checkpoint 03.1), `run_text_pipeline_seed.py` (checkpoint 03.2), `run_vision_eval.py` and `run_speech_eval.py` (checkpoint 03.3), `run_multimodal_eval.py` (checkpoint 03.4), `run_text_regression.py` (Chat 04 QA text regression queries), and the dataset helpers `build_image_manifest.py`, `make_tts_audio.py`, `add_recordings.py`. |
| `src/` | Pipeline code: `kb.py` (KB loading, identifier expansion), `foundation_audit.py`, `normalizer.py` (L1/L2 text normalisation), `entities.py` (regex + KB-derived gazetteers), `text_encoder.py` (MiniLM, loaded on first use), `intent.py` (intent by nearest exemplar), `retrieval.py` (the full text cascade: deterministic stages, then intent, category filter, cosine similarity and the score + margin decision), `responses.py` (template answers from record fields, with the caveat sentences each flag requires, and the multimodal renderings), `router.py` (the deterministic multimodal routing rules and conflict surfacing), `event_log.py` (JSONL event log and the escalation record), `vision.py` (image checks, CLIP zero-shot ranking against category prompts, KB records and out-of-scope anchors), `speech.py` (audio gate, Whisper-base transcription, hand-off of the transcript into the same text cascade). |
| `models/` | Local model copies (git-ignored): `all-MiniLM-L6-v2/`, `clip-vit-base-patch32/`, `whisper-base/`. A local copy is used when present; otherwise the hub id from `configs/settings.py` is fetched on first use. |
| `tests/` | Consistency gate plus unit tests per module (`python -m pytest tests`). |

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

## Environment notes — what is verified and what is not

- **Verified (11 Sep 2026):** all three requirement sets resolve together with
  `uv pip compile` on **Linux x86_64 / Python 3.12** with the pins held
  (`torch==2.9.1` remains pinned even with `easyocr` added). Resolution is not
  installation; no model was executed in that check.
- **Not yet verified (label kept until measured):** installation and imports on
  **macOS arm64** (run `scripts/smoke_test.py` locally); actual CPU latency and
  memory for any model (run `scripts/benchmark_env.py` — loaders land in
  pipeline phase); behaviour on the Hugging Face Space.
- Pin policy: latest **mature** lines, not latest majors (e.g. `transformers`
  4.57.x and `gradio` 5.50.0 rather than the 5.x/6.x majors released later),
  because the course reference notebooks and the model cards used here are
  from those lines. Revisit only if a concrete blocker appears.
- On Linux, the default PyPI `torch` wheel pulls CUDA support packages that a
  CPU-only Space never uses; if Space build time or disk becomes a problem,
  a Space-specific requirements variant using the CPU wheel index is the
  documented fallback (to be tested on the Space, not assumed).
- Models download at first use into the HF cache; on Spaces the disk is
  **non-persistent**, so set `HF_HOME` (and `EASYOCR_MODULE_PATH` if OCR is
  ever enabled) to project-local paths and expect re-downloads after rebuilds.

## Hugging Face Space status

Space `yasmincinar/nvh-assistant` (Gradio SDK, MIT) was created on 12 Sep 2026
and a hello-world version of `app/app.py` passed the deployment smoke test
there; the real interface has not yet been built on the Space.
Observed facts: the free plan offers **ZeroGPU only** (CPU Basic is not
selectable), and ZeroGPU's startup check requires at least one
`@spaces.GPU`-decorated function — hence the inert `zerogpu_probe()` in
`app/app.py`. The YAML block at the top of this README is the Space
configuration (`app_file`, pinned `sdk_version`, `python_version: 3.12` so
numpy installs from a wheel).

**Source of truth is this GitHub repository.** The Space is updated by
pushing `main` to it at deployment checkpoints (final deployment), not automatically;
the pinned `requirements.txt` has not yet been built on the ZeroGPU image,
and that build is the first step of the final deployment, not a side effect
of every commit. The YAML block above is what makes a plain `git push` to the
Space deployable when that time comes.

## Running the text pipeline

```bash
python -m pytest tests                       # 166 tests; the MiniLM ones skip if the model is unavailable
python scripts/run_deterministic_seed.py     # checkpoint 03.1: deterministic stages only -> outputs/checkpoint_03_1/
python scripts/run_text_pipeline_seed.py     # checkpoint 03.2: full cascade, intent metrics, threshold grid -> outputs/checkpoint_03_2/
python scripts/run_text_pipeline_seed.py --set heldout   # same pipeline on the frozen held-out set, no tuning
python scripts/benchmark_env.py --model minilm --warmup 1 --runs 3        # load time and RSS
python scripts/benchmark_env.py --model minilm_encode --warmup 1 --runs 5 # encode latency
python -m src.normalizer                     # prints the normaliser rule table (report appendix)
```

## Running the assistant

```bash
python app/app.py                       # local interface at http://127.0.0.1:7860
python scripts/run_multimodal_eval.py --split dev        # 35 authored scenarios -> outputs/checkpoint_03_4/multimodal/dev/
python scripts/run_multimodal_eval.py --split heldout    # 33 held-out scenarios, run once
python scripts/run_multimodal_eval.py --split regression # scenarios written after interface defects (Chat 04 QA), reported separately
python scripts/run_text_regression.py                     # text-only regression queries with expected flags (data/text/queries_qa.csv)
python scripts/run_multimodal_eval.py --split dev --confirm-image-only   # conservative image-only variant
```

Models load on the first question. Each turn appends one line to
`outputs/logs/events.jsonl` (ids, decision, band, scores, flags, latency;
no words, no media); an assistance request appends a ticket with a
reference number to `outputs/logs/tickets.jsonl`.

The page shows the session as a conversation, but that is presentation
only: each request is routed on its own from the current text, photo and
audio, earlier turns are never added to a new request, and "Clear
conversation" only empties the screen. The status next to every answer is
a symbol plus words (strong match, uncertain, no reliable match, question
back to you, inputs disagree, official information), so colour is never
the only signal; the similarity numbers behind it sit under "Evidence &
details" and are described there as retrieval distances, not
probabilities. Quick-reply buttons after a clarification or a conflict
fill in the request the answer asks for (for example "security in
Terminal 1", or the same question without the photo) and send it through
the same path as a typed one. The layout was reworked after the blind
evaluations (see `docs/checkpoints/05_0_ui_presentation.md`); no
retrieval, routing, threshold, knowledge-base or model code changed.

## Running the vision and speech pipelines

```bash
python scripts/run_speech_eval.py --split dev              # Whisper on the synthetic dev clips -> outputs/checkpoint_03_3/speech/dev_tts/
python scripts/run_speech_eval.py --split heldout          # same on the held-out clips
python scripts/run_speech_eval.py --split dev --speakers human   # human recordings only (after add_recordings.py)
python scripts/run_vision_eval.py --split dev              # CLIP on the labelled images; writes STATUS.md while the manifest is empty
python scripts/benchmark_env.py --model whisper --warmup 1 --runs 3
python scripts/benchmark_env.py --model clip --warmup 1 --runs 3
```

Transcripts go through the same normaliser and entity extractor as typed
text; the speech evaluation reports WER at both normalisation levels, the
identifier tokens recovered, and how often the outcome reached from the
transcript matches the outcome reached from the typed reference. The audio
gate bounds (`audio_min_seconds` etc.) and the vision thresholds (unset until
a labelled dev image split exists) are in `configs/settings.py`.

Decision thresholds (`tau_high`, `tau_low`, `margin_delta`, `tau_intent`) live
in `configs/settings.py` and were chosen on the 43-query dev split by the
coarse grid in `run_text_pipeline_seed.py`; the held-out split is not used
for them. Displayed scores are cosine similarities, not probabilities.

## Provenance and privacy

Everything in `data/` is synthetic and authored for this project; no real
airport's data was copied, and `source: synthetic` is machine-checked by the
audit. Planned audio recordings use pseudonymous speaker codes and written
consent; the running system will not retain raw audio or images (see the
Evidence Pack's GDPR section).
