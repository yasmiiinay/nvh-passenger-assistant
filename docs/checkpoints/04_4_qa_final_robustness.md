# QA pass 04.4 — Final robustness

17 September 2026. Working mode: TEST → DIAGNOSE → FIX GENERAL CAUSE →
REGRESSION TEST → COMPARE, applied to five carried items in one pass, one
commit per item so that each before/after is attributable. Models,
architecture, `tau_high`, `tau_low`, `margin_delta`, the vision anchors
and the vision bands are unchanged. Baseline for every comparison is the
accepted 04.3 state (7dcc9a6). Status: VERIFIED. Re-run on the MacBook on 17 September: every text,
multimodal, speech and vision row identical to the workspace run apart
from latency (MacBook median 52 ms dev, 39 ms held-out, slowest turn 0.51 s).

Regression cases were written before any of the five changes (qa007–qa014
in `queries_qa.csv`, mm_142–145 in the manifest) and run once on the
baseline code; their "before" columns below come from that run.

## Item 1 — Weak text raising false conflicts (9980a6e)

**Reproduced.** mm_114/115: "What does the blue sign with a person and a
suitcase mean?" clarifies with candidates at 0.26 (accessibility,
information); with a strong photo of another category R3 raised a
conflict. The three genuine R3 conflicts on the sets (mm_015, 112, 113)
carry text at 0.56–0.66.

**General cause.** R3 defended any clarify candidates against the photo,
including a leader between `tau_low` and `tau_high`, which is a guess.

**Fix.** `text_position_confident`: a text position may contradict a
strong photo only when it comes from a deterministic stage or scores at
or above `tau_high`. Otherwise the photo leads, the weak candidates do not
narrow the photo's records, the outcome carries `text_weak` and the answer
says "Your words did not match anything closely, so the answer below comes
from the photo."

**Before → after.** Held-out conflict precision 0.71 → 1.00 (tp 5, fp
2 → 0, fn 0), correct 23 → 24 (mm_115), mm_114 clarify instead of
conflict (still a safe mismatch: the suitcase symbol is read as baggage,
the known check-in confusion). mm_145 (h031 + strong lounge photo):
conflict → lounge answer. Dev, text, speech unchanged.

## Item 2 — ASR noise producing flight redirects (d55c504)

**Reproduced.** mm_032, the 5 dB SNR "Where is gate B12?" transcribed as
"Where is KP12?": the raw pattern (two capitals, two to four digits) fired
and the turn was redirected to flight information.

**General cause.** A two-letter code with two digits has the same shape
as a gate id that noise has re-spelled. Every real flight reference in
the sets (q035, q036, h027) carries the word "flight".

**Fix.** The raw form counts only with the word "flight" in the text or a
number of three or more digits (gates never exceed two). Flight-status
wording without a code still redirects through the intent path (qa008
"Is BA117 delayed?" stays a redirect).

**Before → after.** mm_032 wrong redirect → abstain (the clip is
unanswerable; over-cautious by the judge), mm_144 the same, qa007
"Where is KP12?" abstains. All redirects retained on dev, held-out and
regression. Speech WER and propagation unchanged.

## Item 3 — Alias against the terminal asked about; reversed aliases (5810a24)

**Reproduced.** qa004 "Where is the check-in hall in Terminal 2?" answered
the Terminal 1 record with "is not at Terminal 2", because "check-in hall"
is an alias of that record only. q009 "queue at security north" reached
the semantic stage because the alias list has "north security" but not
"security north".

**General cause.** A single alias hit answers regardless of the terminal;
two-word aliases were matched in one order only.

**Fix.** (a) When an alias names a record that does not serve the
terminal asked about and exactly one record of the same category does,
that record is answered (`terminal_retargeted`, "For Terminal 2, that
is:"); with none, the mismatch answer stands (qa011 lost property); an
airport-level service is not retargeted since it serves the terminal
itself. (b) The gazetteer indexes the reversed order of every two-word
alias made of plain words (39 forms, 149 aliases in all), never taking a
phrase another record owns; the audit checks reversed forms for
collisions.

**Before → after.** Dev 35 → 36 (q009 answered Security North by alias);
held-out unchanged; qa004 and qa010 correct; no other row moved.

## Item 4 — Single-candidate answers and the intent condition (9f0abe5)

**Reproduced.** h019/mm_102 "Baby changing facilities?" answered a
restroom record at 0.56 with intent 0.33; qa012 "Baby changing room?"
answered the first-aid room deterministically; aud_044 (the Turkish
recording, transcribed as "k a bsi office enerid") answered the
lost-property office.

**General causes.** Two. A semantic answer needed similarity and margin
only, never a recognised intent. And a category cue that left one record
("room" → the only medical record, "office" → the only lost-property
record, "claim" → the only Terminal 2 baggage record) answered outright
with no similarity check at all: single-candidate behaviour in its purest
form.

**Fix.** `tau_intent_answer = 0.40`: a semantic answer also needs the
nearest-exemplar intent score at or above it, otherwise the top record is
offered for confirmation (`intent_weak`, "Do you mean …?"). Every correct
dev semantic answer has intent ≥ 0.61, so any value in (0.30, 0.61]
leaves dev unchanged; 0.40 is a round value inside that range. A
single-record cue now hands that record to the semantic stage on its own
(`cue_single_record`), which applies the usual score, margin and intent
checks; the grounded negative and the cue's narrowing are unchanged.

**Before → after.** Held-out text wrong-record 1 → 0 and multimodal
wrong-confident 1 → 0 (h019/mm_102 confirm instead of answer); aud_044
answer → clarify; dev unchanged (q006, q018 now confirmed semantically at
0.67 and 0.59, same answers); h012, h008 the same answers at 0.62 and 0.67.
Cost: aud_122, the project owner's "Baggage claim terminal 2" heard as
"Beggich claim terminal 2", was answered correctly by the cue alone and now
abstains (human recordings 4/5 → 3/5); the photo still carries mm_116,
whose route changes from voice-led to image-led (held-out routing 0.97 →
0.94, verdict unchanged). Residual: qa012 still answers the first-aid room
through the assist policy (intent 0.418, similarity 0.35). The one value
that would block it while keeping h024 (intent 0.459) is 0.45, which
would be fitted to held-out and regression rows rather than dev; it is
recorded, not applied.

## Item 5 — Out-of-scope and action-request safety (this commit)

No rule changed. Both runners now report safety counters: the text
summary lists out-of-scope queries that ended in an answer; the
multimodal summary lists out-of-scope photos, out-of-scope sentences and
action requests that ended in an answer. All are empty on dev, held-out
and regression after items 1–4 (mm_102 was the one entry before item 4).
Tests assert that every action request renders the refusal first and
never contains a word claiming the action was done. Out-of-scope
pictograms still end in "which terminal?" (mm_024, mm_121) or "X or Y"
(mm_023, mm_122): safe, and the residue of the frozen anchors.

## Consolidated before → after (baseline 7dcc9a6 → this pass)

| Measure | Text dev | Text held-out | MM dev | MM held-out | Regression | Speech |
|---|---|---|---|---|---|---|
| Correct | 35/43 → 36/43 | 24/36 → 24/36 | 27/35 → 27/35 | 23/33 → 24/33 | text 8/14 → 11/14; mm 10/12 → 12/12 | – |
| Wrong record / wrong-confident | 1 → 1 | 1 → 0 | 2 → 2 | 1 → 0 | 0 → 0 | – |
| Wrong redirect | 0 → 0 | 0 → 0 | 1 → 0 | 0 → 0 | 1 → 0 | – |
| Over-cautious | – | – | 2 → 3 | 2 → 2 | 1 → 0 | – |
| Safe mismatch | – | – | 3 → 3 | 7 → 7 | 0 → 0 | – |
| Conflict P / R | – | – | 1.00 / 0.80 → same | 0.71 / 1.00 → 1.00 / 1.00 | fp 1 → 0 | – |
| Routing | – | – | 1.00 → 1.00 | 0.97 → 0.94 | 1.00 → 1.00 | – |
| False grounded negatives / OOS answers | 0 / 0 → 0 / 0 | 0 / 1 → 0 / 0 | – | 1 → 0 | – | – |
| Flag checks | – | – | – | – | 8/10 → 10/10 | – |
| ASR propagation (typed ok / asr ok) | – | – | – | – | – | dev 95 / 91 → same; held-out 20 / 17 → same; human 5 / 4 → 5 / 3 |
| WER (L2) | – | – | – | – | – | 0.151 / 0.092 / 0.421 unchanged |
| Vision per-image | – | – | – | – | – | byte-identical |

Rows that changed across the whole pass: text q009 (clarify → answer,
correct), q006, q018, h008, h012 (same answers, now confirmed by the
semantic stage), h019 (answer → confirm), h024 (`cross_terminal_service`
flag added); multimodal mm_032 (redirect → abstain), mm_102 (answer →
confirm), mm_114/115 (conflict → clarify), mm_116 (route only); speech
aud_044 (answer → clarify), aud_122 (answer → abstain); regression qa004,
qa007, qa010, mm_144, mm_145 to correct, qa012 unchanged (wrong).

The remaining wrong-confident answers are the two dev cases known since
03.2: q004/mm_002 "Where do I board my flight?" answered with Pier B gates
(intent `find_gate` at 0.61, above any dev-safe condition) and mm_022,
where the judge expects a conflict that the uncertain photo is not allowed
to raise. Neither is touched by this pass.

## Decision

Accepted as a whole. Every harmful confident count went down or stayed
(wrong-confident held-out 1 → 0, wrong redirect 1 → 0, false conflicts
2 → 0, out-of-scope answers 1 → 0, false grounded negatives 0), outcome
accuracy went up on dev text (+1) and held-out multimodal (+1) and moved
nowhere else, and the one cost is a safe decision replacing a correct
one (aud_122 abstain); mm_032's new abstain replaces a wrong redirect. Open, recorded: qa012 and
the assist-policy threshold; out-of-scope pictograms still asking for a
terminal; the identifier conflict class untestable without OCR.
