# Manual usability diagnostics (final usability build)

Date: 17 September 2026. These are hands-on tests of the running interface,
carried out after both blind evaluations. They are diagnostics, not an
evaluation: the tester knew the system and its rules, the cases were written
to probe known failure classes, and some sentences were used while the fixes
were designed. They show how the system behaves for a passenger and where it
still fails; they are not accuracy estimates and are not added to any blind
or held-out metric.

Three kinds of run are recorded:

- typed questions in Chrome against the local server;
- photos uploaded in Chrome (dataset pictograms, pictograms not in the
  dataset, and five sign images found on the web);
- spoken questions recorded by the author with her own voice in Safari on a
  MacBook microphone.

Privacy. The voice recordings were made in the browser and processed locally;
they are not stored in the repository. Only the transcripts Whisper produced,
as shown in the interface, are reproduced here. The web sign images are not
redistributed; they are described below.

Builds. Round 1 ran on commit d976a36 plus 13147f5/e3f14c0 (usability
hardening pass). The findings of round 1 led to round 2 (this commit); rows
marked "round 2" were re-checked on the round-2 build.

## 1. Typed questions (Chrome, round 1)

Sixteen questions written after the hardening pass, none of them from the
diagnostic set that drove it.

| # | Question | Result | |
|---|---|---|---|
| T1 | Which way is check-in desk number 218? | Check-in, Terminal 2 | pass |
| T2 | I'm beside Security South and I need first aid. | First Aid Room (Security South used as location); answer opened with opening hours because "first" was read as an hours word | record right, wording fixed |
| T3 | Where can I use the toilet once I've gone through security in Terminal 1? | Restrooms, Terminal 1 Departures and Airside | pass |
| T4 | I've arrived in Terminal 1 and just want somewhere for coffee. | Harbour Café | pass |
| T5 | I need reduced-mobility assistance. Where should I go? | Asked for the terminal (accessibility points only) | pass |
| T6 | What's the best way to change from Terminal 1 to Terminal 2? | "Do you mean Terminal Shuttle?" | fixed (13147f5): now answers |
| T7 | Where can I store my suitcase in a locker? | No reliable information about lockers | pass |
| T8 | Is Security South still open at 8:45 pm? | "Yes … open at 20:45; listed hours 04:30–21:00" | pass |
| T9 | When does the last airport train leave? | Rail station, hours 04:30–00:45 | pass |
| T10 | I misplaced my wallet somewhere in the airport. | Lost Property Office | pass |
| T11 | Where is security in T1? → And Terminal 2? | North/South question, then Security, Terminal 2 | pass |
| T12 | Where is security in T1? → Where is gate C5? | Pier C Gates; no carry-over | pass |
| T13 | What about arrivals? | Asked what to find (no service picked) | pass |
| T14 | I'm near the information desk and I feel unwell. Is there a nurse? | First Aid Room | pass |
| T15 | Where can I get wheelchair help in Terminal 1 arrivals? | Assistance Point, Terminal 1 Main Entrance | pass |
| T16 | Is there an ATM in Terminal 2? | No reliable information about "atm" | pass |

## 2. Photos (Chrome)

| # | Image | Result (round 1) | Round 2 wording |
|---|---|---|---|
| I1 | Women's toilet pictogram, not in the dataset | restroom, strong; terminal asked | "This looks like a restroom sign. Are you in Terminal 1 or Terminal 2?" with Terminal 1 / Terminal 2 buttons that now complete the question |
| I2 | First-aid pictogram (dev image) | medical, strong; First Aid Room | unchanged |
| I3 | Restaurant pictogram (dev image) | restaurant, strong, margin 0.026 | short terminal question |
| I4 | Rail pictogram (dev image) | transport, strong; five records and "Which terminal are you in?" | lists the five places; no terminal question, since all serve both terminals |
| I5 | Suitcase icon cropped from a phone photo of a screen | baggage, strong | short terminal question |
| I6 | Unrelated photograph (flowers) | no reliable match | unchanged |
| I7 | I1 rotated 12° and halved | restroom, strong; "the photo looks bright" | quality note dropped on a strong match |
| I8 | First-aid pictogram + "Where can I get medical help?" | First Aid Room, photo agrees; answer called First Aid "the nearest designated assistance point" | assistance-point sentence now only for PRM points |

Five sign images from the web, none in the dataset (scores from the frozen
CLIP bands; vision was not changed):

| # | Image | Top categories | Behaviour |
|---|---|---|---|
| N1 | Photographed hanging sign "Gate C7" | baggage 0.320, check-in 0.320, gate 0.301 (margin 0.001), uncertain | round 1 offered "baggage or check-in"; round 2 asks what the sign says, because the photo is closest to the printed-document anchor |
| N2 | Blue diagonal arrow | transport 0.328, accessibility 0.324, uncertain | offers two categories; there is no out-of-scope anchor for directional arrows |
| N3 | Photographed "Departures" sign | baggage 0.321, gate 0.320, uncertain | as N1 in round 2 |
| N4 | Wheelchair pictogram | accessibility 0.362 (margin 0.096), strong | correct; "an accessibility sign" (article fixed) |
| N5 | Lost-property pictogram (umbrella, bag, question mark) | security 0.318 (margin 0.024), strong | confident wrong category |

N5 follows from a documented scope limit: `lost_property` has no visual class
in the controlled vocabulary, so CLIP has no prompt to match and the image
falls to the nearest category. N1–N3 show the same style-generalisation
failure as the blind image cases: signs whose meaning is carried by large
text split their similarity between categories. The system stays uncertain on
them rather than confident, which is the safer failure.

HEIC. An iPhone `.HEIC` photo selected in Chrome was silently dropped by the
browser image component (the passenger saw "Please type a question"). The
label now says "JPEG or PNG"; server-side HEIC support does not help an
upload the browser never sends.

## 3. Own voice (Safari, MacBook microphone)

| Transcript shown | Round 1 result | Round 2 |
|---|---|---|
| (clip rejected: too quiet, −46 dBFS) | asked to re-record or type | unchanged (gate −45 dBFS, frozen) |
| "Reach Ray is Gate C9." | Pier C Gates | unchanged |
| "My check-in counter is 212." | Check-in, Terminal 2 | unchanged |
| "I am next to Security Salt and I need a nurse." | First Aid Room | unchanged |
| "I need wheelchair help. I am in terminal 1 arrivals." | Assistance Point, Terminal 1 Main Entrance | unchanged |
| "How can I change from terminal 2 to terminal 1?" | Terminal Shuttle | unchanged |
| "Do you have an ATM in terminal 1?" | no reliable information | unchanged |
| "Is Sacred North open at 9.15 p.m.?" | "Harbour Café or Aurora Lounge?" | "could not find that" (safe, still not the right answer) |
| "There is baggage claim in Terminal 1." | Baggage Reclaim, Terminal 1 | unchanged |

Seven of the eight usable clips were resolved correctly although three
transcripts contained substitutions ("Reach Ray", "Security Salt", "Sacred
North"): an identifier, a service word ("nurse") or a unique alias carried the
meaning. The failure had two causes, neither in Whisper's control of the
identifier: "9.15 p.m." was normalised to "9 15 p m" and read as 09:15, and an
opening-hours intent pulled café and lounge records in beside the single
security record the cue had found. Both were fixed as general rules in round 2
(clock spellings with and without meridiem; an hours or directions intent no
longer widens a single-record cue). The ASR substitution itself remains: with
"Sacred" instead of "Security" the similarity to Security North is 0.21, below
the abstain threshold, so the system now declines instead of guessing.

The recorder layout was also tested: after recording, the playback controls
were clipped by the fixed-height card, and the card's clear (X) control was
redundant next to the "optional" label. Round 2 lets the voice card grow,
hides the X and adds a "Record again" button that appears once a clip exists.

## 4. What this evidence supports

- Deterministic evidence (identifiers, aliases, service words) survives ASR
  noise better than similarity: three of three noisy transcripts that carried
  such a word were answered correctly.
- Photos of clean pictograms work at category level; photos whose meaning is
  in text do not, and KB categories without a visual class are a source of
  confident wrong categories.
- The interface failures found here (clipped recorder, silent HEIC drop, long
  evidence panel) were invisible to the automated evaluation, which calls the
  pipeline directly.

Limitations of this evidence: one tester who knew the system, one microphone
and accent, a handful of images per case, and cases chosen to probe known
failure classes.
