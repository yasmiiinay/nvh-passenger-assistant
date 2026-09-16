"""The retrieval cascade (Architecture Freeze v1.1 4.4).

Frozen order:  normalise -> exact identifier -> alias/gazetteer -> intent ->
category filter -> semantic similarity -> decision.  `resolve_deterministic`
covers everything up to the gazetteer plus two scripted branches that must
run before any retrieval at all; `resolve_semantic` takes over only when the
deterministic stages hand a query on unresolved. Deterministic matches are
therefore always preferred to similarity, by construction.

Scripted branches in the deterministic half:

  * volatile redirect: a flight reference or a volatile phrase means any
    KB answer could be stale, so the query is redirected to the official
    source *before* an identifier is looked up ("what gate is flight XY456
    leaving from" must not become a gate answer).
  * grounded negatives: a well-formed identifier outside every KB range, a
    terminal outside the closed set, or a service category the KB holds only
    in another terminal. These are answered from KB structure, not from
    similarity, and are the cases a semantic stage would get wrong by
    returning the nearest plausible record.

Why the two grounded-negative shapes get different decisions: a non-existent
identifier ("B21") is most likely a misread or misheard token, so the system
abstains and asks the passenger to check the boarding pass. A service that
exists only elsewhere ("lounge in Terminal 2") is a real absence in the KB,
so the system answers "no" and points to where it is.

Anything not decided here is handed on unresolved with the evidence collected
so far (candidates, category hints, terminal). Unresolved is not a failure of
this stage: the paraphrase, vague and out-of-scope queries are the semantic
stage's job by design.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

import numpy as np

from src.entities import Extraction, Gazetteers, extract
from src.intent import NO_INTENT, load_exemplars, predict_intent
from src.text_encoder import encode

STAGE_EXACT = "exact_identifier"
STAGE_ALIAS = "alias_lookup"
STAGE_NONE = "no_retrieval"          # scripted branches: redirect, deictic clarify
STAGE_CATEGORY = "category_filter_semantic"
STAGE_FULL_KB = "semantic_full_kb"


@dataclass
class RetrievalResult:
    query: str
    normalized: str
    entities: dict[str, str]
    resolved: bool
    stage: str | None = None          # one of evaluation.retrieval_metrics.STAGES, or None if unresolved
    decision: str | None = None       # answer / clarify / abstain / redirect, or None if unresolved
    matched_record_id: str | None = None
    candidates: list[str] = field(default_factory=list)
    reason: str = ""
    flags: list[str] = field(default_factory=list)
    handoff: dict = field(default_factory=dict)   # what the semantic stage receives
    # filled by the semantic stage only
    intent: str | None = None
    intent_score: float | None = None
    intent_exemplar: str | None = None
    match_score: float | None = None  # cosine similarity of the top record
    margin: float | None = None       # top1 - top2 cosine
    ranked: list[tuple[str, float]] = field(default_factory=list)   # top records with scores
    clarification_field: str | None = None   # "terminal" when the clarify asks for it instead of listing records

    def as_dict(self) -> dict:
        return asdict(self)


# kept so the 03.1 code and tests read naturally
DeterministicResult = RetrievalResult


def _decide(result: RetrievalResult, stage: str, decision: str, reason: str,
            record_id: str | None = None, candidates: list[str] | None = None) -> RetrievalResult:
    result.resolved = True
    result.stage, result.decision, result.reason = stage, decision, reason
    result.matched_record_id = record_id
    result.candidates = candidates if candidates is not None else ([record_id] if record_id else [])
    return result


def _identifier_range_text(gaz: Gazetteers, prefix: str) -> str:
    owners = gaz.range_owner(prefix)
    if not owners:
        return "no such range in the knowledge base"
    return "; ".join(f"{shown}{lo} to {shown}{hi}" for _, lo, hi, shown in owners)


def resolve_deterministic(query: str, gaz: Gazetteers) -> RetrievalResult:
    """Run the deterministic stages on one text query.

    Returns a resolved result (stage + decision set) or an unresolved one whose
    `handoff` carries candidates and category hints for the semantic stage.
    """
    ex: Extraction = extract(query, gaz)
    result = RetrievalResult(query=ex.raw, normalized=ex.normalized,
                             entities=ex.as_json_dict(), resolved=False)
    if ex.of_type("time"):
        # extracted but never reasoned about: the response layer must not
        # claim open/closed or compute waits (MVP has no clock)
        result.flags.append("time_reference_no_clock")

    terminals = ex.of_type("terminal")
    terminal_values = {t.value for t in terminals if t.exists}
    unknown_terminals = [t.value for t in terminals if not t.exists]

    # ---- scripted branch 1: volatile redirect (before any lookup) ----
    volatile_hits = [e for e in ex.of_type("service")
                     if e.record_ids and gaz.records[e.record_ids[0]].get("volatility") == "high"]
    if ex.of_type("flight_ref") or volatile_hits:
        target = (volatile_hits[0].record_ids[0] if volatile_hits
                  else next(rid for rid, r in gaz.records.items() if r.get("volatility") == "high"))
        trigger = ("flight reference " + ex.of_type("flight_ref")[0].value if ex.of_type("flight_ref")
                   else f"volatile phrase '{volatile_hits[0].surface}'")
        result.flags.append("volatile")
        return _decide(result, STAGE_NONE, "redirect",
                       f"{trigger}: live flight data is never answered from the KB", target)

    # ---- stage 1: exact identifier ----
    identifiers = [e for e in ex.entities if e.type in ("gate_id", "desk_id", "belt_id")]
    missing = [e for e in identifiers if not e.exists]
    if missing or unknown_terminals:
        parts = []
        for e in missing:
            prefix = e.value.rstrip("0123456789")
            parts.append(f"{e.value} is well-formed but outside the known range ({_identifier_range_text(gaz, prefix)})")
        for t in unknown_terminals:
            parts.append(f"{t} does not exist (terminals: {', '.join(sorted(gaz.terminals))})")
        alternatives = sorted({owner[0] for e in missing
                               for owner in gaz.range_owner(e.value.rstrip("0123456789"))})
        result.flags.append("grounded_negative")
        return _decide(result, STAGE_EXACT, "abstain", "; ".join(parts), None, alternatives)
    if identifiers:
        targets = sorted({e.record_ids[0] for e in identifiers})
        if len(targets) == 1:
            return _decide(result, STAGE_EXACT, "answer",
                           f"exact identifier {identifiers[0].value}", targets[0])
        result.flags.append("conflicting_identifiers")
        return _decide(result, STAGE_EXACT, "clarify",
                       "identifiers point to different records: " + ", ".join(e.value for e in identifiers),
                       None, targets)

    # ---- stage 2: alias / gazetteer ----
    alias_hits = ex.of_type("service")
    alias_targets = sorted({e.record_ids[0] for e in alias_hits if e.record_ids})
    if len(alias_targets) == 1:
        target = alias_targets[0]
        if terminal_values and gaz.records[target]["terminal"] not in terminal_values:
            # the service exists, but not where the passenger asked; the
            # response must say so rather than silently answer for Terminal 1
            result.flags.append("terminal_mismatch")
        return _decide(result, STAGE_ALIAS, "answer", f"alias '{alias_hits[0].surface}'", target)
    if len(alias_targets) > 1:
        narrowed = [rid for rid in alias_targets if gaz.records[rid]["terminal"] in terminal_values]
        if len(narrowed) == 1:
            return _decide(result, STAGE_ALIAS, "answer",
                           f"{len(alias_targets)} alias matches narrowed by terminal", narrowed[0])
        result.candidates = alias_targets
        result.reason = "several aliases matched; not narrowed by terminal"

    # ---- stage 2b: category cue (+ terminal) ----
    cue_categories = sorted({c for _, c in ex.category_cues})
    hint_records: list[str] = []
    if len(cue_categories) == 1 and not alias_targets:
        category = cue_categories[0]
        in_category = gaz.records_in_category(category)
        cue_text = ", ".join(sorted({t for t, _ in ex.category_cues}))
        if terminal_values:
            in_terminal = [rid for rid in in_category if gaz.records[rid]["terminal"] in terminal_values]
            if len(in_terminal) == 1:
                return _decide(result, STAGE_ALIAS, "answer",
                               f"category cue '{cue_text}' + terminal narrows to one record", in_terminal[0])
            if not in_terminal and in_category:
                result.flags.append("grounded_negative")
                return _decide(result, STAGE_ALIAS, "answer",
                               f"no '{category}' record in {', '.join(sorted(terminal_values))}; "
                               f"exists elsewhere", None, in_category)
            hint_records = in_terminal
        elif len(in_category) == 1:
            return _decide(result, STAGE_ALIAS, "answer",
                           f"category cue '{cue_text}': single record in category", in_category[0])
        else:
            hint_records = in_category

    # ---- scripted branch 2: deictic text with no other evidence ----
    if ex.of_type("deictic_ref") and not (alias_targets or cue_categories or terminal_values):
        result.flags.append("deictic")
        return _decide(result, STAGE_NONE, "clarify",
                       f"deictic reference '{ex.of_type('deictic_ref')[0].value}' without a photo", None)

    # ---- unresolved: hand on to the semantic stage ----
    result.handoff = {
        "category_hints": cue_categories,
        "terminal": sorted(terminal_values),
        "candidates": result.candidates or hint_records,
        "deictic": bool(ex.of_type("deictic_ref")),
    }
    if not result.reason:
        result.reason = "no identifier, alias or decisive category cue"
    return result


# ---------------------------------------------------------------------------
# Semantic stages
# ---------------------------------------------------------------------------

@dataclass
class TextIndex:
    """Exemplar and KB vectors, computed once per process."""
    exemplars: list[dict]
    exemplar_vecs: np.ndarray
    record_ids: list[str]
    record_vecs: np.ndarray


def build_text_index(gaz: Gazetteers, exemplars_path) -> TextIndex:
    exemplars = load_exemplars(exemplars_path)
    record_ids = [r["record_id"] for r in gaz.kb["records"]]
    record_texts = [gaz.records[rid]["retrieval_text"] for rid in record_ids]
    return TextIndex(exemplars, encode([e["exemplar"] for e in exemplars]),
                     record_ids, encode(record_texts))


def rank_records(query_vec: np.ndarray, index: TextIndex, allowed: list[str]) -> list[tuple[str, float]]:
    """Cosine similarity of the query against the allowed records, best first.
    A plain matrix product: the vectors are already unit length."""
    positions = [index.record_ids.index(rid) for rid in allowed]
    sims = index.record_vecs[positions] @ query_vec
    order = np.argsort(-sims)
    return [(allowed[i], round(float(sims[i]), 4)) for i in order]


def candidate_records(intent: str, handoff: dict, gaz: Gazetteers, filter_mode: str) -> tuple[list[str], str]:
    """Which records the similarity search may consider, and the stage name.

    filter_mode "intent" is the frozen design: the intent's compatible
    categories. "cues" uses the lexical category hints from the deterministic
    stage instead when present (the evaluated variant). "none" searches the
    whole KB. A terminal mentioned in the query narrows the set when that
    leaves anything. An empty set falls back to the whole KB."""
    categories: list[str] = []
    if filter_mode == "intent" and intent != NO_INTENT:
        categories = gaz.vocabulary["intents"][intent]["compatible_categories"]
    elif filter_mode == "cues":
        categories = handoff.get("category_hints") or (
            gaz.vocabulary["intents"][intent]["compatible_categories"] if intent != NO_INTENT else [])
    allowed = [rid for rid in gaz.records if gaz.records[rid]["category"] in categories]
    terminals = handoff.get("terminal") or []
    if terminals:
        in_terminal = [rid for rid in allowed if gaz.records[rid]["terminal"] in terminals]
        allowed = in_terminal or allowed
    if allowed:
        return allowed, STAGE_CATEGORY
    return list(gaz.records), STAGE_FULL_KB


def decide(ranked: list[tuple[str, float]], tau_high: float, tau_low: float,
           margin_delta: float) -> tuple[str, float, float]:
    """answer / clarify / abstain from the top score and the top1-top2 margin."""
    top_score = ranked[0][1]
    margin = top_score - ranked[1][1] if len(ranked) > 1 else top_score
    if top_score < tau_low:
        return "abstain", top_score, margin
    if top_score >= tau_high and margin >= margin_delta:
        return "answer", top_score, margin
    return "clarify", top_score, margin


def offered_candidates(ranked: list[tuple[str, float]], margin_delta: float) -> list[str]:
    """What a clarify question offers: the leader, plus the runner-up only when
    it lies within margin_delta of the leader. Never a third record; the full
    ranking stays in `ranked` for the evidence panel. The whole top-3 used to
    be offered, which put records well below the leader in front of the
    passenger (QA pass 1)."""
    offered = [ranked[0][0]]
    if len(ranked) > 1 and ranked[0][1] - ranked[1][1] < margin_delta:
        offered.append(ranked[1][0])
    return offered


def tied_by_terminal(ranked: list[tuple[str, float]], margin_delta: float, gaz: Gazetteers) -> list[str]:
    """Records within margin_delta of the leader when they are all one category
    and sit in more than one terminal: the passenger's terminal, not a list of
    names, is then the missing piece. Terminal is the only such field the
    entity extractor can read back, so level and zone are not asked for.
    Returns [] when the rule does not apply."""
    top = ranked[0][1]
    tied = [rid for rid, score in ranked if top - score < margin_delta]
    if len(tied) < 2:
        return []
    if len({gaz.records[rid]["category"] for rid in tied}) != 1:
        return []
    if len({gaz.records[rid]["terminal"] for rid in tied}) < 2:
        return []
    return tied


def resolve_semantic(result: RetrievalResult, gaz: Gazetteers, index: TextIndex, thresholds: dict,
                     filter_mode: str = "intent", query_vec: np.ndarray | None = None) -> RetrievalResult:
    """Semantic stages for a query the deterministic stages left unresolved.

    `thresholds` holds tau_intent, tau_high, tau_low and margin_delta (see
    Settings.thresholds()); they are passed explicitly so the evaluation can
    sweep them without touching the global settings."""
    if result.resolved:
        return result
    if query_vec is None:
        query_vec = encode([result.normalized])[0]
    prediction = predict_intent(query_vec, index.exemplar_vecs, index.exemplars, thresholds["tau_intent"])
    result.intent = prediction["intent"]
    result.intent_score = prediction["score"]
    result.intent_exemplar = prediction["exemplar"]

    if result.intent != NO_INTENT and gaz.vocabulary["intents"][result.intent]["volatility"] == "volatile":
        target = next(rid for rid, r in gaz.records.items() if r.get("volatility") == "high")
        result.flags.append("volatile")
        return _decide(result, STAGE_NONE, "redirect",
                       f"intent {result.intent} ({prediction['score']}): live flight data is never answered from the KB",
                       target)

    allowed, stage = candidate_records(result.intent, result.handoff, gaz, filter_mode)
    ranked = rank_records(query_vec, index, allowed)
    decision, score, margin = decide(ranked, thresholds["tau_high"], thresholds["tau_low"],
                                     thresholds["margin_delta"])
    result.ranked = ranked[:3]
    result.match_score, result.margin = round(score, 4), round(margin, 4)
    top_id = ranked[0][0]
    if decision == "answer" and gaz.records[top_id].get("volatility") == "high":
        # the live-information record only ever carries the redirect; it is
        # never presented as an answer, whatever its similarity score
        result.flags.append("volatile")
        return _decide(result, stage, "redirect",
                       f"top record {top_id} at {score:.2f} holds live information; redirecting", top_id)
    if decision == "clarify" and result.intent != NO_INTENT and \
            gaz.vocabulary["intents"][result.intent]["response_type"] == "assist":
        # assistance requests are answered with the nearest designated point
        # and its contact instead of a follow-up question (vocabulary note)
        result.flags.append("assist_policy")
        decision = "answer"
    if decision == "answer":
        return _decide(result, stage, "answer", f"top record {top_id} at {score:.2f}, margin {margin:.2f}", top_id)
    if decision == "clarify":
        tied = tied_by_terminal(ranked, thresholds["margin_delta"], gaz)
        if tied and not result.entities.get("terminal"):
            result.clarification_field = "terminal"
            return _decide(result, stage, "clarify",
                           f"{len(tied)} {gaz.records[tied[0]]['category']} records within the margin across terminals; asking for the terminal",
                           None, tied)
        return _decide(result, stage, "clarify",
                       f"score {score:.2f} or margin {margin:.2f} below threshold; offering top candidates",
                       None, offered_candidates(ranked, thresholds["margin_delta"]))
    return _decide(result, stage, "abstain", f"best similarity {score:.2f} below abstain threshold", None,
                   [rid for rid, _ in ranked[:3]])


def resolve(query: str, gaz: Gazetteers, index: TextIndex, thresholds: dict,
            filter_mode: str = "intent") -> RetrievalResult:
    """Full text cascade: deterministic first, semantic only if still unresolved."""
    result = resolve_deterministic(query, gaz)
    if result.resolved:
        return result
    return resolve_semantic(result, gaz, index, thresholds, filter_mode)
