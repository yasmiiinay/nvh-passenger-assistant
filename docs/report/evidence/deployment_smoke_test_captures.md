# Deployment smoke test — verbatim page-text captures

Raw text of the deployed application's main panel, as returned by the automated
browser's page-text extraction during the 05.1 smoke test on 2026-09-18
(Space commit `030552f`, direct URL `yasmincinar-nvh-assistant.hf.space`).
Each block is copied unchanged from the capture; only the static header/footer
lines of the page ("Nordhaven Airport Assistant", composer labels, scope note)
are omitted where marked `[…]`. Technical-details panels that were opened and
photographed rather than captured as text are referenced by screenshot.

These captures are the source for exact quotations in
`user_testing/structured_user_testing.md`; the screenshots
`ui_deployment_*.png` show the same states as rendered.

## A — text, after the quick reply "Car Park P1" (capture 1)

```
PASSENGER
Where does the long-stay car park shuttle leave from at Terminal 1?
NORDHAVEN ASSISTANT

There are 2 transport locations in Terminal 1: Car Park P1 or Terminal Shuttle (T1 ↔ T2). Which one do you mean?

?
Question back to you
From your words
PASSENGER
Car Park P1
NORDHAVEN ASSISTANT

Car Park P1 is in Terminal 1, P1 (Opposite Terminal 1; footbridge at Level 1).

From Departures, cross the covered footbridge at the north end of the Check-in Hall.

📍
Location:
Terminal 1 · P1
🕒
Hours:
always open
♿
Access:
Step-free
✓
Strong match
From your words
EVIDENCE & DETAILS FOR THE LAST ANSWER
```

Evidence panel (screenshot `ui_deployment_text.png`): Outcome *Answer* · Based on *your words* ·
Why *A place name in your question* · Matched place *Car Park P1* · Match strength *Strong match*.

## B — image only, `img_007.png` (capture 2)

```
PASSENGER
Sent without a question
NORDHAVEN ASSISTANT

This looks like an information sign. Are you in Terminal 1 or Terminal 2?

?
Question back to you
From your photo
Terminal 1
Terminal 2
EVIDENCE & DETAILS FOR THE LAST ANSWER
▼
OUTCOME
Question back to you
BASED ON
your photo
WHY
The kind of sign recognised in your photo
OPTIONS
Flight Information (Departure and Arrival Boards), Information Desk, Terminal 2, Information Desk, Terminal 1 Arrivals, Information Desk, Terminal 1 Departures
MATCH STRENGTH
Strong match (score 0.31)
Technical details
```

Screenshot: `ui_deployment_extra_image_only.png`.

## C — voice only, synthetic clip "Where can I catch a taxi outside Terminal 2?" (capture 3)

```
PASSENGER · VOICE
Voice recording
HEARD AS
Where can I catch a taxi outside Terminal 2?
NORDHAVEN ASSISTANT

Taxi Rank also serves Terminal 2.

Taxi Rank is in Terminal 1, Forecourt (Arrivals, Level 0 (outside)).

Exit the Arrivals Hall and turn right along the forecourt.

📍
Location:
Terminal 1 · Forecourt
🕒
Hours:
staffed marshal 06:00-23:00; taxis available at all times
♿
Access:
Step-free, accessible toilet nearby
✓
Strong match
From your voice
You said — edit if this is wrong, then press Enter to ask again
EVIDENCE & DETAILS FOR THE LAST ANSWER
▼
OUTCOME
Answer
BASED ON
your voice
WHY
A place name in your question
MATCHED PLACE
Taxi Rank
MATCH STRENGTH
Strong match
Technical details
```

Screenshot: `ui_deployment_extra_voice.png`.

## D — image + text, `img_007.png` + "I'm in Terminal 1, where is the nearest one of these?" (capture 4)

```
PASSENGER
I'm in Terminal 1, where is the nearest one of these?
NORDHAVEN ASSISTANT

This looks like an information sign. Which one do you mean: Flight Information (Departure and Arrival Boards), Information Desk, Terminal 1 Arrivals or Information Desk, Terminal 1 Departures?

?
Question back to you
From your photo, words used to narrow down
Terminal 1
EVIDENCE & DETAILS FOR THE LAST ANSWER
▼
OUTCOME
Question back to you
BASED ON
your photo, words used to narrow down
WHY
The kind of sign recognised in your photo
OPTIONS
Flight Information (Departure and Arrival Boards), Information Desk, Terminal 1 Arrivals, Information Desk, Terminal 1 Departures
MATCH STRENGTH
Strong match (score 0.31)
Technical details
```

Technical details (screenshot `ui_deployment_extra_multimodal_technical.png`): Decision *Question back to you* ·
Evidence used *your photo, words used to narrow down* · Input modalities *text, image* ·
Understood as *i am in terminal 1 where is the nearest 1 of these* ·
Why *image category information (0.31) matches 3 records; terminal unknown* ·
Detected intent *find_transport · nearest example 0.60 ("how do I get to the other terminal")* ·
Entities *terminal = Terminal 1, deictic_ref = these* · Retrieval stage *category_filter_semantic* ·
Top records by similarity *Bus Terminal 0.48, Car Park P1 0.47, Nordhaven Airport Rail Station 0.47* ·
Photo, top categories *information 0.31, restaurant 0.28, check in 0.28 · margin 0.031* ·
Photo, closest non-sign anchor *a blank or blurry image 0.26* · Similarity *0.31 · strong match* ·
Pending clarification *kept for one turn: category information, terminal Terminal 1* ·
Candidates *Flight Information (Departure and Arrival Boards), Information Desk, Terminal 1 Arrivals, Information Desk, Terminal 1 Departures* ·
Flags *text weak, image needs terminal*.

## E — text, "Is there a post office where I can buy stamps in the airport?" (capture 5)

```
PASSENGER
Is there a post office where I can buy stamps in the airport?
NORDHAVEN ASSISTANT

I cannot book, reserve, print or arrange anything; I can only give information about the airport.

!
No reliable match
From your words
EVIDENCE & DETAILS FOR THE LAST ANSWER
▼
OUTCOME
No answer
BASED ON
your words
WHY
Booking or arranging things is not something this assistant does
MATCH STRENGTH
No reliable match
Technical details
```

Technical details (screenshot `ui_deployment_extra_uncertainty_technical.png`): Decision *No answer* ·
Input modalities *text* · Understood as *is there a post office where i can buy stamps in the airport* ·
Retrieval stage *no_retrieval* · Evidence used *your words* ·
Why *'post office' is a service the knowledge base does not hold* ·
Entities *unsupported_service = post office* · Flags *unsupported_service, action_request*.
