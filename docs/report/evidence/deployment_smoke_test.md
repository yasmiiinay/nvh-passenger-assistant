# Deployment record and smoke test — Hugging Face Space

Checkpoint 05.1. This is deployment verification of the hosted Gradio
application. It is not an evaluation dataset and is not comparable with
Blind v1/v2/v3.

## Deployment

| Item | Value |
|---|---|
| Space | https://huggingface.co/spaces/yasmincinar/nvh-assistant |
| Canonical repository | https://github.com/yasmiiinay/nvh-passenger-assistant |
| Space `main` commit | `030552f8ba9d4c25c0a86eca9cbfa68185cfa7e1` |
| Source commit (GitHub `main`) | `081b2794c92341217d4225bde57a6d4a0f5dcb00` |
| Behavioural freeze | `2d05b1c`; blind v3 evaluated commit `f2a7ed9` |
| Space hardware | ZeroGPU (`zero-a10g`); all inference runs on CPU, no `spaces.GPU` inference path |
| Space SDK | Gradio 5.50.0, Python 3.12 (local evaluation environment: Python 3.14.3) |
| Smoke test date | 2026-09-18 |

The Space commit is a deployment-only subset of the source commit: `app/`,
`src/`, `configs/`, `requirements.txt`, `README.md` and the `data/` files the
application loads at run time (`kb/`, `text/`, `vocabulary.json`,
`vision_prompts.json`). `git diff main deploy-space` over those paths is empty
except for one README metadata line (`short_description` shortened to satisfy
the 60-character Hub limit). `docs/`, `scripts/`, `tests/`, `evaluation/`, the
evaluation media under `data/images/files` and `data/audio/files`, and all
blind-set stimuli were deliberately not published to the public Space.

Model weights are not committed; `src/vision.py`, `src/speech.py` and
`src/text_encoder.py` fall back to the Hub identifiers when the git-ignored
`models/` directory is absent, so the Space downloads CLIP ViT-B/32,
Whisper-base and all-MiniLM-L6-v2 lazily on first use of each modality.

## Scope of this test versus Blind v3

Blind v3 exercised the frozen core pipeline directly through
`scripts/run_final_blind.py`, which imports `src/` and `evaluation/` and never
imports `app/`. The deployed application drives the same frozen core through
`app/app.py::run_turn`. UI integration was covered by `tests/test_app.py` and
manual QA (checkpoints 03.4–04.6), not by the blind harness. The five inputs
below were chosen to avoid every Blind v3 query, image, clip and scenario; they
verify that the hosted application loads, that each modality reaches the
backend, and that uncertainty handling is visible. They do not measure accuracy.

## Smoke tests

| # | Modality | Input | Deployed outcome | Pass |
|---|---|---|---|---|
| A | Text | "Where does the long-stay car park shuttle leave from at Terminal 1?" | Clarification between *Car Park P1* and *Terminal Shuttle (T1 ↔ T2)*; selecting *Car Park P1* returned a Strong-match answer with location, hours and route | Pass |
| B | Image only | `data/images/files/img_007.png` (AIGA information pictogram, dev split; not in any blind set), no text | "This looks like an information sign. Are you in Terminal 1 or Terminal 2?" — category *information* 0.31, Question back to you, From your photo | Pass |
| C | Voice only | Synthetic 16 kHz clip, "Where can I catch a taxi outside Terminal 2?" (espeak-ng, uploaded through the recorder's file path) | Transcribed verbatim; answer *Taxi Rank* (Terminal 1 forecourt, "also serves Terminal 2"), Strong match, From your voice; editable transcript shown | Pass |
| D | Image + text | `img_007.png` + "I'm in Terminal 1, where is the nearest one of these?" | Clarification among the three *information* records in Terminal 1; evidence "From your photo, words used to narrow down"; entities `terminal = Terminal 1`, `deictic_ref = these`; flags `text weak, image needs terminal` | Pass |
| E | Uncertainty | "Is there a post office where I can buy stamps in the airport?" | No reliable match; no retrieval; entities `unsupported_service = post office`; flags `unsupported_service, action_request` | Pass |

Pass criterion: the UI accepted the input, the backend returned a response
with routing evidence within ~30 s, and no Gradio error was raised. First-use
model downloads on the cold Space took roughly 20–40 s per modality and were
not repeated afterwards.

The live-microphone recording path was not exercised in this run (the
automated browser session had no microphone); voice was verified through the
recorder's upload path, which shares the same Whisper and text pipeline. A
short live recording by the author is recommended before submission.

## Observations (behavioural, not deployment defects — left unchanged)

- A: "long-stay car park shuttle" sits between two Terminal 1 transport
  records and the margin rule asked rather than guessed. Reasonable, but the
  phrase itself does not discriminate between a shuttle *to a car park* and a
  shuttle *between terminals* in the KB descriptions.
- D: the text intent was scored as `find_transport` (0.60, nearest exemplar
  "how do I get to the other terminal") and flagged weak; the image carried
  the decision. The candidate list was correctly narrowed to Terminal 1, yet
  the evidence line still reads "terminal unknown" and the quick reply offers
  "Terminal 1" again. Wording inconsistency in the evidence text, not a routing
  error.
- E: both `unsupported_service` and `action_request` fired; the user-facing
  reason picked the action-request wording ("I cannot book, reserve, print or
  arrange anything") over the more accurate "post office is not a service the
  knowledge base holds", which appears only under Technical details. Correct
  abstention, less helpful explanation.

## Deployment-only issues encountered

- First push rejected: Hub requires binary files to use Xet/LFS. Resolved by
  excluding the evaluation media, which no runtime code path reads.
- Second push rejected: `short_description` over 60 characters. Resolved by
  shortening the README metadata line on the deployment branch only.
- `git fetch`/`ls-remote` against the Space fails with Apple Git 2.50.1 unless
  `-c protocol.version=0` is passed.
- The Web of Trust browser extension flags `*.hf.space` subdomains; the
  `huggingface.co/spaces/...` URL is unaffected and is the one to cite.

## Screenshots

Captured from the direct Space URL at 1512 × 691 (browser viewport).

| File | Content |
|---|---|
| `ui_deployment_text.png` | Test A resolved: Car Park P1 answer with evidence panel (Answer, your words, matched place, Strong match) |
| `ui_deployment_multimodal.png` | Test D: uploaded pictogram thumbnail + typed text, clarification, "From your photo, words used to narrow down" |
| `ui_deployment_uncertainty.png` | Test E: unsupported request, "No reliable match", evidence panel |
| `ui_deployment_extra_image_only.png` | Test B: image-only clarification |
| `ui_deployment_extra_voice.png` | Test C: voice turn with "Heard as" transcript, answer and editable transcript box |
| `ui_deployment_extra_multimodal_technical.png` | Test D technical details: intent score, entities, retrieval stage, CLIP top categories and margin |
| `ui_deployment_extra_uncertainty_technical.png` | Test E technical details: `no_retrieval`, entities and flags |
