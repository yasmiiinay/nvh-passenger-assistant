"""Nordhaven International passenger assistant: the Gradio interface.

One callback, `run_turn`, takes whatever the passenger supplied (typed text, a
photo, a voice clip), routes it through src.router and renders the outcome.
Models are loaded on the first question, not at import, so the Space starts
quickly and a modality that is never used is never loaded.

The page shows the session as a conversation. Each request is routed from
the current text, photo and audio; the only thing carried from one turn to
the next is the previous turn's unresolved clarification (category,
terminal, zone: `Outcome.pending_next`), which a short follow-up such as
"what about terminal 2?" completes (04.6). Earlier turns stay on screen for
reference and are never appended to a new request; "Clear conversation"
drops both the transcript and that pending context. Quick-reply buttons
fill in a new request and send it through the same path as a typed one.

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
from src.responses import compact_facts, record_details, render_outcome
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
HISTORY_NOTE = ("Earlier messages are shown for reference. A short follow-up may use the immediately "
                "preceding clarification; otherwise requests are processed independently.")
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

SCORE_NOTE = ("Scores are cosine similarities: a retrieval distance on a 0–1 scale, not a probability of "
              "correctness. For this system they sit between about 0.25 and 0.60, so 0.37 can be a strong match; "
              "the status comes from the score together with the gap to the runner-up, not from the number alone.")


def evidence_rows(outcome: Outcome, gaz) -> list[tuple[str, str]]:
    """Label/value pairs for the evidence panel, all read from the outcome."""
    rows = [("Decision", DECISION_LABELS.get(outcome.decision, outcome.decision)),
            ("Evidence used", ROUTE_LABELS.get(outcome.route, outcome.route)),
            ("Input modalities", ", ".join(outcome.modalities) or "none usable"),
            ("Why", outcome.reason or "see the answer")]
    text = outcome.text
    if text is not None:
        rows.append(("Understood as", text.normalized))
        if text.entities:
            rows.append(("Entities", ", ".join(f"{k} = {v}" for k, v in text.entities.items())))
        if text.intent:
            rows.append(("Detected intent", f"{text.intent} · nearest example {text.intent_score:.2f} "
                                            f"(\"{text.intent_exemplar}\")"))
        rows.append(("Retrieval stage", text.stage or "none"))
        if text.ranked:
            rows.append(("Top records by similarity",
                         ", ".join(f"{gaz.records[rid]['name']} {score:.2f}" for rid, score in text.ranked)))
    vision = outcome.vision
    if vision is not None:
        rows.append(("Photo, top categories",
                     ", ".join(f"{c.replace('_', ' ')} {s:.2f}" for c, s in vision.category_ranking)
                     + f" · margin {vision.category_margin:.3f}"))
        rows.append(("Photo, closest non-sign anchor", f"{vision.best_anchor[0]} {vision.best_anchor[1]:.2f}"))
        if vision.check.flags:
            rows.append(("Photo quality flags", ", ".join(vision.check.flags)))
    speech = outcome.speech
    if speech is not None:
        rows.append(("Audio", f"{speech.check.seconds:.1f} s · {speech.check.rms_dbfs:.0f} dBFS · "
                              f"{'accepted' if speech.check.ok else 'rejected: ' + str(speech.check.problem)}"))
    if outcome.score is not None:
        rows.append(("Similarity", f"{outcome.score:.2f} · {outcome.band or 'not banded'}"))
    if outcome.matched_record_id:
        rows.append(("Matched record", outcome.matched_record_id))
        rows.extend(record_details(gaz.records[outcome.matched_record_id], gaz)[1:])
    if outcome.text is not None and "followup_context" in outcome.flags:
        rows.append(("Follow-up context", "this request completed the previous clarification"))
    if outcome.pending_next:
        kept = ", ".join(f"{k} {v}" for k, v in outcome.pending_next.items() if v)
        rows.append(("Pending clarification", f"kept for one turn: {kept}"))
    if outcome.candidates:
        rows.append(("Candidates", ", ".join(gaz.records[r]["name"] for r in outcome.candidates if r in gaz.records)))
    if outcome.conflict:
        d = outcome.conflict_detail
        rows.append(("Conflict", f"words point to {d.get('text_record') or ', '.join(d.get('text_categories', []))}; "
                                 f"photo points to {d.get('image_category')}; resolution: {d.get('resolution')}"))
    if outcome.flags:
        rows.append(("Flags", ", ".join(outcome.flags)))
    return rows


def evidence_html(outcome: Outcome, gaz) -> str:
    cells = "".join(f'<div class="ev-row"><dt>{html.escape(label)}</dt><dd>{html.escape(value)}</dd></div>'
                    for label, value in evidence_rows(outcome, gaz))
    return f'<dl class="ev-grid">{cells}</dl><p class="ev-note">{SCORE_NOTE}</p>'


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


def fact_row(outcome: Outcome, gaz, response: str = "") -> str:
    """Compact facts under a short answer: icon plus text label plus a KB
    field of the record the outcome selected (rule G, 04.6). Nothing here
    influences routing; the values come from src.responses.compact_facts.
    A fact the answer sentence already states word for word is left out."""
    record = gaz.records.get(outcome.matched_record_id) if outcome.decision == "answer" else None
    if not record:
        return ""
    items = "".join(f'<li><span class="fact-icon" aria-hidden="true">{icon}</span>'
                    f'<span class="fact-label">{html.escape(label)}:</span> {html.escape(value)}</li>'
                    for icon, label, value in compact_facts(record) if value not in response)
    return f'<ul class="facts">{items}</ul>'


def quick_replies(outcome: Outcome, gaz, text: str | None, image_path: str | None) -> list[dict]:
    """Buttons that build the next request for the passenger. Each one is a
    fresh request through the same pipeline; a terminal button is the short
    follow-up the pending clarification completes."""
    if outcome.decision == "clarify" and outcome.clarification_field == "terminal" and outcome.text is not None:
        terminals = sorted({gaz.records[rid]["terminal"] for rid in outcome.candidates})
        return [{"label": t, "text": t} for t in terminals]
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
    parts.append('<div class="bubble">')
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
    parts.append('</div></div>')
    return "".join(parts)


def assistant_html(response: str, key: str, route: str, facts: str = "") -> str:
    paragraphs = "".join(f"<p>{html.escape(p)}</p>" for p in response.split("\n") if p.strip())
    if key == "redirect":
        body = (f'<div class="official"><div class="role">Official information</div>{paragraphs}</div>')
    else:
        body = f'<div class="answer">{paragraphs}</div>'
    meta = "From " + html.escape(ROUTE_LABELS.get(route, route))
    return (f'<div class="turn turn--assistant"><div class="role">Nordhaven Assistant</div>{body}{facts}'
            f'<div class="meta">{status_chip(key)}<span class="meta-text">{meta}</span></div></div>')


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
        outcome = route(text, image_path, audio_path, ctx, pending=session.get("pending"))
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
        evidence = evidence_html(outcome, gaz)
    key = status_key(outcome)
    facts = fact_row(outcome, gaz, response) if gaz is not None else ""
    transcript = ""
    if outcome.speech is not None:
        transcript = outcome.speech.transcript_raw or ""
    session["history"].append({"passenger": passenger_html(text, image_path, transcript, bool(audio_path)),
                               "assistant": assistant_html(response, key, outcome.route, facts)})
    session["pending"] = outcome.pending_next      # one turn only: replaced by every request
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
.gradio-container { --bg:#f3f2f2; --surface:#e8e6e6; --ink:#201e1d; --accent:#ec3013; --accent-deep:#ae1800;
                    --muted:#605d5d; --rule:rgba(32,30,29,.35); --gutter:40px; --gutter-block:calc(var(--gutter) + 12px);
                    max-width: 1100px !important; width: 100% !important; margin: 0 auto;
                    background: var(--bg) !important; color: var(--ink); }
.gradio-container main.app { padding: 0 !important; }
.gradio-container .block, .gradio-container .form { border: 0 !important; background: none !important; box-shadow: none !important; }
footer, .built-with { display: none !important; }
body, .gradio-container, .gradio-container * { font-family: "Archivo", system-ui, sans-serif; border-radius: 0 !important; }
#app { gap: 0; }

/* header */
#header { display: flex; align-items: center; justify-content: space-between; gap: 16px;
          padding: 14px var(--gutter); border-bottom: 2px solid var(--rule); }
#header .mark { color: var(--accent); font-size: 24px; line-height: 1; }
#header h1 { margin: 0; font-size: 19px; line-height: 1.15; font-weight: 800; }
#header p { margin: 3px 0 0 0; font-size: 13px; color: var(--muted); }
#header .brand { display: flex; align-items: center; gap: 14px; }
#assist-toggle { min-height: 44px; flex: 0 0 auto !important; padding: 0 16px; background: transparent;
                 border: 1px solid var(--rule); font-weight: 600; font-size: 14px; }

/* empty state */
#examples { padding: 20px var(--gutter) 0; }
#examples-label { margin: 0 0 8px; }
#examples .row { justify-content: flex-start; gap: 8px; }
#examples .ex { min-height: 44px; flex: 0 0 auto !important; padding: 0 14px; background: var(--bg);
                border: 1px solid var(--rule); font-weight: 400; font-size: 15px; }
#examples-hint { font-size: 14px; color: var(--muted); margin-top: 4px; }

/* session history */
#history-bar { padding: 14px var(--gutter) 0; align-items: flex-end; justify-content: space-between; gap: 12px; }
#history-bar .block { padding: 0 !important; }
#history-note { font-size: 13px; color: var(--muted); margin-top: 2px; max-width: 60ch; }
#clear { background: transparent; border: 0; min-height: 44px; flex: 0 0 auto !important; padding: 0 8px;
         font-weight: 600; font-size: 14px; color: var(--muted); text-decoration: underline; text-underline-offset: 3px; }
#clear:hover { color: var(--ink); }

/* conversation */
#conversation-wrap { padding: 0 !important; }
#conversation { padding: 8px var(--gutter) 4px; display: flex; flex-direction: column; gap: 22px; }
.role, .subrole, #examples-label { font-weight: 800; font-size: 11px; letter-spacing: .1em; text-transform: uppercase; color: var(--muted); }
.turn { display: flex; flex-direction: column; gap: 8px; }
.turn--user { align-items: flex-end; text-align: left; }
.turn--user .bubble { background: var(--surface); padding: 12px 16px; max-width: min(60ch, 85%);
                      display: flex; flex-direction: column; gap: 8px; }
.turn--user .answer { color: #2b2929; }
.turn--assistant { align-items: flex-start; }
.turn--assistant .role { color: var(--accent-deep); }
.answer, .answer p { font-size: 16px; line-height: 1.55; max-width: 68ch; margin: 0; }
.answer p + p { margin-top: 10px; }
.muted { color: var(--muted); }
.facts { list-style: none; margin: 2px 0 0 0; padding: 0; display: flex; flex-wrap: wrap; gap: 6px 18px; font-size: 13.5px; color: #3a3737; }
.facts li { display: inline-flex; align-items: baseline; gap: 6px; max-width: 100%; }
.fact-icon { font-size: 14px; }
.fact-label { font-weight: 700; color: var(--ink); }
.meta { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; font-size: 13px; color: var(--muted); margin-top: 2px; }
.meta-text { line-height: 1.4; }
.chip { display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px; padding: 3px 9px;
        border: 1px solid var(--rule); background: var(--bg); color: var(--ink); font-weight: 600; }
.chip--none { color: var(--accent-deep); border-color: var(--accent-deep); }
.chip--media { align-self: flex-start; background: var(--bg); font-weight: 400; }
.thumb { width: 112px; height: 84px; object-fit: contain; background: var(--bg); border: 1px solid var(--rule); }
.official { padding: 16px 18px; background: var(--surface); border-left: 2px solid var(--ink); max-width: 620px; }
.official p { font-size: 16px; line-height: 1.55; margin: 8px 0 0 0; }

/* after the last answer */
#notice { padding: 8px var(--gutter-block) 0; color: var(--accent-deep); font-size: 15px; }
#quick { padding: 2px var(--gutter-block) 0; }
#quick .row { justify-content: flex-start; gap: 8px; }
#quick button { min-height: 44px; flex: 0 0 auto !important; padding: 0 16px; border: 1px solid var(--ink);
                background: var(--bg); font-weight: 600; font-size: 14px; }
#transcript { padding: 6px var(--gutter-block) 0 !important; }
#evidence { margin: 10px var(--gutter-block) 0 !important; width: auto !important; padding: 0 !important;
            border-top: 1px solid var(--rule) !important; }
#evidence .label-wrap { padding: 8px 0 !important; }
#evidence .label-wrap span { font-weight: 800; font-size: 11px; letter-spacing: .1em; text-transform: uppercase; color: var(--muted); }
#evidence, #evidence * { overflow-x: visible !important; }
#evidence .block { padding: 0 !important; }
.ev-grid { display: grid; grid-template-columns: 1fr 1fr; column-gap: 40px; row-gap: 0; margin: 4px 0 0 0; }
.ev-row { display: grid; grid-template-columns: 150px 1fr; gap: 12px; padding: 9px 0; border-bottom: 1px solid var(--rule); }
.ev-row dt { font-weight: 800; font-size: 11px; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); padding-top: 2px; }
.ev-row dd { margin: 0; font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: 13px; line-height: 1.45;
             color: var(--ink); overflow-wrap: anywhere; }
.ev-note { font-size: 12.5px; color: var(--muted); margin: 10px 0 8px; max-width: 80ch; }

/* assistance */
#assistance { padding: 16px var(--gutter-block) 18px !important; margin-top: 16px; border-top: 1px solid var(--rule) !important; }
#assistance .block, #assistance .html-container, #assistance .prose { padding: 0 !important; }
#assistance-note { font-size: 14px; }
#assistance textarea { background: var(--bg); border: 1px solid var(--rule) !important; font-size: 15px; }
#assistance button { flex: 0 0 auto !important; width: auto !important; align-self: flex-start; min-height: 44px;
                     padding: 0 18px; background: var(--ink); color: var(--bg); font-weight: 700; border: 0; font-size: 14px; }

/* composer */
#composer { border-top: 2px solid var(--rule); background: var(--surface); padding: 14px var(--gutter-block) 14px; margin-top: 24px; gap: 8px; }
#composer .block { padding: 0 !important; }
#composer .row { gap: 10px; }
#question textarea, #transcript textarea { min-height: 48px; font-size: 16px; background: var(--bg);
                    border: 1px solid var(--rule) !important; padding: 12px 14px; }
#question label span, #transcript label span, #attachments label span { font-size: 12px; font-weight: 600;
                    letter-spacing: .04em; color: var(--muted); }
#question label span { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
#send { background: var(--accent); color: var(--bg); font-weight: 800; border: 0; min-height: 48px;
        flex: 0 0 auto !important; padding: 0 22px; align-self: flex-end; }
#send:hover { background: #dd2b0f; }
#attachments { align-items: stretch; max-width: 720px; }
#attachments { align-items: flex-start; }
#attachments > .block, #photo, #voice { min-height: 0 !important; height: 150px !important; max-height: 150px !important;
                        background: var(--bg) !important; border: 1px solid var(--rule) !important; overflow: hidden; }
/* the recorder grows while recording so Stop, the timer and the waveform stay reachable (H1) */
#voice { height: auto !important; max-height: none !important; min-height: 150px !important; overflow: visible; }
#voice .controls, #voice .audio-container, #voice .component-wrap { overflow: visible; }
/* Gradio's clear icon is the only reliable way to discard a recording, so it stays; visually secondary (H2) */
#voice .icon-button-wrapper, #photo .icon-button-wrapper { opacity: .55; }
#voice .icon-button-wrapper:hover, #photo .icon-button-wrapper:hover { opacity: 1; }
#photo .upload-container, #photo .upload-container > button { height: 100% !important; max-height: 148px !important; }
#attachments .label-wrap, #attachments label { font-size: 12px; }
#photo .upload-container, #photo .image-container { height: 100%; }
#photo .wrap { font-size: 13px; }
#voice .controls, #voice .audio-container { min-height: 0; }
#scope { font-size: 12.5px; color: var(--muted); margin: 2px 0 0 -12px; max-width: 80ch; }
:focus-visible { outline: 2px solid var(--accent) !important; outline-offset: 2px; }

@media (max-width: 760px) {
  .gradio-container { --gutter: 18px; --gutter-block: 30px; }
  #header { flex-direction: column; align-items: flex-start; }
  #composer .row, #quick .row, #examples .row, #history-bar, #attachments { flex-direction: column; align-items: stretch; }
  #send { align-self: stretch; }
  .turn--user .bubble { max-width: 100%; }
  #attachments > .block, #photo { height: 140px !important; max-height: 140px !important; }
  #voice { height: auto !important; max-height: none !important; min-height: 140px !important; }
  .ev-grid { grid-template-columns: 1fr; }
  .ev-row { grid-template-columns: 1fr; gap: 2px; }
  #send { width: 100% !important; }
  #photo .upload-container, #photo .upload-container > button { max-height: 138px !important; }
}
"""


def build_ui() -> gr.Blocks:
    theme = gr.themes.Base(primary_hue="red", neutral_hue="stone",
                           font=[gr.themes.GoogleFont("Archivo"), "system-ui", "sans-serif"]
                           ).set(body_background_fill="#f3f2f2", body_background_fill_dark="#f3f2f2")
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
                evidence = gr.HTML(value="", padding=False)

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
                                        image_mode=None, height=150, elem_id="photo")
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
                    gr.update(visible=bool(result["evidence"])), result["evidence"],
                    result["session"], "", None, None]

        def on_send(text, image_path, audio_path, session):
            return to_outputs(run_turn(text, image_path, audio_path, session))

        def on_quick(index, session):
            choice = (session or {}).get("quick", [])[index] if index < len((session or {}).get("quick", [])) else {}
            return to_outputs(run_turn(choice.get("text"), choice.get("image"), None, session))

        def on_example(label, session):
            return to_outputs(run_turn(label, None, None, session))

        def on_clear(session):
            # a fresh transcript and no pending clarification; the session id stays for the event log
            kept = {"session_id": (session or {}).get("session_id", new_session_id()), "pending": None}
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
