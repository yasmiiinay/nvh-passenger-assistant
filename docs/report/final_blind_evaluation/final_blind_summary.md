# Final blind evaluation — frozen system, one run

Date: 17 September 2026. Evaluated commit: `41bd9019a2bec43ce0f1d23b3b0d7f06ed1af062`
(`Freeze final blind text evaluation set`, on top of `042d6978…`, the
image + multimodal freeze named in the brief; `git diff 042d697 41bd901`
touches no file under `src/`, `configs/`, `data/`, `evaluation/`, `app/`,
`scripts/` or `tests/`, so the behavioural code is that of `042d697`). The
brief cited a text-freeze commit `1238d277…`; no such object exists in the
repository or on the remote, and `41bd901` is the commit that carries
`final_blind_text.csv` with the hash recorded in `blind_text_sha256.txt`.

Assets verified before the run against the frozen check files: 20 text
cases, 8 PNG images, 6 WAV clips, 12 multimodal scenarios, four manifests;
every SHA-256 matched. Expected labels were populated in the manifests
before the run and were not edited. Each case was run exactly once with
`scripts/run_final_blind.py` (evaluation code only); the summary
aggregation was rebuilt from the per-case files with `--summary-only`
after a counting bug in the first aggregation, without re-running any
inference. Thresholds in force: `tau_high` 0.50, `tau_low` 0.25,
`margin_delta` 0.10, `tau_intent` 0.30, `tau_intent_answer` 0.40,
`vision_tau_high` 0.30, `vision_tau_low` 0.24, `vision_margin_delta`
0.015. Per-case files: `final_blind_text_results.csv`,
`final_blind_image_results.csv`, `final_blind_audio_results.csv`,
`final_blind_multimodal_results.csv`; metrics in `final_blind_summary.json`.

Verdict labels follow the project's judge (`evaluation/multimodal_metrics.judge_scenario`):
`correct`; `wrong_confident` (an answer that should not have been given,
or the wrong record); `over_cautious` (answer expected, a safe decision
given); `safe_mismatch` (a safe decision expected, a different safe
decision or category given); `wrong_redirect`. Routing on the multimodal
set is scored through the mapping written in the runner, because the
author's route labels (`fuse_consistent`, `flag_cross_modal_conflict`,
`image_resolves_deictic`, `image_only`, `voice_only`) are not the router's
rule names.

## 1. Text (20 cases)

| Measure | Count | Rate |
|---|---|---|
| Correct verdict | 11 / 20 | 0.55 |
| Decision as expected | 12 / 20 | 0.60 |
| Category as expected (17 cases with a category) | 14 / 17 | 0.82 |
| Expected record answered (11 cases with a record) | 7 / 11 | 0.64 |
| Wrong-record / wrong-confident answers | 3 (B010, B018, B020) | 0.15 |
| Clarify ↔ answer mismatches | 4 (B002, B010, B011, B013) | |
| Abstain expected, not given | 3 (B018, B019, B020) | |
| Incorrect redirects | 1 (B014) | |
| Missed redirects | 0 | |
| False grounded negatives | 0 | |
| Safe outcome (no wrong-confident, no wrong redirect) | 16 / 20 | 0.80 |

Correct: B001, B004, B005, B006, B007, B008 (the Turkish sentence
abstained), B009, B012, B015, B016, B017.

## 2. Vision (8 images)

| Measure | Count | Rate |
|---|---|---|
| Top-1 category (6 in-scope) | 3 / 6 | 0.50 |
| Top-3 inclusion (6 in-scope) | 4 / 6 | 0.67 |
| In-scope outcome correct | 1 / 6 (IMG_B02) | 0.17 |
| Out-of-scope ended safely (clarify) | 2 / 2 | 1.00 |
| Out-of-scope abstained as expected | 0 / 2 | 0.00 |
| Wrong-confident image answers | 0 | |
| By stratum, outcome correct | clean 1/2, photographed 0/2, angled 0/1, blurred 0/1, out-of-scope 0/2 | |

Bands: strong match on IMG_B01, B03, B05; uncertain on B04, B06, B07,
B08; no image was placed in "no reliable match" and the out-of-scope
anchors did not fire on either excluded sign (closest anchors 0.24 and
0.20, below the in-scope top scores).

## 3. Speech (6 clips)

| Measure | Value |
|---|---|
| Mean WER (L2 normalisation) | 0.061 |
| WER by condition | clean 0.00, terminal_specific 0.00, fast_natural 0.00, mild_noise 0.00, identifier 0.364 |
| Identifier accuracy (1 clip carries one) | 0 / 1 |
| Decision as expected | 5 / 6 (0.83) |
| Expected record answered | 5 / 6 (0.83) |
| ASR errors that changed the outcome | 1 (AUD_B03) |
| ASR errors absorbed by clarify/abstain | 0 |

All six clips passed the audio gate. Five transcripts were exact.
AUD_B03 "gate A11" was heard as "gay day 11"; the identifier was lost and
the sentence ("boarding pass … which pier") was then read as a
flight-status request and redirected.

## 4. Multimodal (12 scenarios)

| Measure | Count | Rate |
|---|---|---|
| Correct verdict | 5 / 12 | 0.42 |
| Decision as expected | 5 / 12 | 0.42 |
| Expected record answered (7 answer cases) | 4 / 7 | 0.57 |
| Routing as expected (mapped) | 6 / 12 | 0.50 |
| Conflict detection | tp 1, fp 2, fn 3; precision 0.33, recall 0.25 | |
| Wrong-confident | 2 (MM_B04, MM_B05) | |
| Unsafe answers (answer where none expected) | 2 (same) | |
| Safe clarify / abstain | 2 (MM_B06, MM_B11); plus 2 conflicts raised where an answer was expected (MM_B01, MM_B08) | |
| Consistent scenarios correct | 4 / 8 | 0.50 |
| Conflicting scenarios correct | 1 / 4 | 0.25 |

Correct: MM_B02, MM_B03, MM_B07, MM_B10, MM_B12.

## 5. Failure analysis (after the full run; nothing changed)

Severity: benign (the passenger is not misled), safe failure (a safe
decision where a better one existed), potentially misleading (a confident
sentence that points the wrong way). "Known" means the class is recorded
in a checkpoint or QA note in `docs/checkpoints/`.

| Case | Expected | Observed | Likely cause | Severity | Known? |
|---|---|---|---|---|---|
| B002 | answer checkin_t2 | terminal question (T1 or T2) | "desk says 225" does not match the desk pattern (`desk(s) NNN`), so no identifier; the semantic stage ties the two check-in records | safe failure | new (entity pattern coverage) |
| B003 | clarify security | clarify "Bus Terminal or Terminal Shuttle?" | cue `security` + Terminal 1 leaves two checkpoints; the intent classifier reads "which way" as `ask_directions`, whose categories are transport, and the intent filter discards the cue | potentially misleading question | related to the intent-filter design (03.2) |
| B010 | clarify accessibility | answer first_aid_t1 as "nearest designated assistance point" | assist policy turns a clarify into an answer for `request_accessibility_help` at intent 0.42 / similarity 0.42, and the top record is the medical room, not a PRM point | potentially misleading | known: assist-policy residual (QA 04.4 §4, qa012) |
| B011 | answer restaurant_skyline | "Skyline Restaurant or Harbour Café?" | two restaurant records within the margin; "cleared security" is not an entity the filter can use | safe failure | ambiguity handling |
| B013 | answer taxi_rank_t1 | "Taxi Rank or Rail Station?" | both serve Terminal 2 after the 04.3 scope field; margin below `margin_delta` | safe failure | ambiguity handling |
| B014 | answer rail_station | redirect to flight information | no flight code or volatile phrase; the intent classifier labels "first and last … run" as `ask_flight_status`, which redirects | potentially misleading | new (intent-driven redirect on non-flight timing) |
| B018 | abstain | refusal sentence, then Car Park P1 information | designed action-request behaviour: "I cannot book, reserve…" first, then the record; the judge counts the record as an answer | benign (refusal is explicit) | known (03.4 §7 "action requests") |
| B019 | abstain | restroom terminal question | out-of-scope text scoring 0.31, above `tau_low`, against restroom records | safe failure, odd question | known (text OOS near `tau_low`, 03.4) |
| B020 | abstain | answer lounge_aurora | "airport hotel" scores 0.53 against the lounge with a recognised intent; no hotel record to contradict it | potentially misleading | new variant of the known OOS-above-`tau_high` class (h019) |
| IMG_B01 | answer restrooms_t2 | accessibility, strong; "which terminal?" among PRM points | the wheelchair pictogram dominates; "Pier C" text is not read (no OCR) | safe failure | visual similarity + OCR absent (Architecture Freeze) |
| IMG_B03 | answer rail_station | transport, strong; "which terminal?" among five transport records | the image gives a category; the record needs the label "Rail Station" read from the sign | safe failure | design limit: image → category, not record; OCR absent |
| IMG_B04 | answer info_desk_t1_arrivals | uncertain (baggage / check-in) | information symbol not recognised; margin 0.004 | safe failure | visual similarity |
| IMG_B05 | answer checkin_t2 | check-in, strong; "which terminal?" | desk range 201–230 is text; OCR absent | safe failure | OCR absent |
| IMG_B06 | answer gates_pier_c | uncertain (baggage / check-in), blur flagged | "C7" is text; blur; margin 0.002 | safe failure | OCR absent; blur |
| IMG_B07 | abstain | uncertain clarify (baggage / gate) | smoking pictogram; anchors do not fire on pictograms | safe failure | known (03.3 anchors on pictograms) |
| IMG_B08 | abstain | uncertain clarify (medical / baggage) | pharmacy pill symbol resembles the medical prompt | safe failure | known class |
| AUD_B03 | answer gates_pier_a | redirect | ASR "gay day 11" loses the identifier; remaining words read as flight status | potentially misleading | ASR propagation (03.3), intent redirect |
| MM_B01 | answer restrooms_t2 | conflict: "Pier C Gates" vs accessibility sign | alias "pier c" resolves the text to the gate record before the words "accessible toilets" are used; the strong accessibility photo then disagrees | safe failure (asks) | new (alias precedence over the request) |
| MM_B04 | conflict | answer first_aid_t1, with "could not identify the sign… answered from your words" | uncertain photo (info desk not recognised) may not raise a conflict; alias "first aid" answers | potentially misleading for the yes/no question, mitigated by the note | known design boundary (03.4 §5, mm_022) |
| MM_B05 | conflict | answer gates_pier_c, same note | uncertain photo (pharmacy) may not raise a conflict; alias "c gates" answers | same as above | known |
| MM_B06 | abstain | clarify "First Aid Room or Information Desk?" | "this area" has "this" as deictic but "area" is a gate cue, so the deictic branch is skipped; the smoking image is uncertain, so the weak text leads | safe failure, misleading candidates | new (deictic vocabulary and cue interaction) |
| MM_B08 | answer restrooms_t2 | conflict: restroom (voice, 0.83) vs accessibility sign | the accessible-toilet sign is read as the accessibility category; the KB keeps restroom and accessibility apart | safe failure | category taxonomy (KB/schema) |
| MM_B09 | conflict | redirect | the AUD_B03 transcript; R1 redirect precedes conflict handling | potentially misleading | ASR propagation |
| MM_B11 | answer gates_pier_c | uncertain clarify, blur flagged | as IMG_B06 | safe failure | OCR absent |

Grouped: OCR-dependent expectations 5 (IMG_B01, B03, B05, B06, MM_B11);
visual similarity 3 (IMG_B04, B07, B08); ASR propagation 2 (AUD_B03,
MM_B09); intent-filter or intent-redirect errors 2 (B003, B014);
ambiguity handling 3 (B002, B011, B013); unsupported / out-of-scope
handling 3 (B018 by label, B019, B020); assist policy 1 (B010); alias
precedence 1 (MM_B01); uncertain-photo conflict boundary 2 (MM_B04,
B05); deictic vocabulary 1 (MM_B06); category taxonomy 1 (MM_B08).

Potentially misleading outcomes: B010, B014, B020, AUD_B03, MM_B04,
MM_B05, MM_B09 (7 of 46 cases). No image-only case produced a confident
wrong answer. No false grounded negative occurred.

## 6. Comparison with development and held-out results (descriptive)

| Measure | Development | Held-out | Final blind |
|---|---|---|---|
| Text correct | 36/43 (0.84) | 24/36 (0.67) | 11/20 (0.55) |
| Text wrong-record answers | 1 | 0 | 3 |
| Vision top-1 (in-scope) | 18/19 (0.95) | 18/21 (0.86) | 3/6 (0.50) |
| Speech: reference → ASR outcome kept | 95 → 91 / 100 | 20 → 17 / 20 | 6 expected → 5 / 6 |
| Speech WER (L2) | 0.151 | 0.092 | 0.061 |
| Multimodal correct | 27/35 (0.77) | 24/33 (0.73) | 5/12 (0.42) |
| Multimodal wrong-confident | 2 | 0 | 2 |
| Multimodal routing | 1.00 | 0.94 | 0.50 (mapped) |
| Conflict precision / recall | 1.00 / 0.80 | 1.00 / 1.00 | 0.33 / 0.25 |

The blind results are worse than held-out on every text and multimodal
measure and much worse on vision; speech is in line (one identifier
lost, as on held-out). The samples are small (20, 8, 6, 12), so the
figures are indicative, not conclusive. Three things distinguish the
blind set from the development and held-out material and account for
most of the gap without excusing it: the images are newly drawn signs
with text labels rather than AIGA pictograms, and five of the six
in-scope expectations require reading that text (desk range, gate
number, "Pier C", "Rail Station", "Arrivals"), which the frozen system
cannot do without the gated OCR; the text and voice sentences are longer
and more conversational, which exposes the intent classifier (B003,
B014, AUD_B03) more than the shorter development phrasings did; and the
scenario author treats an uncertain photo as able to contradict words
(MM_B04, MM_B05), which the router deliberately does not allow. None of
these observations was used to change anything. The blind set stays
separate from the development and held-out data.

## 7. Safety observations

Wrong-confident: 3 text (B010, B018, B020), 0 image, 0 speech, 2
multimodal (MM_B04, MM_B05). Of these, B018 carries the explicit refusal
sentence first and is an answer only by the judge's rule; MM_B04 and
MM_B05 carry the sentence that the photo could not be identified. Wrong
redirects: B014, AUD_B03, MM_B09 (one transcript counted twice). Safe
clarifications or abstentions where an answer was expected: B002, B011,
B013, five images, MM_B01, MM_B08, MM_B11. Out-of-scope requests: the
Turkish sentence abstained; pharmacy, hotel and smoking did not (two
clarifies, one confident lounge answer). Every action request rendered
the refusal first.

## 8. Limitations of this evaluation

Small samples per modality; a single author of both labels and assets;
synthetic signs rather than photographs of installed signage; synthetic
voices for the six clips; the routing labels required a mapping to the
router's rules; and the judge counts an action-request response that
gives the record after the refusal as a confident answer.

## 9. Freeze integrity

No blind label, asset or manifest was changed (hashes verified before
the run). No threshold, exemplar, alias, gazetteer, KB record, template,
normalisation, routing rule, model or prompt was changed. No case was
re-run after inspection; the only second execution was the summary
aggregation from the per-case files. No tuning of any kind was performed
after the run.
