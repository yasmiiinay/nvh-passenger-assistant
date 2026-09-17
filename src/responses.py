"""Text response assembly from a retrieval result (Architecture Freeze v1.1 4.8,
concise passenger layer added in usability hardening 04.6).

Every sentence comes from a KB field or from a fixed template; nothing is
generated. Empty record fields are left out, never filled in. The flags set
by the cascade decide which caveats are added:

  volatile                  live flight information: redirect, no KB answer
  time_reference_no_clock   the passenger asked about "now" or "tonight";
                            hours are given, open/closed is never claimed
  time_explicit             the passenger gave a clock time; it is compared
                            with the listed hours when those parse (04.6)
  grounded_negative         the KB says the thing does not exist there
  terminal_mismatch         the service exists, but only in the other terminal
  cross_terminal_service    the record sits in another terminal but serves the
                            one asked about (airport-level service)
  terminal_retargeted       the alias named a record elsewhere; the answer is
                            the same kind of record in the terminal asked about
  assist_policy             assistance request answered with the nearest point
  action_request            the passenger asked us to do something (book,
                            reserve, print); the request is refused and the
                            named place is pointed to
  unsupported_service       a named service the KB does not hold (04.6)
  fragment / followup_context
                            a service-free follow-up, asked about or completed
                            from the previous clarification (04.6)

Two layers (04.6). `render` produces the short passenger-facing answer:
two to four sentences that address the aspect the question asked about
(where, hours, accessibility, directions). `record_details` lists every
field of the selected record for the evidence panel, so nothing the KB
holds is hidden, it is just not read out unasked.
"""
from __future__ import annotations

import re

from src.retrieval import RetrievalResult, asks_live_status, is_action_request   # noqa: F401 (re-exported)

SCORE_NOTE = "a similarity measure, not a probability that the answer is correct"
BAND_FOR_SCORE = {"answer": "strong match", "clarify": "uncertain", "abstain": "no reliable match"}

# "first"/"last" only as "first train" / "last bus", never the "first" of "first aid"
HOURS_WORDS = re.compile(r"\b(open|opens|opening|close|closes|closed|closing|hours|what time|when does|when is|"
                         r"until|late|early|(?:first|last) (?:train|trains|bus|buses|shuttle|departure))\b")
DIRECTION_WORDS = re.compile(r"\b(how do i get|how to get|way to|route|reach|walk|far|get there|directions)\b")
ACCESS_WORDS = re.compile(r"\b(step ?free|lift|elevator|wheelchair|accessible|ramp|stairs|mobility)\b")
CLOCK_RANGE = re.compile(r"^(\d\d):(\d\d)-(\d\d):(\d\d)(?:\s*\(.*\))?$")
PERIOD_LABELS = {"mon_sun": "daily", "mon_fri": "Monday to Friday", "sat_sun": "Saturday and Sunday",
                 "mon_sat": "Monday to Saturday"}


# ---------------------------------------------------------------------------
# small readers
# ---------------------------------------------------------------------------

def _asked_terminal(result: RetrievalResult) -> str:
    return result.entities.get("terminal") or "the terminal you asked about"


def _first_sentence(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    head = re.split(r"(?<=[.;])\s+", text, maxsplit=1)[0].rstrip(";.")
    return head + "."


def _place(record: dict) -> str:
    """"Terminal 1, Pier B (Airside, Level 2)"; the level is left out when the
    zone already says it ("Departures" / "Departures, Level 1")."""
    level = record.get("level", "")
    if level and level.split(",")[0].strip().lower() not in record["zone"].lower():
        return f"{record['terminal']}, {record['zone']} ({level})"
    return f"{record['terminal']}, {record['zone']}"


def _hours_lines(record: dict) -> list[str]:
    hours = record.get("opening_hours") or {}
    return [f"{PERIOD_LABELS.get(period, period.replace('_', ' to '))} {value}" for period, value in hours.items()]


def _access_bits(record: dict) -> list[str]:
    access = record.get("accessibility") or {}
    bits = []
    if access.get("step_free"):
        bits.append("step-free access")
    if access.get("induction_loop"):
        bits.append("induction loop")
    if access.get("accessible_toilet_nearby"):
        bits.append("accessible toilet nearby")
    return bits


def question_aspect(result: RetrievalResult) -> str:
    """What the question is about: hours, directions, accessibility or,
    by default, where. Read from the intent and the words, never guessed
    from the record."""
    words = result.normalized
    if "time_explicit" in result.flags or "time_reference_no_clock" in result.flags or \
            result.intent == "ask_opening_hours" or HOURS_WORDS.search(words):
        return "hours"
    if result.intent == "ask_directions" or DIRECTION_WORDS.search(words):
        return "directions"
    if result.intent == "request_accessibility_help" or "assist_policy" in result.flags or \
            result.entities.get("service_family") == "accessibility" or ACCESS_WORDS.search(words):
        return "accessibility"
    return "where"


def _open_at(record: dict, clock: str) -> list[tuple[bool, str, str]] | None:
    """(open?, listed range, period label) per listed period, or None when a
    period is not a plain HH:MM-HH:MM range. Overnight ranges wrap."""
    hour, minute = (int(p) for p in clock.split(":"))
    asked = hour * 60 + minute
    out = []
    for period, value in (record.get("opening_hours") or {}).items():
        m = CLOCK_RANGE.match(value.strip())
        if not m:
            return None
        start = int(m.group(1)) * 60 + int(m.group(2))
        end = int(m.group(3)) * 60 + int(m.group(4))
        is_open = start <= asked < end if start < end else (asked >= start or asked < end)
        label = "" if period == "mon_sun" else f" {PERIOD_LABELS.get(period, period)}"
        out.append((is_open, f"{m.group(1)}:{m.group(2)}–{m.group(3)}:{m.group(4)}", label))
    return out or None


def hours_verdict(record: dict, clock: str) -> str | None:
    """"Yes/No, scheduled to be open at HH:MM" when the listed hours are plain
    ranges; None when they are not (then the hours are quoted). A clock of
    the form "09:15|21:15" is a time given without am/pm: when both readings
    agree the verdict is given, otherwise the passenger is asked which."""
    readings = clock.split("|")
    results = [_open_at(record, reading) for reading in readings]
    if any(r is None for r in results):
        return None
    if len(readings) == 2:
        morning, evening = results
        if [o for o, _, _ in morning] != [o for o, _, _ in evening]:
            listed = "; ".join(f"{rng}{label}" for _, rng, label in morning)
            return (f"{record['name']} is listed as {listed}, so the answer depends on whether you mean "
                    f"{readings[0]} or {readings[1]}.")
        clock = f"{readings[0]} or {readings[1]}"
        results = [morning]
    verdicts = results[0]
    if len(verdicts) == 1:
        is_open, listed, _ = verdicts[0]
        return (f"{'Yes' if is_open else 'No'}. {record['name']} is scheduled to be "
                f"{'open' if is_open else 'closed'} at {clock}; its listed hours are {listed}.")
    parts = [f"{'open' if is_open else 'closed'}{label} ({listed})" for is_open, listed, label in verdicts]
    return f"At {clock} {record['name']} is scheduled to be " + " and ".join(parts) + "."


# ---------------------------------------------------------------------------
# the concise answer
# ---------------------------------------------------------------------------

def concise_record_text(record: dict, gaz, result: RetrievalResult | None, aspect: str = "where") -> list[str]:
    """Two to four short sentences that answer the aspect asked about."""
    lines = []
    if aspect == "hours":
        clock = (result.entities.get("clock_time") if result else None)
        verdict = hours_verdict(record, clock) if clock else None
        if verdict:
            lines.append(verdict)
        else:
            listed = "; ".join(_hours_lines(record))
            lines.append(f"{record['name']}: listed hours {listed}." if listed
                         else f"{record['name']} has no listed hours in the airport information.")
            if result is not None and "time_reference_no_clock" in result.flags:
                lines.append("I cannot see the current time, so please compare these hours with the time "
                             "where you are.")
        lines.append(f"It is in {_place(record)}.")
        return lines
    if aspect == "accessibility":
        bits = _access_bits(record)
        lines.append(f"{record['name']} is in {_place(record)}.")
        if bits:
            lines.append("Accessibility: " + ", ".join(bits) + ".")
        if (record.get("accessibility") or {}).get("notes"):
            lines.append(record["accessibility"]["notes"])
        point = (record.get("accessibility") or {}).get("assistance_point_record")
        if point and point in gaz.records and point != record["record_id"]:
            lines.append(f"Nearest assistance point: {gaz.records[point]['name']}.")
        if record.get("assistance_contact") and record["category"] == "accessibility":
            lines.append("Help: " + record["assistance_contact"] + ".")
        return lines[:4]
    if aspect == "directions":
        lines.append(f"{record['name']} is in {_place(record)}.")
        if record.get("directions"):
            lines.append(record["directions"])
        return lines
    # where
    lines.append(f"{record['name']} is in {_place(record)}.")
    if record.get("directions"):
        lines.append(_first_sentence(record["directions"]))
    if record.get("availability_note") and record.get("volatility") == "high":
        lines.append(record["availability_note"])
    return lines


def _clarify_text(result: RetrievalResult, gaz) -> str:
    if "deictic" in result.flags:
        return "Please add a photo of the sign, or describe what you are looking for."
    if "fragment" in result.flags and not result.candidates:
        terminal = result.entities.get("terminal")
        landmark = result.entities.get("landmark")
        zone = result.entities.get("zone")
        if terminal:
            return f"What would you like to find in {terminal}?"
        if landmark and landmark in gaz.alias_index:
            return f"What would you like to find near {gaz.records[gaz.alias_index[landmark]]['name']}?"
        if zone:
            return f"What would you like to find {'in ' + zone if zone in ('arrivals', 'departures') else zone}?"
        return "What would you like to find there?"
    if result.clarification_field == "terminal":
        category = gaz.records[result.candidates[0]]["category"].replace("_", "-")
        terminals = sorted({gaz.records[rid]["terminal"] for rid in result.candidates})
        return f"There is more than one {category} location. Are you in {' or '.join(terminals)}?"
    if len(result.candidates) == 1:
        return f"Do you mean {gaz.records[result.candidates[0]]['name']}?"
    if result.candidates:
        names = [gaz.records[rid]["name"] for rid in result.candidates]
        terminals = {gaz.records[rid]["terminal"] for rid in result.candidates}
        categories = {gaz.records[rid]["category"] for rid in result.candidates}
        if len(categories) == 1 and len(terminals) == 1:
            category = next(iter(categories)).replace("_", " ")
            return (f"There are {len(names)} {category} locations in {next(iter(terminals))}: "
                    f"{' or '.join(names)}. Which one do you mean?")
        return "Which of these do you mean: " + " or ".join(names) + "?"
    return "Could you say a bit more about what you are looking for?"


def _abstain_text(result: RetrievalResult, gaz) -> list[str]:
    if "action_request" in result.flags:
        lines = ["I cannot book, reserve, print or arrange anything; I can only give information about the airport."]
        if result.candidates:
            record = gaz.records[result.candidates[0]]
            lines.append(f"For information: {record['name']} is in {_place(record)}.")
        return lines
    if "unsupported_service" in result.flags:
        term = result.entities.get("unsupported_service", "that")
        return [f"I don't have reliable information about \"{term}\" in this airport knowledge base. "
                "Please check an information desk or official airport information."]
    if "grounded_negative" in result.flags:
        return [result.reason[0].upper() + result.reason[1:] + ".",
                "Please check your boarding pass or ask at an information desk."]
    return ["I could not find that in the airport information I hold.",
            "An information desk can help; there is one in each terminal."]


def render(result: RetrievalResult, gaz) -> str:
    """The short text shown to the passenger for one cascade result."""
    lines: list[str] = []
    if asks_live_status(result.normalized):
        if "live_status_request" not in result.flags:
            result.flags.append("live_status_request")
        lines.append("I do not have live queue or waiting times; the terminal displays show them.")

    if result.decision == "redirect":
        record = gaz.records[result.matched_record_id]
        lines.append("I do not hold live flight, gate or delay information.")
        lines.append(record["availability_note"])
        return "\n".join(lines)

    if result.decision == "abstain":
        lines.extend(_abstain_text(result, gaz))
        return "\n".join(lines)

    if result.decision == "clarify":
        lines.append(_clarify_text(result, gaz))
        return "\n".join(lines)

    # answer
    if "grounded_negative" in result.flags:
        category = gaz.records[result.candidates[0]]["category"].replace("_", " ")
        lines.append(f"There is no {category} in {_asked_terminal(result)}.")
        nearest = "; ".join(f"{gaz.records[rid]['name']} ({gaz.records[rid]['terminal']})" for rid in result.candidates)
        lines.append(f"Nearest: {nearest}.")
        return "\n".join(lines)

    record = gaz.records[result.matched_record_id]
    aspect = question_aspect(result)
    if "terminal_mismatch" in result.flags:
        lines.append(f"{record['name']} is not in {_asked_terminal(result)}; it is in {record['terminal']}.")
    if "terminal_retargeted" in result.flags:
        lines.append(f"For {_asked_terminal(result)}, that is {record['name']}.")
    if "cross_terminal_service" in result.flags:
        lines.append(f"{record['name']} also serves {_asked_terminal(result)}.")
    if "assist_policy" in result.flags:
        lines.append(f"The nearest designated assistance point is {record['name']}, {_place(record)}.")
        if record.get("assistance_contact"):
            lines.append("Help: " + record["assistance_contact"] + ".")
        return "\n".join(lines)
    if "followup_context" in result.flags:
        lines.append(f"For {record['category'].replace('_', ' ')} in {record['terminal']}:")
    lines.extend(concise_record_text(record, gaz, result, aspect))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# full details for the evidence panel (04.6)
# ---------------------------------------------------------------------------

def record_details(record: dict, gaz) -> list[tuple[str, str]]:
    """Every KB field of the selected record, as label/value pairs. This is
    what the long answer used to read out; it now sits behind "Evidence &
    details" so the passenger can check it without being handed it."""
    rows = [("Record", f"{record['name']} ({record['record_id']})"),
            ("Location", _place(record))]
    if record.get("description"):
        rows.append(("Description", record["description"]))
    if record.get("directions"):
        rows.append(("Directions", record["directions"]))
    hours = _hours_lines(record)
    if hours:
        rows.append(("Opening hours", "; ".join(hours)))
    if record.get("availability_note"):
        rows.append(("Availability", record["availability_note"]))
    access = record.get("accessibility") or {}
    bits = _access_bits(record)
    if bits or access.get("notes"):
        rows.append(("Accessibility", ", ".join(bits) + (f". {access['notes']}" if access.get("notes") else "")))
    point = access.get("assistance_point_record")
    if point and point in gaz.records and point != record["record_id"]:
        rows.append(("Nearest assistance point", gaz.records[point]["name"]))
    if record.get("assistance_contact"):
        rows.append(("Help", record["assistance_contact"]))
    rows.append(("Source", f"synthetic knowledge base for a fictional airport; last verified {record['last_verified']}"))
    return rows


def compact_facts(record: dict) -> list[tuple[str, str, str]]:
    """At most four (icon, label, value) facts for the fact row under a
    short answer. Values are KB fields of the selected record, unchanged
    apart from the hours separator; nothing is inferred (rule G, 04.6)."""
    facts = [("\U0001F4CD", "Location", f"{record['terminal']} · {record['zone']}")]
    hours = record.get("opening_hours") or {}
    if "mon_sun" in hours:
        value = hours["mon_sun"]
        facts.append(("\U0001F552", "Hours", value.replace("-", "–", 1) if CLOCK_RANGE.match(value.strip()) else value))
    elif hours:
        facts.append(("\U0001F552", "Hours", "; ".join(_hours_lines(record))))
    bits = _access_bits(record)
    if bits:
        facts.append(("♿", "Access", ", ".join(bits).replace("step-free access", "Step-free")))
    if record.get("directions"):
        facts.append(("\U0001F9ED", "Route", _first_sentence(record["directions"])))
    return facts[:4]


# ---------------------------------------------------------------------------
# multimodal outcomes (checkpoint 03.4)
# ---------------------------------------------------------------------------

def _category_label(category: str, gaz) -> str:
    return f"{category.replace('_', ' ')} ({gaz.vocabulary['categories'][category]['description'].lower()})"


def _names(record_ids: list[str], gaz) -> str:
    return "; ".join(f"{gaz.records[rid]['name']} ({gaz.records[rid]['terminal']})" for rid in record_ids)


def _modality_notes(outcome, gaz) -> list[str]:
    """Sentences that say what the other inputs contributed. The transcript
    itself is shown by the interface as "heard as", so it is not repeated."""
    lines = []
    if outcome.speech is not None:
        if outcome.speech.check.ok and "text" in outcome.modalities:
            lines.append("I used your typed question rather than the recording.")
        elif not outcome.speech.check.ok:
            lines.append(f"I could not use the voice clip ({outcome.speech.check.problem}); "
                         "please re-record closer to the microphone or type your question.")
    if outcome.vision is not None and outcome.route in ("text_leads", "voice_leads"):
        if "image_agrees" in outcome.flags:
            lines.append(f"The photo agrees: it looks like a {_category_label(outcome.image_category, gaz)} sign.")
        elif "image_disagrees" in outcome.flags:
            lines.append(f"Note: the photo looks like a {_category_label(outcome.image_category, gaz)} sign, "
                         "which is not what your question refers to. I have answered the question; "
                         "if you meant the sign, please ask about it on its own.")
        elif "image_uncertain_agrees" in outcome.flags:
            lines.append(f"The photo most likely shows a {_category_label(outcome.image_category, gaz)} sign, "
                         "which fits your question, so I went by your words.")
        elif "image_uncertain" in outcome.flags:
            lines.append("I could not identify the sign in the photo with any confidence, so I answered from your words.")
        elif "image_not_recognised" in outcome.flags:
            lines.append("I could not recognise an airport sign in the photo, so I answered from your words.")
    if outcome.error:
        lines.append(f"One input could not be read ({outcome.error}).")
    return lines


def render_outcome(outcome, gaz) -> str:
    """Text shown to the passenger for a routed multimodal outcome."""
    lines: list[str] = []
    if outcome.route == "none":
        if outcome.speech is not None and not outcome.speech.check.ok:
            lines.extend(_modality_notes(outcome, gaz))
        elif outcome.error:
            lines.append(f"I could not read that input ({outcome.error}).")
            lines.append("Please type your question, or try a JPEG or PNG photo and a WAV or MP3 recording.")
        else:
            lines.append("Please type a question, add a photo of a sign, or record your question.")
        return "\n".join(lines)
    if outcome.route in ("text_leads", "voice_leads", "text_only", "voice_only") and outcome.decision != "conflict":
        lines.extend(render(outcome.text, gaz).split("\n"))
        lines.extend(_modality_notes(outcome, gaz))
        return "\n".join(lines)

    if outcome.decision == "conflict":
        detail = outcome.conflict_detail
        text_part = (gaz.records[detail["text_record"]]["name"] if detail.get("text_record")
                     else " or ".join(_category_label(c, gaz) for c in detail["text_categories"]))
        lines.append(f"Your words point to {text_part}, but the photo looks like a "
                     f"{_category_label(detail['image_category'], gaz)} sign. Which one do you mean?")
        lines.append("Options: " + _names(outcome.candidates, gaz) + ".")
        lines.extend(_modality_notes(outcome, gaz))
        return "\n".join(lines)

    # image-led or image-only
    if outcome.decision == "abstain":
        lines.append("I could not recognise an airport sign in this photo.")
        if outcome.vision is not None and outcome.vision.check.flags:
            lines.append("The photo looks " + " and ".join(outcome.vision.check.flags) + "; a clearer, closer photo may help.")
        lines.append("You can also type or say what you are looking for, or ask at an information desk.")
        lines.extend(_modality_notes(outcome, gaz))
        return "\n".join(lines)

    category = outcome.image_category
    if outcome.decision == "clarify":
        if "image_no_clear_leader" in outcome.flags:
            # runner-up within the vision margin: name both, never a third
            first, second = (c for c, _ in outcome.vision.category_ranking[:2])
            lines.append(f"I am not sure what this sign shows; it may be {_category_label(first, gaz)} or "
                         f"{_category_label(second, gaz)}. Could you say what you are looking for, "
                         "or take a closer photo?")
        elif "image_uncertain" in outcome.flags:
            lines.append(f"This most likely shows a {_category_label(category, gaz)} sign, but I am not certain. "
                         "Is that what you are looking for?")
        elif "image_confirm" in outcome.flags:
            lines.append(f"This looks like a {_category_label(category, gaz)} sign. "
                         f"Is that what you are looking for? If so, the place is: {_names(outcome.candidates, gaz)}.")
        else:
            lines.append(f"This looks like a {_category_label(category, gaz)} sign. "
                         f"There is more than one such place: {_names(outcome.candidates, gaz)}. "
                         "Which terminal are you in?")
        if outcome.vision is not None and outcome.vision.check.flags:
            lines.append("The photo looks " + " and ".join(outcome.vision.check.flags) + ".")
        lines.extend(_modality_notes(outcome, gaz))
        return "\n".join(lines)

    # image-led answer
    record = gaz.records[outcome.matched_record_id]
    if "deictic" in outcome.flags:
        lines.append(f"This sign means: {_category_label(category, gaz)}.")
    else:
        lines.append(f"From the photo this looks like a {_category_label(category, gaz)} sign.")
    if "text_not_understood" in outcome.flags:
        lines.append("I did not understand the words, so the answer comes from the photo.")
    elif "text_weak" in outcome.flags:
        lines.append("Your words did not match anything closely, so the answer comes from the photo.")
    lines.extend(concise_record_text(record, gaz, outcome.text, question_aspect(outcome.text) if outcome.text else "where"))
    lines.extend(_modality_notes(outcome, gaz))
    return "\n".join(lines)
