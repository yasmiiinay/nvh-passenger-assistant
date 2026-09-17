# QA 04.5 — Post-Blind Generalisation Revision (v1.1)

17 September 2026. Three small general changes, one commit each
(58b7623, 258531f, and the cue-set commit that closes this note), on top of
the v1 system that Blind Evaluation v1 was run on (`41bd901` / `bceaca4`).
Baseline for every comparison is the stored v1 output of dev, held-out,
regression and speech; vision was not re-run because `src/vision.py`, the
prompts and the anchors are byte-identical.

## Methodological status

- Blind Evaluation v1 (`docs/report/final_blind_evaluation/`) is preserved
  unchanged: no label, asset, manifest or result file was edited, and the
  blind runner was not executed again.
- v1.1 is informed by the error classes that v1 exposed (a timetable
  question redirected to the flight boards; a deictic phrase whose noun was
  read as a category cue; a category cue overridden by the intent filter),
  not by its cases. No blind sentence, transcript, image or scenario
  appears in an exemplar, alias, unit test, regression row or threshold
  choice; the new tests and regression rows are synthetic sentences and
  existing development assets.
- Thresholds, exemplars, aliases, the KB, the vocabulary file, the speech
  configuration and the vision pipeline are unchanged. OCR stays off.

## Change 1 — Flight-context guard (58b7623)

**Root cause.** The semantic stage redirected on the `ask_flight_status`
intent alone. Timetable wording about trains or buses ("when do the first
and last … run", "does … stay open past midnight") resembles the
flight-status exemplars ("when does boarding begin", "what time does my
plane leave"), so a transport question could be sent to the flight boards.

**Evidence before the change.** All 9 genuine text redirects on dev,
held-out and regression and all 21 speech redirects carry explicit flight
context: a flight code (q035, q036, h027, qa008, qa009 and their clips),
the word "flight" (h028, h029, aud_040, aud_064) or "boarding" (q037 and
its five voices, aud_123). The content words of the seven
`ask_flight_status` exemplars are flight, plane, boarding, delayed,
cancelled, departing. One speech redirect had lost its context to ASR
(aud_113: "what gate is fly it x-y-456 leaving from") and h011 ("ask about
flight connections", expected clarify) contains "flight".

**Implementation.** `has_flight_context`: a flight code, a volatile
phrase, or one of {flight, flights, plane, boarding, delayed, delay,
cancelled, departing} in the normalised text. The intent redirect fires
only with context; without it the volatile intent is discarded
(`intent_unsupported`), the words alone choose the records, and the
live-information record is left out of the ranking. The deterministic
code and phrase paths of 04.4 are untouched.

**New tests.** Three timetable sentences that must not redirect; three
flight-status sentences that must; `has_flight_context` on words, a code
and nothing.

**Before → after.** Text dev 36/43 → 36/43, held-out 24/36 → 24/36, every
decision identical (q043's abstain candidate list no longer lists the
flight-information record). Multimodal dev and held-out identical. Speech
dev 91 → 90 of 100 outcomes kept: aud_113 now clarifies instead of
redirecting, the transcript having neither "flight" nor a code. h011 is
unchanged (still a wrong redirect, since it contains "flight").

## Change 2 — Deictic routing (258531f)

**Root cause.** The deictic set was the vocabulary's four values ("this
sign", "this", "here", "that") and the deictic branch yielded to any
category cue. A phrase such as "this area" produced a deictic token and a
cue at once ("area" occurs only in gate aliases), the cue won, and the
photo did not lead. Separately, "this evening" was read as deictic.

**Implementation.** `src/entities.py`: the determiners in either number
(this, these, that, those) followed by an optional generic head noun
(sign, signs, area, place, spot, symbol, symbols, icon, thing, one), or
"here", form one deictic phrase whose span is consumed before cue
extraction, so its noun is never a cue; a determiner inside a time phrase
is not deictic. The retrieval branch is unchanged: a deictic phrase with no
alias, identifier, terminal or remaining cue asks for a photo, and with a
photo the router lets the image lead as before. A service word beside the
deictic ("this baggage sign") still yields its cue and goes to retrieval.

**New tests.** Four deictic phrases with generic nouns (no cue produced);
"this evening" not deictic; "this baggage sign" keeps its cue; the
deterministic branch asks for a photo; regression qa015 "What is this
place used for?" and mm_146 (qa015 with an out-of-scope dev pictogram,
expected image-led clarify), both written before the run.

**Before → after.** No existing dev, held-out, regression or speech row
changed; qa015 and mm_146 pass.

## Change 3 — Small coherent cue-set preservation (this commit)

**Root cause.** A category cue plus a terminal can narrow to two or three
records of one category, but when the intent classifier labelled the
sentence with another intent the semantic search ran over that intent's
categories and the cue's records were never scored (a security question
phrased with "which way" was searched among transport records).

**Implementation.** The 04.4 single-record hand-off is widened to a set of
at most three records of one category (`cue_records`, `CUE_SET_MAX = 3`).
The semantic stage scores that set on its own when the intent has no
category or agrees with the cue; when the intent disagrees, the set is
searched together with the intent's categories, so a weak cue cannot
override strong similarity elsewhere and a wrong intent cannot discard a
right cue. The single-record case now follows the same rule (a generic
cue such as "desk" no longer forces a check-in question onto an
information desk when the intent says check-in). Decision logic is
untouched: margin, `tau_high`, the terminal question for records spread
over terminals and the intent condition all apply as before. Cues that
narrow to more than three records remain hints.

**New tests.** A security question with a terminal (two checkpoints
listed, no terminal asked); one without (terminal asked); the
disagreeing-intent union and the agreeing-intent restriction on
`candidate_records`; a five-record cue stays a hint.

**Before → after.** Text dev 36/43 → 36/43 (q017's clarify now offers two
information desks instead of a desk and a check-in hall); held-out 24/36
unchanged; multimodal identical on both splits (mm_116's weak transcript
is flagged `text_weak` instead of `text_not_understood`, same image-led
answer); speech unchanged except aud_122 ("Beggich claim terminal 2"),
abstain → clarify.

## Frozen, untouched

No OCR (EasyOCR not installed, `enable_ocr` false). No speech change
(`src/speech.py`, Whisper-base, gate bounds unchanged). No KB or
vocabulary change. No alias, exemplar or threshold derived from the blind
set; no threshold changed at all. No assist-policy redesign. No OOS
threshold retuning. `src/vision.py`, `data/vision_prompts.json` and the
anchors byte-identical to v1.

## Remaining limitations (documented, not fixed)

- Assist policy: a `request_accessibility_help` intent at moderate
  confidence can answer with the medical room rather than a PRM point;
  fixing it means redesigning the policy or moving `tau_intent_answer`
  onto held-out evidence (QA 04.4 §4).
- Unsupported services above `tau_high`: a request for something the KB
  does not hold (a hotel, a pharmacy) can score above 0.5 against a
  related record with a recognised intent and be answered; only a
  negative vocabulary or a calibrated score would catch it.
- ASR identifier robustness: a gate id heard as other words is lost, and
  the remaining sentence can be read as something else; the audio gate
  and the flight-context guard bound the damage but do not recover the
  identifier.
- Text-bearing signs: desk ranges, gate numbers and text-only signs are
  outside the visual scope (README, "Supported visual scope").
- Visual conflicts: an uncertain photo cannot contradict words (03.4
  design), so a wrong sign photographed beside a clear question is noted,
  not raised as a conflict; identifier conflicts need OCR.

## Final v1.1 metrics

| Measure | v1 (baseline) | v1.1 |
|---|---|---|
| Tests | 192 | 211 |
| Text dev correct / wrong record | 36/43, 1 | 36/43, 1 |
| Text held-out correct / wrong record | 24/36, 0 | 24/36, 0 |
| Text regression (queries_qa) | 11/14, flags 10/10 | 12/15, flags 11/11 |
| Multimodal dev | 27/35, wrong-confident 2, routing 1.00 | same |
| Multimodal held-out | 24/33, wrong-confident 0, routing 0.94, conflict 5/0/0 | same |
| Multimodal regression | 12/12 | 13/13 |
| Speech dev / held-out / human (outcome kept) | 91/100, 17/20, 3/5 | 90/100, 17/20, 3/5 |
| Speech WER (L2) | 0.151 / 0.092 / 0.421 | unchanged |
| Vision | dev 0.947, held-out 0.857 | code unchanged, not re-run |

## Freeze recommendation

v1.1 is suitable to freeze for a new independent blind evaluation: the
three changes are general rules with synthetic tests, they leave every
dev and held-out decision in place, the one cost is a lucky redirect on an
ASR-damaged clip becoming a clarify, and no blind material was reused. The
new blind set should be authored without reference to v1's cases, with
the image rule stated in advance as pictogram or visually recognisable
signs without text-dependent expectations, and its author should record
that rule and the v1 results were known when it was written.
