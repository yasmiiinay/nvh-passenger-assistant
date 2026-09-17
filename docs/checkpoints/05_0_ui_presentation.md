# 05.0 — Interface presentation rework (post-evaluation, presentation only)

Date: 17 September 2026. Base: v1.1 behaviour as frozen for blind evaluation
v2 (commit 4d149d1; main at 505c09d). Status: implemented and tested in the
development workspace; screenshots taken from a headless browser against
the local server (Archivo web font not loaded there, so the font in the
screenshots is the system fallback).

## Scope and boundary

The interface was redesigned from a written UI concept (chat-style
transcript, status chips with a symbol and words, quick replies, an
"Evidence & details" panel, a single composer for text, photo and voice,
an explicit "Request assistance" action) after both blind evaluations were
complete. The boundary was set before starting and holds:

- Changed: `app/app.py` (layout, CSS, how outcomes are shown), `tests/test_app.py`,
  README paragraph, this note, five screenshots under `docs/report/screenshots/`.
- Unchanged: everything under `src/`, `configs/`, `data/`, and all evaluation
  scripts. No threshold, template sentence, knowledge-base record, router rule
  or model call was touched. `git diff --stat 505c09d -- src configs data scripts`
  is empty.

The answer text the passenger reads is still exactly the string returned by
`src.responses.render_outcome`; the page only splits it into paragraphs and
escapes it. Every measurement in the QA notes and both blind evaluations
therefore still describes what this interface shows.

## What the page now does

Session history. The page keeps earlier passenger/assistant turns on screen.
This is a display list in Gradio session state; the router is called with
the current text, photo and audio only, and nothing from earlier turns is
appended to a request. "Clear conversation" empties the list. A note in the
evidence panel says so ("Session history is shown for reference. Each
request is processed independently."). A message that looks like a
follow-up ("What about Terminal 2?") is processed on its own and will
usually be a clarification or an abstention, which is the honest outcome
for a system without dialogue state.

Status chip. Every assistant turn carries one chip made of a symbol and
words: strong match, uncertain (please confirm), no reliable match,
question back to you, inputs disagree, official information, could not
read the input. The chip is derived from `Outcome.decision` and
`Outcome.band` by a lookup table (`STATUS`), not by new logic. Colour is
used only on "no reliable match" and always together with the words.

Fact chips. Next to the status: which evidence the answer came from (the
existing `ROUTE_LABELS`), and for a matched record its terminal and zone,
stated opening hours and step-free flag, read from the knowledge-base
record. These repeat facts already in the answer text in a scannable form.

Quick replies. Up to three buttons appear after a clarification or a
conflict. Each one is a pre-filled new request sent through the same
callback as typed text:

| outcome | buttons | request sent |
|---|---|---|
| clarify, `clarification_field == "terminal"` | Terminal 1 / Terminal 2 | `"<category> in Terminal N"`, the same example the answer text gives |
| clarify, 1–3 named candidates | the record names | the record name |
| conflict with text and photo | Use my question / Use the photo | the text alone, or the photo alone |

No button re-enters the router with extra state. A terminal quick reply
after "Where is security?" sends "security in Terminal 1", which for
Nordhaven correctly yields a second clarification between Security North
and Security South (two records in Terminal 1); the next quick reply
resolves it by name via the alias stage.

Official information. A redirect outcome is shown inside a ruled panel
labelled "Official information" instead of a plain answer, so the redirect
reads as a hand-off rather than an answer.

Voice. After an audio turn the transcript is shown in an editable box
("You said — edit if this is wrong"); submitting it sends the edited text
as a new text-only request.

Assistance. "Request assistance" in the header opens the existing
escalation panel (note, reference number, contact route from the KB).
Wording states that no one is connected to the chat.

Composer. One text field, the photo and voice inputs side by side, Send
and Clear conversation, and the scope sentence (not a live agent, no live
flight status, fictional airport). The photo component keeps
`image_mode=None` so transparent pictograms are not flattened to black.

## Accessibility checks kept from 03.4

- Every input keeps a visible label; nothing relies on placeholder text alone.
- Status is never colour-only.
- Single column at 400 px; measured `scrollWidth` 400 at a 400 px viewport
  (no horizontal scroll). Touch targets 44–48 px.
- Focus outline 2 px accent on every control.
- Similarity numbers appear only inside "Evidence & details", described as
  a retrieval distance, not a probability; no percentage is shown next to an
  answer.

## Tests

`tests/test_app.py` was rewritten for the new callback shape (`run_turn`
returns a dict). New checks: every status has words as well as a symbol;
passenger text is HTML-escaped; quick replies are produced only for terminal
clarifications, short candidate lists and text+photo conflicts; a second
turn keeps the first on screen while the turn counter and history grow;
the independence note is present in the evidence text. Full suite: 215
passed (was 211; four new interface tests).

## Not done, deliberately

- No thumbnail-and-remove attachment previews in the composer; Gradio's own
  photo and audio components are used as they are.
- No "Yes / No" quick replies for an uncertain photo. A "yes" would need the
  router to answer from an uncertain image, which is a policy change.
- The web font is loaded from Google Fonts by the Gradio theme; on a network
  that blocks it the system font is used, which is acceptable.

## Evidence for the report

Screenshots in `docs/report/screenshots/`: empty state, strong-match answer,
clarification with terminal quick replies, conflict with "Use my question /
Use the photo", and the 400 px single-column view. They are illustrations
of the interface, not evaluation results.
