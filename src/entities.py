"""Deterministic entity extraction: regex + frozen vocabulary + KB-derived gazetteers.

Sources, in the order they are consulted:
  1. identifier regexes derived from data/vocabulary.json (gate_id, desk_id,
     belt_id, terminal, flight_ref, time, deictic_ref);
  2. the exact-match identifier index expanded from the KB identifier ranges
     (src/kb.py), used to mark each well-formed identifier as existing or not;
  3. the service gazetteer built at load time from every record's name and
     aliases (vocabulary.json: "no separate list to drift");
  4. category cues: single tokens that occur in the name/aliases of records
     of exactly one category. They are derived, not authored, so they are
     returned separately from entities and never resolve a record on their
     own (see src/retrieval.py for the two narrow ways they are used).

All matching runs on normalised text (src/normalizer.py), so a typed query
and an ASR transcript are handled identically. The flight_ref pattern is the
one exception: its uppercase form is looked for in the raw text as well,
because lowercasing would make "NH123" indistinguishable from "at 10".

Usability hardening 04.6 added, from vocabulary.json "query_interpretation":
  5. a service or identifier mention that follows a location preposition
     ("near Security North", "at gate B12") is a LANDMARK, not the requested
     service: Entity.role tells the cascade which is which;
  6. zone / journey-stage phrases (airside, after security, arrivals, just
     landed ...), service families (accessibility vs medical), inter-terminal
     transfer wording, explicit clock times, unsupported-service terms and a
     small alias supplement, all consumed so their words are not read again
     as category cues;
  7. a fragment flag for service-free text ("what about terminal 2?").
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from src.kb import load_kb
from src.normalizer import normalize, normalize_l1

# Words that carry no service information and would otherwise become
# category cues by accident ("a" occurs only in gate aliases). This is not
# stop-word removal: the query text is never altered, only the cue table.
CUE_EXCLUDED = {
    "a", "an", "and", "the", "to", "of", "in", "on", "at", "for", "from",
    "with", "by", "i", "my", "me", "you", "is", "are", "where", "how", "what",
    "between", "before", "after", "near", "there", "here", "this", "that",
    "help", "have",   # request words ("medical help", "i have lost"), not service names (04.6)
}

GATE_PATTERN = re.compile(r"\b([abc])(\d{1,2})\b")
# "desk 225", "desk is 225", "desk number 225", "check in counter 225": the
# identifier grammar, not one phrasing (04.6)
_ID_LINK = r"(?:\s+(?:number|no))?(?:\s+(?:is|at))?(?:\s+(?:number|no))?\s+"   # "desk 225", "desk is 225", "desk number 225"
DESK_PATTERN = re.compile(r"\b(?:check ?in\s+)?(?:desk|counter)s?" + _ID_LINK + r"(\d{3})\b")
BELT_PATTERN = re.compile(r"\b(?:belt|carousel)s?" + _ID_LINK + r"(\d{1,2})\b")
# an explicit clock time. The normaliser turns "8:30 p.m." into "8 30 p m",
# so the meridiem is read in both spellings; a bare "20 30" counts only after
# a time preposition, and a bare hour of 1-12 without am/pm stays ambiguous
MERIDIEM_TIME = re.compile(r"\b(\d{1,2})(?:[ :](\d{2}))?\s?(a ?m|p ?m)\b")
PREPOSITION_TIME = re.compile(r"\b(?:at|by|around|until|before|after|from) (\d{1,2})[ :](\d{2})\b")
DESTINATION_PATTERN = re.compile(r"\b(?:to|towards|toward|into|onto)\s+(?:the\s+)?$")
# words that carry no service meaning on their own; a query left with only
# these (after its identifiers, aliases, zones and terminals are taken out)
# is a fragment that must not be sent to similarity search (04.6)
FUNCTION_WORDS = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "at", "by", "for", "from", "with", "about", "as",
    "i", "me", "my", "we", "you", "your", "it", "its", "this", "that", "these", "those", "there", "here",
    "is", "are", "am", "was", "be", "do", "does", "did", "can", "could", "would", "should", "will",
    "what", "where", "which", "how", "when", "who", "why", "way", "go", "get", "find", "need", "want",
    "looking", "like", "please", "thanks", "thank", "ok", "okay", "yes", "no", "now", "then", "also",
    "same", "other", "one", "instead", "so", "um", "uh", "hmm", "just", "still", "again", "too",
    "terminal", "terminals", "t1", "t2", "not", "have", "has", "had", "been", "im", "ive",
    "near", "beside", "next", "opposite", "close", "around", "outside", "front", "behind", "over", "up", "down",
}
TERMINAL_PATTERN = re.compile(r"\bterminal\s+(\d)\b")
FLIGHT_RAW_PATTERN = re.compile(r"\b([A-Z]{2})\s?(\d{2,4})\b")
FLIGHT_SPOKEN_PATTERN = re.compile(r"\bflight\s+([a-z]{2})\s?(\d{2,4})\b")
DEICTIC_HEAD_NOUNS = ("sign", "signs", "area", "place", "spot", "symbol", "symbols", "icon", "thing", "one")
TIME_PATTERN = re.compile(
    r"\b(right now|now|tonight|today|this morning|this afternoon|this evening|"
    r"\d{1,2}(?::\d{2})?\s?(?:am|pm)|\d{1,2} oclock)\b")


@dataclass(frozen=True)
class Entity:
    type: str
    value: str                       # canonical form (vocabulary pattern)
    surface: str                     # text as matched in the normalised query
    exists: bool | None = None       # identifiers/terminals: known to the KB?
    record_ids: tuple[str, ...] = () # records this entity points to, if any
    role: str = "target"             # "landmark" when named as the passenger's position, not the request


@dataclass
class Extraction:
    raw: str
    normalized: str
    entities: list[Entity] = field(default_factory=list)
    category_cues: list[tuple[str, str]] = field(default_factory=list)  # (token, category)
    zones: list[str] = field(default_factory=list)          # airside / landside / arrivals / departures
    families: list[str] = field(default_factory=list)       # accessibility / medical
    unsupported: list[str] = field(default_factory=list)    # named services the KB does not hold
    transfer: bool = False                                  # movement between the two terminals
    destination: str | None = None                          # a zone the passenger is heading to ("up to departures")
    fragment: bool = False                                  # no service words at all

    def of_type(self, entity_type: str, role: str | None = "target") -> list[Entity]:
        """Entities of one type; by default only those the passenger asks
        for. role=None returns landmarks as well."""
        return [e for e in self.entities if e.type == entity_type and (role is None or e.role == role)]

    def landmarks(self) -> list[Entity]:
        return [e for e in self.entities if e.role == "landmark"]

    def as_json_dict(self) -> dict[str, str]:
        """Same shape as entities_json in queries_seed.csv (first value per type)."""
        out: dict[str, str] = {}
        for e in self.entities:
            out.setdefault("landmark" if e.role == "landmark" else e.type, e.value)
        return out


def reversed_two_word(phrases: set[str]) -> set[str]:
    """"security north" for "north security": a two-word alias is read in
    either order when both words are plain words. Passengers put the
    qualifier after the head as often as before it (QA 04.4)."""
    out = set()
    for p in phrases:
        words = p.split()
        if len(words) == 2 and all(w.isalpha() and len(w) >= 2 for w in words):
            out.add(f"{words[1]} {words[0]}")
    return out


class Gazetteers:
    """Lookup tables built once from the KB and vocabulary."""

    def __init__(self, kb: dict, vocabulary: dict):
        self.kb = kb
        self.vocabulary = vocabulary
        self.records = {r["record_id"]: r for r in kb["records"]}
        self.terminals = set(vocabulary["entities"]["terminal"]["values"])
        self.deictic_values = sorted(vocabulary["entities"]["deictic_ref"]["values"],
                                     key=len, reverse=True)
        self.identifier_index: dict[str, str] = {}
        self.identifier_ranges: dict[str, list[tuple[str, int, int, str]]] = {}  # rid, lo, hi, display prefix
        self.alias_index: dict[str, str] = {}
        self.volatile_phrases: dict[str, str] = {}
        self.category_cues: dict[str, str] = {}
        self.query_words = vocabulary.get("query_interpretation", {})
        self._build()

    def _build(self) -> None:
        token_categories: dict[str, set[str]] = {}
        for r in self.kb["records"]:
            rid = r["record_id"]
            for token in r["_expanded_identifiers"]:
                self.identifier_index[token.upper()] = rid
            for rng in r.get("identifier_ranges", []):
                self.identifier_ranges.setdefault(rng["prefix"].strip().upper(), []).append(
                    (rid, int(rng["from"]), int(rng["to"]), rng["prefix"].upper()))
            phrases = [r["name"]] + list(r.get("aliases", [])) + \
                list(self.query_words.get("service_synonyms", {}).get(rid, []))
            normalised_phrases = {normalize(p) for p in phrases if p}
            if r.get("volatility") == "high":
                # volatile records feed the redirect branch only; their words
                # must not become category cues ("flight" -> information).
                for p in normalised_phrases:
                    self.volatile_phrases[p] = rid
                continue
            for p in normalised_phrases | reversed_two_word(normalised_phrases):
                if p in self.alias_index and self.alias_index[p] != rid:
                    continue   # a reversed form must never take a phrase another record owns
                self.alias_index[p] = rid
                for token in p.split():
                    if token in CUE_EXCLUDED or len(token) < 2 or not token.isalpha():
                        continue
                    token_categories.setdefault(token, set()).add(r["category"])
        self.category_cues = {t: next(iter(c)) for t, c in token_categories.items()
                              if len(c) == 1}
        self._alias_patterns = [
            (p, re.compile(rf"\b{re.escape(p)}\b"))
            for p in sorted(self.alias_index, key=len, reverse=True)]
        self._volatile_patterns = [
            (p, re.compile(rf"\b{re.escape(p)}\b"))
            for p in sorted(self.volatile_phrases, key=len, reverse=True)]
        self._cue_pattern = re.compile(
            r"\b(" + "|".join(re.escape(t) for t in sorted(self.category_cues, key=len, reverse=True)) + r")\b")
        # The vocabulary's deictic values ("this sign", "this", "here", "that")
        # generalised to the determiners in either number followed by an
        # optional generic head noun, so that "this area" or "these signs" is
        # one deictic phrase and its noun is not read as a category cue
        # ("area" occurs only in gate aliases). Time phrases such as "this
        # evening" are excluded below (QA 04.5).
        determiners = sorted({v for v in self.deictic_values if " " not in v and v != "here"} | {"these", "those"})
        self._deictic_pattern = re.compile(
            r"\b(?:(?:" + "|".join(determiners) + r")(?:\s+(?:" + "|".join(DEICTIC_HEAD_NOUNS) + r"))?|here)\b")
        # 04.6 word lists (vocabulary.json "query_interpretation"); each is
        # compiled once, longest phrase first, and matched on free spans only
        def phrase_pattern(phrases):
            phrases = sorted({normalize(p) for p in phrases if p}, key=len, reverse=True)
            return re.compile(r"\b(" + "|".join(re.escape(p) for p in phrases) + r")\b") if phrases else None
        preps = self.query_words.get("location_prepositions", [])
        self._landmark_pattern = (re.compile(r"(?:^|\s)(?:" + "|".join(re.escape(normalize(p)) for p in preps) +
                                             r")\s+(?:the\s+|my\s+|a\s+|an\s+)?$") if preps else None)
        self._zone_patterns = [(zone, phrase_pattern(phrases))
                               for zone, phrases in self.query_words.get("zone_phrases", {}).items()]
        self._family_patterns = [(fam, phrase_pattern(phrases))
                                 for fam, phrases in self.query_words.get("service_families", {}).items()]
        self._transfer_pattern = phrase_pattern(self.query_words.get("transfer_phrases", []))
        self._unsupported_pattern = phrase_pattern(self.query_words.get("unsupported_services", []))
        self._lead_in_pattern = phrase_pattern(self.query_words.get("fragment_lead_ins", []))

    def records_in_category(self, category: str) -> list[str]:
        return [r["record_id"] for r in self.kb["records"] if r["category"] == category]

    def range_owner(self, prefix: str) -> list[tuple[str, int, int, str]]:
        return self.identifier_ranges.get(prefix.strip().upper(), [])

    def serves(self, record_id: str, terminal: str) -> bool:
        """Whether the record is for passengers of that terminal (see load_kb)."""
        return terminal in self.records[record_id]["serves_terminals"]

    def cue_table_rows(self) -> list[dict]:
        return [{"token": t, "category": c} for t, c in sorted(self.category_cues.items())]


def load_gazetteers(kb_path: str | Path, vocabulary_path: str | Path) -> Gazetteers:
    with open(vocabulary_path, encoding="utf-8") as fh:
        vocabulary = json.load(fh)
    return Gazetteers(load_kb(kb_path), vocabulary)


def _identifier_entity(gaz: Gazetteers, entity_type: str, canonical: str, surface: str,
                       role: str = "target") -> Entity:
    rid = gaz.identifier_index.get(canonical)
    return Entity(entity_type, canonical, surface, exists=rid is not None,
                  record_ids=(rid,) if rid else (), role=role)


def _role_at(norm: str, start: int, gaz: Gazetteers) -> str:
    """"landmark" when the mention is introduced by a location preposition
    ("near", "beside", "at", "from" ...), otherwise "target"."""
    if gaz._landmark_pattern is not None and gaz._landmark_pattern.search(norm[:start]):
        return "landmark"
    return "target"


def extract(text: str, gaz: Gazetteers, domain_rules: bool = True) -> Extraction:
    """Extract entities and category cues from one query (typed or transcribed).

    domain_rules=False runs the extractor on L1 (generic) normalisation only;
    used by the speech evaluation to measure what the L2 rules repair."""
    raw = "" if text is None else str(text)
    norm = normalize(raw) if domain_rules else normalize_l1(raw)
    result = Extraction(raw=raw, normalized=norm)
    ents = result.entities
    consumed: list[tuple[int, int]] = []

    def free(span: tuple[int, int]) -> bool:
        return all(span[1] <= s or span[0] >= e for s, e in consumed)

    # --- flight references: raw uppercase form, or spoken "flight xy 123" ---
    # A bare two-letter code with two digits has the same shape as a gate id
    # that ASR noise has mangled ("B12" heard as "KP12"), so the raw form
    # needs either the word "flight" or a longer number; flight-status
    # wording without a code still reaches the redirect through the intent.
    seen_flights: set[str] = set()
    for m in FLIGHT_RAW_PATTERN.finditer(raw):
        if "flight" in norm.split() or len(m.group(2)) >= 3:
            seen_flights.add(f"{m.group(1)} {m.group(2)}")
    for m in FLIGHT_SPOKEN_PATTERN.finditer(norm):
        seen_flights.add(f"{m.group(1).upper()} {m.group(2)}")
    for value in sorted(seen_flights):
        ents.append(Entity("flight_ref", value, value.lower()))

    # --- identifiers (existence checked against the expanded KB index) ---
    for m in DESK_PATTERN.finditer(norm):
        ents.append(_identifier_entity(gaz, "desk_id", f"DESK {m.group(1)}", m.group(0),
                                       _role_at(norm, m.start(), gaz)))
        consumed.append(m.span())
    for m in BELT_PATTERN.finditer(norm):
        ents.append(_identifier_entity(gaz, "belt_id", f"BELT {m.group(1)}", m.group(0),
                                       _role_at(norm, m.start(), gaz)))
        consumed.append(m.span())
    for m in GATE_PATTERN.finditer(norm):
        if free(m.span()):
            start = m.start() - 5 if norm[max(0, m.start() - 5):m.start()] == "gate " else m.start()
            ents.append(_identifier_entity(gaz, "gate_id", f"{m.group(1).upper()}{m.group(2)}", m.group(0),
                                           _role_at(norm, start, gaz)))
            consumed.append((start, m.end()))   # "gate" belongs to the identifier, not to the cue table

    # --- terminal (closed set; an unknown terminal is kept with exists=False) ---
    # Not added to `consumed`: aliases such as "accessible toilet terminal 2"
    # contain the terminal words and must still match.
    for m in TERMINAL_PATTERN.finditer(norm):
        value = f"Terminal {m.group(1)}"
        ents.append(Entity("terminal", value, m.group(0), exists=value in gaz.terminals))

    # --- volatile phrases (aliases of volatility-high records) ---
    for phrase, pattern in gaz._volatile_patterns:
        for m in pattern.finditer(norm):
            if free(m.span()):
                rid = gaz.volatile_phrases[phrase]
                ents.append(Entity("service", phrase, m.group(0), exists=True, record_ids=(rid,)))
                consumed.append(m.span())

    # --- service gazetteer: longest alias first, no overlaps ---
    for phrase, pattern in gaz._alias_patterns:
        for m in pattern.finditer(norm):
            if free(m.span()):
                rid = gaz.alias_index[phrase]
                ents.append(Entity("service", phrase, m.group(0), exists=True, record_ids=(rid,),
                                   role=_role_at(norm, m.start(), gaz)))
                consumed.append(m.span())

    # --- explicit clock times, then relative time references ---
    time_spans = []
    clock_matches = [(m, m.group(3).replace(" ", "")) for m in MERIDIEM_TIME.finditer(norm)]
    clock_matches += [(m, None) for m in PREPOSITION_TIME.finditer(norm)
                      if not any(m.start() < c.end() and m.end() > c.start() for c, _ in clock_matches)]
    for m, meridiem in sorted(clock_matches, key=lambda item: item[0].start()):
        if not free(m.span()):
            continue
        hour, minute = int(m.group(1)), int(m.group(2) or 0)
        if hour > 23 or minute > 59 or (meridiem and not 1 <= hour <= 12):
            continue
        if meridiem == "pm" and hour < 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0
        value = f"{hour:02d}:{minute:02d}"
        if meridiem is None and 1 <= hour <= 12:
            # "at 9 15": morning or evening; both readings are kept (04.6)
            value = f"{hour:02d}:{minute:02d}|{(hour % 12) + 12:02d}:{minute:02d}"
        ents.append(Entity("clock_time", value, m.group(0)))
        time_spans.append(m.span())
        consumed.append(m.span())
    for m in TIME_PATTERN.finditer(norm):
        if free(m.span()):
            ents.append(Entity("time", m.group(1), m.group(1)))
            time_spans.append(m.span())

    # --- 04.6 word lists: zones, service families, transfer, unsupported ---
    for zone, pattern in gaz._zone_patterns:
        for m in (pattern.finditer(norm) if pattern else ()):
            if free(m.span()):
                # "up to departures" is where the passenger is going, not
                # where they are: consumed, but not a constraint
                if DESTINATION_PATTERN.search(norm[:m.start()]):
                    result.destination = result.destination or zone
                elif zone not in result.zones:
                    result.zones.append(zone)
                consumed.append(m.span())
    for family, pattern in gaz._family_patterns:
        for m in (pattern.finditer(norm) if pattern else ()):
            if free(m.span()):
                if family not in result.families:
                    result.families.append(family)
                consumed.append(m.span())
    if gaz._transfer_pattern is not None:
        for m in gaz._transfer_pattern.finditer(norm):
            if free(m.span()):
                result.transfer = True
                consumed.append(m.span())
    if gaz._unsupported_pattern is not None:
        for m in gaz._unsupported_pattern.finditer(norm):
            if free(m.span()):
                # "toilets after passport control": an unsupported place used
                # as a landmark says where the passenger is, not what they want
                if _role_at(norm, m.start(), gaz) == "target":
                    result.unsupported.append(m.group(1))
                consumed.append(m.span())

    # --- deictic references: determiner plus optional generic noun, or "here" ---
    # The phrase is consumed so its noun cannot double as a category cue; a
    # determiner inside a time phrase ("this evening") is not deictic.
    for m in gaz._deictic_pattern.finditer(norm):
        if any(m.start() < e and m.end() > s for s, e in time_spans):
            continue
        ents.append(Entity("deictic_ref", m.group(0), m.group(0)))
        consumed.append(m.span())

    # --- category cues: tokens outside consumed spans ---
    for m in gaz._cue_pattern.finditer(norm):
        if free(m.span()):
            result.category_cues.append((m.group(1), gaz.category_cues[m.group(1)]))

    # --- transfer: two different terminals named, or transfer wording ---
    if len({t.value for t in result.of_type("terminal", role=None)}) >= 2:
        result.transfer = True

    # --- fragment: nothing left that could name a service ---
    residual = norm
    for start, end in sorted(consumed, reverse=True):
        residual = residual[:start] + " " + residual[end:]
    for m in TERMINAL_PATTERN.finditer(residual):
        residual = residual.replace(m.group(0), " ")
    if gaz._lead_in_pattern is not None:
        residual = gaz._lead_in_pattern.sub(" ", residual)
    leftover = [t for t in residual.split() if t not in FUNCTION_WORDS and not t.isdigit()]
    has_request = bool(result.of_type("service") or result.category_cues or result.families or
                       result.unsupported or result.transfer or
                       result.of_type("deictic_ref") or result.of_type("flight_ref") or
                       [e for e in result.entities
                        if e.type in ("gate_id", "desk_id", "belt_id") and e.role == "target"])
    result.fragment = bool(norm.strip()) and not has_request and not leftover and not result.destination

    # A landmark is only a landmark when something else is asked for. "How
    # long is the queue at security north?" names one service after "at" and
    # asks about that service; it is the target after all.
    if not has_request and (leftover or result.destination) and result.landmarks():
        result.entities = [Entity(e.type, e.value, e.surface, e.exists, e.record_ids, "target")
                           if e.role == "landmark" else e for e in result.entities]

    return result
