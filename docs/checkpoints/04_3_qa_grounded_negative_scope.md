# QA pass 04.3 — Cross-terminal grounded-negative logic

17 September 2026. Working mode: TEST → DIAGNOSE → FIX GENERAL CAUSE →
REGRESSION TEST → COMPARE. Continues from the accepted 04.2. Thresholds,
the semantic ranking, the vision and speech paths, the out-of-scope
anchors, the flight-reference pattern and the action-request handling are
untouched. Status: EXECUTED in the workspace with all three models
present; MacBook re-run outstanding.

## 1. Issue

h024 "How often does the shuttle to terminal 2 run?" answered "There is no
transport in Terminal 2. Nearest: Rail Station (Terminal 1); …" (recorded
at the 03.2 held-out run and carried since). A false "no" is the one
confident error that sends a passenger away from a service that exists,
which is why it was taken before the conflict, recall and robustness items.

## 2. Reproduction and rule path

Reproduced line for line. `resolve_deterministic`: no identifier; no alias
("shuttle" alone is not an alias, "shuttle bus" is); the category-cue table
maps "shuttle" to `transport`; the terminal pattern yields Terminal 2.
Stage 2b then takes the five transport records, keeps those whose
`terminal` field equals Terminal 2, finds none, and fires the grounded
negative ("no 'transport' record in Terminal 2; exists elsewhere") with the
whole category as alternatives.

Root cause is both parts of the question in the brief:

- **Schema semantics.** Every record has one `terminal`, which means where
  it is. Seven records are airport-level services filed under Terminal 1:
  the ground transport of spec §4 ("landside, between the terminals":
  shuttle, taxi rank, rail station, bus terminal, car park), the flight
  boards ("throughout both terminals") and the first-aid room ("serves
  both terminals"). The KB had no way to say so; the descriptions did.
- **Precondition.** The grounded negative, the alias terminal check and the
  semantic terminal filter all read `terminal` as "who it serves". Given the
  schema, any Terminal 2 question about an airport-level service became a
  "no" or a "not at Terminal 2".

The spec's intended asymmetries (no lounge and no lost-property office in
Terminal 2) are true negatives that must keep firing.

## 3. Fix

| Where | Change |
|---|---|
| `data/kb/airport_kb.json` | `serves_terminals: ["Terminal 1", "Terminal 2"]` on the seven airport-level records (seven added lines, no other change). |
| `src/kb.py` | Loader default `serves_terminals = [terminal]` for every other record. |
| `src/entities.py` | `Gazetteers.serves(record_id, terminal)`; the one reader of the new field. |
| `src/retrieval.py` | Every terminal narrowing uses `serves`: the alias check (flag `cross_terminal_service` when the record serves the asked terminal from elsewhere, `terminal_mismatch` only when it does not), alias narrowing, the cue stage (grounded negative only when no record of the category serves the terminal), and the semantic stage's allowed-set filter. Second rule: the high-volatility live-information record, which only ever redirects, is left out of the cue stage's category set (§4 explains why). |
| `src/router.py` | Image candidates narrowed by the text's terminal use `serves` too. |
| `src/responses.py` | New sentence for `cross_terminal_service`: "Taxi Rank is in Terminal 1 and also serves Terminal 2." The `terminal_mismatch` sentence is unchanged for records that are genuinely elsewhere. |
| `src/foundation_audit.py`, `docs/airport_spec.md` | `terminal_scope` check (known terminals, includes the record's own); the field documented under spec §4. |
| `data/text/queries_qa.csv`, `scripts/run_text_regression.py` | Five text regression queries with `expected_flags` (present / `!absent`), a small runner reusing the cascade and the text judge; h024 itself as mm_141 in the multimodal regression split. |
| tests | Terminal scope separates location from service (h024 shape, true negative, first aid by alias, lost property mismatch), loader default, live-information record not a desk, parking wording updated. 180 pass. |

No sentence, alias or exemplar specific to h024 was added.

## 4. An intermediate result that shaped the fix

With `serves_terminals` alone, h012 "help desk in terminal 2" (held-out)
regressed from an answer to a bad clarify, and mm_110 with it: the flight
boards record is category `information`, so marking it as serving
Terminal 2 gave that terminal two information records and the cue stage
could no longer narrow to the one desk. The record is a redirect target
(`volatility: high`) and is never answered from the KB; it had been
inflating the Terminal 1 information set in the same way without anyone
noticing, because Terminal 1 has two desks anyway. Excluding
high-volatility records from the cue stage's category set is the general
statement of that; it restored h012 and changed nothing else on either
split.

## 5. Before / after

Vision `per_image.csv` byte-identical on both splits. Text and multimodal:

| Measure | Text dev | Text held-out | MM dev | MM held-out |
|---|---|---|---|---|
| Correct | 35/43 → 35/43 | 24/36 → 24/36 | 27/35 → 27/35 | 23/33 → 23/33 |
| Wrong record / wrong-confident | 1 → 1 | 1 → 1 | 2 → 2 | 1 → 1 |
| Decisions (answer/clarify/abstain/redirect) | 22/13/5/3 → same | 15/15/2/4 → same | – | – |
| Grounded negatives fired | q019 → q019 | h024 → none | mm_022, mm_035 → same | – |
| Routing / conflict tp-fp-fn | – | – | 1.00, 4-0-1 → same | 0.97, 5-2-0 → same |

Rows that changed: h024 (grounded negative → answer `shuttle_t1_t2` at
0.70, margin 0.30, through the category-filtered semantic stage now that
the shuttle is allowed in Terminal 2); h025 "drop off point for taxis at
terminal 2" and h035 "parking at terminal 2" (same record and verdict,
flag `terminal_mismatch` → `cross_terminal_service`, so the sentence is now
"Taxi Rank is in Terminal 1 and also serves Terminal 2" rather than "is
not at Terminal 2"); q027 "wheelchair help terminal 2" (same answer, the
runner-up in the allowed set changed, margin 0.17 → 0.14). The judge
credited h024 as "correct" before and after, which is why the held-out
count does not move: the 03.2 note already recorded that the lenient rule
hid this case, and the false-"no" count is the measure that changes
(1 → 0). q019, the true negative, still fires; mm_022 and mm_035 are
unchanged.

## 6. Regression cases (expectations written before the run)

| Case | Query | Expected | Before (04.2) | After |
|---|---|---|---|---|
| qa002 h024 shape | "Is there a shuttle bus from terminal 2?" | answer shuttle; `cross_terminal_service`, no `grounded_negative`/`terminal_mismatch` | answer shuttle with `terminal_mismatch` ("not at Terminal 2") | as expected |
| qa003 true negative | "Does Terminal 2 have a lounge?" | `grounded_negative`, lounge as pointer | fires | still fires |
| qa004 terminal-specific | "Where is the check-in hall in Terminal 2?" | answer `checkin_t2`, no scope flag | answer `checkin_t1` with `terminal_mismatch` | unchanged, wrong |
| qa005 cross-terminal | "Is there a first aid room in Terminal 2?" | answer `first_aid_t1`, `cross_terminal_service` | `terminal_mismatch` | as expected |
| qa006 no terminal | "How often does the shuttle run?" | answer shuttle, no `grounded_negative` | clarify (confirm shuttle, 0.47) | unchanged |
| mm_141 | h024 by id | answer `shuttle_t1_t2` | wrong_confident (grounded negative) | correct |

Flag checks 4 of 5 as expected; verdicts 4 of 6 by the text judge; the
multimodal regression split is 8/8. The two misses are not this pass's
rule: qa004 is an alias defect ("check-in hall" is an alias of the Terminal
1 record only, and a single alias hit answers even when another record of
the category serves the asked terminal), and qa006 is the single-candidate
threshold item already on the list (the right record, 0.47 against
`tau_high` 0.50, so a confirmation rather than an answer). Both are
recorded with the expectation I wrote, not re-labelled.

## 7. Open observations

- Alias hit versus asked terminal (qa004): a general candidate for a later
  pass is to let a terminal entity re-target a single alias hit to the
  same-category record that serves that terminal, when one exists, and
  keep `terminal_mismatch` only when none does.
- The terminal in "shuttle **to** terminal 2" is a destination, not the
  passenger's location. The entity extractor does not read prepositions;
  the scope field made the distinction unnecessary here, but a query such
  as "how do I get from terminal 2 to the lounge" still carries Terminal 2
  as if the passenger were asking about services there.
- The car park is now an airport-level service by the spec's §4 grouping;
  the old test wording "Car Park P1 is not at Terminal 2" was updated
  accordingly.

## 8. Decision

**Accepted.** The false grounded negative on the held-out set is gone
(1 → 0) with the true negative retained (q019, qa003, and the lounge and
lost-property asymmetries in tests); outcome accuracy, wrong-record and
wrong-confident counts, clarify and abstain counts, routing and conflict
detection are identical on dev and held-out; two Terminal 2 answers became
truthful about scope. The alias re-targeting observation goes to the QA
list.
