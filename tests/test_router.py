"""Routing rules on synthetic evidence: no model is loaded. Each test builds
the RetrievalResult / VisionResult / SpeechResult a modality would have
produced and checks which rule fires and what is surfaced."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from configs.settings import SETTINGS
from src.entities import load_gazetteers
from src.event_log import contact_route
from src.responses import render_outcome
from src.retrieval import RetrievalResult
from src.router import Context, apply_rules, narrow_by_text
from src.speech import AudioCheck, SpeechResult
from src.vision import ImageCheck, VisionResult

THRESHOLDS = {"vision_tau_high": 0.30, "vision_tau_low": 0.24, "vision_margin_delta": 0.015}


@pytest.fixture(scope="module")
def ctx():
    gaz = load_gazetteers(SETTINGS.kb_path, SETTINGS.vocabulary_path)
    return Context(gaz, None, None, SETTINGS.thresholds(), THRESHOLDS)


def text(decision, record=None, candidates=(), stage="exact_identifier", entities=None, flags=(), query="q"):
    return RetrievalResult(query=query, normalized=query, entities=dict(entities or {}), resolved=True,
                           stage=stage, decision=decision, matched_record_id=record,
                           candidates=list(candidates), flags=list(flags), reason="synthetic")


def image(category, band, records, score=0.34, oos=False, flags=()):
    ranking = [(category, score), ("information", score - 0.03), ("transport", score - 0.05)]
    return VisionResult(path="x.png", check=ImageCheck(200, 200, 300.0, 120.0, list(flags)),
                        category_ranking=ranking, category_margin=0.03, best_anchor=("a photograph of a person", 0.2),
                        out_of_scope=oos, record_ranking=[(r, score) for r in records], record_margin=0.0, band=band)


def audio(ok=True, transcript="where is gate b12"):
    check = AudioCheck(2.0, -20.0, 16000, ok, None if ok else "too quiet (-60 dBFS)")
    return SpeechResult("x.wav", check, transcript_raw=transcript if ok else None)


def test_nothing_usable_abstains(ctx):
    out = apply_rules(None, None, None, ctx)
    assert out.route == "none" and out.decision == "abstain"


def test_identifier_text_leads_and_agreeing_image_is_noted(ctx):
    t = text("answer", "gates_pier_b", entities={"gate_id": "B12"})
    out = apply_rules(t, image("gate", "strong match", ["gates_pier_a", "gates_pier_b", "gates_pier_c"]), None, ctx)
    assert out.route == "text_leads" and out.decision == "answer" and out.matched_record_id == "gates_pier_b"
    assert "image_agrees" in out.flags and not out.conflict
    assert "The photo agrees" in render_outcome(out, ctx.gaz)


def test_identifier_beats_a_strong_disagreeing_image_but_surfaces_it(ctx):
    t = text("answer", "gates_pier_b", entities={"gate_id": "B12"})
    out = apply_rules(t, image("baggage", "strong match", ["baggage_reclaim_t1", "baggage_reclaim_t2"]), None, ctx)
    assert out.decision == "answer" and out.matched_record_id == "gates_pier_b"
    assert out.conflict and "image_disagrees" in out.flags
    assert out.conflict_detail["resolution"] == "identifier leads"
    assert "not what your question refers to" in render_outcome(out, ctx.gaz)


def test_alias_answer_against_strong_different_image_is_a_conflict(ctx):
    t = text("answer", "lounge_aurora", stage="alias_lookup")
    out = apply_rules(t, image("restaurant", "strong match", ["restaurant_skyline", "cafe_harbour"]), None, ctx)
    assert out.decision == "conflict" and out.conflict and out.route == "text_leads"
    assert set(out.candidates) == {"lounge_aurora", "restaurant_skyline", "cafe_harbour"}
    body = render_outcome(out, ctx.gaz)
    assert "which one do you mean" in body and "Aurora Lounge" in body


def test_alias_answer_with_agreeing_image_is_reinforced(ctx):
    t = text("answer", "lounge_aurora", stage="alias_lookup")
    out = apply_rules(t, image("lounge", "strong match", ["lounge_aurora"]), None, ctx)
    assert out.decision == "answer" and "image_agrees" in out.flags and not out.conflict


def test_uncertain_image_never_raises_a_conflict(ctx):
    t = text("answer", "lounge_aurora", stage="alias_lookup")
    out = apply_rules(t, image("restaurant", "uncertain", ["restaurant_skyline"]), None, ctx)
    assert out.decision == "answer" and not out.conflict and "image_uncertain" in out.flags


def test_deictic_text_lets_the_image_lead(ctx):
    t = text("clarify", stage="no_retrieval", flags=["deictic"], entities={"deictic_ref": "this sign"})
    out = apply_rules(t, image("lounge", "strong match", ["lounge_aurora"]), None, ctx)
    assert out.route == "image_leads" and out.decision == "answer" and out.matched_record_id == "lounge_aurora"
    assert "This sign means" in render_outcome(out, ctx.gaz)
    out = apply_rules(t, image("gate", "strong match", ["gates_pier_a", "gates_pier_b", "gates_pier_c"]), None, ctx)
    assert out.decision == "clarify" and "image_needs_terminal" in out.flags and len(out.candidates) == 3


def test_text_terminal_narrows_the_image_candidates(ctx):
    t = text("clarify", stage="no_retrieval", flags=["deictic"], entities={"deictic_ref": "this sign", "terminal": "Terminal 2"})
    out = apply_rules(t, image("gate", "strong match", ["gates_pier_a", "gates_pier_b", "gates_pier_c"]), None, ctx)
    assert out.decision == "answer" and out.matched_record_id == "gates_pier_c"
    assert narrow_by_text(["restrooms_t2", "restrooms_t1_arrivals"], text("clarify", candidates=["restrooms_t1_arrivals"], stage="category_filter_semantic"), ctx.gaz) == ["restrooms_t1_arrivals"]


def test_vague_text_clarify_conflicts_with_a_strong_other_category(ctx):
    t = text("clarify", candidates=["restrooms_t1_arrivals", "restrooms_t2"], stage="category_filter_semantic")
    out = apply_rules(t, image("restaurant", "strong match", ["cafe_harbour"]), None, ctx)
    assert out.decision == "conflict" and out.route == "image_leads"


def test_text_not_understood_falls_to_the_image(ctx):
    t = text("abstain", stage="whole_kb_semantic")
    out = apply_rules(t, image("medical", "strong match", ["first_aid_t1"]), None, ctx)
    assert out.decision == "answer" and "text_not_understood" in out.flags


def test_volatile_redirect_ignores_the_image(ctx):
    t = text("redirect", "flight_information", stage="no_retrieval", flags=["volatile"])
    out = apply_rules(t, image("baggage", "strong match", ["baggage_reclaim_t1"]), None, ctx)
    assert out.decision == "redirect" and not out.conflict and out.route == "text_leads"


def test_image_only_bands(ctx):
    strong_single = apply_rules(None, image("lounge", "strong match", ["lounge_aurora"]), None, ctx)
    assert strong_single.route == "image_only" and strong_single.decision == "answer"
    strong_multi = apply_rules(None, image("restroom", "strong match", ["restrooms_t2", "restrooms_t1_arrivals"]), None, ctx)
    assert strong_multi.decision == "clarify" and "image_needs_terminal" in strong_multi.flags
    uncertain = apply_rules(None, image("restroom", "uncertain", ["restrooms_t2"]), None, ctx)
    assert uncertain.decision == "clarify" and "image_uncertain" in uncertain.flags
    oos = apply_rules(None, image("restroom", "no reliable match", [], oos=True), None, ctx)
    assert oos.decision == "abstain" and "image_not_recognised" in oos.flags
    assert "could not recognise" in render_outcome(oos, ctx.gaz)


def test_confirm_policy_turns_an_image_only_answer_into_a_question(ctx):
    strict = Context(ctx.gaz, None, None, ctx.thresholds, THRESHOLDS, confirm_image_only_answers=True)
    out = apply_rules(None, image("lounge", "strong match", ["lounge_aurora"]), None, strict)
    assert out.decision == "clarify" and "image_confirm" in out.flags


def test_rejected_audio_asks_to_rerecord_or_uses_the_photo(ctx):
    out = apply_rules(None, None, audio(ok=False), ctx)
    assert out.route == "none" and out.decision == "clarify" and "audio_rejected" in out.flags
    assert "re-record" in render_outcome(out, ctx.gaz)
    out = apply_rules(None, image("lounge", "strong match", ["lounge_aurora"]), audio(ok=False), ctx)
    assert out.route == "image_only" and out.decision == "answer" and "audio_rejected" in out.flags


def test_voice_transcript_is_the_text_path(ctx):
    t = text("answer", "gates_pier_b", entities={"gate_id": "B12"})
    out = apply_rules(t, None, audio(), ctx, typed=False)
    assert out.route == "voice_only" and out.modalities == ["voice"]
    assert 'I heard: "where is gate b12"' in render_outcome(out, ctx.gaz)


def test_action_request_flag_is_set_at_routing_time(ctx):
    t = text("abstain", stage="whole_kb_semantic", query="can you book me a taxi")
    out = apply_rules(t, None, None, ctx)
    assert "action_request" in out.flags
    assert "cannot book" in render_outcome(out, ctx.gaz)


def test_contact_route_prefers_the_record_then_the_terminal(ctx):
    out = apply_rules(text("answer", "gates_pier_c", entities={"gate_id": "C3"}), None, None, ctx)
    assert contact_route(out, ctx.gaz) == "Information desk, Terminal 2"
    out = apply_rules(text("abstain", stage="whole_kb_semantic", entities={"terminal": "Terminal 2"}), None, None, ctx)
    assert "Terminal 2" in contact_route(out, ctx.gaz)
    out = apply_rules(None, None, None, ctx)
    assert "assistance line" in contact_route(out, ctx.gaz)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))


# ---- QA pass 1: uncertainty rendering and R3 precedence ----

def test_uncertain_image_does_not_override_text_that_offers_candidates(ctx):
    # the observed suitcase case: text already narrowed to the two reclaim
    # records, the photo is baggage-first but in the uncertain band
    t = text("clarify", candidates=["baggage_reclaim_t1", "baggage_reclaim_t2"], stage="category_filter_semantic",
             query="an airport sign for baggage reclaim")
    out = apply_rules(t, image("baggage", "uncertain", ["baggage_reclaim_t2", "baggage_reclaim_t1"], score=0.28), None, ctx)
    assert out.route == "text_leads" and out.decision == "clarify"
    assert out.candidates == ["baggage_reclaim_t1", "baggage_reclaim_t2"]
    assert "image_uncertain" in out.flags and "image_uncertain_agrees" in out.flags and not out.conflict
    shown = render_outcome(out, ctx.gaz)
    assert "Which of these do you mean?" in shown and "most likely shows a baggage" in shown
    assert "transport" not in shown and "accessibility" not in shown


def test_uncertain_image_of_another_category_is_only_noted(ctx):
    t = text("clarify", candidates=["baggage_reclaim_t1", "baggage_reclaim_t2"], stage="category_filter_semantic")
    out = apply_rules(t, image("transport", "uncertain", ["rail_station", "bus_terminal"], score=0.28), None, ctx)
    assert out.route == "text_leads" and out.decision == "clarify" and not out.conflict
    assert "image_uncertain" in out.flags and "image_uncertain_agrees" not in out.flags
    assert "could not identify the sign" in render_outcome(out, ctx.gaz)


def test_uncertain_image_still_leads_when_the_text_offers_nothing(ctx):
    deictic = text("clarify", stage="no_retrieval", flags=["deictic"], entities={"deictic_ref": "this sign"})
    out = apply_rules(deictic, image("baggage", "uncertain", ["baggage_reclaim_t2", "baggage_reclaim_t1"], score=0.28), None, ctx)
    assert out.route == "image_leads" and out.decision == "clarify" and "image_uncertain" in out.flags
    not_understood = text("abstain", candidates=["lounge_aurora"], stage="full_kb_semantic")
    out = apply_rules(not_understood, image("baggage", "uncertain", ["baggage_reclaim_t2"], score=0.28), None, ctx)
    assert out.route == "image_leads"


def test_uncertain_image_rendering_never_names_a_third_category(ctx):
    clear_leader = image("baggage", "uncertain", ["baggage_reclaim_t2", "baggage_reclaim_t1"], score=0.28)
    clear_leader.category_margin = 0.018
    out = apply_rules(None, clear_leader, None, ctx)
    shown = render_outcome(out, ctx.gaz)
    assert "image_no_clear_leader" not in out.flags
    assert "most likely shows a baggage" in shown and "information" not in shown and "transport" not in shown

    close_runner_up = image("baggage", "uncertain", ["baggage_reclaim_t2"], score=0.28)
    close_runner_up.category_margin = 0.004
    out = apply_rules(None, close_runner_up, None, ctx)
    shown = render_outcome(out, ctx.gaz)
    assert "image_no_clear_leader" in out.flags
    assert "baggage" in shown and "information" in shown and "transport" not in shown
