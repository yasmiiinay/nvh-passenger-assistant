# Final blind evaluation v3 — deployment build, one run

Date: 17 September 2026. Protocol: `docs/evaluation/blind_v3/PROTOCOL_V3.md`,
pre-registered at commit `80eff16` before any v3 case existed.

Behavioural freeze: `2d05b1c` (end of usability hardening 04.6). Dataset
freeze and evaluated commit: `f2a7ed9` ("Freeze independent blind evaluation
v3"). `git diff 2d05b1c f2a7ed9 -- src configs data evaluation requirements.txt`
is empty, so the evaluated behaviour is that of `2d05b1c`; the commits in
between change only the Gradio page and evaluation tooling. Thresholds as
frozen: `tau_high` 0.50, `tau_low` 0.25, margin 0.10, `tau_intent` 0.30,
`tau_intent_answer` 0.40, vision 0.30 / 0.24 / 0.015, audio gate −45 dBFS.

Authorship: a separate chat with no access to this project, given only
`docs/airport_spec.md`, `data/kb/airport_kb.json` and the authoring brief.
`SELF_CHECK_V3.txt` states that the chatbot's code, rules, thresholds,
earlier sets and earlier results were not consulted and that the chatbot was
not run while authoring. The developer produced the eight images and six
clips from the author's descriptions (four TTS, two spoken), without testing
any of them against the system.

Pre-run verification: `scripts/verify_blind_set.py --set v3` printed `OK`
before the run — 20 text, 8 image, 6 audio and 12 multimodal cases, columns
and controlled values as specified, every expected record id and category
present in the KB, asset names matching, and 19 / 19 recorded hashes
verified. The same check reproduces on a second machine from the freeze
commit. Manifest hash (`blind_v3_manifests_sha256.txt`):
`97c4cbb2…`. The set was run once with
`python scripts/run_final_blind.py --set v3`; no case was rerun and nothing
in the set or the system was changed after the results were seen.

## 1. Text (20 cases)

| Measure | Count | Rate |
|---|---|---|
| Correct verdict | 15 / 20 | 0.75 |
| Decision as expected | 17 / 20 | 0.85 |
| Category as expected (17 with a category) | 16 / 17 | 0.94 |
| Expected record answered (11 with a record) | 8 / 11 | 0.73 |
| Wrong-record / wrong-confident answers | 2 (T3_B002, T3_B007) | 0.10 |
| Answer expected, clarification given | 1 (T3_B005) | |
| Abstain expected, not given | 1 (T3_B018) | |
| Missed redirects | 1 (T3_B017) | |
| Incorrect redirects | 0 | |
| Safe outcome (no wrong-confident answer, no wrong redirect) | 18 / 20 | 0.90 |

The two wrong-confident answers are both cases where a location in the
question was answered instead of the service asked for, in the two shapes the
04.6 landmark rule does not cover.

- **T3_B002** "im checking in at desk 214, wheres security after that". The
  desk identifier matched exactly and ended the cascade at the identifier
  stage, so "security after that" never reached retrieval. The landmark rule
  demotes a service *alias* after a preposition; it does not demote an
  *identifier* introduced by "I am checking in at". The terminal was taken
  from the desk correctly, so the answer is in the right terminal but names
  the wrong service.
- **T3_B007** "I am arriving by train and I use a wheelchair, where do I ask
  for help when I get off?". The rail station acted as the landmark and
  supplied Terminal 1, and the PRM assist policy then chose the Terminal 1
  main entrance point rather than the rail-station point the arrival implies.
  The KB has a `prm_point_rail` record; the assist policy ranks by terminal,
  not by the landmark that set the terminal.

The three safe failures:

- **T3_B005** (jacket left on the plane, already in arrivals) scored 0.301
  against the lost-property record — above the abstain threshold, below the
  answer threshold — so it asked "Do you mean Lost Property Office?". The
  alias supplement added in 04.6 covers "lost my", "I lost" and "misplaced",
  none of which this phrasing uses.
- **T3_B017** ("which gate does the 14:05 to Amsterdam go from?") is the one
  case that should have been a redirect to the departure boards. The
  unsupported-intent flag was raised (`intent_unsupported`), but the gate
  category still produced a terminal question. The redirect path is reached
  through the `flight_information` record, which this phrasing did not select.
- **T3_B018** ("how do i get to gate D4?") asks for a pier that does not
  exist (the KB has piers A, B and C). The identifier did not match any range,
  the category cue "gate" survived, and the system asked which terminal
  instead of saying that there is no pier D. Nothing in the system checks an
  identifier against the ranges before falling back to the category.

## 2. Vision (8 images)

| Measure | Count | Rate |
|---|---|---|
| Top-1 category (6 in scope) | 5 / 6 | 0.83 |
| Top-3 inclusion | 6 / 6 | 1.00 |
| In-scope outcome correct | 3 / 6 | 0.50 |
| Out-of-scope ended safely | 2 / 2 | 1.00 |
| Out-of-scope abstained as labelled | 1 / 2 | 0.50 |
| Wrong-confident image answers | 0 | |
| By stratum (outcome) | clean 2/2, angled 1/1, photographed 0/2, blurred 0/1, out-of-scope 1/2 | |

Category recognition is much better than in v2 (top-1 0.83 against 0.33), but
the band decides the outcome: every in-scope failure is a correct top-1
category sitting in the uncertain band, so the system asks instead of
answering. IMG3_B03 (photographed first-aid sign) put medical on top at 0.317
with a margin of 0.013, below the 0.015 margin rule, and was offered as
"medical or restroom". IMG3_B06 (photographed taxi sign) was closest to the
printed-document anchor and got the 04.6 "I cannot read the writing" question.
IMG3_B05 (blurred security sign) got the same question plus the blur note.
The remaining mismatch, IMG3_B07, is an out-of-scope image that clarified
rather than abstained: safe, but not the labelled outcome.

This is the pattern the manual diagnostics predicted: photographed signs whose
meaning is carried by large text stay uncertain. Two of the three in-scope
failures would have been correct answers had the margin rule been looser,
which is exactly the trade that keeps wrong-confident image answers at zero
here and in v2.

## 3. Speech (6 clips)

| Measure | Value |
|---|---|
| Mean WER | 0.015 |
| WER by condition | clean 0.00, identifier 0.00, terminal_specific 0.00, mild_noise 0.00, fast_natural 0.091 |
| Identifier accuracy (1 clip) | 1 / 1 |
| Decision as expected | 6 / 6 |
| Expected record answered | 6 / 6 |
| ASR errors that changed the outcome | 0 |
| ASR errors absorbed | 1 (AUD3_B02) |

All six clips passed the gate and all six resolved as labelled, including the
mild-noise clip. The only transcription error, in the fast natural clip, did
not change the outcome. Six clips in five conditions is a small sample; the
result says the speech path is not the bottleneck on this set, not that WER is
0.015 in general.

## 4. Multimodal (12 scenarios)

| Measure | Count | Rate |
|---|---|---|
| Correct verdict | 9 / 12 | 0.75 |
| Decision as expected | 9 / 12 | 0.75 |
| Expected record answered (6 with a record) | 4 / 6 | 0.67 |
| Routing as expected | 11 / 12 | 0.92 |
| Conflict detection | TP 1, FP 0, FN 1 (precision 1.00, recall 0.50) | |
| Wrong-confident answers | 0 | |
| Consistent vs conflicting scenarios correct | 8/10 vs 1/2 | |

Two of the three failures (MM3_B01, MM3_B07) are the same uncertain-band
images as IMG3_B03 and IMG3_B06, reaching the passenger through a different
route; no new fault. The third, **MM3_B11**, is the informative one: a voice
question about toilets was paired with a blurred baggage sign, and the system
answered from the voice with the note "I could not identify the sign in the
photo with any confidence, so I answered from your words" instead of raising a
conflict. Conflict detection requires both modalities to be confident; an
uncertain photo is discarded rather than contradicted. The passenger is told
the photo was ignored, so the behaviour is transparent, but the disagreement
itself is not reported. With one conflict detected out of two, recall 0.50 is
two scenarios' worth of evidence and nothing more.

## 5. What this run supports

Across all 46 cases there were **two wrong-confident answers**, both in text,
both the service-vs-location class, and **no wrong-confident image or
multimodal answer and no incorrect redirect**. The safe-outcome rate is 0.90
for text and 1.00 for the other three modalities. Where the system fails on
this set it usually fails by asking rather than by asserting, which is the
behaviour the thresholds were chosen for.

The weaknesses this run exposes that earlier evidence did not isolate:

1. An exact identifier ends the cascade even when the sentence goes on to ask
   for a different service (T3_B002).
2. The PRM assist policy ranks by terminal and ignores the landmark that
   supplied the terminal, so it can pass over a nearer designated point
   (T3_B007).
3. An identifier outside the KB's ranges is not recognised as non-existent;
   the category cue takes over and produces a clarification (T3_B018).
4. A flight-specific gate question does not reach the redirect path even when
   the unsupported intent is detected (T3_B017).
5. An uncertain photo is dropped rather than treated as disagreement, so a
   real conflict can be reported as a plain answer with a note (MM3_B11).

None of these was fixed. Under the pre-registered protocol the evaluated build
is the deployed build, and no threshold, rule, record or template was changed
after the results were read. They are stated here as the known limitations of
the deployed prototype and as the starting point for any later work.

## 6. What it does not support

The three blind sets measure three different builds with three different
datasets, so the numbers are not comparable as a time series and no
improvement is claimed from them: v1 and v2 measured v1.1, v3 measures the
04.6 deployment build. Within v3, every rate rests on 20, 8, 6 or 12 cases;
per-stratum image rates rest on one or two images each. No significance test
is reported and none would be meaningful at this size.

The set inherits the author's limitations, recorded in `SELF_CHECK_V3.txt`:
clarify is judged by category rather than by the candidate set, redirect rows
carry no record id, the mild-noise condition is uncontrolled, and answer
wording, tone and accessibility of the response are not measured at all. The
images and clips were made by the developer from the author's descriptions,
which is the weakest link in the set's independence: the descriptions were
followed without testing, but the choice of a particular photograph is the
developer's.
