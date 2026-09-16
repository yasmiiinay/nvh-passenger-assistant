# Dataset Schemas v1 (frozen 02C)

Schemas, populated during Chat 03 (see the checkpoint notes for counts). Header-only manifest CSVs sit
in each data folder so collection starts by filling rows, not inventing columns.
Controlled values (category, intent, query_type, split, decision outcomes) come
from `data/vocabulary.json` and are validated by `scripts/audit_foundation.py`.

## 1. Image dataset — data/images/images_manifest.csv

| Field | Meaning / allowed values |
|---|---|
| image_id | `img_###`, unique |
| category | controlled vocabulary category (visual classes only) |
| source | `aiga_dot` \| `own_photo` \| `commons` |
| licence | e.g. `copyright-free (AIGA)`, `own work`, `CC BY 4.0`, `CC0` — CC BY-SA avoided (Evidence Pack A1) |
| licence_url | link to the licence/file page; blank only for own photos |
| attribution | attribution string even when not legally required |
| modified | `yes`/`no` (crop/resize counts as yes) |
| source_type | quality stratum origin: `clean_icon` \| `photo_signage` |
| quality_stratum | `clean` \| `real_good_light` \| `real_degraded` (RQ1 strata) |
| split | `dev` \| `heldout` |
| expected_label | equals `category`; kept explicit so mislabels are auditable |
| optional_identifier | identifier visible in the image (e.g. `B12`) or blank — feeds the OCR enhancement and conflict scenarios |
| notes | anything a reviewer needs |
| file | path relative to `data/images/`, e.g. `files/img_001.gif`; added at the vision checkpoint so the manifest is runnable |

Images with no airport meaning (used to test out-of-scope detection) carry
`category` and `expected_label` = `out_of_scope`, which is not a vocabulary
category and is never a retrieval target.

Collection rules (from Evidence Pack A1): no identifiable people, no third-party
logos, no boarding passes/documents; per-file licence check for Commons items.

## 2. Text dataset — data/text/queries_seed.csv (already populated: 43 rows)

query_id, query, intent, entities_json (JSON object as string), target_kb_id
(blank allowed only when expected_behaviour ≠ answer), query_type, expected_behaviour
(decision outcome), split, notes.

`data/text/queries_heldout.csv` (36 rows, frozen before any run) and
`data/text/queries_spoken.csv` share the schema. The spoken file holds
sentences a speaker chose at recording time that are not in either text
set (`s###` ids); they are declared there, with their expected outcome,
before the clip is scored, and they are not used for text evaluation.
`data/text/queries_qa.csv` (`qa###` ids, split `regression`) holds sentences
typed into the interface during QA or written for a QA pass, with one extra
optional column `expected_flags` (`|`-separated cascade flags that must be
present, `!flag` for one that must be absent; blank = not asserted). They are
run by `scripts/run_text_regression.py` and may be referenced from the
multimodal manifest; they are never part of dev or held-out figures.

## 3. Audio dataset — data/audio/audio_manifest.csv

| Field | Meaning |
|---|---|
| audio_id | `aud_###`, unique |
| query_id | the text query this utterance realises: `q###` seed, `h###` held-out or `s###` spoken (WER reference = reference_transcript) |
| speaker_id | pseudonymous code `spk_01`… — **never names** (GDPR minimisation; consent forms stored outside the repo) |
| reference_transcript | exact words spoken, human-verified |
| environment | `quiet` \| `cafe_noise` \| `announcement_noise` (playback-added noise, documented) |
| noise_condition | `clean` \| `moderate` \| `heavy` |
| expected_identifiers | canonical identifiers the transcript contains, `;`-separated, or blank |
| target_kb_id | copied from the query row for propagation-gap runs |
| split | `dev` \| `heldout` |
| file | path relative to `data/audio/`, e.g. `files/aud_001.wav` (16 kHz mono WAV); added at the speech checkpoint |

`data/audio/derived_manifest.csv` holds clips made from existing ones for
the low-quality scenarios (same columns plus `derived_from` and
`derivation`: a gain reduction below the loudness gate, or white noise at
5 dB SNR). They are kept out of `audio_manifest.csv` so the speech
evaluation figures do not change.

Speaker codes `tts_<voice>` mark synthetic speech produced with the
operating system's built-in voices; those clips are a separate stratum from
human recordings and are reported as such, never mixed into a single WER.

Audio files themselves are consented recordings; raw audio is never logged by
the running system (v1.1 privacy posture) — the dataset copies live only in the
local data folder, not in any interaction log.

## 4. Multimodal dataset — data/multimodal/multimodal_manifest.csv

| Field | Meaning |
|---|---|
| sample_id | `mm_###`, unique |
| image_id | from images manifest, or blank |
| query_id | text query id, or blank |
| audio_id | audio id, or blank (exactly one of query_id/audio_id set when text/voice present) |
| modality_condition | one of the six conditions in `evaluation/multimodal_metrics.CONDITIONS` |
| scenario_type | the situation the case exercises (text_only, image_only, speech_only, text_image_consistent, text_image_conflict, speech_image_consistent, speech_image_conflict, deictic_text_image, oos_image, oos_text, volatile, action_request, low_quality_image, low_quality_audio) |
| expected_route | the router rule expected to lead: text_only, voice_only, image_only, text_leads, voice_leads, image_leads, none |
| expected_decision | answer \| clarify \| abstain \| redirect \| conflict |
| target_kb_id | expected record, blank for abstain/clarify/redirect/conflict cases |
| target_category | for clarify cases, the category the candidates must belong to |
| expected_conflict | `true` when the modalities disagree and the disagreement must be surfaced |
| expected_clarification_field | blank (not asserted), `terminal` (the clarify must ask for the terminal rather than list records) or `none` (the clarify must not ask for a field) |
| consistency_label | `consistent` \| `conflict` \| `single_modality` |
| conflict_type | blank, or `identifier_mismatch` (photo B12 + text B21), `category_mismatch` (baggage photo + lounge question) |
| query_type | controlled query type |
| split | `dev` \| `heldout` \| `regression` (multimodal manifest and `queries_qa.csv` only: cases written after a defect was seen in the interface, reported separately) |
