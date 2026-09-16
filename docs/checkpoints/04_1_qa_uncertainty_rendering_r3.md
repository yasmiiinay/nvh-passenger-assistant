# QA pass 04.1 — Uncertainty rendering and R3 precedence

16 September 2026. Working mode: TEST → DIAGNOSE → FIX GENERAL CAUSE →
REGRESSION TEST → COMPARE. First item of Chat 04, taken from the manual
interface observation recorded at the end of the 03.4 note. No threshold,
band or conflict rule was changed; no model was touched. Status: EXECUTED in
the workspace with all three models present; MacBook re-run outstanding.

## 1. Issue

Typed "an airport sign for baggage reclaim" with the AIGA baggage check-in
pictogram (img_005, a suitcase) produced "I am not sure what this sign shows;
it may be baggage, transport, accessibility. Could you say what you are
looking for?". Reproduced here line for line. The text alone reaches the
semantic stage (category filter, baggage) and ends in clarify between the two
reclaim halls at 0.489 / 0.464, with Aurora Lounge third at 0.409; the photo
scores baggage 0.277, transport 0.259, accessibility 0.241 (margin 0.018,
score below `vision_tau_high`, so the uncertain band). One correction to the
03.4 note: the text resolves through the category-filtered semantic stage,
not the alias stage.

## 2. Root causes

Two general causes, neither specific to this sentence or this pictogram.

1. **Clarify offered the whole top-3.** `resolve_semantic` handed
   `ranked[:3]` to the clarify decision regardless of the score gaps, and the
   image-led uncertain rendering listed all three category candidates. The
   decision rule already uses `margin_delta` to say whether the runner-up
   is a serious alternative; the rendering ignored it. Across dev and
   held-out, 17 clarify rows carried a third record, 11 of them within
   `margin_delta` of the leader, 6 well below it (e.g. h015 coffee: 0.558,
   0.528, then a rail station at 0.411).
2. **R3 let an uncertain photo replace a text question that already had
   candidates.** `text_is_open` counted any clarify without an identifier as
   open, so the photo led even when the words had narrowed to two records.
   The stated 03.4 principle (an uncertain photo neither answers nor
   conflicts) was honoured for answers and conflicts but not for clarify.

## 3. Fix

| Where | Change |
|---|---|
| `src/retrieval.py` | `offered_candidates`: a clarify offers the leader, plus the runner-up only when it lies within `margin_delta`; never a third. `ranked` keeps the top-3 with scores for the evidence panel. Abstain candidates unchanged (never shown). |
| `src/router.py` | R3 fires for an uncertain photo only when the text offers no candidates (`text_has_candidates`); otherwise R6 keeps the text and notes the photo. `_image_leads` sets `image_no_clear_leader` when the category margin is below `vision_margin_delta`. R6 sets `image_uncertain_agrees` when the photo's leading category is among the text candidates' categories. |
| `src/responses.py` | Text clarify: one candidate → "Do you mean X? Please confirm…"; two → "Which of these do you mean? X or Y?". Image uncertain: clear leader → "This most likely shows a X sign, but I am not certain. Is that what you are looking for?"; no clear leader → "it may be X or Y … or take a closer photo". Uncertain agreeing photo is noted as fitting the question. Notes about the other inputs now come before the source line. |
| `data/text/queries_qa.csv`, manifest | The observed sentence as `qa001`; three scenarios mm_134–136 in a new `regression` split with expectations written before the run (see §5). |
| tests | `offered_candidates` rule; four router/rendering tests covering the observed case, a disagreeing uncertain photo, the cases where an uncertain photo must still lead, and the two rendering levels. 172 tests pass. |

Nothing else changed: thresholds, bands, the conflict rules, the exact,
alias, category-cue and grounded-negative stages, the vision index and the
speech path are untouched.

## 4. Before / after on the frozen sets

Text (`run_text_pipeline_seed.py`): dev 35/43 and held-out 24/36 unchanged;
`cascade_summary.json` byte-identical on both splits. `cascade_results.csv`
differs only in the `candidates` column of 8 dev and 9 held-out clarify
rows (third, and in two cases also second, record no longer offered); no
decision, record, stage, score or verdict changed. Vision
(`run_vision_eval.py`): `per_image.csv` and `summary.json` byte-identical on
both splits.

Multimodal (`run_multimodal_eval.py`), same 35 + 33 scenarios:

| Measure | Dev before | Dev after | Held-out before | Held-out after |
|---|---|---|---|---|
| Routing accuracy | 1.00 | 1.00 | 0.97 | 0.97 |
| Correct | 27 | 27 | 23 | 23 |
| Wrong-confident | 2 | 2 | 1 | 1 |
| Over-cautious | 2 | 2 | 2 | 2 |
| Safe mismatch | 3 | 3 | 7 | 7 |
| Wrong redirect | 1 | 1 | 0 | 0 |
| Conflict P / R | 1.00 / 0.80 | 1.00 / 0.80 | 0.71 / 1.00 | 0.71 / 1.00 |

No scenario changed route, decision, record, conflict flag or verdict.
Rows that differ at all: candidate lists shortened on the text side of
mm_015, mm_029, mm_112–115, mm_123; new flags on mm_023 and mm_122
(`image_no_clear_leader`, both out-of-scope pictograms with margins under
0.015) and on mm_110 (`image_uncertain_agrees`, the blurry photo that
agrees with the text). The 68 frozen scenarios contain no "uncertain photo
plus text with candidates" case, which is why the run could not show the
defect and why the fix moves nothing on it.

## 5. Regression scenarios (split `regression`, n = 3)

Expectations written before the run: route `text_leads`, decision
`clarify`, no conflict, target category from the text.

| Scenario | Inputs | Before | After |
|---|---|---|---|
| mm_134 agreeing | img_004 (check-in pictogram; check_in 0.351, security 0.338, margin 0.014) + q005 "Where can I check in?" | image_leads; "it may be check in, security, baggage"; judged correct by category | text_leads; "Which of these do you mean? Check-in T1 or T2?"; photo noted as fitting; correct |
| mm_135 disagreeing | img_023 (transport pictogram, uncertain) + q010 "Where do I pick up my suitcase?" | image_leads; five transport records offered; safe_mismatch | text_leads; the two reclaim halls; "could not identify the sign … answered from your words"; correct |
| mm_136 observed | img_005 + qa001 "an airport sign for baggage reclaim" | image_leads; three categories listed; judged correct by category | text_leads; the two reclaim halls; photo noted as most likely baggage; correct |

Routing 0/3 → 3/3, verdicts 2 → 3. Two of the three were already "correct"
under the judge before the fix, because the judge checks the candidate
category and not which question the passenger was asked; the route column
is what records the change. The regression split is not development or
held-out evidence and is kept out of both counts.

## 6. Costs and open observations

- **Tied same-category triples.** With "never a third", q008 "Where is
  security?" (0.501, 0.499, 0.466) now offers Security South T1 or Security
  North T1 and no longer names Security T2, which a passenger in Terminal 2
  would need. In 10 of the 17 shortened clarify rows the dropped record is
  within `margin_delta` and in the leader's category (security, toilets,
  information desks, gates). In none of the 17 was the dropped record the
  row's target. The general cause is the twin-record problem already on the
  QA list: when the offered candidates are records of one category in
  different terminals, the useful question is "which terminal?", as the
  image side already asks, not a list of names. Left for that pass rather
  than widened here.
- Conflict responses still list both sides in full (`Options:`), which can
  reach five names when a category has three records; the text side is now
  at most two. Not changed in this pass.
- "Which terminal are you in?" under an uncertain out-of-scope pictogram
  (mm_023, mm_122) is unchanged; it belongs to the pictogram-anchor item.
- The single-candidate clarify wording ("Do you mean Lost Property Office?")
  now also covers q013 and q039, where the old text asked "Which of these do
  you mean?" with one name.

## 7. Decision

**Accepted.** Accuracy and safety metrics on dev and held-out are identical
before and after; the regression scenarios move from wrong route to
expected route without a new answer being given anywhere; the passenger-facing
text no longer names a third candidate in any clarify. The cost in §6 is
recorded and routed to the twin-record pass.

Interface screenshots of the new wording and the MacBook re-run are still to
be taken.
