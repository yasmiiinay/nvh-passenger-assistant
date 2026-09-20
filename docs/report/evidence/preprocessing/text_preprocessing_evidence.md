# Text preprocessing evidence

Real outputs of the frozen functions `src/normalizer.py::normalize_l1` / `normalize_l2`, `src/entities.py::extract` and `src/retrieval.py::resolve_deterministic` on queries from `data/text/queries_*.csv`. `✓KB` / `✗KB` marks whether an identifier or terminal exists in the knowledge base. The last column is the deterministic interpretation only; queries it leaves unresolved go on to the MiniLM semantic stage (not run here).

| id | case | raw query | L1 generic | L2 airport | entities | cues | deterministic interpretation |
|---|---|---|---|---|---|---|---|
| q007 | exact identifier (desk) | Where is desk 145? | where is desk 145 | (= L1) | desk_id=DESK 145 ✓KB | — | stage `exact_identifier` → **answer**, record `checkin_t1` |
| q001 | exact identifier (gate) | Where is gate B12? | where is gate b12 | (= L1) | gate_id=B12 ✓KB | — | stage `exact_identifier` → **answer**, record `gates_pier_b` |
| q006 | terminal reference + service | Check-in desks Terminal 2 | check in desks terminal 2 | (= L1) | terminal=Terminal 2 ✓KB | cue desks→check_in | unresolved → handed to the semantic stage |
| q026 | service request, no identifier | I need wheelchair assistance | i need wheelchair assistance | (= L1) | — | family accessibility | unresolved → handed to the semantic stage |
| q036 | flight reference (volatile) | What gate is flight XY456 leaving from? | what gate is flight xy456 leaving from | (= L1) | flight_ref=XY 456 | cue gate→gate | stage `no_retrieval` → **redirect**, record `flight_information`, flags ['volatile'] |

**Reasons recorded by the cascade**

- **q007** — exact identifier DESK 145
- **q001** — exact identifier B12
- **q006** — not resolved deterministically; handoff = `{"cue_records": ["checkin_t2"], "category_hints": ["check_in"], "terminal": ["Terminal 2"], "zones": [], "families": [], "transfer": false, "landmark_records": [], "candidates": ["checkin_t2"], "deictic": false}`
- **q026** — not resolved deterministically; handoff = `{"cue_records": [], "category_hints": ["accessibility"], "terminal": [], "zones": [], "families": ["accessibility"], "transfer": false, "landmark_records": [], "candidates": ["prm_point_t1_entrance", "prm_point_t1_checkin", "prm_point_t2", "prm_point_rail"], "deictic": false}`
- **q036** — flight reference XY 456: live flight data is never answered from the KB

## The same functions on a spoken-style transcript

Typed queries rarely need the L2 rules; ASR output does. This string is not from the dataset — it is a constructed example of the letter-word and terminal-short-form forms that Whisper produces for spoken identifiers, shown to make the L2 step visible:

| input | L1 generic | L2 airport | entities |
|---|---|---|---|
| How do I get to gate bee twelve in T2 | how do i get to gate bee 12 in t2 | how do i get to gate b12 in terminal 2 | gate_id=B12; terminal=Terminal 2 |

## Order of operations (as implemented)

1. `normalize_l1`: NFKC, lowercase, contraction expansion, punctuation and whitespace rules, cardinal number words → digits.
2. `normalize_l2`: letter / NATO words → pier letters in gate context, identifier spacing collapse (`b 12` → `b12`), terminal short forms (`t2` → `terminal 2`), service-name homophones.
3. `extract`: regex identifiers (flight refs on the raw text, gate/desk/belt/terminal/time/deictic on the normalised text), then the service gazetteer built from KB names and aliases; each identifier is marked as existing or not in the KB.
4. `resolve_deterministic`: volatile redirect → exact identifier → alias/gazetteer → grounded negatives; anything unresolved is handed to the semantic stage with the entities and cues found here.

## Where the embedding sees the text

After the deterministic stages, `src/text_encoder.py::encode` passes the normalised string to `sentence-transformers/all-MiniLM-L6-v2`. Its WordPiece tokenizer turns `what gate is flight xy456 leaving from` into `what gate is flight x ##y ##45 ##6 leaving from` (10 pieces); the alphanumeric code is fragmented, so identifier matching cannot be left to the embedding — it is done before this point. (Full tokenisation examples: `data_exploration/text_preprocessing_examples.md`.)
