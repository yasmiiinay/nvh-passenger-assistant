# Structured deployment scenarios (user-testing evidence)

## Methodology

The five scenarios below are the **manual deployment smoke test** of the hosted
application (`https://huggingface.co/spaces/yasmincinar/nvh-assistant`, Space
commit `030552f`, source commit `081b279`), recorded on 2026-09-18 in
`docs/report/evidence/deployment_smoke_test.md` with screenshots in
`docs/report/evidence/ui_deployment_*.png`. Inputs were fresh, chosen to avoid
every Blind v3 query, image, clip and scenario, and each exercises one required
modality of the final interface: text, image, voice, image + text, and an
unsupported request. The tests were performed by the developer through the
deployed Gradio UI; there were no external participants, so this is
**integration verification** of the end-to-end application, not a user study
and not an accuracy benchmark. "Expected behaviour" is what the frozen design
specifies for the input (router rules R0–R6 and the KB contents); "actual" is
the recorded output. Expectations for scenarios 1 and 2 were written before
the run; those for 3–5 were derived from the design rules after the outputs
were seen, so they are not pre-registered predictions. The "Correct?",
"Observed limitation" and "Suggested improvement" columns are the developer's
interpretation of the recorded outputs, not recorded data.

## Scenario table

| # | Scenario | Input modality | Passenger input | Expected behaviour | Actual system behaviour | Correct? | Observed limitation | Suggested improvement (future work; not implemented) |
|---|---|---|---|---|---|---|---|---|
| 1 | Transport service in a named terminal, with a one-turn clarification | Text | "Where does the long-stay car park shuttle leave from at Terminal 1?" — then the quick reply **Car Park P1** | A KB-grounded answer for the Terminal 1 parking record; a clarification is acceptable if the wording matches more than one transport record within the margin rule | Turn 1: *"There are 2 transport locations in Terminal 1: Car Park P1 or Terminal Shuttle (T1 ↔ T2). Which one do you mean?"* — Question back to you, From your words. Turn 2: *"Car Park P1 is in Terminal 1, P1 (Opposite Terminal 1; footbridge at Level 1). From Departures, cross the covered footbridge at the north end of the Check-in Hall."* Location · Hours: always open · Access: step-free; Strong match; evidence Why = "A place name in your question" | Correct after clarification | "Long-stay car park shuttle" did not separate a shuttle *to a car park* from the shuttle *between terminals* in the KB descriptions, so the system asked rather than answered directly; two turns were needed | Add discriminating aliases (e.g. "long-stay", "P1 shuttle") to the parking record, or show one-line descriptions with the clarification options so the passenger can choose faster |
| 2 | Photographed sign without any words | Image only | `img_007.png` (AIGA information pictogram, development split; not in any blind set), text box empty | Recognise the sign category and, because information desks exist in both terminals, ask which terminal rather than guess | *"This looks like an information sign. Are you in Terminal 1 or Terminal 2?"* — Question back to you, From your photo; evidence: category *information* 0.31 (cosine), options = Flight Information boards, Information Desk T2, Information Desk T1 Arrivals, Information Desk T1 Departures; quick replies Terminal 1 / Terminal 2 | Safe clarification | With no words and no terminal, the image alone cannot resolve to one of four information records; the flight-information boards are listed among the options although a "?" pictogram usually denotes a staffed desk | Weight the information-desk records above the flight-information boards for the *information* pictogram, or ask "desk or departure boards?" after the terminal is known |
| 3 | Spoken question about ground transport at the other terminal | Voice (recorder upload path) | Synthetic 16 kHz clip, "Where can I catch a taxi outside Terminal 2?" | Transcript shown for correction; answer the taxi record and make clear which terminal it is in | Heard as *"Where can I catch a taxi outside Terminal 2?"* (verbatim); answer *"Taxi Rank also serves Terminal 2. Taxi Rank is in Terminal 1, Forecourt (Arrivals, Level 0 (outside)). Exit the Arrivals Hall and turn right along the forecourt."* Hours: staffed marshal 06:00–23:00, taxis at all times; Strong match; From your voice; editable transcript displayed | Correct | The directions are written from the Terminal 1 Arrivals Hall; a passenger standing in Terminal 2 gets the right record but not a route from where they are. The clip was synthesised and uploaded, not recorded through the microphone | Store terminal-relative directions for records that serve both terminals; complete a live-microphone check before submission (see below) |
| 4 | Photographed sign plus a deictic question naming the terminal | Image + text | `img_007.png` + "I'm in Terminal 1, where is the nearest one of these?" | Image supplies the category, text supplies the terminal; candidates narrowed to Terminal 1 information records, then either an answer or a clarification among them | *"This looks like an information sign. Which one do you mean: Flight Information (Departure and Arrival Boards), Information Desk, Terminal 1 Arrivals or Information Desk, Terminal 1 Departures?"* — Question back to you, "From your photo, words used to narrow down"; technical details: entities `terminal = Terminal 1`, `deictic_ref = these`; text intent scored weak (`find_transport` 0.60), image led; candidates correctly limited to the three Terminal 1 records; flags `text weak, image needs terminal` | Safe clarification; routing correct, explanation partly inconsistent | The candidate list was narrowed to Terminal 1, yet an evidence line still reads "terminal unknown" and the quick reply offers "Terminal 1" again; "nearest" cannot be used because the passenger's position within the terminal is unknown | Generate the evidence wording and quick replies from the narrowed candidate set rather than from the image-only branch; when the terminal is known, offer the remaining records as the quick replies |
| 5 | Service the airport does not have, phrased as a purchase | Text (uncertainty / unsupported) | "Is there a post office where I can buy stamps in the airport?" | No KB answer; abstain with a reason that says the service is not covered, and do not invent a location | *"I cannot book, reserve, print or arrange anything; I can only give information about the airport."* — No reliable match; evidence Outcome = No answer, retrieval stage `no_retrieval`; technical details: entities `unsupported_service = post office`, flags `unsupported_service, action_request`, why = "'post office' is a service the knowledge base does not hold" | Safe abstention; reason wording less precise than the evidence | Both `unsupported_service` and `action_request` fired ("buy" matched the action rule); the passenger-facing sentence chose the action-request wording, while the accurate reason appears only under Technical details | Rank the unsupported-service explanation above the action-request explanation whenever a named unsupported service is present; consider pointing to the information desk as the official source for services outside the KB |

Pass criterion used in the smoke test: the UI accepted the input, the backend
returned a response with routing evidence within roughly 30 s, and no Gradio
error occurred. All five scenarios met it.

## Observations

- Every required modality reached the backend and returned routing evidence on
  the deployed build; the answer, clarification and abstention states were all
  observable in the interface, each with an evidence panel that names the
  route, the matched record or candidate list and the cosine score band.
- Three of five scenarios ended in a clarification or abstention on the first
  turn. That is the intended behaviour of the frozen policy for inputs that do
  not identify one record — but it also means a passenger often needs a second
  action, which the quick replies make cheap.
- The text-side wording layer lags the routing layer in two places (scenarios
  4 and 5): the decision is right, the sentence explaining it is not the most
  precise one available. Both are recorded in the smoke-test evidence and left
  unchanged in the frozen build.
- Evidence panels expose cosine similarities with an explicit note that they
  are retrieval distances, not probabilities; scenario 2's category score of
  0.31 is a "strong match" on the vision scale, which sits far below the text
  scale.

## Limitations of this evidence

- Single tester (the developer), five scenarios, one session: this verifies
  integration of the hosted application, not accuracy, coverage or usability
  with passengers. No satisfaction or task-time data was collected and none is
  claimed.
- Voice was verified through the recorder's **upload** path with a synthesised
  clip, because the automated browser session had no microphone. Upload and
  microphone recordings share the same audio gate, Whisper and text pipeline,
  but **direct live microphone capture in the deployed Space remains a small,
  unverified deployment step**. If a live recording is made before submission,
  this table should be updated with its result.
- The scenarios were chosen by the developer with knowledge of the system;
  they avoid Blind v3 material but are not a random sample of passenger
  requests.
- The transcript in scenario 3 was verbatim for a synthetic voice; the earlier
  preprocessing evidence (`preprocessing/audio_preprocessing_evidence.md`)
  shows a quiet human clip being mis-transcribed, so verbatim transcription
  should not be generalised from this scenario.

## Distinction from Blind v3

Blind v3 is the formal evaluation: 46 independently authored cases, frozen
before execution, run once through `scripts/run_final_blind.py` directly
against the frozen core, with pre-registered metrics (decision, category and
record accuracy, safe-outcome rate, WER, conflict precision/recall). The
scenarios here were run afterwards through the deployed Gradio interface
(`app/app.py::run_turn`), which the blind harness never imports. They answer
"does the hosted application work end to end across modalities?", not "how
accurate is the system?". The two must not be pooled, compared or presented as
a time series, and the five rows above are not an additional evaluation set.

## Report-ready summary (≈150 words)

The final deployed interface was exercised in five structured deployment
scenarios covering typed text, an uploaded pictogram, a spoken query, a
pictogram combined with text, and an unsupported service request. All five
completed end to end on the hosted Space: each input reached the frozen core,
returned a KB-grounded response with routing evidence, and raised no
application error. These scenarios verify integration of the deployed
application rather than providing another independent accuracy benchmark;
Blind v3 remains the formal evaluation. Clarification (scenarios 1, 2 and 4)
and abstention (scenario 5) were directly observable, each with its evidence
panel, and one scenario resolved to a full answer after a single quick-reply
follow-up. Two minor inconsistencies were retained as limitations rather than
corrected: an evidence line that reports the terminal as unknown after the
text had already narrowed the candidates, and an abstention explanation that
chose the less precise of two applicable reasons. Voice was verified through
the recorder's upload path; live microphone capture remains a small
verification gap.
