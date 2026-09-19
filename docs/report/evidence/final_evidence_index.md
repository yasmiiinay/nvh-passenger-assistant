# Final evidence index and assignment coverage audit

Repository: https://github.com/yasmiiinay/nvh-passenger-assistant (main at `f3a207f` when indexed; README and index updated afterwards)
Deployed prototype: https://huggingface.co/spaces/yasmincinar/nvh-assistant (Space commit `030552f`, deployment-only subset of source commit `081b279`; behavioural core identical to freeze `2d05b1c` and Blind v3 evaluated commit `f2a7ed9`)

Status values: **COMPLETE** = evidence in the repository is sufficient to support the report claim; **PARTIAL** = evidence exists but has a stated gap; **MISSING** = no evidence yet; **NOT REQUIRED** = not applicable to this design. Paths are relative to the repository root; `E/` = `docs/report/evidence/`, `C/03_2` etc. = `docs/checkpoints/03_2_*.md` and so on.

## 1. Environment setup — 10 %

| Requirement | Status | Primary evidence | Supporting evidence | Report figure/table | Appendix | Notes / remaining limitation |
|---|---|---|---|---|---|---|
| Python environment and pinned dependencies | COMPLETE | `requirements.txt` (runtime, pinned), `requirements-dev.txt` (eval/test only) | `README.md` §Setup, §Environment notes | short dependency table | `requirements*.txt` | Local venv is Python 3.14.3; Space runs 3.12 — state both |
| Core libraries and their roles | COMPLETE | `README.md` §Repository layout (module-by-module) | `configs/settings.py` model ids | — | — | torch, transformers, sentence-transformers, numpy, Pillow, soundfile/scipy, gradio |
| Run instructions | COMPLETE | `README.md` §Running the assistant, §Running the text pipeline, §Running the vision and speech pipelines | `scripts/smoke_test.py` | — | — | — |
| Repository structure | COMPLETE | `README.md` §Repository layout | tree: `app/ src/ configs/ data/ evaluation/ scripts/ tests/ docs/` | — | — | — |
| Start-up / smoke verification | COMPLETE | `E/deployment_smoke_test.md` (hosted); `scripts/smoke_test.py`, `tests/` (15 files) | `C/03_3` §2b/§5 (identical results on two machines) | — | — | — |
| Local vs hosted environment difference | COMPLETE | `E/deployment_smoke_test.md` §Deployment (3.14 vs 3.12, ZeroGPU, Hub weights, ephemeral FS) | `README.md` §Hugging Face Space status (updated to the deployed state) | — | — | state both Python versions; not identical environments |

## 2. Data acquisition and exploration — 15 %

| Requirement | Status | Primary evidence | Supporting evidence | Report figure/table | Appendix | Notes / remaining limitation |
|---|---|---|---|---|---|---|
| Visual dataset and labels | COMPLETE | `data/images/images_manifest.csv` (101 rows: category, source, quality stratum, split, notes), `data/images/provenance_commons.csv` | `docs/dataset_schemas.md` §1; `E/data_exploration/data_exploration_notes.md` | — | schema | 40 in-scope / 61 OOS; `security` and `accessibility` prompt categories have no images |
| Visual class distribution | COMPLETE | `E/data_exploration/visual_class_distribution.png` | notes file | **Fig.** class + split + quality strata | — | dev 37 / held-out 64; 64 clean icons / 37 photos |
| Representative image samples | COMPLETE | `E/data_exploration/visual_representative_samples.png` | — | appendix fig | ✓ | one dev icon per label + one OOS |
| Similar / dissimilar / generalisation examples | COMPLETE | `E/data_exploration/visual_similarity_generalisation.png` | notes file | **Fig.** (or appendix if space is short) | ✓ | dataset property, not a model result |
| Visual quality / imbalance discussion | COMPLETE | `E/data_exploration/data_exploration_notes.md` §Visual | `C/03_3` §2 | text | — | — |
| Text / intent dataset and distribution | COMPLETE | `data/text/intent_exemplars.csv` (95), `queries_seed/heldout/spoken/qa.csv` (97); `E/data_exploration/text_intent_distribution.png` | `docs/dataset_schemas.md` §2 | appendix fig | ✓ | all exemplars are dev; no held-out exemplar set |
| Vocabulary / tokenisation evidence | COMPLETE | `E/data_exploration/text_preprocessing_examples.md` (vocabulary inventory, real normaliser/entity outputs, MiniLM WordPiece example) | `data/vocabulary.json` | small table | ✓ | — |
| Audio dataset and conditions | COMPLETE | `E/data_exploration/audio_dataset_summary.md`, `audio_duration_distribution.png` | `data/audio/audio_manifest.csv`, `derived_manifest.csv`; `docs/dataset_schemas.md` §3 | compact table | ✓ | 120 TTS + 5 human, all quiet/clean; 4 derived degraded clips |
| Multimodal scenario dataset | PARTIAL | `data/multimodal/multimodal_manifest.csv` (68 authored scenarios, 35 dev / 33 held-out) | `docs/dataset_schemas.md` §4; `C/03_4` §1, §4 | — | ✓ | not covered by the 05.3 exploration package; counts come from `C/03_4` |
| KB dataset, schema and record distribution | COMPLETE | `E/data_exploration/kb_dataset_summary.md`; `data/kb/airport_kb.json`; `docs/report/appendix_A_nvh_airport_spec_and_kb.docx` | `docs/airport_spec.md`; `src/kb.py` | compact table (category × terminal) | **Appendix A** | 32 records, 12 categories, T1 24 / T2 8 |

## 3. Preprocessing — 10 %

| Requirement | Status | Primary evidence | Supporting evidence | Report figure/table | Appendix | Notes / remaining limitation |
|---|---|---|---|---|---|---|
| Text normalisation (L1/L2) | COMPLETE | `E/preprocessing/text_preprocessing_evidence.md` (real outputs, five dataset queries + one spoken-style string) | `src/normalizer.py`; `E/preprocessing/preprocessing_code_snippets.md` | **Table** (3–4 rows) | ✓ full table | — |
| Entity / identifier handling | COMPLETE | same file (entities, cues, deterministic interpretation) | `src/entities.py`, `src/retrieval.py` | same table | ✓ | — |
| Tokenisation / embeddings | COMPLETE | `E/preprocessing/text_preprocessing_evidence.md` §Where the embedding sees the text; `E/data_exploration/text_preprocessing_examples.md` §MiniLM | `src/text_encoder.py` | one line | ✓ | `xy456` → `x ##y ##45 ##6` |
| Image loading / conversion / CLIP processor | COMPLETE | `E/preprocessing/image_preprocessing_evidence.md`, `image_preprocessing_example.png` | `src/vision.py`; snippets file | appendix fig | ✓ | mean/std normalisation is inside `CLIPProcessor`, stated |
| Audio loading / resampling / Whisper processor | COMPLETE | `E/preprocessing/audio_preprocessing_evidence.md`, `audio_preprocessing_example.png` | `src/speech.py`; snippets file | appendix fig | ✓ | includes one real mis-transcription (`aud_121`) |
| Shared typed + transcribed path | COMPLETE | `E/preprocessing/preprocessing_pipeline_notes.md` | `src/speech.py::process_transcript`; architecture figure | text + figure | — | — |

## 4. Model design — 15 %

| Requirement | Status | Primary evidence | Supporting evidence | Report figure/table | Appendix | Notes / remaining limitation |
|---|---|---|---|---|---|---|
| Architecture diagram | COMPLETE | `E/architecture_multimodal_pipeline.png` / `.pdf` (+ `.py` generator) | — | **Fig. 1** | pdf | — |
| MiniLM text retrieval | COMPLETE | `src/text_encoder.py`, `src/intent.py`, `src/retrieval.py` | `C/03_2` §1, §5 (threshold choice), §6 (category-cue experiment) | text | — | nearest-exemplar intent; no classifier trained |
| CLIP ViT-B/32 vision | COMPLETE | `src/vision.py`, `data/vision_prompts.json` | `C/03_3` §1–2b (prompt design, flatten-on-white bug, thresholds) | text | — | zero-shot; scores are similarities |
| Whisper-base speech | COMPLETE | `src/speech.py` | `C/03_3` §3–5 (size choice, gate, English forcing) | text | — | — |
| Deterministic routing / fusion | COMPLETE | `src/router.py` (rules R0–R6 in docstring) | `C/03_4` §3 (routing design table), §5 | **Table** (rule order, compact) | full rule table ✓ | nothing averaged |
| KB retrieval cascade | COMPLETE | `src/retrieval.py` docstring (frozen order), `src/kb.py` | `C/03_1`, `C/03_2` §4 | text | — | deterministic before semantic |
| Uncertainty / conflict handling | COMPLETE | `configs/settings.py` thresholds; `src/retrieval.py::decide`; router R4 | `C/03_2` §5, `C/04_4` §1 | thresholds table | — | — |
| Template response generation | COMPLETE | `src/responses.py` | `C/04_6` | text | — | no generative model |
| Five modality combinations | COMPLETE | `src/router.py`; `C/03_4` §4 (routing evaluation over combinations); Blind v3 multimodal set (image-only, voice-only, text+image, voice+image) | all five exercised on the Space: smoke tests A–E plus live-microphone tests F (voice) and G (voice + image) | — | — | — |
| Design rationale and alternatives considered | COMPLETE | `C/03_2` §5–6 (threshold selection, category-cue experiment), `C/03_3` §1, §3 (CLIP prompt design, Whisper size choice), `C/03_4` §3 (routing design), `C/04_5` (post-blind revision decisions), `configs/settings.py` comments, `README.md` §Versions | — | text | checkpoint sections ✓ | rationale is evidenced across the existing checkpoint artefacts; the earlier planning documents (Architecture Freeze v1.1, Evidence Pack 02B2) are deliberately not added to the repository — the report cites the checkpoints |
| Explicit non-features | COMPLETE | `README.md`; `E/architecture_multimodal_pipeline.png` footer; `configs/settings.py` (`enable_ocr=False`, `similarity_backend="numpy"`) | `E/ethics/` | one sentence | — | no generative LLM, no OCR, no runtime FAISS, no live API |

## 5. Training / evaluation — 20 %

| Requirement | Status | Primary evidence | Supporting evidence | Report figure/table | Appendix | Notes / remaining limitation |
|---|---|---|---|---|---|---|
| Text: intent P/R/F1 | COMPLETE | `C/03_2` §3 (dev 43: accuracy 0.791, macro-F1 0.768, per-intent P/R/F1 table) | `evaluation/text_metrics.py`; held-out comparisons in `C/03_4` §2, `C/04_5` §Final v1.1 metrics | per-intent table → appendix; headline in **core metrics table** | ✓ | no trained classifier, so "training" = threshold selection on dev |
| Text: confusion matrix | PARTIAL | none committed as a figure | per-intent table in `C/03_2` §3 substitutes | optional appendix fig | — | could be generated from committed results without new runs; not done |
| Text: retrieval / record outcomes, safe outcomes | COMPLETE | `C/03_2` §4, `C/04_4` §Consolidated, `C/04_5` §Final v1.1 metrics (dev 36/43, held-out 24/36, wrong record 0) | Blind v3 text | **core metrics table** | ✓ | — |
| Vision: top-1, top-3, by stratum, OOS, failure analysis | COMPLETE | `C/03_3` §2b (dev top-1 0.947, held-out 0.857; top-3; per stratum; OOS behaviour; misses interpreted) | Blind v3 image results | **core metrics table** | ✓ | — |
| Speech: WER, downstream outcomes, error types | COMPLETE | `C/03_3` §5 (dev WER L1 0.157 / L2 0.151, propagation), `C/04_4` §Consolidated (dev / held-out / human WER 0.151 / 0.092 / 0.421; outcome kept 91/100, 17/20, 3/5) | `E/preprocessing/audio_preprocessing_evidence.md` (mis-transcription); `evaluation/speech_metrics.py` | **core metrics table** | ✓ | human-speaker WER 0.421 on 5 clips is the honest counterweight to Blind v3's 0.015 |
| Multimodal: decision, routing, conflict P/R, wrong-confident | COMPLETE | `C/03_4` §4–6 (routing 1.00 / 0.97), `C/04_4` §1 (conflict precision 0.71 → 1.00), `C/04_5` (held-out 24/33, wrong-confident 0) | Blind v3 multimodal | **core metrics table** | ✓ | — |
| Blind v3: independent authoring protocol | COMPLETE | `docs/evaluation/blind_v3/PROTOCOL_V3.md`, `AUTHOR_BRIEF_V3.md` | pre-registration commit `80eff16` | text | ✓ | — |
| Blind v3: dataset freeze and one-run methodology | COMPLETE | `final_blind_v3_*.csv` + `blind_v3_*_sha256.txt` + `SELF_CHECK_V3.txt` (repo root); `scripts/verify_blind_set.py`; freeze commit `f2a7ed9`; results commit `18c71ed` | `scripts/run_final_blind.py` | text | ✓ | evaluated commit's core is byte-identical to `2d05b1c` |
| Blind v3: final metrics | COMPLETE | `docs/report/final_blind_evaluation_v3/final_blind_v3_summary.md` + `.json` + four results CSVs | — | **Blind v3 table** | ✓ per-case CSVs | text 17/20, category 16/17, record 8/11, safe 18/20, wrong-confident 2; vision top-1 5/6, top-3 6/6, in-scope 3/6, OOS 2/2, wrong-confident 0; speech WER 0.015, 6/6; multimodal decision 9/12, routing 11/12, record 4/6, conflict P 1.00 R 0.50, wrong-confident 0 |
| Blind v3: known limitations | COMPLETE | `final_blind_v3_summary.md` (per-failure analysis); `C/04_5` §Remaining limitations | `E/user_testing/` | text | — | identifier overriding requested service; PRM ranking; non-existent ranges → clarify; some live-gate phrasing; uncertain image not a conflict; photographed signs harder; no OCR |
| Blind v1 / v2 (earlier sets) | COMPLETE (context only) | `docs/report/final_blind_evaluation/`, `final_blind_evaluation_v2/`; `C/04_5` | — | mention only | ✓ | **not a controlled series**: datasets and builds differ; v3 is the evaluation of the frozen build |
| Metrics graphs | PARTIAL | none committed; all metrics are tables | — | optional one figure | — | a single bar chart from `final_blind_v3_summary.json` is report-side work, not a new run |
| Harness-vs-UI limitation | COMPLETE | `E/deployment_smoke_test.md` §Scope; `E/user_testing/` §Distinction | `scripts/run_final_blind.py` imports `src/` not `app/`; `tests/test_app.py` covers `run_turn` | one sentence | — | must be stated in the report |

## 6. Deployment and user testing — 15 %

| Requirement | Status | Primary evidence | Supporting evidence | Report figure/table | Appendix | Notes / remaining limitation |
|---|---|---|---|---|---|---|
| Deployed prototype link | COMPLETE | https://huggingface.co/spaces/yasmincinar/nvh-assistant | `E/deployment_smoke_test.md` §Deployment (commits, hardware, SDK) | link | — | public; cite the `huggingface.co/spaces/...` URL |
| Exact deployment record | COMPLETE | `E/deployment_smoke_test.md` | local branch `deploy-space`; README YAML block | small table | ✓ | deployment-only subset, README `short_description` differs by one line |
| UI screenshots | COMPLETE | `E/ui_deployment_text.png`, `ui_deployment_multimodal.png`, `ui_deployment_uncertainty.png` (+ four `extra_*`, + `ui_deployment_live_voice*.png` at retina resolution) | `docs/report/screenshots/` (pre-deployment UI states: empty, strong match, clarify, conflict, evidence panel, narrow 400 px); `docs/checkpoints/images/` | **Fig.** one screenshot or 2–3 panel | ✓ | deployment shots are 1512×691 viewport captures |
| Text / image / voice-upload / multimodal / uncertainty smoke tests | COMPLETE | `E/deployment_smoke_test.md` §Smoke tests; `E/deployment_smoke_test_captures.md` (verbatim page text) | screenshots | — | ✓ | inputs chosen to avoid all Blind v3 items |
| Structured five-scenario table | COMPLETE | `E/user_testing/structured_user_testing.md` (+ `.csv`) | evidence-class note; captures file | **Table** | ✓ full version | integration verification by the developer, no external participants — never "user study" |
| Evidence audit of the scenarios | COMPLETE | `E/user_testing/structured_user_testing.md` §Evidence classes | commit `64cf04c` | — | ✓ | expectations for scenarios 3–5 are post-hoc, stated |
| Live microphone capture on the Space | COMPLETE | `E/deployment_smoke_test.md` §Live-microphone verification (test F), `E/ui_deployment_live_voice.png` | `E/user_testing/` §Limitations | — | ✓ | manual verification, 2026-09-19; upload path verified separately in test C |
| Voice + image on the deployed Space | COMPLETE | `E/deployment_smoke_test.md` §Live-microphone verification (test G), `E/ui_deployment_live_voice_photo.png` | evaluated offline in `C/03_4` and Blind v3 MM3_B11–12 | — | ✓ | image-led route with the spoken terminal narrowing; verification only, not an evaluation case |
| Manual QA / usability evidence (pre-deployment) | COMPLETE | `docs/report/manual_usability_diagnostics_046.md`; `C/04_1`–`04_6`; `tests/test_usability_046.py` | screenshots in `docs/report/screenshots/` | mention | ✓ | manual QA, not blind evaluation |

## 7. Ethics / regulatory — 15 %

| Requirement | Status | Primary evidence | Supporting evidence | Report figure/table | Appendix | Notes / remaining limitation |
|---|---|---|---|---|---|---|
| Privacy / data minimisation, event logging, ticket note | COMPLETE | `E/ethics/ethics_regulatory_evidence.md` §2, §9 | `src/event_log.py`, `app/app.py`, `README.md` §Provenance and privacy | **ethics matrix** (compact) | ✓ full file | note field is the one PII-capable stored field; no notice/consent/retention routine |
| Uploaded-media risks, sensitive passenger information | COMPLETE | §3 | no OCR (`configs/settings.py`) | matrix | ✓ | platform temp-file handling unknown |
| ASR bias | COMPLETE | §4 | `E/data_exploration/audio_dataset_summary.md`; `E/preprocessing/audio_preprocessing_evidence.md`; Blind v3 | matrix | ✓ | no demographic evaluation performed |
| Vision generalisation | COMPLETE | §5 | `E/data_exploration/`; Blind v3 | matrix | ✓ | — |
| English-only limitation | COMPLETE | §6 | `src/speech.py` forced English | matrix | — | — |
| Accessibility | COMPLETE | §7 | `app/app.py` STATUS/CSS; KB accessibility fields; PRM records | matrix | — | design consideration, no WCAG audit |
| Uncertainty / false certainty, official redirects | COMPLETE | §8 | `src/retrieval.py`, `src/responses.py`; Blind v3 limits | matrix | — | — |
| No live data, no human-agent backend | COMPLETE | §8, §9 | `app/app.py::request_assistance` | matrix | — | ticket file ephemeral on the Space |
| Synthetic-data limitations | COMPLETE | §10 | `README.md` §Provenance; `E/data_exploration/` | text | — | — |
| GDPR-oriented discussion | COMPLETE | §11 (no compliance claim) | — | text | — | external references required (see asset plan) |
| Ethics matrix | COMPLETE | `E/ethics/ethics_matrix.csv` (12 rows) | — | **Table** (trimmed to 6–8 rows if space is short) | ✓ full | — |

## Final submission requirements

| Item | Status | Evidence |
|---|---|---|
| Architecture diagram | COMPLETE | `E/architecture_multimodal_pipeline.png/.pdf` |
| Data-exploration outputs | COMPLETE | `E/data_exploration/` (9 files) |
| KB schema | COMPLETE | `docs/report/appendix_A_nvh_airport_spec_and_kb.docx`; `E/data_exploration/kb_dataset_summary.md`; `docs/dataset_schemas.md` |
| Preprocessing evidence | COMPLETE | `E/preprocessing/` (7 files) |
| Model design | COMPLETE | source + architecture figure + checkpoint rationale (`C/03_2`–`C/04_5`) |
| Component evaluation | COMPLETE | `C/03_2`, `C/03_3`, `C/03_4`, `C/04_4`, `C/04_5` |
| Metrics tables / graphs | PARTIAL | tables complete (checkpoints + Blind v3 summary); no committed graph |
| UI screenshots | COMPLETE | `E/ui_deployment_*.png`; `docs/report/screenshots/` |
| Structured scenarios | COMPLETE | `E/user_testing/` |
| Critical limitations | COMPLETE | `final_blind_v3_summary.md`; `C/04_5` §Remaining limitations; `E/data_exploration/data_exploration_notes.md`; `E/ethics/` §4–10 |
| Ethics | COMPLETE | `E/ethics/` |
| Working prototype link | COMPLETE | Space URL above |
| GitHub / supplementary code | COMPLETE | repository URL above; `scripts/report/` regenerates the evidence |
| Appendices | COMPLETE (material ready) | Appendix A docx exists; other appendix candidates marked ✓ above |
| Harvard references | MISSING | not yet compiled — a report-writing task; checklist in `final_report_asset_plan.md` |

## Counts

COMPLETE 76 · PARTIAL 4 · MISSING 1 · NOT REQUIRED 0 (81 indexed rows across the seven areas and the submission list; the submission list re-counts some items).

## Final gap audit

**A. Genuinely missing.** The Harvard reference list — it does not exist yet and belongs to the report-writing stage. Nothing else is missing.

**B. Partial.**
1. ~~README §Hugging Face Space status out of date~~ — updated (docs-only).
2. ~~Design-rationale document not in the repository~~ — closed by decision: rationale is evidenced across the existing checkpoint artefacts and the report cites those; the planning documents are not added.
3. No committed confusion matrix or metrics graph; all evaluation results are tables. Optional: one figure generated from the committed Blind v3 JSON (no new runs).
4. ~~Live microphone capture unverified~~ — verified manually on 2026-09-19 (test F).
5. ~~Voice + image not smoke-tested on the Space~~ — verified manually on 2026-09-19 (test G).
6. The multimodal scenario manifest (68 rows) is described in `C/03_4` and `docs/dataset_schemas.md` but was not part of the 05.3 exploration package.
7. Local Python 3.14 vs Space Python 3.12 — documented, must be stated rather than assumed identical.
8. Deployment screenshots are viewport captures (1512×691); higher-resolution retakes are optional.

**C. Exists but should stay appendix-only.** Per-intent P/R/F1 table; per-case Blind v3 CSVs and the v1/v2 folders; the four `ui_deployment_extra_*` screenshots and `docs/report/screenshots/`; the full preprocessing traces and code snippets; `visual_representative_samples.png` and `audio_duration_distribution.png`; the full ethics file and 12-row matrix; the verbatim capture file; the evidence-class audit; Appendix A.

**D. Methodological limitations that must be disclosed.** Blind v1→v2→v3 are not a controlled series; Blind v3 drove `src/` directly, not `app/app.py`; thresholds were set on 43 dev queries and 19 in-scope dev images; the speech set is 96 % TTS with one human speaker; two vision prompt categories have no images; the five scenarios are developer-run integration checks with post-hoc expectations for three of them; no external participants, no WCAG audit, no fairness evaluation; English-only; synthetic airport and KB; hosted retention is a platform property, not a control.

**E. Must not be changed now (frozen).** `src/`, `configs/`, `data/`, `evaluation/`, `app/app.py` behaviour, every Blind v1/v2/v3 file and SHA, the Space's deployed commit. The wording inconsistencies found in 05.5 (terminal-unknown line, action-request reason) and the Blind v3 limitation list are future work, not fixes to apply before the report.
