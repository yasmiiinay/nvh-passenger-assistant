"""Multimodal routing (Architecture Freeze v1.1 4.6).

One function, `route`, takes whatever the passenger supplied (typed text, a
photo, a voice clip), gathers the evidence each modality produces on its
own, and applies a fixed order of rules to decide which modality leads and
what the outcome is. Nothing is averaged: a modality either leads, agrees,
is noted as not usable, or is surfaced as a conflict.

Rule order (first that applies wins):

  R0  nothing usable                          -> abstain
  R1  text redirects (volatile)               -> redirect, image only noted
  R2  text carries an identifier              -> text leads; a strong image of a
                                                 different category is surfaced
                                                 as a disagreement, not merged
  R3  text is deictic, vague or not understood
      and the image is usable                 -> image leads; text narrows
                                                 (terminal, candidates). An
                                                 uncertain image leads only when
                                                 the text offers no candidates
  R4  text answered by alias or similarity
      and the image is strong                 -> same category: reinforced;
                                                 different: conflict
  R5  image only                              -> image leads
  R6  otherwise                               -> text (or the voice transcript)
                                                 stands on its own

Voice enters as text: the clip goes through the audio gate and Whisper and
the transcript takes the place of typed text. A rejected clip with a usable
photo falls through to the image rules; without a photo it asks the
passenger to re-record or type.

One-turn clarification context (04.6): `route` accepts the previous turn's
`pending` clarification (category, terminal, zone) and returns in
`Outcome.pending_next` what the next turn may inherit. Only a short
fragment ("what about terminal 2?") consults it; a complete question
ignores it; anything but a clarification leaves nothing behind. No image or
audio data is ever carried.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path

from configs.settings import SETTINGS
from src.retrieval import RetrievalResult, asks_live_status, is_action_request, pending_context, resolve
from src.speech import SpeechResult, check_audio, has_speech_text, load_audio, process_transcript, transcribe
from src.vision import VisionResult, analyse_image, build_vision_index, load_prompts

IDENTIFIER_STAGES = ("exact_identifier",)
BAND_FOR_TEXT_DECISION = {"answer": "strong match", "redirect": "strong match",
                          "clarify": "uncertain", "abstain": "no reliable match", "conflict": "uncertain"}


@dataclass
class Context:
    """Everything the router needs that is built once per process."""
    gaz: object
    text_index: object
    vision_index: object
    thresholds: dict
    vision_thresholds: dict | None
    confirm_image_only_answers: bool = False   # conservative variant evaluated in checkpoint 03.4


def build_context(gaz, text_index, confirm_image_only_answers: bool = False) -> Context:
    vision_index = build_vision_index(gaz, load_prompts(SETTINGS.vision_prompts_path))
    return Context(gaz, text_index, vision_index, SETTINGS.thresholds(), SETTINGS.vision_thresholds(),
                   confirm_image_only_answers)


@dataclass
class Outcome:
    route: str                                  # none, text_only, voice_only, image_only, text_leads, image_leads
    decision: str                               # answer / clarify / abstain / redirect / conflict
    matched_record_id: str | None = None
    candidates: list[str] = field(default_factory=list)
    band: str | None = None
    score: float | None = None
    reason: str = ""
    flags: list[str] = field(default_factory=list)
    conflict: bool = False
    conflict_detail: dict = field(default_factory=dict)
    clarification_field: str | None = None      # "terminal" when the question asks for it rather than listing records
    image_category: str | None = None
    modalities: list[str] = field(default_factory=list)   # what the passenger supplied and was usable
    text: RetrievalResult | None = None
    vision: VisionResult | None = None
    speech: SpeechResult | None = None
    error: str | None = None
    pending_next: dict | None = None            # clarification context the next turn may use (04.6)

    def as_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# evidence from each modality on its own
# ---------------------------------------------------------------------------

def text_evidence(text: str | None, ctx: Context, pending: dict | None = None) -> RetrievalResult | None:
    if not text or not text.strip():
        return None
    return resolve(text.strip(), ctx.gaz, ctx.text_index, ctx.thresholds, pending=pending)


def speech_evidence(audio_path: str | Path, ctx: Context) -> SpeechResult:
    """Gate, transcribe, normalise. Retrieval is run by the caller on the
    transcript so that the voice path is literally the text path."""
    samples, rate = load_audio(audio_path)
    check = check_audio(samples, rate)
    result = SpeechResult(path=str(audio_path), check=check)
    if not check.ok:
        return result
    transcript = transcribe(samples, rate)
    if not has_speech_text(transcript):
        result.transcript_raw = transcript
        result.check.ok, result.check.problem = False, "no speech recognised"
        return result
    return process_transcript(result, transcript, ctx.gaz, ctx.text_index, ctx.thresholds, run_retrieval=False)


def image_evidence(image_path: str | Path, ctx: Context) -> VisionResult:
    return analyse_image(image_path, ctx.vision_index, ctx.vision_thresholds)


# ---------------------------------------------------------------------------
# small readers used by the rules
# ---------------------------------------------------------------------------

def image_usable(vision: VisionResult | None) -> bool:
    return vision is not None and not vision.out_of_scope and vision.band in ("strong match", "uncertain")


def image_strong(vision: VisionResult | None) -> bool:
    return vision is not None and not vision.out_of_scope and vision.band == "strong match"


def text_categories(result: RetrievalResult, gaz) -> set[str]:
    """Categories the text evidence points at: the matched record's, or the
    candidates' when the text ended in clarify or a grounded negative."""
    ids = [result.matched_record_id] if result.matched_record_id else list(result.candidates)
    return {gaz.records[rid]["category"] for rid in ids if rid in gaz.records}


def text_has_identifier(result: RetrievalResult) -> bool:
    return result.stage in IDENTIFIER_STAGES or any(k in result.entities for k in ("gate_id", "desk_id", "belt_id"))


def text_is_open(result: RetrievalResult) -> bool:
    """Text that leaves room for the image to lead: deictic, vague (clarify
    without an identifier) or not understood (abstain without entities)."""
    if "deictic" in result.flags:
        return True
    if result.decision == "clarify" and not text_has_identifier(result):
        return True
    return result.decision == "abstain" and "grounded_negative" not in result.flags


def text_position_confident(result: RetrievalResult, thresholds: dict) -> bool:
    """Whether the text says enough to contradict a strong photo: a
    deterministic stage (no score), or a similarity at or above tau_high. A
    clarify whose leader sits between tau_low and tau_high is a guess, and a
    guess must not be defended against a photo (QA 04.4)."""
    return result.match_score is None or result.match_score >= thresholds["tau_high"]


def text_has_candidates(result: RetrievalResult) -> bool:
    """A clarify that already offers records is a question worth keeping; an
    uncertain photo must not replace it with a broader one (QA pass 1)."""
    return result.decision == "clarify" and bool(result.candidates)


def narrow_by_text(record_ids: list[str], result: RetrievalResult | None, gaz,
                   use_candidates: bool = True) -> list[str]:
    """Keep the image's records that the text does not rule out: a terminal
    entity narrows to that terminal; clarify candidates narrow to the overlap
    (not when the candidates are a weak guess, see text_position_confident)."""
    if result is None:
        return record_ids
    narrowed = record_ids
    terminal = result.entities.get("terminal")
    if terminal:
        in_terminal = [rid for rid in narrowed if gaz.serves(rid, terminal)]
        narrowed = in_terminal or narrowed
    if use_candidates and result.decision == "clarify" and result.candidates:
        overlap = [rid for rid in narrowed if rid in result.candidates]
        narrowed = overlap or narrowed
    return narrowed


# ---------------------------------------------------------------------------
# the rules
# ---------------------------------------------------------------------------

def _from_text(out: Outcome, result: RetrievalResult) -> Outcome:
    if is_action_request(result.normalized) and "action_request" not in result.flags:
        result.flags.append("action_request")
    if asks_live_status(result.normalized) and "live_status_request" not in result.flags:
        result.flags.append("live_status_request")
    out.decision = result.decision
    out.matched_record_id = result.matched_record_id
    out.candidates = list(result.candidates)
    out.band = BAND_FOR_TEXT_DECISION[result.decision]
    out.score = result.match_score
    out.reason = result.reason
    out.clarification_field = result.clarification_field
    out.flags.extend(result.flags)
    return out


def _image_leads(out: Outcome, vision: VisionResult, text: RetrievalResult | None, ctx: Context) -> Outcome:
    """Image supplies the category; text, if any, narrows the records."""
    gaz = ctx.gaz
    category, score = vision.category_ranking[0]
    out.image_category = category
    out.score = score
    out.band = vision.band
    records = narrow_by_text([rid for rid, _ in vision.record_ranking], text, gaz,
                             use_candidates="text_weak" not in out.flags)
    out.candidates = records
    if vision.band == "uncertain":
        out.decision = "clarify"
        out.flags.append("image_uncertain")
        if vision.category_margin < ctx.vision_thresholds["vision_margin_delta"]:
            out.flags.append("image_no_clear_leader")
        out.reason = f"image band uncertain: top categories {[c for c, _ in vision.category_ranking]}"
        return out
    if len(records) == 1:
        if ctx.confirm_image_only_answers and text is None:
            out.decision = "clarify"
            out.flags.append("image_confirm")
            out.reason = f"image alone identifies {category}; confirmation required by policy"
            return out
        out.decision = "answer"
        out.matched_record_id = records[0]
        out.reason = f"image category {category} ({score:.2f}) leaves one record"
        return out
    out.decision = "clarify"
    out.clarification_field = "terminal"
    out.flags.append("image_needs_terminal")
    out.reason = f"image category {category} ({score:.2f}) matches {len(records)} records; terminal unknown"
    return out


def apply_rules(text: RetrievalResult | None, vision: VisionResult | None,
                speech: SpeechResult | None, ctx: Context, typed: bool = True) -> Outcome:
    gaz = ctx.gaz
    out = Outcome(route="none", decision="abstain", text=text, vision=vision, speech=speech)
    voice = speech is not None and speech.check.ok and not typed
    if typed and text is not None:
        out.modalities.append("text")
    if speech is not None and speech.check.ok:
        out.modalities.append("voice")
    if vision is not None:
        out.modalities.append("image")
    if speech is not None and not speech.check.ok:
        out.flags.append("audio_rejected")
    if vision is not None and vision.check.flags:
        out.flags.extend("image_" + f for f in vision.check.flags)
    if vision is not None and (vision.out_of_scope or vision.band == "no reliable match"):
        out.flags.append("image_not_recognised")

    text_route = ("voice" if voice else "text") + ("_leads" if vision is not None else "_only")

    # R0
    if text is None and not image_usable(vision):
        if vision is not None:
            out.route, out.decision = "image_only", "abstain"
            out.band = "no reliable match"
            out.reason = "photo not recognised as an airport sign" + (
                f" (closest anchor: {vision.best_anchor[0]})" if vision.out_of_scope else "")
            out.image_category = None
            return out
        out.route = "none"
        out.decision = "clarify" if speech is not None else "abstain"
        out.band = "no reliable match"
        out.reason = speech.check.problem if speech is not None else "no usable input"
        return out

    # R1
    if text is not None and text.decision == "redirect":
        out.route = text_route
        return _from_text(out, text)

    # R2
    if text is not None and text_has_identifier(text):
        out.route = text_route
        _from_text(out, text)
        if image_strong(vision):
            image_cat = vision.category_ranking[0][0]
            out.image_category = image_cat
            if image_cat in text_categories(text, gaz):
                out.flags.append("image_agrees")
            else:
                out.conflict = True
                out.flags.append("image_disagrees")
                out.conflict_detail = {"text_record": text.matched_record_id, "text_categories": sorted(text_categories(text, gaz)),
                                       "image_category": image_cat, "resolution": "identifier leads"}
        return out

    # R3
    if text is not None and text_is_open(text) and image_usable(vision) \
            and (image_strong(vision) or not text_has_candidates(text)):
        image_cat = vision.category_ranking[0][0]
        cats = text_categories(text, gaz)
        if image_strong(vision) and cats and image_cat not in cats and text.decision == "clarify" \
                and text_position_confident(text, ctx.thresholds):
            out.route = "image_leads"
            out.decision = "conflict"
            out.conflict = True
            out.band = "uncertain"
            out.image_category = image_cat
            out.candidates = list(text.candidates) + [rid for rid, _ in vision.record_ranking]
            out.conflict_detail = {"text_record": None, "text_categories": sorted(cats),
                                   "image_category": image_cat, "resolution": "asked"}
            out.reason = f"text points at {sorted(cats)}, photo at {image_cat}"
            return out
        out.route = "image_leads"
        if text.decision == "abstain":
            out.flags.append("text_not_understood")
        elif text.decision == "clarify" and not text_position_confident(text, ctx.thresholds):
            out.flags.append("text_weak")
        if "deictic" in text.flags:
            out.flags.append("deictic")
        if cats and image_cat in cats:
            out.flags.append("text_agrees")
        return _image_leads(out, vision, text, ctx)

    # R4
    if text is not None and text.decision == "answer" and image_strong(vision):
        image_cat = vision.category_ranking[0][0]
        out.image_category = image_cat
        if image_cat in text_categories(text, gaz):
            out.route = text_route
            _from_text(out, text)
            out.flags.append("image_agrees")
            return out
        out.route = text_route
        out.decision = "conflict"
        out.conflict = True
        out.band = "uncertain"
        out.candidates = [text.matched_record_id] + [rid for rid, _ in vision.record_ranking]
        out.conflict_detail = {"text_record": text.matched_record_id, "text_categories": sorted(text_categories(text, gaz)),
                               "image_category": image_cat, "resolution": "asked"}
        out.reason = f"text answers {text.matched_record_id}, photo looks like {image_cat}"
        out.flags.extend(text.flags)
        return out

    # R5
    if text is None:
        out.route = "image_only"
        return _image_leads(out, vision, None, ctx)

    # R6
    out.route = text_route
    _from_text(out, text)
    if vision is not None and image_usable(vision) and vision.band == "uncertain":
        out.image_category = vision.category_ranking[0][0]
        out.flags.append("image_uncertain")
        if out.image_category in text_categories(text, gaz):
            out.flags.append("image_uncertain_agrees")
    return out


def route(text: str | None, image_path: str | Path | None, audio_path: str | Path | None,
          ctx: Context, pending: dict | None = None) -> Outcome:
    """Gather evidence and apply the rules. Typed text takes precedence over
    a voice clip when both are given; the transcript is still recorded.
    `pending` is the previous turn's clarification context, if any."""
    speech = None
    vision = None
    errors = []
    if audio_path:
        try:
            speech = speech_evidence(audio_path, ctx)
        except ValueError as exc:
            errors.append(f"audio: {exc}")
    if image_path:
        try:
            vision = image_evidence(image_path, ctx)
        except ValueError as exc:
            errors.append(f"image: {exc}")
    query = text.strip() if text and text.strip() else None
    typed = query is not None
    if query is None and speech is not None and speech.check.ok:
        query = speech.transcript_raw
    text_result = text_evidence(query, ctx, pending)
    out = apply_rules(text_result, vision, speech, ctx, typed=typed)
    if errors:
        out.error = "; ".join(errors)
        out.flags.append("input_error")
    # only a text clarification that still stands leaves context behind; a
    # photo that settled the question, a conflict or an answer clears it
    out.pending_next = pending_context(text_result, ctx.gaz) if out.decision == "clarify" else None
    return out
