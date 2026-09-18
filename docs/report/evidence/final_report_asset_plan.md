# Final report asset plan (2500–3000 words)

Companion to `final_evidence_index.md`. Everything listed exists in the repository unless marked *to produce*; nothing here requires a new run, a change to the frozen build, or new results.

## Recommended figures for the main report

| # | Figure | Source file | Why in the main body |
|---|---|---|---|
| Fig. 1 | Architecture of the implemented multimodal pipeline | `docs/report/evidence/architecture_multimodal_pipeline.pdf` (vector; PNG fallback) | required by the brief; shows the shared text path, CLIP evidence, deterministic router, KB and template responses |
| Fig. 2 | Visual dataset: images per label with split, and source/quality strata | `docs/report/evidence/data_exploration/visual_class_distribution.png` | the single figure that carries the class-imbalance and clean-icon-bias argument |
| Fig. 3 | Similar symbols, clean vs photographed vs degraded, out-of-scope | `docs/report/evidence/data_exploration/visual_similarity_generalisation.png` | makes the vision-generalisation limitation visible; drop to appendix if the word count is tight |
| Fig. 4 | Deployed interface | `docs/report/evidence/ui_deployment_multimodal.png` (photo + text + evidence) — or a 2-panel with `ui_deployment_uncertainty.png` | one screenshot that shows input, answer/clarification, badge and evidence panel at once |
| optional Fig. 5 | Blind v3 headline metrics as a bar chart | *to produce* from `docs/report/final_blind_evaluation_v3/final_blind_v3_summary.json` (report-side plotting, no new evaluation) | only if the module expects a graph; the table (Table 4) already carries the numbers |

## Recommended tables for the main report

| # | Table | Source | Size guidance |
|---|---|---|---|
| Table 1 | Datasets at a glance: images (101; 40/61; 37/64; 64/37), text (95 exemplars, 97 labelled queries), audio (125 + 4; 120 TTS / 5 human), KB (32 records, 12 categories, 24/8), multimodal scenarios (68) | `data_exploration/*.md`, `kb_dataset_summary.md`, `C/03_4` | 5 rows |
| Table 2 | Preprocessing trace: 3 real queries through L1 → L2 → entities → deterministic stage, plus the `xy456` tokenisation line | `preprocessing/text_preprocessing_evidence.md` | 3–4 rows; image/audio traces go to the appendix |
| Table 3 | Core component evaluation (development / held-out): text outcome accuracy and wrong-record count; intent accuracy and macro-F1; vision top-1/top-3 by split and stratum; speech WER (dev / held-out / human) and outcome-kept counts; multimodal decision, routing, conflict P/R, wrong-confident | `C/03_2` §3–4, `C/03_3` §2b, §5, `C/04_4` §Consolidated, `C/04_5` §Final v1.1 metrics | one table, ≤ 12 rows |
| Table 4 | Blind v3 results (46 cases): text 17/20, 16/17, 8/11, safe 18/20, wrong-confident 2; vision 5/6, 6/6, 3/6, OOS 2/2, wrong-confident 0; speech WER 0.015, 6/6; multimodal 9/12, 11/12, 4/6, conflict P 1.00 / R 0.50, wrong-confident 0 | `final_blind_v3_summary.md` | one table, 4 blocks |
| Table 5 | Structured deployment scenarios (five rows; the eight columns trimmed to input, expected, actual, verdict, limitation) | `user_testing/structured_user_testing.md` | fit to one page; full version in appendix |
| Table 6 | Ethics and residual risk (6–8 rows from the 12-row matrix: log contents, uploaded media, ASR bias, vision generalisation, English-only, false certainty, live data / handover, accessibility) | `ethics/ethics_matrix.csv` | include if word count permits; otherwise cite the appendix |
| optional Table 7 | Router rule order R0–R6 | `src/router.py` docstring; `C/03_4` §3 | 7 rows; alternatively describe in prose and put the table in the appendix |

## Appendix / repository mapping

| Appendix | Content | Source |
|---|---|---|
| A | Nordhaven airport specification and KB schema | `docs/report/appendix_A_nvh_airport_spec_and_kb.docx`; `docs/dataset_schemas.md`; `kb_dataset_summary.md` |
| B | Data exploration: representative samples, intent distribution, audio durations, dataset observations | `data_exploration/visual_representative_samples.png`, `text_intent_distribution.png`, `audio_duration_distribution.png`, `data_exploration_notes.md` |
| C | Preprocessing traces: image and audio evidence with figures, code excerpts, pipeline notes | `preprocessing/*` |
| D | Design rationale: threshold selection, category-cue experiment, Whisper size choice, prompt design, routing design | `C/03_2` §5–6, `C/03_3` §1–3, `C/03_4` §3, `configs/settings.py`; add the Architecture Freeze v1.1 document here if it is brought into `docs/` |
| E | Complete evaluation: per-intent P/R/F1, per-stratum vision results, speech propagation, QA before/after tables, final v1.1 metrics | `C/03_2`, `C/03_3`, `C/03_4`, `C/04_4`, `C/04_5` |
| F | Blind v3 protocol, author brief, freeze evidence and per-case results | `docs/evaluation/blind_v3/*`, `final_blind_evaluation_v3/*`, `blind_v3_*_sha256.txt`, `SELF_CHECK_V3.txt` |
| G | Deployment record, verbatim captures, extra screenshots, pre-deployment UI states | `deployment_smoke_test.md`, `deployment_smoke_test_captures.md`, `ui_deployment_extra_*.png`, `docs/report/screenshots/` |
| H | Structured scenarios (full eight columns) and the evidence-class audit | `user_testing/structured_user_testing.md`, `.csv` |
| I | Ethics and regulatory evidence (full) and the 12-row matrix | `ethics/*` |
| J | Environment: pinned requirements, Space configuration, local/hosted differences | `requirements*.txt`, README YAML block, `deployment_smoke_test.md` §Deployment |

Do not duplicate: a figure or table that is in the main body is only cited, not repeated, in the appendix.

## Suggested report structure and word budget (target 2 800)

| § | Section | Words | Assets | Draws on |
|---|---|---|---|---|
| 1 | Introduction and problem definition — passenger assistance, three modalities, why retrieval over generation, scope (fictional NVH, English-only) | 220 | — | README, ethics §1, §6 |
| 2 | Environment and data — setup, local vs hosted, datasets and their limits, KB | 400 | Fig. 2, (Fig. 3), Table 1 | index §1–2 |
| 3 | Preprocessing — one text pipeline for typed and spoken input, image path, what is inside the HF processors | 300 | Table 2 | index §3 |
| 4 | Model and multimodal fusion design — MiniLM cascade, CLIP as retrieval, Whisper hand-off, router R0–R6, uncertainty policy, template responses; explicit non-features | 450 | Fig. 1, (Table 7) | index §4 |
| 5 | Evaluation and critical analysis — component results, Blind v3 protocol and results, failure analysis, threshold and margin trade-offs, harness-vs-UI limitation, why v1–v3 is not a series | 750 | Table 3, Table 4, (Fig. 5) | index §5 |
| 6 | Deployment and structured testing — Space, smoke tests, five scenarios, integration-verification framing, live-mic gap | 300 | Fig. 4, Table 5 | index §6 |
| 7 | Ethics and regulatory considerations — data minimisation as implemented, media risks, ASR/vision bias, English-only, accessibility, false certainty, no live data / handover, GDPR-oriented assessment | 350 | Table 6 | index §7 |
| 8 | Conclusion and future work | 130 | — | index gap audit §B, ethics §12 |
| | **Total** | **2 900** | | |

Evaluation (§5) carries the largest allocation; §2 is next because the datasets bound every later claim.

## External reference checklist (Harvard; none cited here — all require lookup)

| Needed for | Source to cite | Status |
|---|---|---|
| Sentence embeddings, all-MiniLM-L6-v2 | Sentence-BERT paper (Reimers & Gurevych) and the model card | verify authors, year, venue, model-card URL |
| CLIP zero-shot similarity and its documented biases | CLIP paper (Radford et al.) | verify year, venue |
| Whisper-base, multilingual capability, robustness | Whisper paper (Radford et al.) | verify year; note the model card for `whisper-base` |
| Hugging Face Transformers (pipeline, CLIPProcessor, WhisperFeatureExtractor) | Transformers library paper (Wolf et al.) and documentation | verify |
| Gradio Blocks | Gradio paper (Abid et al.) or documentation | verify |
| Vector search alternative discussed (FAISS, dev-only equivalence check) | FAISS paper (Johnson et al.) | verify; cite only if FAISS is discussed |
| Word error rate definition | standard ASR evaluation reference | choose an authoritative source |
| AIGA/DOT symbol signs (visual dataset source) | AIGA / US DOT symbol-sign set; Wikimedia Commons category recorded in `images_manifest.csv` licence fields | verify licence statement and URL |
| GDPR principles (Art. 5), transparency (Art. 12–14), special categories (Art. 9) | Regulation (EU) 2016/679 | cite the regulation text; verify article numbers |
| Voice and image data guidance | UK ICO guidance on biometric / video data (or equivalent supervisory authority) | verify title and date |
| Accessibility | WCAG 2.1 (W3C Recommendation) | verify version and date |
| AI transparency obligations (optional) | EU AI Act | cite only if used; verify |
| Assignment brief | AI7016 Multi-Modal Chatbots set exercise (Oct 2025) | cite the module document |

Every row above requires external verification of bibliographic details before it enters the reference list; nothing in this file should be copied into the references as-is.
