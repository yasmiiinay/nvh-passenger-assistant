"""Nordhaven International passenger assistant: the Gradio interface.

One callback, `run_turn`, takes whatever the passenger supplied (typed text, a
photo, a voice clip), routes it through src.router and renders the outcome.
Models are loaded on the first question, not at import, so the Space starts
quickly and a modality that is never used is never loaded.

The page shows the session as a conversation, but every request is processed
on its own: the router only ever sees the current text, photo and audio.
Earlier turns stay on screen for reference and are never appended to a new
request. Quick-reply buttons are a convenience that fill in a new request
(for example "security in Terminal 1") and send it through the same path as
a typed one.

Run locally:  python app/app.py
"""
from __future__ import annotations

import base64
import html
import io
import sys
import time
import traceback
from pathlib import Path

import gradio as gr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from configs.settings import SETTINGS
from src.entities import load_gazetteers
from src.event_log import event_from_outcome, log_event, new_session_id, open_ticket
from src.responses import render_outcome
from src.retrieval import RetrievalResult, build_text_index
from src.router import Outcome, build_context, route

try:
    import spaces   # present on ZeroGPU Spaces only; the probe below satisfies its startup check
    _gpu_decorator = spaces.GPU
except ImportError:
    def _gpu_decorator(fn):
        return fn


@_gpu_decorator
def zerogpu_probe() -> str:
    return "ok"


AIRPORT = "Nordhaven International (NVH)"
TITLE = "Nordhaven Airport Assistant"
SUBTITLE = "Ask about gates, baggage, transport and airport services."
SCOPE_NOTE = ("Text, photo and voice can be combined in one request. Nordhaven Assistant is not a live agent "
              "and does not show live flight status. Demonstration system for a fictional airport; "
              "all information is synthetic.")
HISTORY_NOTE = ("Shown for reference only. The assistant keeps no memory of earlier turns: each request is "
                "processed on its own, from the text, photo and voice you send with it.")
EXAMPLES = ["Where is gate B12?", "Where can I collect my baggage?", "How do I get to Terminal 2?",
            "What does this sign mean?"]
QUICK_REPLY_SLOTS = 3

# every status carries a symbol and words, so colour is never the only signal
STATUS = {"strong match": ("&#10003;", "Strong match", "chip--ok"),
          "uncertain": ("?", "Uncertain, please confirm", "chip--ask"),
          "no reliable match": ("!", "No reliable match", "chip--none"),
          "redirect": ("&#9432;", "Official information", "chip--info"),
          "conflict": ("&#8644;", "Inputs disagree", "chip--ask"),
          "clarify": ("?", "Question back to you", "chip--ask"),
          "error": ("!", "Could not read the input", "chip--none")}
ROUTE_LABELS = {"text_only": "your words", "voice_only": "your voice", "image_only": "your photo",
                "text_leads": "your words, photo checked", "voice_leads": "your voice, photo checked",
                "image_leads": "your photo, words used to narrow down", "none": "nothing usable"}
DECISION_LABELS = {"answer": "Answer", "clarify": "Question back to you", "abstain": "No answer",
                   "redirect": "Referred to the official source", "conflict": "Your inputs disagree"}

_context = None


def get_context():
    global _context
    if _context is None:
        gaz = load_gazetteers(SETTINGS.kb_path, SETTINGS.vocabulary_path)
        _context = build_context(gaz, build_text_index(gaz, SETTINGS.intent_exemplars_path))
    return _context


# ---------------------------------------------------------------------------
# what the evidence panel shows
# ---------------------------------------------------------------------------

def evidence_markdown(outcome: Outcome, gaz) -> str:
    lines = [f"**Decision:** {DECISION_LABELS.get(outcome.decision, outcome.decision)}",
             f"**Evidence used:** {ROUTE_LABELS.get(outcome.route, outcome.route)}",
             f"**Why:** {outcome.reason or 'see the answer'}"]
    text = outcome.text
    if text is not None:
        lines.append(f"**Understood as:** `{text.normalized}`")
        if text.entities:
            lines.append("**Entities:** " + ", ".join(f"{k} = {v}" for k, v in text.entities.items()))
        if text.intent:
            lines.append(f"**Intent:** {text.intent} (nearest example score {text.intent_score:.2f}: "
                         f"\"{text.intent_exemplar}\")")
        lines.append(f"**Retrieval stage:** {text.stage or 'none'}")
        if text.ranked:
            lines.append("**Top records by similarity:** " +
                         ", ".join(f"{gaz.records[rid]['name']} {score:.2f}" for rid, score in text.ranked))
    vision = outcome.vision
    if vision is not None:
        lines.append("**Photo, top categories:** " +
                     ", ".join(f"{c.replace('_', ' ')} {s:.2f}" for c, s in vision.category_ranking) +
                     f" (margin {vision.category_margin:.3f})")
        lines.append(f"**Photo, closest non-sign anchor:** {vision.best_anchor[0]} {vision.best_anchor[1]:.2f}")
        if vision.check.flags:
            lines.append("**Photo quality flags:** " + ", ".join(vision.check.flags))
    speech = outcome.speech
    if speech is not None:
        lines.append(f"**Audio:** {speech.check.seconds:.1f} s, {speech.check.rms_dbfs:.0f} dBFS, "
                     f"{'accepted' if speech.check.ok else 'rejected: ' + str(speech.check.problem)}")
    if outcome.score is not None:
        lines.append(f"**Match score:** {outcome.score:.2f}. This is a cosine similarity between your input and "
                     "the record or category text: a retrieval distance, not a probability. Values for this "
                     "system sit between about 0.25 and 0.60, so 0.37 can be a strong match; the status comes "
                     "from the score together with the gap to the runner-up, not from the number alone.")
    if outcome.matched_record_id:
        lines.append(f"**Matched record:** `{outcome.matched_record_id}`")
    if outcome.candidates:
        lines.append("**Candidates:** " + ", ".join(gaz.records[r]["name"] for r in outcome.candidates if r in gaz.records))
    if outcome.conflict:
        d = outcome.conflict_detail
        lines.append(f"**Conflict:** words point to {d.get('text_record') or ', '.join(d.get('text_categories', []))}; "
                     f"photo points to {d.get('image_category')}; resolution: {d.get('resolution')}")
    if outcome.flags:
        lines.append("**Flags:** " + ", ".join(outcome.flags))
    lines.append(HISTORY_NOTE)
    return "\n\n".join(lines)


# ---------------------------------------------------------------------------
# how one turn is shown
# ---------------------------------------------------------------------------

def status_key(outcome: Outcome) -> str:
    if outcome.route == "none":
        return "error"
    if outcome.decision in ("redirect", "conflict", "clarify"):
        return outcome.decision
    return outcome.band or "no reliable match"


def status_chip(key: str) -> str:
    symbol, words, cls = STATUS[key]
    return f'<span class="chip {cls}"><span aria-hidden="true">{symbol}</span> {words}</span>'


def fact_chips(outcome: Outcome, gaz) -> list[str]:
    """Short facts next to the status. Rule: a chip may restate, in a shorter
    form, only what the answer text already says about the selected record
    (terminal and zone, opening hours, step-free access, all printed by
    src.responses._record_text); it never adds a claim the answer does not
    make. The test suite checks this against every knowledge-base record."""
    chips = [f'<span class="chip">From {html.escape(ROUTE_LABELS.get(outcome.route, outcome.route))}</span>']
    record = gaz.records.get(outcome.matched_record_id) if outcome.decision == "answer" else None
    if record:
        place = " · ".join(p for p in (record.get("terminal"), record.get("zone")) if p)
        if place:
            chips.append(f'<span class="chip">{html.escape(place)}</span>')
        hours = (record.get("opening_hours") or {}).get("mon_sun")
        if hours:
            chips.append(f'<span class="chip">Open {html.escape(hours.replace("-", " – "))}</span>')
        if (record.get("accessibility") or {}).get("step_free"):
            chips.append('<span class="chip">Step-free access</span>')
    return chips


def quick_replies(outcome: Outcome, gaz, text: str | None, image_path: str | None) -> list[dict]:
    """Buttons that build the next request for the passenger. Each one is a
    fresh request through the same pipeline; nothing is remembered."""
    if outcome.decision == "clarify" and outcome.clarification_field == "terminal" and outcome.text is not None:
        category = gaz.records[outcome.candidates[0]]["category"].replace("_", "-")
        terminals = sorted({gaz.records[rid]["terminal"] for rid in outcome.candidates})
        return [{"label": t, "text": f"{category} in {t}"} for t in terminals]
    if (outcome.decision == "clarify" and outcome.text is not None and "deictic" not in outcome.flags
            and 0 < len(outcome.candidates) <= QUICK_REPLY_SLOTS):
        names = [gaz.records[rid]["name"] for rid in outcome.candidates]
        return [{"label": (f"Yes, {n}" if len(names) == 1 else n), "text": n} for n in names]
    if outcome.decision == "conflict" and text and image_path:
        return [{"label": "Use my question", "text": text},
                {"label": "Use the photo", "image": image_path}]
    return []


def thumbnail(image_path: str, box: int = 112) -> str | None:
    """A small inline copy of the uploaded photo for the transcript; None when
    the file is not an image the interface can show."""
    try:
        from PIL import Image
        with Image.open(image_path) as im:
            im.thumbnail((box, box))
            buffer = io.BytesIO()
            im.convert("RGBA").save(buffer, format="PNG")
    except Exception:
        return None
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def passenger_html(text: str | None, image_path: str | None, transcript: str | None, audio: bool) -> str:
    parts = ['<div class="turn turn--user">']
    parts.append('<div class="role">Passenger' + (' · voice' if audio else '') + '</div>')
    if image_path:
        thumb = thumbnail(image_path)
        parts.append(f'<img class="thumb" src="{thumb}" alt="Photo you attached">' if thumb
                     else '<div class="chip chip--media">Photo attached</div>')
    if audio:
        parts.append('<div class="chip chip--media">Voice recording</div>')
        if transcript:
            parts.append(f'<div class="subrole">Heard as</div><div class="answer">{html.escape(transcript)}</div>')
    if text:
        parts.append(f'<div class="answer">{html.escape(text)}</div>')
    if not text and not audio and image_path:
        parts.append('<div class="answer muted">Sent without a question</div>')
    parts.append('</div>')
    return "".join(parts)


def assistant_html(response: str, key: str, chips: list[str]) -> str:
    paragraphs = "".join(f"<p>{html.escape(p)}</p>" for p in response.split("\n") if p.strip())
    if key == "redirect":
        body = (f'<div class="official"><div class="role">Official information</div>{paragraphs}</div>')
    else:
        body = f'<div class="answer">{paragraphs}</div>'
    return (f'<div class="turn turn--assistant"><div class="role">Assistant</div>{body}'
            f'<div class="chips">{status_chip(key)}{"".join(chips)}</div></div>')


def conversation_html(history: list[dict]) -> str:
    if not history:
        return '<div id="conversation" class="empty"></div>'
    return '<div id="conversation">' + "".join(t["passenger"] + t["assistant"] for t in history) + "</div>"


# ---------------------------------------------------------------------------
# callbacks
# ---------------------------------------------------------------------------

def run_turn(text, image_path, audio_path, session) -> dict:
    """Process one request on its own and return what the page needs:
    conversation HTML, transcript, evidence, quick replies, session state."""
    session = dict(session or {})
    session.setdefault("session_id", new_session_id())
    session.setdefault("history", [])
    session["turn"] = session.get("turn", 0) + 1
    text = (text or "").strip()
    if not text and not image_path and not audio_path:
        return {"conversation": conversation_html(session["history"]),
                "notice": "Please type a question, add a photo of a sign, or record your question.",
                "transcript": "", "evidence": "", "quick": [], "session": session}
    start = time.perf_counter()
    try:
        ctx = get_context()
        outcome = route(text, image_path, audio_path, ctx)
        response = render_outcome(outcome, ctx.gaz)
    except Exception as exc:                       # the interface must never show a traceback
        traceback.print_exc()
        log_event({"timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "session_id": session["session_id"],
                   "turn_index": session["turn"], "error": f"{type(exc).__name__}: {exc}"[:200]})
        response = "Something went wrong while reading your input. Please try again, or type your question."
        outcome = Outcome(route="none", decision="abstain", error=type(exc).__name__)
        gaz, evidence = None, ""
    else:
        gaz = ctx.gaz
        log_event(event_from_outcome(outcome, session["session_id"], session["turn"], time.perf_counter() - start))
        evidence = evidence_markdown(outcome, gaz)
    key = status_key(outcome)
    chips = fact_chips(outcome, gaz) if gaz is not None else []
    transcript = ""
    if outcome.speech is not None:
        transcript = outcome.speech.transcript_raw or ""
    session["history"].append({"passenger": passenger_html(text, image_path, transcript, bool(audio_path)),
                               "assistant": assistant_html(response, key, chips)})
    session["last"] = {"decision": outcome.decision, "record_id": outcome.matched_record_id,
                       "candidates": list(outcome.candidates), "conflict": outcome.conflict,
                       "terminal": outcome.text.entities.get("terminal") if outcome.text is not None else None}
    quick = quick_replies(outcome, gaz, text, image_path) if gaz is not None else []
    session["quick"] = quick
    return {"conversation": conversation_html(session["history"]), "notice": "", "transcript": transcript,
            "evidence": evidence, "quick": quick, "session": session}


def request_assistance(note, session):
    """Write an escalation record and show the reference and the contact
    route the knowledge base names. This is a record, not a live chat."""
    session = dict(session or {})
    last = session.get("last")
    if not last:
        return "Ask a question first, then request assistance if the answer did not help."
    ctx = get_context()
    stub = Outcome(route="none", decision=last["decision"], matched_record_id=last["record_id"],
                   candidates=last["candidates"], conflict=last["conflict"])
    if last.get("terminal"):
        stub.text = RetrievalResult(query="", normalized="", entities={"terminal": last["terminal"]}, resolved=True)
    ticket = open_ticket(stub, ctx.gaz, session.get("session_id", "unknown"), note or "")
    return (f"Your request has been recorded with reference **{ticket['reference']}**. "
            f"Please quote it at: {ticket['contact_route']}. "
            "This assistant cannot connect you to a person; the airport's own staff and displays "
            "are the official source for anything time-critical.")


# ---------------------------------------------------------------------------
# layout
# ---------------------------------------------------------------------------

CSS = """
.gradio-container { --bg:#f3f2f2; --surface:#eae9e9; --ink:#201e1d; --accent:#ec3013; --accent-deep:#ae1800;
                    --muted:#605d5d; --rule:rgba(32,30,29,.4); --gutter:40px;
                    max-width: 1280px !important; margin: 0 auto; background: var(--bg) !important; color: var(--ink); }
.gradio-container main.app { padding: 0 !important; }
.gradio-container .block, .gradio-container .form { border: 0 !important; background: none !important; box-shadow: none !important; }
footer, .built-with { display: none !important; }
body, .gradio-container, .gradio-container * { font-family: "Archivo", system-ui, sans-serif; border-radius: 0 !important; }
#app { gap: 0; }
#header { display: flex; align-items: center; justify-content: space-between; gap: 16px;
          padding: 16px var(--gutter); border-bottom: 2px solid var(--rule); }
#header .mark { color: var(--accent); font-size: 26px; line-height: 1; }
#header h1 { margin: 0; font-size: 20px; line-height: 1.12; font-weight: 800; }
#header p { margin: 4px 0 0 0; font-size: 14px; color: var(--muted); }
#header .brand { display: flex; align-items: center; gap: 16px; }
#assist-toggle { min-height: 44px; flex: 0 0 auto !important; padding: 0 20px; background: transparent; border: 1px solid var(--rule); }
#conversation-wrap { padding: 0 !important; }
#conversation { padding: 4px var(--gutter) 8px; }
#history-bar { padding: 16px var(--gutter) 0; align-items: center; justify-content: space-between; }
#history-bar .block { padding: 0 !important; }
#history-note { font-size: 13px; color: var(--muted); margin-top: 2px; }
#conversation .turn { display: flex; flex-direction: column; gap: 8px; padding: 16px 0; }
#conversation .turn--user { padding: 12px 16px; margin-top: 16px; background: var(--surface);
                            border-left: 2px solid var(--ink); }
#conversation .turn--user:first-child { margin-top: 0; }
#conversation .turn--assistant { padding: 16px 0 20px; margin-top: 8px; border-bottom: 1px solid var(--rule); }
#conversation .turn--assistant:last-child { border-bottom: 0; }
.role, .subrole, #examples-label { font-weight: 800; font-size: 11px; letter-spacing: .1em; text-transform: uppercase; color: var(--muted); }
.turn--assistant .role { color: var(--accent-deep); }
.answer, .answer p { font-size: 16px; line-height: 1.55; max-width: 68ch; margin: 0; }
.answer p + p { margin-top: 8px; }
.turn--user .answer { color: #444141; }
.muted { color: var(--muted); }
.chips { display: flex; flex-wrap: wrap; gap: 8px; }
.chip { display: inline-flex; align-items: center; gap: 8px; font-size: 13px; padding: 5px 10px;
        border: 1px solid var(--rule); background: var(--bg); color: var(--ink); }
.chip--none { color: var(--accent-deep); border-color: var(--accent-deep); font-weight: 600; }
.chip--ok { font-weight: 600; }
.chip--media { align-self: flex-start; background: var(--surface); }
.thumb { width: 112px; height: 84px; object-fit: contain; background: var(--surface); border: 1px solid var(--rule); }
.official { padding: 18px 20px; background: var(--surface); border: 1px solid var(--rule);
            border-left: 2px solid var(--ink); max-width: 620px; }
.official p { font-size: 16px; line-height: 1.55; margin: 8px 0 0 0; }
#examples { padding: 0 var(--gutter) 8px; }
#examples-label { margin: 24px 0 8px; }
#examples .row { justify-content: flex-start; }
#examples .ex { min-height: 44px; flex: 0 0 auto !important; padding: 0 14px; background: var(--bg); border: 1px solid var(--rule); font-weight: 400; font-size: 15px; }
#examples-hint { font-size: 14px; color: var(--muted); }
#quick { padding: 0 var(--gutter) 16px; }
#quick .row { justify-content: flex-start; }
#quick button { min-height: 44px; flex: 0 0 auto !important; padding: 0 20px; border: 1px solid var(--rule); background: var(--bg); font-weight: 600; }
#notice { padding: 8px var(--gutter); color: var(--accent-deep); font-size: 15px; }
#evidence { margin: 0 var(--gutter) 16px !important; width: auto !important; background: var(--surface) !important;
            border: 1px solid var(--rule) !important; padding: 0 16px 8px !important; }
#evidence .prose { font-size: 14px; }
#assistance { padding: 16px var(--gutter) 16px !important; border-top: 1px solid var(--rule) !important; }
#assistance textarea { background: var(--bg); border: 1px solid var(--rule) !important; font-size: 16px; }
#assistance button { flex: 0 0 auto !important; width: auto !important; align-self: flex-start; min-height: 48px; padding: 0 20px;
                     background: var(--accent); color: var(--bg); font-weight: 800; border: 0; }
#evidence .label-wrap span, #assistance .label-wrap span { font-weight: 800; font-size: 11px; letter-spacing: .1em; text-transform: uppercase; color: var(--muted); }
#composer { border-top: 2px solid var(--rule); background: var(--surface); padding: 18px var(--gutter) 22px; margin-top: 8px; }
#composer textarea, #transcript textarea { min-height: 48px; font-size: 16px; background: var(--bg);
                    border: 1px solid var(--rule) !important; padding: 12px; }
#composer label span, #transcript label span { font-size: 12px; font-weight: 600; letter-spacing: .04em; color: var(--muted); }
#send { background: var(--accent); color: var(--bg); font-weight: 800; border: 0; min-height: 48px;
        flex: 0 0 auto !important; padding: 0 24px; align-self: flex-end; }
#send:hover { background: #dd2b0f; }
#clear { background: transparent; border: 1px solid var(--rule); min-height: 40px; flex: 0 0 auto !important;
         padding: 0 16px; font-weight: 600; font-size: 14px; }
#attachments { align-items: stretch; }
#attachments > .block { min-height: 220px; }
#question, #transcript, #assistance .block, #examples .block, #notice { padding-left: 0 !important; padding-right: 0 !important; }
#scope { font-size: 13px; color: var(--muted); margin-top: 8px; }
#photo, #voice { background: var(--bg) !important; border: 1px solid var(--rule) !important; }
#assistance-note { font-size: 14px; }
:focus-visible { outline: 2px solid var(--accent) !important; outline-offset: 2px; }
@media (max-width: 760px) {
  .gradio-container { --gutter: 18px; }
  #header { flex-direction: column; align-items: flex-start; }
  #composer .row, #quick .row, #examples .row, #history-bar { flex-direction: column; align-items: stretch; }
  #send { align-self: stretch; }
}
"""


def build_ui() -> gr.Blocks:
    theme = gr.themes.Base(primary_hue="red", neutral_hue="stone",
                           font=[gr.themes.GoogleFont("Archivo"), "system-ui", "sans-serif"])
    with gr.Blocks(theme=theme, css=CSS, title=f"{AIRPORT} passenger assistant") as demo:
        session = gr.State({})
        with gr.Column(elem_id="app"):
            with gr.Row(elem_id="header"):
                gr.HTML(f'<div class="brand"><span class="mark" aria-hidden="true">&#9992;</span>'
                        f'<div><h1>{TITLE}</h1><p>{SUBTITLE}</p></div></div>')
                assist_toggle = gr.Button("Request assistance", elem_id="assist-toggle", scale=0, min_width=200)

            with gr.Column(elem_id="examples") as examples:
                gr.HTML('<div id="examples-label">Try asking</div>')
                with gr.Row():
                    example_buttons = [gr.Button(q, elem_classes=["ex"]) for q in EXAMPLES]
                gr.HTML('<div id="examples-hint">You can also send a photo of a sign, or record your question. '
                        'Both work together with text.</div>')

            with gr.Row(elem_id="history-bar", visible=False) as history_bar:
                gr.HTML(f'<div class="role">Session history</div><div id="history-note">{HISTORY_NOTE}</div>')
                clear = gr.Button("Clear conversation", elem_id="clear", scale=0, min_width=180)
            conversation = gr.HTML(conversation_html([]), elem_id="conversation-wrap")
            notice = gr.HTML("", elem_id="notice", visible=False)
            with gr.Row(elem_id="quick", visible=False) as quick_row:
                quick_buttons = [gr.Button("", visible=False) for _ in range(QUICK_REPLY_SLOTS)]
            transcript = gr.Textbox(label="You said — edit if this is wrong, then press Enter to ask again",
                                    visible=False, lines=1, elem_id="transcript")
            with gr.Accordion("Evidence & details for the last answer", open=False, elem_id="evidence",
                              visible=False) as evidence_panel:
                evidence = gr.Markdown(value=HISTORY_NOTE)

            with gr.Column(visible=False, elem_id="assistance") as assistance:
                gr.HTML('<div class="role">Assistance request</div>')
                gr.Markdown("If the answer did not help, leave a short note. A reference number is recorded "
                            "for the airport's contact route named in the answer. No one is connected to this chat.",
                            elem_id="assistance-note")
                note = gr.Textbox(label="Your note (optional)", lines=2)
                request = gr.Button("Record assistance request", variant="primary")
                ticket_out = gr.Markdown(value="")

            with gr.Column(elem_id="composer"):
                with gr.Row():
                    text_in = gr.Textbox(label="Your question", placeholder="Ask about your journey…", lines=1,
                                         elem_id="question", scale=6)
                    send = gr.Button("Send →", elem_id="send", scale=0, min_width=140)
                with gr.Row(elem_id="attachments"):
                    # image_mode=None keeps the file as uploaded: the default RGB conversion
                    # turns a transparent pictogram into a black square before it reaches us
                    image_in = gr.Image(label="Photo of a sign (optional)", type="filepath", sources=["upload"],
                                        image_mode=None, height=180, elem_id="photo")
                    audio_in = gr.Audio(label="Ask by voice (optional)", type="filepath",
                                        sources=["microphone", "upload"], elem_id="voice")
                gr.HTML(f'<div id="scope">{SCOPE_NOTE}</div>')

        turn_outputs = [conversation, examples, history_bar, notice, quick_row, *quick_buttons, transcript,
                        evidence_panel, evidence, session, text_in, image_in, audio_in]

        def to_outputs(result: dict) -> list:
            quick = result["quick"]
            buttons = [gr.update(value=q["label"], visible=True) for q in quick]
            buttons += [gr.update(value="", visible=False)] * (QUICK_REPLY_SLOTS - len(buttons))
            heard = result["transcript"]
            has_history = bool(result["session"].get("history"))
            return [result["conversation"], gr.update(visible=not has_history), gr.update(visible=has_history),
                    gr.update(value=result["notice"], visible=bool(result["notice"])),
                    gr.update(visible=bool(quick)), *buttons, gr.update(value=heard, visible=bool(heard)),
                    gr.update(visible=bool(result["evidence"])), result["evidence"] or HISTORY_NOTE,
                    result["session"], "", None, None]

        def on_send(text, image_path, audio_path, session):
            return to_outputs(run_turn(text, image_path, audio_path, session))

        def on_quick(index, session):
            choice = (session or {}).get("quick", [])[index] if index < len((session or {}).get("quick", [])) else {}
            return to_outputs(run_turn(choice.get("text"), choice.get("image"), None, session))

        def on_example(label, session):
            return to_outputs(run_turn(label, None, None, session))

        def on_clear(session):
            kept = {"session_id": (session or {}).get("session_id", new_session_id())}
            return to_outputs({"conversation": conversation_html([]), "notice": "", "transcript": "",
                               "evidence": "", "quick": [], "session": kept})

        send.click(on_send, inputs=[text_in, image_in, audio_in, session], outputs=turn_outputs)
        text_in.submit(on_send, inputs=[text_in, image_in, audio_in, session], outputs=turn_outputs)
        transcript.submit(lambda heard, s: to_outputs(run_turn(heard, None, None, s)),
                          inputs=[transcript, session], outputs=turn_outputs)
        for i, button in enumerate(quick_buttons):
            button.click(on_quick, inputs=[gr.State(i), session], outputs=turn_outputs)
        for button in example_buttons:
            button.click(on_example, inputs=[button, session], outputs=turn_outputs)
        clear.click(on_clear, inputs=[session], outputs=turn_outputs)
        assist_open = gr.State(False)
        assist_toggle.click(lambda is_open: (gr.update(visible=not is_open), not is_open),
                            inputs=[assist_open], outputs=[assistance, assist_open])
        request.click(request_assistance, inputs=[note, session], outputs=[ticket_out])
    return demo


if __name__ == "__main__":
    build_ui().launch()
