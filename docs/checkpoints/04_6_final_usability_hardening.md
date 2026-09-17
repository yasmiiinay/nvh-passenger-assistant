# 04.6 — Final usability hardening and response UX (deployment build)

Date: 17 September 2026. Base: local main after c02c868 (v1.1 behaviour,
presentation rework 05.0). Status: implemented and tested in the development
workspace; the Safari recorder check (section H) is a manual step on the
MacBook and is recorded below as pending.

## Why this pass exists, and what it is not

Blind Evaluation v2 (`docs/report/final_blind_evaluation_v2/`) measured the
frozen v1.1 system (commit 4d149d1). After it, manual usability testing of
the interface with ordinary passenger phrasings exposed failure classes the
evaluation sets had not isolated: a landmark named after "near" or "at"
was answered instead of the service asked for, identifiers survived only in
one phrasing, journey-stage words (airside, just landed) were ignored,
"special assistance" resolved to first aid, an inter-terminal transfer
competed with the rail station, "baggage lockers" became baggage reclaim,
a fragment such as "What about Terminal 2?" was sent to similarity search
and came back as a café, and an explicit "at 8:30 pm" produced "I cannot
see the current time". The answers were also long: every KB field was read
out for every question.

This pass fixes those classes for deployment. The blind evaluations were
NOT rerun, no blind dataset or result file was touched, and the build this
produces is a later "final usability-hardened deployment build", not the
system the blind-v2 metrics describe. Nothing here is a performance claim
for the final build beyond the dev, held-out and usability regression
results reported in section 8.

Frozen and unchanged: `data/kb/airport_kb.json` (32 records), the blind
datasets and result files, the CLIP and Whisper models and their code
(`src/vision.py`, `src/speech.py`), the MiniLM encoder, every threshold in
`configs/settings.py`, and the evaluation scripts. No LLM, OCR, Docker,
FAISS or new model was added.

## Manual diagnostic observations (v1.1)

Text: ten failures listed in the brief (desk 225, check-in in Terminal 2,
after-security meal and bathroom, special assistance → first aid, "sick
near Security North" → Security North, T1→T2 → shuttle-or-rail,
"last train" → confirmation, baggage lockers → reclaim, "open at 8:30 pm"
→ no-clock caveat) plus the follow-up "What about Terminal 2?" → Pier C
Café. Voice: Whisper was not the bottleneck; the transcripts that failed
("My chicken desk is 225", "sick near security north", "from terminal 1
to terminal 2") failed in the text layer. Vision: functional on in-domain
pictograms; the blind-image weakness remains a documented domain/style
generalisation issue and vision was not touched.

## General failure classes and the changes

All word lists live in `data/vocabulary.json` under a new additive key
`query_interpretation` (the KB file is untouched). Every rule is read from
the extraction, applied before similarity search, and documented in the
module docstrings.

| class | change | where |
|---|---|---|
| requested service vs mentioned location (C1) | A service alias or identifier that follows a location preposition (near, beside, at, from, after, past …) gets `Entity.role = "landmark"`. Landmarks are never the alias target; they supply the terminal (and the zone tags of their record) as constraints, and their record is excluded from the semantic candidate set. A landmark is only a landmark when something else is asked for: "How long is the queue at security north?" keeps Security North as the target. | `src/entities.py` (`_role_at`), `src/retrieval.py` |
| identifier grammar (C2) | `desk / counter / check-in desk … [number] [is/at] NNN`, `belt / carousel … N`; "gate" is consumed with the identifier so it stops acting as a category cue. "My chicken desk is 225" resolves through the identifier; no ASR correction dictionary was added. | `src/entities.py` |
| journey-stage zones (C3) | Zone phrases (airside / after security / passed security …, landside / before security, arrivals / just landed / arrived …, departures / departing …) are consumed and become constraints. Each record carries `zone_tags` derived only from its own `level` and `zone` fields (`src/kb.py`). A constraint that would empty the candidate set is dropped, not enforced. A zone after "to / towards" is a destination, not a constraint ("up to departures"). | `src/kb.py`, `src/entities.py`, `src/retrieval.py` (`constrain`) |
| accessibility vs medical (C4) | Two service families (special assistance, wheelchair, reduced mobility, PRM … / sick, ill, injured, medical, nurse, doctor …) name the category and outrank single-token cues ("first" from "first aid"). Generic assistance with no location and PRM points in both terminals asks for the terminal instead of guessing the Terminal 1 entrance; with a terminal the nearest point is still answered (assist policy). | `src/entities.py`, `src/retrieval.py` |
| inter-terminal transfer (C5) | Two different terminals in one query, or transfer wording (between terminals, change terminal, other terminal …), resolve like an alias to the record that connects the terminals, read from the KB (`connecting_records`: a name or alias that names both terminals or a transfer). With other service evidence present the same set constrains the semantic candidates. | `src/retrieval.py` |
| unsupported services (C6) | A small airport-specific list of services the Nordhaven KB does not hold (lockers, ATM, currency exchange, pharmacy, smoking, prayer room, shops, hotel, showers, car hire, passport control …). Named as the request and with no alias or identifier present, the query is refused with one concise sentence; used as a landmark ("toilets after passport control") it is ignored and the request proceeds. | `data/vocabulary.json`, `src/retrieval.py` |
| fragments (C7) | Text left with only function words once identifiers, aliases, zones, terminals and lead-ins ("what about", "and") are removed never reaches similarity search: with a pending clarification it completes it, otherwise it is asked "What would you like to find in Terminal 2?". | `src/entities.py` (`FUNCTION_WORDS`, `fragment`), `src/retrieval.py` (`_resolve_fragment`) |
| alias supplement | Three records gain synonyms outside the frozen KB (`service_synonyms`): rail station (train, trains, railway, rail station), taxi rank (taxi, cab), lost property (lost my, I lost, misplaced …). "What time is the last train" therefore resolves deterministically instead of scoring 0.49 against the 0.50 answer threshold. | `data/vocabulary.json`, `src/entities.py` |
| action requests | "Book / reserve / print …" is refused as an abstention with the named place as a pointer, instead of a refusal sentence in front of a full answer. This matches the dev label q039 and the blind-v2 finding on T2_B017 without touching the blind set. | `src/retrieval.py` (`_apply_action_policy`) |

Explicit clock times (E): "8:30 pm", "20:30", "at 8 30" become a
`clock_time` entity (`HH:MM`) and the flag `time_explicit`; the response
compares it with the record's listed hours when those are a plain daily
range (overnight ranges wrap), otherwise it quotes the hours. "Open now"
keeps the no-clock caveat.

### One-turn clarification context (D)

`route(..., pending)` accepts the previous turn's context and returns
`Outcome.pending_next`; the interface stores it in session state and
replaces it on every request. `pending_context` reduces an unresolved text
clarification to `{category, terminal, zones}`; answers, redirects,
abstentions, conflicts and photo-settled questions leave nothing behind.
Only a fragment consults it (`STAGE_CONTEXT = "clarification_context"`,
flag `followup_context`); a fresh query that ends in a terminal question
also takes a terminal given one turn earlier. It survives exactly one turn,
carries no image or audio, and "Clear conversation" drops it. The
interface copy now reads: "Earlier messages are shown for reference. A
short follow-up may use the immediately preceding clarification; otherwise
requests are processed independently."

### Concise responses (F, G)

`src/responses.py` has two layers. `render` produces two to four sentences
for the aspect asked (where: place and one direction; hours: verdict or
listed hours and place; accessibility: access facts, notes, assistance
point, contact; directions: place and the directions field). Provenance,
the similarity band and the full field dump are gone from the transcript.
`record_details` returns every field of the selected record for the
evidence panel, and `compact_facts` at most four icon + label + value
items (Location, Hours, Access, Route) for the fact row. Rule G replaces
the 05.0 rule: a fact item may show a field of the record the outcome
selected even when the short answer does not repeat it; it must come from
that record only, never influence selection, never contradict the answer,
never add an inferred fact. `test_compact_facts_come_only_from_the_selected_record`
checks all 32 records. Clarifications are one sentence; "I heard: …" is no
longer repeated in the answer because the transcript is shown as "Heard
as" in the passenger turn.

### Voice recorder layout (H)

The voice card is no longer a fixed 150 px box: `#voice` has a minimum
height and grows while recording so the Stop control, timer and waveform
stay inside the card; the photo card keeps its fixed height. Gradio's
top-right clear icon is kept, because it is the only reliable way to
discard a recording and re-record; it is rendered visually secondary
(reduced opacity until hovered). No JavaScript was added. Labels stay
"Photo of a sign (optional)" and "Ask by voice (optional)".

## Regression results (final build vs v1.1)

Reference snapshot: v1.1 (after QA 04.5). All runs on the same dev,
held-out, regression, multimodal and speech sets; nothing was re-labelled.

| set | v1.1 | final build |
|---|---|---|
| text dev (43) | 36 correct, 1 wrong record (q019) | 37 correct, 1 wrong record (q019, unchanged) |
| text held-out (36) | 24 correct, 0 wrong records | 29 correct, 0 wrong records |
| text QA regression (15) | 12 correct | 11 correct (qa013, see below) |
| multimodal dev (35) | 27 correct, wc 2 | 28 correct, wc 2 (unchanged cases), conflict 4/0/1 unchanged |
| multimodal held-out (33) | 24 correct, routing 0.939, conflict 5/0/0 | 26 correct, routing 0.970, conflict 5/0/0 |
| multimodal regression (13) | 13 | 13 |
| speech dev TTS (100) | typed 95, ASR 90 | typed 100, ASR 95 (five shuttle clips), WER unchanged |
| speech held-out TTS / human | 17/20, 3/5 | 17/20, 3/5 |

Changed verdicts, all inspected: dev q034 (T1→T2 transfer, now shuttle),
q039 (booking a taxi, now refused as labelled), held-out h014 (airside
sit-down meal → Skyline), h015 (coffee near the arrivals exit → Harbour
Café), h023 (cash machine → refused), h026 (train → rail station), h036
(from the rail station up to departures → rail station); multimodal
mm_029, mm_123, mm_127 (safe mismatches that are now the labelled
abstention). The one verdict that moved the other way is deliberate: dev
q026 "I need wheelchair assistance" and regression qa013 "my mother needs
a wheelchair" were labelled answer (spec section 5: assistance errs toward
answering); under C4 a generic assistance request with no location now
asks for the terminal, which the judge counts as over-cautious. No new
wrong-record answer appeared on any set; flight redirects, cross-terminal
grounded negatives, conflict detection and image-only uncertainty
behaviour are unchanged.

### The sixteen usability cases

| # | case | v1.1 | final build |
|---|---|---|---|
| 1 | Where is gate B17? | gates_pier_b | gates_pier_b |
| 2 | My check-in desk is 225. Where do I go? | terminal clarify | checkin_t2 |
| 3 | Where is security in Terminal 1? | North / South clarify | North / South clarify |
| 4 | Is Security South open at 8:30 pm? | right record, "cannot see the current time" | "Yes … open at 20:30; listed hours 04:30–21:00" |
| 5 | I just landed in Terminal 2. Where do I collect my bag? | baggage_reclaim_t2 | baggage_reclaim_t2 |
| 6 | I lost my headphones. Where should I go? | "Do you mean Lost Property Office?" | lost_property_t1 |
| 7 | I just arrived in Terminal 1 and want a coffee. | cafe_harbour | cafe_harbour |
| 8 | I've passed security in Terminal 1 and want a sit-down meal. | Skyline / Harbour clarify | restaurant_skyline |
| 9 | I need a bathroom after security in Terminal 1. | departures / arrivals clarify | restrooms_t1_departures |
| 10 | I need wheelchair assistance in Terminal 2. | prm_point_t2 | prm_point_t2 |
| 11 | I need special assistance. Where should I go? | first_aid_t1 (answer) | terminal clarify over PRM points |
| 12 | I feel sick near Security North. Where can I get medical help? | security_t1_north | first_aid_t1 |
| 13 | How do I get from Terminal 1 to Terminal 2? | shuttle / rail clarify | shuttle_t1_t2 |
| 14 | What time is the last train from the airport? | "Do you mean … Rail Station?" | rail_station, listed hours |
| 15 | Has flight NV402 landed yet? | redirect | redirect |
| 16 | Are there baggage lockers in Terminal 2? | baggage_reclaim_t2 (strong) | refused: no reliable information about lockers |

Follow-up: "Where is security in Terminal 1?" then "What about Terminal
2?" → security_t2 through the pending context (v1.1: Pier C Café). A full
unrelated question after the clarification ignores the context; two turns
later the context is gone; "Clear conversation" drops it.

Voice transcripts (text level): "Where is Gate B17?" → gate; "My chicken
desk is 225. Where do I go?" → checkin_t2 (v1.1: terminal clarify);
"Various Security Terminal 1" → North / South clarify; "I just landed in
Terminal 2, where do I collect my bag?" → baggage_reclaim_t2; "I feel sick
near security north …" → first_aid_t1 (v1.1: security north); "How do I
get from terminal 1 to terminal 2?" → shuttle (v1.1: shuttle / rail);
"has flight NV402 landed yet" → redirect.

Paraphrases not among the diagnostic sentences (all in
`tests/test_usability_046.py`): other landmark + medical request (check-in
hall + nurse; Pier B + first aid), other desk and belt syntax (counter 118,
desk number is 210, carousel number 3, belt is number 8), other
after-security wording (through security, airside), other transfer wording
(change terminals, the other terminal, from T2 to T1, shuttle between the
terminals), reduced mobility, faint + medical room, other unsupported
services (locker, cash machine, exchange money, pharmacy, duty free), other
explicit times (20:30, 11 pm), and false-positive checks (supported services
are not refused, an unsupported place used as a landmark does not block the
request, medical does not become PRM and vice versa, a destination zone is
not a constraint, "bus terminal" is not a transfer, empty input and
greetings are not fragments).

Tests: 282 passed (`python -m pytest tests`), of which 61 are the new
usability regression file; `tests/test_responses.py`, `test_app.py`,
`test_router.py`, `test_retrieval_semantic.py` and `test_entities.py` were
updated for the concise layer, the pending context and the new rules.

Interface checks (headless Chromium): the follow-up flow renders as a
transcript with the fact row under answers; the evidence panel holds the
record fields; 400 px viewport has no horizontal scroll (`scrollWidth`
400); the voice card grows instead of clipping. Manual Safari smoke test
(record ≥ 5 s, Stop visible, transcript, re-record, photo replacement,
400 px) is required on the MacBook before deployment and has not been done
in this workspace.

## Round 2 (after Chrome, photo and own-voice runs)

The manual runs recorded in `docs/report/manual_usability_diagnostics_046.md`
exposed the following failure classes. Each fix is a general rule with
paraphrase and false-positive tests; thresholds, KB, CLIP and Whisper are
unchanged.

| Class | Seen in | Change |
|---|---|---|
| Clock times with a.m./p.m. spelling ("9.15 p.m.", "8 pm") read as morning | own voice | meridiem and preposition clock patterns; a bare hour 1–12 keeps both readings and the verdict says when they differ |
| An hours or directions intent widened a single-record cue to unrelated records | own voice ("Sacred North") | aspect intents keep the cue records |
| Terminal quick replies missing after a photo clarification | I1, I3, I5 | photo clarifications carry the one-turn pending context |
| Terminal question asked when every candidate serves both terminals | I4 | the candidates are listed instead |
| Sign whose meaning is in text offered two unrelated categories | N1, N3 | nearest anchor is the printed-document anchor → ask what the sign says |
| Uncertain photo carried its guessed category into the next turn; evidence listed baggage options for an unreadable sign | Chrome re-check, N1 | an uncertain photo leaves no clarification context; "Options" hidden when the sign cannot be read (flag `image_text_sign` now set by the router; metrics unchanged, the flag appears in the flags column of mm_023 and mm_122) |
| Quality note shown on a strong photo match | I7 | note only when the band is not strong |
| First aid described as "the nearest designated assistance point" | I8 | assistance sentence only for accessibility records |
| Article and capitalisation in image wording ("a accessibility sign") | N4 | article and label helpers |
| HEIC photo silently dropped by the browser component | Chrome | label says "JPEG or PNG" (no server change can help) |
| Recorder playback clipped; redundant clear (X) | Safari | voice card grows, X hidden, "Record again" button |
| Evidence panel too long for a passenger | Safari | five-row summary (outcome, based on, why, matched place, match strength); the full table sits under "Technical details" |

Regression after round 2 (snapshot `after_046_4`) is identical to round 1:
text dev 37/43, held-out 29/36 (0 wrong records), QA regression 11/15;
multimodal dev 28/35, held-out 26/33, routing 0.970, conflict 5/0/0,
multimodal regression 13/13; speech WER unchanged. Full suite: 306 passed.
"Sacred North" now abstains: the right outcome would be Security North, but
the transcript's similarity (0.21) is below the abstain threshold, so the
change turns a wrong clarification into a safe refusal rather than a correct
answer. N5 (lost-property pictogram → security, strong) is not fixed: the
controlled vocabulary has no visual class for lost property.

## Remaining limitations

- A landmark is only recognised when something else is asked for; "I'm
  hungry, near Security North" still answers Security North because
  "hungry" is neither a cue, a family word nor a recognised intent.
- The unsupported-service list is authored; a service not on it and not in
  the KB still falls to the semantic stage, where the intent gate usually
  turns it into a confirmation question rather than an answer.
- The pending context is one turn deep by design; "and the one before
  that?" has no meaning to the system.
- Hours verdicts cover plain daily ranges only; "staffed marshal
  06:00-23:00; taxis available at all times" is quoted, not judged.
- Zone tags come from the level and zone strings of the KB; a record whose
  fields do not say "airside" or "arrivals" carries no tag and is never
  excluded by a zone constraint.
- Vision is unchanged, so the blind-image weakness (drawn pictograms and
  photographed signs of other styles) stands as documented in 04.5 and the
  blind v2 summary.

## Report wording

"Blind Evaluation v2 was performed on the frozen v1.1 behavioural system.
Subsequent manual usability testing exposed general failure classes in
service-vs-location interpretation, contextual retrieval,
unsupported-service handling and short follow-ups. A later
deployment-oriented usability hardening pass addressed these classes. The
blind evaluation was not rerun, so its results remain evidence for v1.1
rather than a performance claim for the final deployment build."
