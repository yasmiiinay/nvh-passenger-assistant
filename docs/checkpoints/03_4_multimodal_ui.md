# Checkpoint 03.4 — Multimodal integration and the interface

13 September 2026. Working mode: IMPLEMENT → TEST → MEASURE → RECORD. The
last development checkpoint: the three modality pipelines from 03.2 and
03.3 are joined by a deterministic router, rendered through the existing
template layer, put behind a Gradio interface, logged, and evaluated end to
end on an authored scenario set. No modality pipeline was retrained or
re-tuned; the frozen text, vision and speech results were re-run after the
integration and are unchanged (§2). Status labels as before: IMPLEMENTED,
EXECUTED (this workspace), VERIFIED (also on the MacBook), NOT YET EVALUATED.
Both scenario splits were re-run on the MacBook and every route, decision,
record and verdict matched this workspace line for line; the checkpoint is
VERIFIED.

## 1. Files changed

| File | Change |
|---|---|
| `src/router.py` | new: evidence gathering per modality, the rule cascade, `Outcome` |
| `src/responses.py` | `render_outcome` for image-led, conflict and no-input cases; multimodal notes; action and live-status flags set once |
| `src/event_log.py` | new: JSONL event log, escalation record, contact route from the KB |
| `evaluation/multimodal_metrics.py` | `judge_scenario`, `rates`; stubs removed |
| `scripts/run_multimodal_eval.py` | new: end-to-end runner with modality-contribution analysis |
| `data/multimodal/multimodal_manifest.csv` | 68 authored scenarios, 35 dev and 33 held-out |
| `data/audio/derived_manifest.csv`, `files/aud_126..129.wav` | four clips derived from existing ones (gain, noise) for the low-quality cases |
| `app/app.py` | the interface (replaces the deployment smoke test) |
| `src/vision.py`, `requirements.txt` | HEIC opener registered, oversized photos reduced to 2048 px (found in the MacBook browser session) |
| `tests/test_router.py`, `test_event_log.py`, `test_app.py` | 17 + 3 + 5 tests |
| `docs/dataset_schemas.md`, `README.md` | multimodal manifest columns, derived clips, how to run |

## 2. Tests and regression checks

`python -m pytest tests` — **167 passed** (this workspace and the MacBook, all models present).
`scripts/audit_foundation.py` — ALL CHECKS PASS.

Regression after integration, byte-for-byte against the frozen outputs:
text dev and held-out (every 03.2 file identical: 35/43, 24/36), vision dev
and held-out (top-1 0.947 / 0.857, band counts identical), speech dev (WER,
propagation, failure types identical). The integration touched
`responses.py` only to add rendering paths and to set two flags earlier;
the change of flag timing was checked to leave the text evaluation files
unchanged.

## 3. Routing design

`src/router.py` gathers what each modality says on its own and applies
rules in a fixed order; the first that applies wins and the reason is
recorded in the outcome. There is no score averaging anywhere.

| Rule | Condition | Behaviour |
|---|---|---|
| R0 | no text, no accepted voice clip, no usable photo | abstain (or, with a rejected clip, ask to re-record or type) |
| R1 | text decision is redirect | redirect; a photo is noted only |
| R2 | text carries a gate, desk or belt identifier | text leads. A strong photo of the same category is noted as agreeing; a strong photo of another category is surfaced as a disagreement in the answer, never merged, and the answer stands |
| R3 | text is deictic, vague (clarify without identifier) or not understood, and the photo is usable | photo leads: its category picks the records, a terminal in the text and any clarify candidates narrow them; one record left → answer, several → clarify asking the terminal, photo uncertain → clarify with the top-3 categories. If the text's clarify candidates are in a different category from a strong photo → **conflict** |
| R4 | text answered by alias or similarity, photo strong | same category → answer, reinforced; different category → **conflict** with both sides listed |
| R5 | photo only | photo leads as in R3 |
| R6 | anything else | text (or the voice transcript) stands alone; an uncertain photo is noted |

Voice is not a separate path: the clip goes through the gate and Whisper
and the transcript takes the place of typed text. Typed text takes
precedence when both are present, and the transcript is still shown.
"Usable" photo means not out of scope and not in the no-reliable-match
band; "strong" means the strong band. An uncertain photo never raises a
conflict and never overrides words, which is the conservative reading of
the 03.3 finding that pictogram margins are small.

A conflict is a fifth decision, alongside answer, clarify, abstain and
redirect. It carries both sides (`conflict_detail`) and the response lists
the candidates from both and asks which the passenger means. Identifier
mismatch conflicts (a photo of B12 with a question about B21) remain
untestable without OCR, as the Architecture Freeze anticipated; every
conflict here is a category mismatch.

Weighted late fusion was not evaluated. On this scenario set the text side
resolves deterministically (identifier, alias, grounded negative or
redirect) in most combined cases, so there is no text score to fuse; the
semantic branch produces scores only for the vague cases, which R3 already
gives to the photo. The comparison stays optional and is not claimed.

## 4. Routing evaluation

68 scenarios in `data/multimodal/multimodal_manifest.csv`, authored with
their expected route, decision, record or category and conflict flag before
the first run, and not edited afterwards. They combine existing labelled
items: 43 seed and 36 held-out text queries, 125 audio clips, 101 images,
plus four derived clips. Dev scenarios use dev images, clips and queries;
held-out scenarios use held-out ones, including the human speaker. Fourteen
situation types are covered (text only, image only, speech only, text +
image consistent and conflicting, speech + image consistent and
conflicting, deictic text + image, out-of-scope image and text, volatile,
action request, low-quality image and audio).

| Measure | Dev (35) | Held-out (33) | Pooled (68) |
|---|---|---|---|
| Routing accuracy (route as expected) | 1.00 | 0.97 | 0.985 |
| Correct outcome | 27 (0.77) | 23 (0.70) | 50 (0.735) |
| Wrong-confident | 2 (0.057) | 1 (0.030) | 3 (0.044) |
| Over-cautious (answer expected, safe decision given) | 2 | 2 | 4 |
| Safe mismatch (safe expected, different safe decision) | 3 | 7 | 10 |
| Wrong redirect | 1 | 0 | 1 |
| Safe decision when no answer was expected | 32/36 (0.889) | 21/22 (0.955) | 37/40 (0.925) |
| Conflict detection | P 1.00, R 0.80 (4 tp, 0 fp, 1 fn) | P 0.71, R 1.00 (5 tp, 2 fp, 0 fn) | P 0.82, R 0.90 |

The one routing miss is mm_112: "Coffee near the arrivals exit" was
expected to lead as text, but typed on its own it ends in clarify (three
candidates across two categories), so the router correctly let the photo
lead and raised the conflict; the expectation, not the router, was wrong
about which rule would fire, and the outcome was judged correct.

**Modality contribution** (combined scenarios only): on dev, 16 of 18
combined scenarios are correct, against 5 of 12 for the text alone and 6
of 18 for the photo alone; six were correct only in combination (three
conflict cases, which neither modality can produce alone, two voice + photo
answers and the voice + photo redirect). Held-out: 11 of 13 combined correct, text alone 3
of 7, photo alone 2 of 13; seven correct only in combination, one lost by
combination (mm_115, a false conflict, §5).

## 5. Conflict handling

Nine of the ten expected conflicts were detected (four with an identifier
on the text side, where the answer stands and the disagreement is stated;
five without, where the conflict decision asks the passenger). The one miss
(mm_022) is a design boundary, not a bug: "Is there a lounge in terminal
2?" with a toilet photo. The photo scored in the uncertain band (0.31,
margin 0.003), and an uncertain photo is not allowed to contradict words,
so the text's grounded-negative answer stood ("no lounge in Terminal 2;
the Aurora Lounge is in Terminal 1"). The judge counts it as
wrong-confident because a conflict was expected; the sentence given is
correct for the words. The two false conflicts (mm_114, mm_115) come from
the text side: "What does the blue sign with a person and a suitcase
mean?" contains no deictic phrase the entity extractor knows, so the text
cascade guessed two weak candidates (accessibility, information) at low
similarity, and R3 treated those guesses as a position to defend against
the photo. A general rule that only a confident text position (similarity
above `tau_high`) may raise a conflict would fix both; it is not applied
here because the evidence for it is the held-out run, and it goes to the
Chat 04 QA list with the other text-side items.

## 6. Wrong-confident answers

Three in 68. mm_002: "Where do I board my flight?" answered with Pier B
gates, the q004 case recorded at the 03.2 closure (exemplar revision side
effect). mm_102: "Baby changing facilities?" answered with a toilet record
at 0.56, the h019 case from the 03.2 held-out run (out-of-scope text
above `tau_high`). mm_022 as described in §5. None is new to this
checkpoint and none is a routing error; two are the text pipeline's
carried defects and one is the judge disagreeing with a defensible policy.
The wrong redirect (mm_032) is new and worth recording: the 5 dB SNR clip of
"Where is gate B12?" was transcribed as "Where is KP12?", and "KP12" matched
the flight-reference pattern (a raw uppercase letter-digit token), so the
turn was redirected to flight information. Noise turned an identifier into
a flight code; the flight-reference pattern is loose enough to be fed by
ASR damage. Carried to QA.

## 7. Safe clarify and abstain behaviour

Of the 40 scenarios where no answer was expected, 37 ended without an
answer. The ten "safe mismatch" cases are all of one shape: the system
asked rather than refused. Out-of-scope pictograms (barber, drinking
fountain, customs, the photo of the barber symbol) landed in clarify, not
abstain, because the anchors do not fire on pictograms (03.3) and the
margin rule sends them to "uncertain" or to "which terminal?"; the two
action requests ("book me a taxi", "print my boarding pass") ended in
clarify with the "I cannot book, reserve, print or arrange anything"
sentence on top; "Nearest cash machine?" clarified. A passenger reading
those responses is not misled, but "which terminal are you in?" under a
barber sign is the wrong question, and that is the residual cost of the
03.3 anchor weakness. The four over-cautious cases are the belt-number ASR
losses (two, both voices heard "belt 8/9" as something else), the red
first-aid variant in the uncertain band, and the noisy "Gate A11" clip.

**The conservative variant (section B of the brief).** With
`confirm_image_only_answers` on, a photo alone never answers; it asks for
confirmation. On dev this turned three correct image-only answers (lounge,
first aid, and the rejected-clip-plus-photo case) into questions and
prevented nothing: the two out-of-scope pictograms were already in clarify
and the wrong-confident cases are text-side. Over-cautious rose from 2 to
5, wrong-confident stayed at 2. The variant is left in the code as an
option and is off; the evidence does not support paying three answers for
no safety gain on this set. The rule that does carry weight is already in
R2 to R4: an uncertain photo neither answers nor conflicts, and a strong
photo cannot override an identifier.

## 8. Known failures carried forward

| Item | Status after 03.4 |
|---|---|
| h024 cross-terminal grounded negative | untouched; not in the scenario set |
| single-candidate threshold | untouched; now three triggers (h019, aud_044, mm_102) |
| twin-record margin | resolved for images by deciding the band on categories (03.3); text side untouched |
| text out-of-scope near `tau_low` | mm_123 "cash machine" clarified rather than abstained |
| paraphrase recall | untouched |
| out-of-scope pictogram strong matches | reach the router as clarify or, in the residual cases, as a strong photo; a general text-confidence gate on conflicts and vocabulary-written pictogram anchors are the QA candidates |
| check-in vs baggage suitcase | mm_114 and mm_133: the suitcase symbol led to baggage candidates; with words present it became a false conflict |
| belt-number ASR | mm_008, mm_108 over-cautious, as in 03.3 |
| anticipated normaliser rules | none fired; decision deferred |
| blur threshold | flags fire on screen photos in good light; informational only |
| new: flight-reference pattern under ASR noise | mm_032 |
| new: weak text candidates raise false conflicts | mm_114, mm_115 |

## 9. The interface

`app/app.py`, `gr.Blocks`, one callback. Inputs: a question box, a photo
upload, a voice clip (microphone or upload). Outputs: the answer, the match
band as text ("Strong match", "Uncertain, please confirm", "No reliable
match", or "Referred to the official source" / "Inputs disagree, please
choose"), the evidence used ("your words, photo checked"), the transcript,
and an evidence panel (decision, why, normalised text, entities, intent
and nearest example, retrieval stage, top records with scores, photo
top-3 with margin, closest anchor, photo quality flags, audio duration and
level, matched record, candidates, conflict detail, flags). Every score is
labelled a similarity, not a probability. A "Request assistance" panel
writes the escalation record (§11). Models load on the first question.

Design: a header with the airport name and one sentence of scope, a
notice that the airport is fictional and that live information is never
given, inputs on the left and outputs on the right, stacking to one column
under about 900 px. Custom CSS is limited to spacing, the notice rule and
hiding the Gradio footer. Nothing is communicated by colour alone: the
band and the decision are words, and the primary button colour only
distinguishes "Ask" from "Clear". Labels are on every component;
`elem_id`s are stable for testing.

One defect was found only through the interface: `gr.Image` converts
uploads to RGB by default, which turns a transparent pictogram into a
black square before it reaches the loader fixed in 03.3, one layer up.
The first browser run of the lockers pictogram came back "uncertain,
blurry and dark" with gate on top, where the evaluation had baggage at
0.37. `image_mode=None` keeps the file as uploaded; a test now asserts
it. This is the same lesson as 03.3: the evaluation runner and the
interface must load the image the same way, and only the browser run
proved they did not.

**Score presentation, changed after the MacBook session.** The band box
first showed "Strong match (match score 0.37)", and the project owner
read 0.37 as a weak result, which is how any passenger would read a
number under 0.5. The raw cosine is not on that scale: correct pictogram
matches sit at 0.28 to 0.37 and text answers at 0.5 to 0.6, and the band
comes from the score together with the margin. The answer and the band
box now carry the band only ("Strong match", "Matched by similarity:
strong match"), the band box has a one-line note under its label, and the
number moved to the evidence panel with a sentence saying what range the
system produces and that the band is not read off the number alone. The
Architecture Freeze wording (match score plus band, no percentages, no
probability) is kept; what changed is where the number appears.

Screenshots (this workspace, headless Chromium, external requests blocked
so the Google font falls back to the system sans-serif):
`docs/checkpoints/images/ui_03_4_start.png`, `ui_03_4_text_answer.png`,
`ui_03_4_conflict.png`, `ui_03_4_photo_not_recognised.png`,
`ui_03_4_mobile.png` (400 px wide).

## 10. Manual interface test cases

Run in a headless browser against the local server, then repeated by eye
on the screenshots; the callbacks are also exercised directly in
`tests/test_app.py`.

| Case | Input | Observed |
|---|---|---|
| empty submit | nothing | "Please type a question, add a photo of a sign, or record your question." band "Not scored" |
| text answer | "Where is gate B12?" | Pier B record, Strong match, evidence "your words", stage exact_identifier in the panel |
| photo + deictic text | lockers pictogram, "What does this sign mean?" | baggage, Strong match 0.37, asks which terminal, both reclaim records listed |
| conflict | "Is there a lounge?" + restaurant pictogram | "Your words point to Aurora Lounge, but the photo looks like a restaurant sign", four options, band "Inputs disagree, please choose" |
| photo not a sign | sunset photograph | "I could not recognise an airport sign in this photo", No reliable match |
| unreadable file | text file uploaded as an image | "I could not read that input", no traceback |
| voice | human clip "Where is belt 9?" | transcript shown ("Various bads mine."), No reliable match, information-desk pointer |
| assistance request | note after the conflict turn | reference NVH-xxxxxx, contact route from the KB, sentence that no person is connected |
| clear | Clear button | all inputs and outputs reset |
| narrow viewport | 400 px | one column, all controls reachable |

Microphone recording could not be exercised here (no audio device in the
workspace). The project owner then ran the interface in Safari on the
MacBook: a spoken "Where is gate B12?" was transcribed exactly and
answered; a typed question with a recording still attached answered from
the typed words and showed the transcript, and the note now says the
typed question was used; a pictogram upload behaved as in the evaluation
(the reduced bar symbol, img_011, in the uncertain band, as on dev). One
new defect came out of that session: a photo taken with the phone was
uploaded as HEIC, which Pillow cannot open, and the component failed
before the callback ran, so every output showed a bare "Error". The
opener from `pillow-heif` is now registered in `src/vision.py` (one new
pinned dependency, justified by iPhone uploads being HEIC by default), the
same photo routes normally, and a test writes and reads a HEIC file. The
same photo was 24.5 megapixels, just under the 25 MP refusal limit set in
03.3; a current phone produces 48 MP, which would have been refused. The
limit is now 120 MP and photos are reduced to 2048 px on the long side
before analysis (CLIP works at 224 px); the vision dev and held-out
results are unchanged by this.

## 11. Logging and escalation

`src/event_log.py` appends one JSON line per turn to
`outputs/logs/events.jsonl`: timestamp, session id, turn index, modalities
supplied, route, decision, record id, candidates, band, score, intent,
stage, image category, image out-of-scope flag, audio accepted flag,
conflict flag, flags, error, latency. Neither the typed words nor the
transcript are stored, and no media is; a test asserts that a name typed
into a question does not appear in the log. Exceptions in the callback
are caught, logged as an error event and shown as a plain sentence.

Escalation is a record, not a hand-over. "Request assistance" writes a
ticket (`outputs/logs/tickets.jsonl`) with a reference number, the last
decision and candidates, the passenger's own note (only here, capped at
500 characters) and the contact route the KB names: the matched record's
assistance contact, else the information desk of the terminal the
passenger mentioned, else the assistance line. The interface says in so
many words that nobody is connected. This is what the KB supports and no
more.

## 12. Runtime observations

Workspace CPU, models warm, per scenario: text only median 9 ms; photo
only 93 ms (max 132 ms); text + photo 87 ms; voice only 1.2 s; voice +
photo 1.5 s (max 2.0 s). MacBook, same scenarios: median 51 ms on dev and
40 ms on held-out, slowest turn (voice + photo) 0.49 s. Cold start: MiniLM, CLIP and Whisper together about 20 s here and
about 8 s on the MacBook, taken on the first question; roughly 2 GB RSS
with all three resident. The interface itself adds nothing measurable.

## 13. Readiness for the Space

Ready to deploy with two checks outstanding. `app/app.py` keeps the
ZeroGPU probe; `requirements.txt` already pins gradio 5.50.0, transformers,
torch, soundfile and scipy; models are fetched from the hub on first use
when `models/` is absent, so the Space needs no weights in the repo. Not
yet verified: the build on the Space itself (cold start with three hub
downloads, ZeroGPU host memory with three models resident, microphone
permission flow in a browser). Both are the Chat 05 deployment steps, and
the smoke-test Space from 02C shows the build path works.

## 14. Carried to Chat 04 Testing and QA

- A text-confidence gate on conflicts (only similarity above `tau_high`
  may contradict a strong photo), with mm_114/115 as the evidence.
- Pictogram-style out-of-scope anchors written from the vocabulary before
  looking at images, or the confirm rule scoped to out-of-scope-prone
  categories; §7 shows the blanket confirm rule is not worth it.
- Flight-reference pattern tightened against ASR damage (mm_032).
- Single-candidate threshold (three triggers now); h019/h024; paraphrase
  recall; text out-of-scope near `tau_low`.
- Action requests: whether "cannot book" should force abstain rather than
  clarify.
- The second blind set (text, images, clips) authored by the project
  owner for the final numbers; the multimodal held-out set has now been
  run once and is no longer blind to the developer.
- Removal of the remaining `write_artifacts` stubs in `evaluation/`.
- MacBook re-run of `--confirm-image-only` (dev and held-out are done and
  identical; the microphone check in a browser is done).

# PROJECT STATE — END OF CHAT 03

- Repository `github.com/yasmiiinay/nvh-airport-assistant`, branch `main`;
  every commit under the project owner's identity. 166 tests; audit passes.
- Closed checkpoints: 03.1 deterministic core; 03.2 text intelligence and
  response assembly (dev 35/43, held-out 24/36, frozen); 03.3 vision and
  speech (vision dev 0.947 / held-out 0.857 top-1; speech dev WER 0.157,
  propagation 95 → 91, held-out 20 → 17, human 4/5; all VERIFIED on the
  MacBook); 03.4 multimodal integration and interface (this note; VERIFIED on the MacBook, line for line).
- Multimodal, 68 scenarios: routing 0.985, correct 0.735, wrong-confident
  0.044, safe when no answer expected 0.925, conflict P 0.82 / R 0.90,
  modality contribution positive on every combined type, confirm variant
  rejected on evidence.
- Frozen results re-verified byte-for-byte after integration.
- Interface complete: text, photo, voice, evidence panel, band wording,
  escalation record, event log without media or words.
- Not started, by design: robustness tuning, second blind set, Space
  deployment (Chat 05), Whisper-small comparison, OCR, weighted fusion.

# Post-checkpoint manual interface observation (16 September 2026)

Recorded after closure; no code was changed and the checkpoint stays
closed. The observation goes to Chat 04 Testing and QA as its first item.

**What was seen.** In the interface on the MacBook, the typed question
"an airport sign for baggage reclaim" together with the AIGA baggage
check-in pictogram (a suitcase, img_005) produced the uncertain-band
response "I am not sure what this sign shows; it may be baggage, transport,
accessibility. Could you say what you are looking for?". Reproduced here:
the text alone resolves through the alias to a clarify between the two
baggage reclaim records (Terminal 1 or 2), which is the more useful
question; the photo scored baggage first with transport and accessibility
close behind, hence the uncertain band.

**Two issues, both on the integration side.**

1. Rule R3 let an uncertain photo lead over text that already had a
   candidate path. The stated principle in §3 is that an uncertain photo
   never overrides words; R3 honours it for answers but not for clarify
   text, so the photo's uncertainty replaced the text's "which terminal?"
   with a broader category question.
2. The uncertainty response exposed too many low-value candidates: the
   photo's full top-3, including categories a passenger looking at a
   suitcase would not consider, and, on the text side, clarify candidates
   well below the leading score (an "Aurora Lounge" entry beside the two
   reclaim records).

Neither changes the frozen numbers: the 68 scenarios contain no case of
"uncertain photo plus text with candidates", which is why the run did not
show it, and the decision policy (thresholds, bands, conflict rules) is not
in question.

**Planned QA work (Chat 04, first item).**

- Render simplification using the existing margin rule: show the runner-up
  only when it lies within `margin_delta` of the leader, never a third
  candidate, for both photo categories and text candidates; three response
  levels for the photo (strong: names the category; uncertain with a clear
  leader: "most likely X, please confirm"; uncertain with no clear leader:
  ask for a clearer photo or a description). No threshold changes.
- R3 precedence review: when the photo is uncertain and the text has clarify
  candidates, the text keeps the turn and the photo is noted as agreeing or
  not.
- Two regression scenarios covering uncertain photo plus text with
  candidates (agreeing and disagreeing categories), added to the manifest
  with expectations written before the run.
- Before and after evaluation on dev and held-out, with any changed
  verdicts listed.
