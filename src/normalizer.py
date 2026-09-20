"""Deterministic text normalisation shared by typed text and ASR transcripts.

Two levels, applied in order (Evidence Pack A4; Architecture Freeze v1.1 4.2):

  L1  generic:  lowercase, contraction expansion, punctuation, whitespace,
                  cardinal number words -> digits. Applied identically to WER
                  references and hypotheses, so it never flatters the ASR.
  L2  airport:  letter words / NATO words -> pier letters, identifier spacing
                  collapse ("b 12" -> "b12"), terminal short forms ("t2" ->
                  "terminal 2"), a small service-name homophone map.

Nothing here removes stop words: the token stream stays intact because gate
identifiers survive only if their neighbours do ("gate a 7" needs "gate" to
disambiguate "a").

Every rule is a row in RULES so the report appendix can print the table with
each rule's level, provenance ("design" = derived from the identifier grammar,
"anticipated" = a plausible ASR confusion not yet observed, "observed" = taken
from the speech-evaluation error catalogue) and a worked example. A rule with provenance
"anticipated" must be re-labelled or removed once real transcripts exist.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    name: str
    level: str          # "L1" or "L2"
    pattern: str        # regex applied to the running lowercase string
    replacement: object # re.sub replacement: a string with groups, or a function of the match
    example_in: str
    example_out: str
    provenance: str     # "design" | "anticipated" | "observed"

    def apply(self, text: str) -> str:
        return re.sub(self.pattern, self.replacement, text)


# ---------------------------------------------------------------------------
# L1: generic
# ---------------------------------------------------------------------------

CONTRACTIONS = {
    "won't": "will not", "can't": "cannot", "shan't": "shall not",
    "let's": "let us", "i'm": "i am", "it's": "it is", "what's": "what is",
    "where's": "where is", "there's": "there is", "who's": "who is",
    "how's": "how is", "that's": "that is", "n't": " not", "'re": " are",
    "'ve": " have", "'ll": " will", "'d": " would",
}

_UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
         "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_NUMBER_WORDS = set(_UNITS) | set(_TENS) | {"hundred", "and"}


def _number_phrase_value(words: list[str]) -> int | None:
    """Value of a cardinal phrase up to 999, or None if the words are not one
    well-formed cardinal. Accepted shapes:
        [unit hundred] [and] [tens] [unit]      "one hundred and forty five"
        unit tens [unit]                        "one forty five" -> 145
    The second shape has no 'hundred' word; it is how desk numbers are spoken
    ("desk one forty five") and is the reason this is not a generic parser.
    Anything else ("one twenty" is fine, "twenty one hundred" is not) returns
    None and the caller converts each word on its own."""
    i, n = 0, len(words)
    hundreds = 0
    if n >= 2 and words[0] in _UNITS and 1 <= _UNITS[words[0]] <= 9 and words[1] == "hundred":
        hundreds, i = _UNITS[words[0]] * 100, 2
        if i < n and words[i] == "and":
            i += 1
            if i == n:
                return None
    elif n >= 2 and words[0] in _UNITS and 1 <= _UNITS[words[0]] <= 9 and words[1] in _TENS:
        hundreds, i = _UNITS[words[0]] * 100, 1
    rest = 0
    if i < n and words[i] in _TENS:
        rest, i = _TENS[words[i]], i + 1
        if i < n and words[i] in _UNITS and 1 <= _UNITS[words[i]] <= 9:
            rest, i = rest + _UNITS[words[i]], i + 1
    elif i < n and words[i] in _UNITS:
        rest, i = _UNITS[words[i]], i + 1
    if i != n or (hundreds == 0 and rest == 0 and words != ["zero"]):
        return None
    return hundreds + rest


def _numbers_to_digits(text: str) -> str:
    """Replace maximal runs of number words with digits. Ordinals ("first
    aid") and non-cardinal uses are untouched because only the closed
    cardinal word list is recognised. 'and' is consumed only inside a run
    that already carries a value ("hundred and five"), never on its own."""
    tokens = text.split()
    out, i = [], 0
    while i < len(tokens):
        if tokens[i] not in _NUMBER_WORDS or tokens[i] == "and":
            out.append(tokens[i])
            i += 1
            continue
        j = i
        while j < len(tokens) and tokens[j] in _NUMBER_WORDS:
            j += 1
        # trailing 'and' belongs to the sentence, not the number
        while j > i and tokens[j - 1] == "and":
            j -= 1
        value = _number_phrase_value(tokens[i:j])
        if value is None:
            # not a clean cardinal run: emit the words one by one, converting
            # only the standalone ones ("two and a half" -> "2 and a half")
            for w in tokens[i:j]:
                out.append(str(_UNITS.get(w, _TENS.get(w, w))) if w in _UNITS or w in _TENS else w)
        else:
            out.append(str(value))
        i = j
    return " ".join(out)


L1_RULES: list[Rule] = [
    Rule("hyphen_to_space", "L1", r"[-‐-―−/]+", " ",
         "check-in desk", "check in desk", "design"),
    Rule("strip_punctuation", "L1", r"[^\w\s']", " ",
         "gate c3?", "gate c3 ", "design"),
    Rule("drop_remaining_apostrophes", "L1", r"'", "",
         "lounge's hours", "lounges hours", "design"),
    Rule("collapse_whitespace", "L1", r"\s+", " ",
         "gate  b12", "gate b12", "design"),
]


def normalize_l1(text: str) -> str:
    """Generic normalisation: the WER-L1 transform and the first pass for
    typed text. Returns lowercase, punctuation-free, single-spaced text with
    cardinal number words converted to digits."""
    if text is None:
        return ""
    t = unicodedata.normalize("NFKC", str(text)).lower()
    for key, value in CONTRACTIONS.items():
        t = t.replace(key, value)
    for rule in L1_RULES:
        t = rule.apply(t)
    t = _numbers_to_digits(t.strip())
    return t.strip()


# ---------------------------------------------------------------------------
# L2: airport-specific
# ---------------------------------------------------------------------------

# Letter words that ASR produces for spoken pier letters. "be" and "see" are
# ordinary English words, so they (and bare "a") are only mapped when a gate
# or pier keyword precedes them; "bee", "bravo", "alpha", "charlie" and bare
# "b"/"c" are safe to map whenever a 1-2 digit number follows.
_SAFE_LETTER_WORDS = {"bee": "b", "bravo": "b", "alpha": "a", "charlie": "c", "b": "b", "c": "c"}
_CONTEXT_LETTER_WORDS = {"a": "a", "be": "b", "bee": "b", "see": "c", "sea": "c",
                         "alpha": "a", "bravo": "b", "charlie": "c", "b": "b", "c": "c"}
_GATE_CONTEXT = r"(?:gate|gates|pier)"


def _map_letter_after_gate_keyword(m: re.Match) -> str:
    return f"{m.group(1)} {_CONTEXT_LETTER_WORDS[m.group(2)]}{m.group(3)}"


def _map_safe_letter(m: re.Match) -> str:
    return f"{_SAFE_LETTER_WORDS[m.group(1)]}{m.group(2)}"


def _alternatives(words: dict[str, str]) -> str:
    return "|".join(sorted(words, key=len, reverse=True))


L2_RULES: list[Rule] = [
    Rule("terminal_short_form", "L2", r"\bt\s?([12])\b", r"terminal \1",
         "t2 check in", "terminal 2 check in", "design"),
    Rule("terminal_glued", "L2", r"\bterminal(\d)\b", r"terminal \1",
         "terminal1", "terminal 1", "anticipated"),
    Rule("letter_word_after_gate_keyword", "L2",
         rf"\b({_GATE_CONTEXT})\s+({_alternatives(_CONTEXT_LETTER_WORDS)})\s+(\d{{1,2}})\b",
         _map_letter_after_gate_keyword, "gate be 12", "gate b12", "design"),
    Rule("letter_word_before_number", "L2",
         rf"\b({_alternatives(_SAFE_LETTER_WORDS)})\s+(\d{{1,2}})\b",
         _map_safe_letter, "bravo 7", "b7", "design"),
    Rule("desk_glued", "L2", r"\bdesk(\d{3})\b", r"desk \1",
         "desk145", "desk 145", "anticipated"),
    Rule("belt_glued", "L2", r"\bbelt(\d{1,2})\b", r"belt \1",
         "belt8", "belt 8", "anticipated"),
    Rule("checkin_variants", "L2", r"\bcheck ?ins?\b", "check in",
         "checkin desks", "check in desks", "design"),
    Rule("wifi_variants", "L2", r"\bwi ?fi\b", "wifi",
         "wi fi password", "wifi password", "design"),
    Rule("homophone_lost_and_found", "L2", r"\blost (?:in|n|an) found\b", "lost and found",
         "lost in found", "lost and found", "anticipated"),
    Rule("homophone_gate", "L2", r"\bgait\b", "gate",
         "gait b12", "gate b12", "anticipated"),
    Rule("homophone_lounge", "L2", r"\blaunch\b(?=.*\b(?:open|airport|terminal)\b)", "lounge",
         "is the launch open", "is the lounge open", "anticipated"),
    Rule("homophone_toilet", "L2", r"\btoilette?s?\b", "toilet",
         "nearest toilette", "nearest toilet", "anticipated"),
    # The two rules below come from the first Whisper-base run on synthetic
    # voices (outputs/checkpoint_03_3/speech): "P1" was emitted as "p 1"
    # (aud_110) and "desk 145" as "disk 145" (aud_053).
    Rule("car_park_letter_split", "L2", r"\bp (\d)\b", r"p\1",
         "parked in p 1", "parked in p1", "observed"),
    Rule("homophone_desk", "L2", r"\bdisk (\d{3})\b", r"desk \1",
         "where is disk 145", "where is desk 145", "observed"),
]

RULES: list[Rule] = L1_RULES + L2_RULES


def normalize_l2(text: str) -> str:
    """Airport normalisation applied on top of L1. Expects L1 output but is
    safe on raw text because it lowercases through normalize_l1 first."""
    t = normalize_l1(text)
    for rule in L2_RULES:
        t = rule.apply(t)
    return re.sub(r"\s+", " ", t).strip()


def normalize(text: str) -> str:
    """The pipeline entry point: L1 then L2. Typed text and transcripts both
    come through here (one text pipeline, v1.1 4.3)."""
    return normalize_l2(text)


def rule_table_markdown() -> str:
    """Rule table for the report appendix (rendered, not hand-copied)."""
    rows = ["| # | Rule | Level | Provenance | Example in | Example out |",
            "|---|---|---|---|---|---|"]
    # the two table-driven L1 steps that are functions rather than regexes
    documented = [
        Rule("lowercase_nfkc", "L1", "-", "-", "Gate B12", "gate b12", "design"),
        Rule("expand_contractions", "L1", "-", "-", "where's", "where is", "design"),
    ] + L1_RULES + [
        Rule("number_words_to_digits", "L1", "-", "-",
             "desk one forty five", "desk 145", "design"),
    ] + L2_RULES
    for i, r in enumerate(documented, 1):
        rows.append(f"| {i} | `{r.name}` | {r.level} | {r.provenance} | "
                    f"`{r.example_in}` | `{r.example_out}` |")
    return "\n".join(rows)


def rule_table_rows() -> list[dict]:
    """Same content as the markdown table, as dicts (for CSV export)."""
    return [{"name": r.name, "level": r.level, "provenance": r.provenance,
             "example_in": r.example_in, "example_out": r.example_out}
            for r in RULES]


if __name__ == "__main__":
    print(rule_table_markdown())
