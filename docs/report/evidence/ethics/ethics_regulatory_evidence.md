# Ethics, privacy, accessibility and regulatory evidence

## 1. Scope and methodology

This document describes the Nordhaven (NVH) passenger-assistant prototype **as
implemented** at the frozen behavioural state (core identical to commit
`2d05b1c`; deployed Space commit `030552f`). Every implementation statement was
checked against one of four sources and is tagged accordingly:

- **[src]** verified by reading the source file named;
- **[ev]** verified from recorded evidence in `docs/report/evidence/` or the
  Blind v3 summary;
- **[interp]** analytical interpretation of the above;
- **[future]** a proposal that is not implemented.

Nothing was changed, added or tested for this document. Where a property could
not be verified from the repository — for example what the hosting platform
retains — it is stated as unknown rather than assumed. The document does not
claim legal compliance with any regulation.

## 2. Privacy and data minimisation

**What the application writes to disk** [src: `src/event_log.py`,
`app/app.py::run_turn`]. Two JSONL files under `outputs/logs/`
(`SETTINGS.outputs_dir / "logs"`):

| file | written by | fields |
|---|---|---|
| `events.jsonl` | `log_event(event_from_outcome(...))` once per turn | `timestamp` (UTC), `session_id`, `turn_index`, `modalities`, `route`, `decision`, `record_id`, `candidates`, `band`, `score`, `intent`, `stage`, `image_category`, `image_out_of_scope`, `audio_ok`, `conflict`, `flags`, `error`, `latency_s` |
| `events.jsonl` (error path) | `log_event({...})` when `route`/`render` raises | `timestamp`, `session_id`, `turn_index`, `error` (exception type and message, cut to 200 characters) |
| `tickets.jsonl` | `open_ticket` when the passenger presses *Request assistance* | `reference` (`NVH-` + 6 random hex), `timestamp`, `session_id`, `decision`, `record_id`, `candidates`, `conflict`, `contact_route`, `note` |

The module docstring states the intent — "nothing a passenger would not expect
to be kept: no audio, no image, no transcript text by default" — and the code
matches it: `event_from_outcome` reads only scores, identifiers, decisions and
flags from the `Outcome`; the passenger's words, the transcript, the image
path and the audio path are not among the fields [src]. The `session_id` is
`int(time.time())` plus two random bytes, created per browser session; no
account, name, IP address or device identifier is generated or stored by the
application [src: `new_session_id`].

**The one free-text field.** The escalation `note` is the passenger's own
words, stripped and truncated to 500 characters, stored with the session id
and contact route [src: `open_ticket`]. Nothing filters it, so a passenger may
type a name, flight number, booking reference or phone number into it, and it
would then be retained in `tickets.jsonl` for as long as that file exists
[interp]. The interface text asks for a note but presents no privacy notice
and no consent step; the only scope statement shown is that the assistant "is
not a live agent", "does not show live flight status" and that "all
information is synthetic" [src: `SCOPE_NOTE`; ev: capture files].

**What stays in memory during a session** [src: `passenger_html`,
`thumbnail`, `run_turn`]. The conversation panel embeds a 112-pixel base64
thumbnail of each uploaded photo and the raw Whisper transcript in the session
history HTML held in Gradio session state; *Clear conversation* replaces the
displayed history and keeps only the session id and an empty pending
clarification [src: `on_clear`]. This is display state, not a log, but it
means the image thumbnail and transcript persist in server memory for the
duration of the browser session.

**What the application does not do** [src]. It never copies, saves or
re-encodes the uploaded audio or image files; it reads the temporary file
path Gradio hands it, processes it, and drops the reference. The README's
statement that "the running system will not retain raw audio or images" is
consistent with the application code [src: `README.md` §Provenance and
privacy]. It is **not** a statement about the hosting platform: Gradio writes
uploads to its own temporary directory and Hugging Face infrastructure keeps
its own request logs, and neither is controlled or inspected by this project
[interp; not verified].

## 3. Uploaded media and sensitive information

There is no OCR and no text is read from images [src: `src/vision.py`
contains no text-recognition path; `SETTINGS.enable_ocr = False`]. The
prototype therefore never *intentionally* extracts a name, flight number or
booking reference from a photographed boarding pass. That is a minimisation
choice, not a privacy guarantee [interp]: a passenger who photographs a
boarding pass, a departures board with their flight, or a sign with other
people in frame still sends that image to the server, where CLIP embeds the
whole frame. The image is compared with text prompts and discarded from
application code after the turn, but its thumbnail remains in the session
panel (§2) and the platform's temporary-file handling is outside the
project's control.

For audio, Whisper transcribes whatever is said, so accidental disclosure —
"my name is …, booking reference …" — becomes text that is normalised,
searched against the KB and shown back in the editable transcript box [src:
`src/speech.py`, `app/app.py`]. The transcript is not logged (§2), but it is
displayed and held in session state. Voice is also biometric in character:
the application does no speaker identification and stores no audio, which
limits that risk, but the recording itself passes through the server [interp].

The vision quality check (blur, dark, bright flags) and the audio gate
(duration, loudness) are quality controls, not content filters; nothing in
the code detects or redacts personal information in either modality [src].

## 4. ASR bias and speech limitations

Evidence, not assumption:

- The speech set is 125 clips: 120 synthetic macOS voices (5 voices × 24
  utterances) and 5 clips from one human speaker; every clip is labelled
  `quiet` / `clean`; degradation exists only in 4 derived clips (−52 dBFS
  gain, 5 dB SNR white noise) [ev: `data_exploration/audio_dataset_summary.md`].
- Blind v3 speech: mean WER 0.015 over 6 clips, all 6 expected records
  answered; the summary itself says this means "the speech path is not the
  bottleneck on this set, not that WER is" generally low [ev:
  `final_blind_v3_summary.md`].
- The preprocessing evidence shows the human clip `aud_121` ("Where is belt
  9?", −40.6 dBFS) transcribed as "Various bads mine." — it clears the −45 dBFS
  gate, `has_speech_text` accepts it, no identifier is extracted [ev:
  `preprocessing/audio_preprocessing_evidence.md`].
- Whisper decoding is forced to English (`language="english"`,
  `task="transcribe"`) [src: `src/speech.py::transcribe`].

Implication [interp]: the low measured WER is a statement about synthetic,
quiet, single-accent audio. Nothing in the project measures performance across
accents, ages, speech impairments, microphones, distance from the device or
terminal noise, and no demographic or fairness evaluation of the ASR was
performed. The one human example in the evidence already fails. The
implemented mitigations are the loudness/duration gate, the editable transcript
("You said — edit if this is wrong, then press Enter to ask again") and the
fact that a wrong transcript falls into the same clarify/abstain policy as an
unclear typed query; none of these detects that a transcript is wrong [src,
interp].

## 5. Vision bias and generalisation

Evidence [ev: `data_exploration/`]: 101 images, 61 of them out-of-scope; 64
clean AIGA/DOT vector icons versus 37 author-supplied photographs (28 good
light, 9 degraded); only 19 in-scope images in the development split across 9
labels, so the vision thresholds were set on very few positives; two prompt
categories, `security` and `accessibility`, have no images at all.

Blind v3 vision [ev: `final_blind_v3_summary.md`]: top-1 category 5/6, top-3
6/6, in-scope outcome accuracy 3/6, out-of-scope detection 2/2, wrong-confident
image answers 0. The summary attributes the in-scope misses to the margin rule
sending photographed signs to clarification rather than answering, and notes
that loosening the margin would have turned some into correct answers at the
cost of the zero wrong-confident count.

Implemented handling [src: `src/vision.py`, `configs/settings.py`]: three
thresholds on cosine scores (τ_high 0.30, τ_low 0.24, margin 0.015), an
out-of-scope test against anchor prompts, blur/brightness flags shown with the
answer, and a UI note that "scores are cosine similarities: a retrieval
distance on a 0–1 scale, not a probability of correctness" [ev: capture files].
No OCR, no augmentation, no fine-tuning.

Implication [interp]: the prototype is more reliable on clean pictograms than
on photographs, and its behaviour on real airport signage — glare, angle,
clutter, multilingual text panels — is not established by the evidence. The
design response is to ask rather than assert when the margin is small; the
cost is that photographed signs often end in a question, which Blind v3 and
the deployment scenarios both show.

## 6. Language inclusion

The prototype is English-only by design [src]: Whisper is forced to English
transcription; the normaliser's contraction and number-word tables, the
vocabulary, the gazetteers and the intent exemplars are English; the two
`non_english` queries in each labelled query set are expected to abstain
[ev: `queries_seed.csv`, `queries_heldout.csv`]. Whisper-base is a
multilingual model, but the application does not expose that capability, and
`task="transcribe"` with a forced language means non-English speech is
rendered as best-effort English text rather than translated or handled
[src: `src/speech.py` docstring].

Implication [interp]: in an international airport this excludes a large share
of passengers from the voice and text paths entirely; the image path is the
only language-independent modality, and it answers location questions only.
This is a stated limitation of the prototype, not an oversight, but it is an
inclusion issue any deployment would have to solve before the assistant could
be offered publicly.

## 7. Accessibility

Implemented, verifiable choices [src: `app/app.py`, `data/kb/airport_kb.json`]:

- Status is never conveyed by colour alone: each status chip pairs an
  `aria-hidden` symbol with words — "Strong match", "Uncertain, please
  confirm", "No reliable match", "Official information", "Inputs disagree",
  "Question back to you", "Could not read the input" [src: `STATUS`,
  `status_chip`].
- Icon-only buttons keep their words as the accessible name ("Add a photo of a
  sign", "Ask by voice"); the question box has a visually hidden label; the
  drop-target hint is a `role="status" aria-live="polite"` region; keyboard
  focus is made visible with a 2 px outline; controls are at least 44–48 px
  high [src: CSS and component definitions].
- Every answer is text; the voice transcript is displayed and editable before
  it is used, so a mis-heard passenger can correct rather than repeat [src].
- All 32 KB records carry an `accessibility` object (`step_free`,
  `accessible_toilet_nearby`, `induction_loop`, `assistance_point_record`,
  `notes`) that is rendered in the fact row; four PRM assistance-point
  records exist and are reachable through the `accessibility` intent family
  [src: KB; `src/entities.py` families].

Not done, and not claimed: no WCAG conformance audit, no screen-reader
testing, no testing with disabled passengers or assistive technology, no
independent participants at all [ev: no such record exists in the
repository]. The Gradio audio recorder's own controls are library defaults
whose accessibility was not assessed. Blind v3 also recorded that PRM ranking
"can prefer terminal-level assistance rather than landmark-nearest
assistance", so the accessibility content is present but its retrieval is
imperfect [ev: known-limitation list].

## 8. False certainty and responsible redirection

Implemented mechanisms [src unless marked]:

1. Deterministic-first retrieval: identifiers and aliases are matched against
   the KB before any embedding; grounded negatives answer "does not exist"
   from KB structure rather than the nearest plausible record
   (`src/retrieval.py`).
2. Thresholds on cosine similarity with a margin rule for text (τ_high 0.50,
   τ_low 0.25, margin 0.10, intent floors 0.30 / 0.40) and vision (0.30 / 0.24
   / 0.015); below them the outcome is *clarify* or *abstain*, never a guess
   (`configs/settings.py`, `retrieval.decide`).
3. Multimodal rule order R0–R6 in which nothing is averaged: a strong image of
   a different category than the text is surfaced as a *conflict* ("Inputs
   disagree"), not merged (`src/router.py`).
4. Unsupported services and action requests are refused with a reason
   ("I don't have reliable information about … Please check an information
   desk or official airport information"; "I cannot book, reserve, print or
   arrange anything") (`src/responses.py::_abstain_text`).
5. Live information is redirected, not answered: a flight reference or
   volatile phrasing triggers "I do not hold live flight, gate or delay
   information." plus the KB record's availability note, *before* any gate
   lookup; queue/waiting-time questions get "I do not have live queue or
   waiting times; the terminal displays show them." (`retrieval.py`,
   `responses.py::render`).
6. Time is never asserted: when the passenger asks about "now" or "tonight",
   hours are shown with "I cannot see the current time, so please compare
   these hours with the time where you are" (`responses.py`; ev: captured in
   the 05.1 session).
7. Every answer carries an evidence panel naming the outcome, the route, the
   matched record or candidates, the match-strength band and, under
   *Technical details*, the raw cosine scores with the note that they are not
   probabilities [ev: captures A–E].

Recorded limits of these safeguards [ev]:

- Blind v3 text: 2 wrong-confident answers out of 20 (an identifier in the
  question answered instead of the service asked for); safe-outcome rate 0.90.
- Blind v3 multimodal: conflict precision 1.00 but recall 0.50 — half the
  planted conflicts were not flagged, because an *uncertain* image is ignored
  rather than counted as disagreement.
- Blind v3 known-limitation list: non-existent gate ranges can fall into
  clarification instead of explicit abstention; some live-gate phrasings miss
  the redirect.
- Deployment scenarios: correct decisions with imprecise explanations — an
  evidence line saying "terminal unknown" after the text had narrowed the
  candidates; the action-request wording chosen over the more specific
  unsupported-service reason [ev: `user_testing/structured_user_testing.md`].

Interpretation: the safeguards convert most uncertainty into questions or
refusals, and the blind set recorded zero wrong-confident image answers; but
"safe" is not "helpful", and the explanation layer sometimes lags the decision
layer. The passenger's remaining protections are the visible evidence panel
and the redirect to official sources.

## 9. Logging and storage limitations

- Path and fields: §2. `outputs/` is git-ignored except for a `.gitkeep`, so
  logs are never committed [src: `.gitignore`].
- No retention period, rotation, deletion routine, access control or
  encryption is implemented for either JSONL file; they grow by appending
  [src: `_append`].
- On the deployed Space the filesystem is ephemeral — the 05.1 record observed
  that log retention equals container lifetime [ev:
  `deployment_smoke_test.md`]. That is a property of the hosting environment,
  not a designed retention control, and it applies equally to the escalation
  tickets: a reference number the passenger is asked to quote could disappear
  when the container restarts [interp].
- Nothing in the application logs IP addresses, user agents or account
  identifiers; whether the platform does is not known from the repository.

## 10. Synthetic-data and prototype limitations

Nordhaven International does not exist. The KB is 32 hand-authored records
with invented hours, directions and contacts, 24 of them in Terminal 1 and 8
in Terminal 2; the "assistance line" is a placeholder number marked synthetic
[src: KB, `event_log.ASSISTANCE_LINE`]. The 97 labelled text queries were
authored by the developer or arose in QA; the speech set is 96 % synthetic
voices; the images are public-domain pictograms and the author's own
photographs [ev: `data_exploration/`]. User testing consisted of five
developer-run deployment scenarios with no external participants [ev:
`user_testing/`].

What this supports [interp]: the architecture, the routing and uncertainty
policy, and the end-to-end integration of three modalities can be
demonstrated and evaluated on this material. What it does not support: any
claim about real passengers, real airports, real signage, or operational
accuracy. A real deployment would need a maintained KB fed by the airport's
own systems, consented human speech across accents, real signage photographs,
and testing with passengers, including those with disabilities.

## 11. GDPR-oriented design assessment

The prototype was not designed against a legal checklist and no compliance
claim is made. Read against the data-protection principles that a real
deployment would have to satisfy [interp throughout; the underlying facts are
the [src] items above]:

- **Data minimisation** — reflected in the event log, which keeps decisions,
  scores and identifiers and not the passenger's words, voice or image; and in
  the absence of OCR. Incomplete: the free-text escalation note and the
  in-session transcript and thumbnail.
- **Purpose limitation** — the log's stated purpose is evaluation and
  debugging; nothing else reads it. Incomplete: no notice tells the passenger
  what is kept or why.
- **Storage limitation** — no retention policy exists; the append-only files
  live as long as the filesystem does. On the Space that is short by accident,
  not by design.
- **Transparency** — strong at the answer level (evidence panel, route, band,
  scores with their meaning) and weak at the data level (no privacy notice, no
  consent step, no description of processing in the interface).
- **Security and accountability** — files are plain JSONL without access
  control; the README records provenance and the synthetic status of all data
  and states the no-retention intent; the audit script checks `source:
  synthetic`. Voice data may attract stricter treatment than text if it is
  processed to identify a person — this prototype does not do so, but a
  deployment would need to state that.

External references that the final report will need for this section (to be
sourced properly; none are cited here): the GDPR text for the principles in
Article 5 and the transparency duties in Articles 12–14 and the special-
category provisions in Article 9; supervisory-authority guidance on voice and
image data (for example the UK ICO); WCAG 2.1 for the accessibility
discussion; the Whisper paper for its reported robustness and accent
behaviour; the CLIP paper for zero-shot similarity and its documented biases;
and, if used, the EU AI Act's treatment of transparency obligations for
AI systems that interact with people.

## 12. Future work (all unimplemented)

- A privacy notice and an explicit consent step for voice and photo upload;
  a per-turn "don't keep anything" option.
- Filtering or redaction of the escalation note; a documented retention period
  and a deletion routine for both JSONL files.
- Consented multi-speaker, multi-accent recordings with real terminal noise;
  a fairness evaluation of ASR by speaker group; a confidence signal from
  Whisper surfaced to the passenger.
- Photographed and multilingual signage in the image set, including examples
  for the `security` and `accessibility` prompt categories; a measured study
  of glare and angle.
- Multilingual operation: language detection, per-language normalisation and
  vocabularies, translated KB fields.
- A screen-reader and keyboard audit against WCAG 2.1, and testing with
  passengers who use assistive technology.
- A live-data adapter for gate and flight status behind the existing redirect
  policy, and a real handover path to airport staff behind the existing
  escalation record.

## Report-ready summary (≈490 words)

The ethical questions this prototype raises follow from what it does with
passenger input: it accepts typed text, a photograph and a voice recording and
answers from a 32-record synthetic knowledge base. Data minimisation is visible in two places. The event log records decisions, routes, scores and
identifiers but not the passenger's words, transcript, image or audio, and no
OCR is performed, so boarding-pass text is never deliberately extracted. These are mitigations, not guarantees. The uploaded image is still embedded whole by
CLIP and its thumbnail stays in the session panel; a spoken name or booking
reference is transcribed, shown and searched; and the free-text escalation
note is stored verbatim up to 500 characters with no filtering. No privacy
notice or consent step exists in the interface, no retention or deletion
routine is implemented, and what the hosting platform keeps in its own
temporary files and logs is outside the project's control. The prototype thus
reflects several GDPR principles in its design without meeting the
transparency and storage-limitation duties a real deployment would carry.

The datasets bound what can be claimed about fairness. Speech evidence is 96 %
synthetic voices with one human speaker in quiet conditions; the low Blind v3
word error rate (0.015 on six clips) shows only that the speech path was not
the bottleneck on that set, and a quiet human clip in the preprocessing
evidence was mis-transcribed outright. Vision evidence is dominated by clean
vector pictograms; photographed, angled and blurred signs are few, and two
prompt categories have no images at all. No evaluation by accent, age,
disability or language was performed, and the system is English-only by
design: Whisper is forced to English and every text resource is English,
which excludes many passengers of an international airport from two
modalities.

The system's response to its own uncertainty is its strongest safeguard.
Similarity thresholds with a margin rule route weak evidence to clarification
or abstention; unsupported services and action requests are refused with a
reason; live flight, gate and queue questions are redirected to official
displays rather than answered from a static KB; hours are shown without
asserting open or closed; and every answer carries an evidence panel naming
the route, the matched record and the score band, with an explicit note that
scores are not probabilities. Blind v3 recorded no wrong-confident image
answers and a 0.90 safe-outcome rate on text, but also two wrong-confident
text answers, missed conflicts when the image was uncertain and, in
deployment, explanations that lag the decisions they explain.

Finally, there is no live airline or airport data and no human behind the
"Request assistance" button: it writes a reference number and names a contact
route from the KB. Accessibility is a design
consideration — status conveyed by words as well as symbols, editable
transcripts, accessibility fields on every record — not a tested or certified
property. The prototype demonstrates an architecture for responsible
multimodal assistance; it does not demonstrate readiness to be placed in front
of passengers.
