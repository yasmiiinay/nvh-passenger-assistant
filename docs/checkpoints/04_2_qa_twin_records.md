# QA pass 04.2 — Twin-record disambiguation

17 September 2026. Working mode: TEST → DIAGNOSE → FIX GENERAL CAUSE →
REGRESSION TEST → COMPARE. Continues from the accepted 04.1. No threshold
(`tau_high`, `tau_low`, `margin_delta`) was changed; no model, anchor,
regex or action-request handling was touched. Status: EXECUTED in the
workspace with all three models present; MacBook re-run outstanding.

## 1. Issue

After 04.1 a clarify offers at most two record names. Where several records
of one category differ only by terminal, that list is arbitrary: "Where is
security?" offered Security South T1 or Security North T1 and no longer
named Security T2. The image side has asked "Which terminal are you in?"
since 03.4; the text side listed names.

## 2. Diagnosis on the existing sets

For every clarify on dev and held-out, the set of records within
`margin_delta` of the leader was taken from the full ranking and checked
for category, terminal and whether the text carried a terminal entity.

- 12 rows (7 dev: q005, q008, q009, q010, q015, q016, q024; 5 held-out:
  h007, h015, h018, h030, h033) have a tied set of one category spread over
  both terminals and no terminal in the text. These are the twin cases.
- 3 rows carry a terminal (q034, h005, h006). In all three the existing
  semantic stage (`candidate_records`) had already narrowed the allowed
  records to that terminal, so the tied set sits in one terminal.
  Requirement 4 ("narrow before asking") is therefore existing behaviour;
  it needed a test, not code.
- 3 rows have tied sets across categories (q017, h031, h036); the rule must
  not fire there.
- The KB's `level` and `zone` fields are free text ("Check-in Hall (north
  end)") and the entity extractor reads back only `terminal`. A question
  about level or zone could not be narrowed on the next turn, so terminal is
  the only field asked for. Same-terminal pairs (north/south security,
  the two Terminal 1 restrooms) keep the 04.1 two-name list; both names are
  alias-resolvable.

## 3. Fix

| Where | Change |
|---|---|
| `src/retrieval.py` | `tied_by_terminal(ranked, margin_delta, gaz)`: the records within `margin_delta` of the leader when they are one category in more than one terminal, else `[]`. In the clarify branch, when it returns records and the text has no terminal entity, `clarification_field = "terminal"` and the candidates are the tied set (kept for the evidence panel, never listed). Otherwise `offered_candidates` from 04.1 applies. `RetrievalResult.clarification_field` added. |
| `src/router.py` | `Outcome.clarification_field`, copied from the text result; the image-led "which terminal" clarify (`image_needs_terminal`) now sets it too, so both sides are counted alike. |
| `src/responses.py` | Terminal question: "There is more than one security location. Are you in Terminal 1 or Terminal 2? Ask again with the terminal, for example \"security in Terminal 1\"." No record name in the sentence. |
| `evaluation/retrieval_metrics.py` | `clarify_type`: `targeted_terminal`, `confirm_one`, `list`, `deictic`, `open`. Counted by both runners (`clarify_types` in the summaries, `clarify_type` per row). The judges are unchanged. |
| manifest, `scripts/run_multimodal_eval.py` | New column `expected_clarification_field` (blank = not asserted, `terminal`, `none`); per-row `clarification_field_ok` and a `clarification_field_checks` count. Four regression scenarios mm_137–140 (§5). Three 04.1 rows had unquoted commas in `notes`; fixed. |
| tests | `tied_by_terminal` rule; q008 asks for the terminal; h006 narrows by terminal and does not ask; q017 mixed categories lists; terminal wording names terminals, not records. 176 pass. |

The system stays single-turn: the question tells the passenger how to ask
again, and "security in Terminal 2" then answers (one record) while
"toilets in Terminal 1" narrows to the two Terminal 1 records and lists
them. A one-turn follow-up memory is deferred to its own QA change so its
effect can be measured on its own.

## 4. Before / after

Vision `per_image.csv`: byte-identical on both splits. Text and multimodal:

| Measure | Text dev | Text held-out | MM dev | MM held-out |
|---|---|---|---|---|
| Correct | 35/43 → 35/43 | 24/36 → 24/36 | 27/35 → 27/35 | 23/33 → 23/33 |
| Wrong-confident / wrong record | 1 → 1 | 1 → 1 | 2 → 2 | 1 → 1 |
| Clarify decisions | 13 → 13 | 15 → 15 | 9 → 9 | 10 → 10 |
| Routing | – | – | 1.00 → 1.00 | 0.97 → 0.97 |
| Conflict tp/fp/fn | – | – | 4/0/1 → 4/0/1 | 5/2/0 → 5/2/0 |
| Generic name-list clarifies | 10 → 3 | 10 → 5 | 1 → 1 | 4 → 3 |
| Targeted terminal clarifies | 0 → 7 | 0 → 5 | 5 → 5 | 6 → 7 |
| Single-record confirmations | 2 → 2 | 5 → 5 | 1 → 1 | 0 → 0 |

"Before" clarify types are derived from the 04.1 outputs (image
`image_needs_terminal` counted as targeted; two or more names as a list).
No decision, record, verdict, route or conflict flag changed on any of the
79 text queries or 68 multimodal scenarios. Rows that differ: the six twin
rows whose candidate list grew back to the full tied set (q008, q009,
q016, h007, h018, h033), and mm_113, where the text side of a conflict now
carries three restroom records instead of two.

## 5. Regression scenarios (split `regression`, now n = 7)

Expectations written before the run, including `expected_clarification_field`.

| Scenario | Query | Expected | Before | After |
|---|---|---|---|---|
| mm_137 T1/T2 pair | q005 "Where can I check in?" | clarify, check_in, `terminal` | list: Check-in T1 or T2 | "Are you in Terminal 1 or Terminal 2?" |
| mm_138 three records | q008 "Where is security?" | clarify, security, `terminal` | list: South T1 or North T1 (T2 hidden) | terminal question; all three kept as candidates in evidence |
| mm_139 terminal present | h006 "…second security checkpoint in terminal 1?" | clarify, security, `none` | list: South T1 or North T1 | unchanged, no terminal asked |
| mm_140 mixed categories | q017 "information desk arrivals" | clarify, information, `none` | list: Info Desk T1 Arrivals or Check-in Hall T1 | unchanged |

Field checks 4/4; verdicts 7/7 on the whole regression split (the three
04.1 scenarios unchanged). The judge verdicts were already "correct" on
all four before the change; the `clarification_field_ok` column is what
records the difference, which is why it was added rather than the judge
loosened.

## 6. Costs and open observations

- q009 "How long is the queue at security north?" now asks for the
  terminal although the passenger named the north checkpoint. The alias
  list has "north security" and "security checkpoint north" but not
  "security north", so the deterministic stage does not fire. That is a KB
  alias gap, not a rule defect; a general fix is to generate the reversed
  "<category> <qualifier>" alias form for every record, to be measured in
  a later pass.
- h033 "gate 14": three pier records tied; the terminal question is asked
  where "which gate letter?" would serve better. Gate ranges are the
  identifier case; the rule is general and the wording stays.
- Conflict responses list both sides in full; with the tied set restored
  the text side of mm_113 now shows three restroom names (six options in
  all). The clarify wording improvement does not reach the conflict
  rendering yet.
- The counts show what moved: on text dev 7 of 10 name lists became a
  terminal question, on held-out 5 of 10; the remaining lists are the
  same-terminal pairs and the mixed-category cases, which is the intended
  residue.

## 7. Decision

**Accepted.** No confident answer was added or changed anywhere; the
clarify and abstain counts are identical; the change is confined to how a
clarify is put to the passenger, and the pre-written regression cases,
including the two must-not-fire cases, pass. The KB alias observation and
the conflict-rendering length go to the QA list.
