# Final blind evaluation v2 — v1.1, one run

Date: 17 September 2026. Behavioural freeze: `a23ab4e229e2950824b66a285919f5f3dc6534c9`
(v1.1, QA 04.5). Dataset freeze: `4d149d118d7551ee8991da039ca58c31efad2702`
(`Freeze independent blind evaluation v2`, whose parent is `a23ab4e`;
`git diff a23ab4e 4d149d1` touches no file under `src/`, `configs/`,
`data/`, `evaluation/`, `app/` or `requirements.txt`). Evaluated at
`4d149d1`.

Pre-run verification: 20 text, 8 image, 6 audio and 12 multimodal cases;
`blind_v2_audio_sha256.txt` 6/6, `blind_v2_images_sha256.txt` 8/8,
`blind_v2_manifests_sha256.txt` 5/5 (including `SELF_CHECK_V2.txt`) and
`final_blind_v2_text_postaudit_sha256.txt` all verified; the text
manifest's SHA-256 equals the post-audit value in the brief
(`e30d6c07…`). Every expected label is populated. The image manifest
states that no expectation depends on OCR, and the descriptions bear
that out. Each case was run exactly once with
`scripts/run_final_blind.py --set v2` (evaluation code only; the runner
was parameterised for the v2 file names, nothing else). Thresholds in
force are those of v1.1: `tau_high` 0.50, `tau_low` 0.25, `margin_delta`
0.10, `tau_intent` 0.30, `tau_intent_answer` 0.40, vision 0.30 / 0.24 /
0.015. Per-case files: `final_blind_v2_text_results.csv`,
`final_blind_v2_image_results.csv`, `final_blind_v2_audio_results.csv`,
`final_blind_v2_multimodal_results.csv`; metrics in
`final_blind_v2_summary.json`. Verdict labels and the route mapping are
those of the v1 summary.

## 1. Text (20 cases)

| Measure | Count | Rate |
|---|---|---|
| Correct verdict | 12 / 20 | 0.60 |
| Decision as expected | 13 / 20 | 0.65 |
| Category as expected (17 with a category) | 15 / 17 | 0.88 |
| Expected record answered (10 with a record) | 7 / 10 | 0.70 |
| Wrong-record / wrong-confident answers | 2 (T2_B017, T2_B019) | 0.10 |
| Clarify ↔ answer mismatches | 3 (T2_B002, B007, B010) | |
| Abstain expected, not given | 3 (T2_B017, B019, B020) | |
| Incorrect redirects | 0 | |
| Missed redirects | 1 (T2_B015) | |
| False grounded negatives | 0 | |
| Safe outcome (no wrong-confident, no wrong redirect) | 18 / 20 | 0.90 |

Correct: T2_B001, B003, B004, B005, B006, B008, B009, B011, B012, B013,
B016, B018.

## 2. Vision (8 images)

| Measure | Count | Rate |
|---|---|---|
| Top-1 category (6 in-scope) | 2 / 6 | 0.33 |
| Top-3 inclusion | 4 / 6 | 0.67 |
| In-scope outcome correct | 1 / 6 (IMG2_B01) | 0.17 |
| Out-of-scope ended safely (clarify) | 2 / 2 | 1.00 |
| Out-of-scope abstained as expected | 0 / 2 | 0.00 |
| Wrong-confident image answers | 0 | |
| By stratum, outcome correct | clean 1/2, photographed 0/2, angled 0/1, blurred 0/1, out-of-scope 0/2 | |

Bands: strong match on IMG2_B01 (medical, answered) and IMG2_B06
(transport); the other six in the uncertain band with margins 0.003 to
0.013, five of them with `baggage` on top. Neither excluded sign reached
an anchor (closest 0.23 for both, below the in-scope scores).

## 3. Speech (6 clips)

| Measure | Value |
|---|---|
| Mean WER (L2) | 0.114 |
| Exact transcriptions | 4 / 6 |
| WER by condition | clean 0.111 (AUD2_B02 "Café" → "Cafe"), identifier 0.00, terminal_specific 0.00, fast_natural 0.00, mild_noise 0.571 |
| Identifier accuracy (1 clip) | 1 / 1 (belt 5) |
| Decision as expected | 5 / 6 (0.83) |
| Expected record answered | 5 / 6 (0.83) |
| ASR errors that changed the outcome | 0 |
| ASR errors absorbed | 2 (AUD2_B02 answered; AUD2_B06 "Our taxis are available after 11 ad notes" still answered the taxi rank) |

All six clips passed the audio gate. AUD2_B05 clarified between the two
restaurant records with an exact transcript; that is the text ambiguity,
not a speech loss.

## 4. Multimodal (12 scenarios)

| Measure | Count | Rate |
|---|---|---|
| Correct verdict | 4 / 12 | 0.33 |
| Decision as expected | 4 / 12 | 0.33 |
| Expected record answered (7 answer cases) | 3 / 7 | 0.43 |
| Routing as expected (mapped) | 10 / 12 | 0.83 |
| Conflict detection | tp 2, fp 0, fn 2; precision 1.00, recall 0.50 | |
| Wrong-confident | 2 (MM2_B09, MM2_B10) | |
| Unsafe answers (answer where none expected) | 2 (same) | |
| Safe clarify / abstain | 6 (MM2_B02, B03, B04, B06, B08, B11) | |
| Consistent scenarios correct | 3 / 8 | 0.38 |
| Conflicting scenarios correct | 1 / 4 | 0.25 |

Correct: MM2_B01, MM2_B05, MM2_B07, MM2_B12. Conflict recall counts
MM2_B09 as detected (the router flagged the disagreement) although the
turn ended in an identifier answer, which is why tp is 2 while the
verdict is wrong-confident.

## 5. Failure analysis (after the full run; nothing changed)

| Case | Expected | Observed | Likely cause | Severity | Known? |
|---|---|---|---|---|---|
| T2_B002 | answer info_desk_t1_departures | "Departures or Arrivals desk?" | "departures level" is not an entity the filter reads; the two T1 desks tie (0.61, margin under 0.10) | safe failure | ambiguity handling (level not extracted) |
| T2_B007 | answer restrooms_t1_departures | "Departures/Airside or Arrivals restrooms?" | "past security" carries the airside cue only as words; the two T1 restroom records tie at 0.74 | safe failure | same |
| T2_B010 | answer car_park_p1 | "Car Park P1 or Assistance Point, Check-in Hall?" | 0.50 against P1 with a PRM point within the margin (both mention the footbridge / check-in hall) | safe failure | semantic retrieval |
| T2_B014 | clarify accessibility | clarify between two information desks | "assistance" resolves to the information category; PRM points not among the candidates | safe failure, misleading question | category taxonomy (assistance vs information) |
| T2_B015 | redirect | "Check-in T2 or T1?" | no flight word, code or phrase ("departure" is not in the context set, "pushed back" is not an exemplar phrase); the 04.5 guard discarded the `ask_flight_status` intent and the words alone found nothing better than 0.27 | safe failure | **new: a direct cost of v1.1 change 1** |
| T2_B017 | abstain | refusal sentence, then the taxi rank | designed action-request behaviour; the judge counts the record as an answer | benign (refusal explicit) | known (v1 B018) |
| T2_B019 | abstain (German) | answer restrooms_t2 at 0.57 | MiniLM places the German sentence near the Terminal 2 restroom text and the terminal entity narrows to it; the answer is the requested service, given without any language handling | potentially misleading by policy (the prototype has no non-English path, so this is luck, not competence) | language limitation, new shape |
| T2_B020 | abstain | "Do you mean Aurora Lounge?" | currency exchange scores 0.36 against the lounge with a weak intent; confirm rather than answer | safe failure, odd question | known class (OOS above `tau_low`) |
| IMG2_B02, B03, B04, B05, B07, B08 | lost property / rail / restaurant / lounge / two OOS | uncertain, baggage on top in five of six, "X or Y?" | the drawn pictograms sit 0.27–0.32 from every category prompt with margins under 0.015; the baggage prompt is the nearest for most flat panel drawings; anchors do not fire | safe failure | vision similarity on a new drawing style; anchors on pictograms (03.3) |
| IMG2_B06, MM2_B11 | answer bus_terminal | transport, strong; "which terminal?" among five transport records | the image gives a category; rail, bus, taxi, car park and shuttle share it | safe failure | category granularity (KB/schema), not OCR |
| AUD2_B05 | answer restaurant_skyline | "Skyline or Harbour?" | exact transcript; the two restaurant records tie (0.63, margin 0.05) | safe failure | ambiguity handling |
| MM2_B02, B03, B08 | answer lost_property / restaurant | confirm or list from the words; photo uncertain | the photo did not reach the strong band, so it neither answers nor reinforces; the words alone are ambiguous or below `tau_high` | safe failure | vision similarity + text ambiguity |
| MM2_B04 | conflict | "Do you mean Rail Station?" | the lounge photo is uncertain and may not raise a conflict | safe failure | known design boundary (03.4 §5) |
| MM2_B06 | abstain | image-led "baggage or transport?" | the deictic phrase routed to the photo as intended (change 2); the hotel pictogram is uncertain, not anchored | safe failure | anchors on pictograms |
| MM2_B09 | conflict | answer baggage_reclaim_t1 with the disagreement stated | R2: a spoken identifier ("belt 5") leads and a strong photo of another category is surfaced, never merged; the label expects the conflict decision instead | potentially misleading by label; the sentence names the disagreement | known design (03.4 §3, R2) |
| MM2_B10 | conflict | answer security_t2 | the lounge photo is uncertain and may not contradict a confident sentence (0.76) | potentially misleading for a "which way" question beside a wrong sign; the note says the photo was not identified | known design boundary |

Grouped: vision similarity on drawn pictograms 6 (+3 multimodal turns
it decided); ambiguity handling 4 (T2_B002, B007, AUD2_B05, and the
restaurant pair in MM2_B03/B08); category granularity 2 (IMG2_B06,
MM2_B11); category taxonomy 1 (T2_B014); semantic retrieval 1
(T2_B010); OOS handling 2 (T2_B017 by label, T2_B020); language 1
(T2_B019); missed redirect 1 (T2_B015); uncertain-photo conflict
boundary 2 (MM2_B04, B10); identifier-leads design 1 (MM2_B09).

Potentially misleading outcomes: T2_B019, MM2_B09, MM2_B10 (3 of 46).
No image produced a wrong confident answer; no false grounded negative;
no wrong redirect.

## 6. Comparison (descriptive; the sets differ)

| Measure | Development | Held-out | Blind v1 (v1 system) | Blind v2 (v1.1) |
|---|---|---|---|---|
| Text correct | 36/43 (0.84) | 24/36 (0.67) | 11/20 (0.55) | 12/20 (0.60) |
| Text wrong-confident | 1 | 0 | 3 | 2 |
| Text wrong / missed redirects | 0 / 0 | 0 / 0 | 1 / 0 | 0 / 1 |
| Text safe outcome | – | – | 16/20 (0.80) | 18/20 (0.90) |
| Vision top-1 (in-scope) | 18/19 (0.95) | 18/21 (0.86) | 3/6 (0.50) | 2/6 (0.33) |
| Vision in-scope outcome | – | – | 1/6 | 1/6 |
| Speech outcome kept | 90/100 | 17/20 | 5/6 | 5/6 |
| Speech WER (L2) | 0.151 | 0.092 | 0.061 | 0.114 |
| Multimodal correct | 27/35 (0.77) | 24/33 (0.73) | 5/12 (0.42) | 4/12 (0.33) |
| Multimodal wrong-confident | 2 | 0 | 2 | 2 |
| Multimodal routing | 1.00 | 0.94 | 0.50 (mapped) | 0.83 (mapped) |
| Conflict precision / recall | 1.00 / 0.80 | 1.00 / 1.00 | 0.33 / 0.25 | 1.00 / 0.50 |

v1 and v2 were written by the same author under different rules (v2
excludes OCR-dependent images and, by the author's audit, isolates one
factor per out-of-scope text case), so the two blind columns are not an
apples-to-apples experiment and the small samples make every figure
indicative. Read descriptively: on v2 the text safe-outcome rate is
higher and both wrong-confident text cases are label-level (a refusal
followed by information, and a German sentence answered with the right
record); the wrong redirect class of v1 did not recur, but the guard
that removed it produced one missed redirect (T2_B015), which is a
regression in kind even if not in count; the deictic change did what it
was meant to (MM2_B06 routed to the photo); routing and conflict
precision are higher; conflict recall and multimodal correctness are
not, because the two remaining conflict misses are the router's own
policy on uncertain photos and on identifiers, which v1.1 did not
change. Vision is no better on v2: the v2 pictograms are a new drawing
style that CLIP places near the baggage prompt with margins below the
band threshold, so the OCR-free set exposed the next limitation rather
than removing the first. Nothing in this comparison was used to change
the system.

## 7. Safety observations

Wrong-confident: 2 text (T2_B017 with the refusal first; T2_B019, the
right record for a German question), 0 image, 0 speech, 2 multimodal
(MM2_B09 with the disagreement stated, MM2_B10 with the "could not
identify the sign" note). Wrong redirects: 0; missed redirect: 1
(T2_B015, ended in a clarify). Safe clarifications or abstentions where
an answer was expected: 3 text, 5 images, 1 clip, 4 multimodal. Out of
scope: the phone-charger request abstained; currency exchange, the
hotel and retail pictograms ended in questions, not answers. Every
action request rendered the refusal first.

## 8. Limitations of this evaluation

Small samples; one author for labels and assets (with a pre-run audit
of two text rows, documented in `SELF_CHECK_V2.txt`); synthetic
pictograms and synthetic voices only (the author notes no human
recordings were available); route labels scored through a mapping; the
judge treats an action-request response that gives the record after
the refusal, and an identifier-led answer that states the photo's
disagreement, as confident answers.

## 9. Freeze integrity and post-run status

No label, asset or manifest changed (hashes verified before the run).
No threshold, exemplar, alias, gazetteer, KB record, template,
normalisation rule, routing rule, prompt, anchor or Whisper setting
changed. No case re-run; no selection among attempts. No tuning of any
kind after this run, and none is planned: v1.1 is the final behavioural
version.
