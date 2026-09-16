"""Text response assembly from a retrieval result (Architecture Freeze v1.1 4.8).

Every sentence comes from a KB field or from a fixed template; nothing is
generated. Empty record fields are left out, never filled in. The flags set
by the cascade decide which caveats are added:

  volatile                  live flight information: redirect, no KB answer
  time_reference_no_clock   the passenger asked about "now" or a clock time;
                            hours are given, open/closed is never claimed
  grounded_negative         the KB says the thing does not exist there
  terminal_mismatch         the service exists, but only in the other terminal
  cross_terminal_service    the record sits in another terminal but serves the
                            one asked about (airport-level service)
  assist_policy             assistance request answered with the nearest point
  action_request            the passenger asked us to do something (book,
                            reserve, print); we only give information

Records with medium or high volatility always carry their availability
note, which is where "live queue times are not available" lives.
"""
from __future__ import annotations

import re

from src.retrieval import RetrievalResult

ACTION_PATTERN = re.compile(
    r"\b(book|reserve|order|print|rebook|arrange|call me|pay for|buy|cancel)\b")
LIVE_STATUS_PATTERN = re.compile(r"\b(queue|queues|waiting time|wait time|how long|busy|crowded)\b")

SCORE_NOTE = "a similarity measure, not a probability that the answer is correct"
BAND_FOR_SCORE = {"answer": "strong match", "clarify": "uncertain", "abstain": "no reliable match"}


def is_action_request(normalized_query: str) -> bool:
    return bool(ACTION_PATTERN.search(normalized_query))


def asks_live_status(normalized_query: str) -> bool:
    return bool(LIVE_STATUS_PATTERN.search(normalized_query))


def _asked_terminal(result: RetrievalResult) -> str:
    return result.entities.get("terminal", "the terminal you asked about")


def _hours_text(record: dict) -> str:
    hours = record.get("opening_hours") or {}
    if not hours:
        return ""
    parts = [f"{period.replace('_', ' to ')}: {value}" for period, value in hours.items()]
    return "Opening hours " + "; ".join(parts) + "."


def _record_text(record: dict, gaz) -> list[str]:
    """The answer body: name, where, description, directions, hours,
    availability note, accessibility, related and assistance contact."""
    lines = [f"{record['name']} ({record['terminal']}, {record['level']}, {record['zone']})."]
    if record.get("description"):
        lines.append(record["description"])
    if record.get("directions"):
        lines.append("Directions: " + record["directions"])
    hours = _hours_text(record)
    if hours:
        lines.append(hours)
    if record.get("availability_note") and record.get("volatility") in ("medium", "high"):
        lines.append(record["availability_note"])
    access = record.get("accessibility") or {}
    access_bits = []
    if access.get("step_free"):
        access_bits.append("step-free access")
    if access.get("induction_loop"):
        access_bits.append("induction loop")
    if access.get("accessible_toilet_nearby"):
        access_bits.append("accessible toilet nearby")
    if access_bits:
        lines.append("Accessibility: " + ", ".join(access_bits) + ".")
    if access.get("notes"):
        lines.append(access["notes"])
    point = access.get("assistance_point_record")
    if point and point in gaz.records and point != record["record_id"]:
        lines.append("Nearest assistance point: " + gaz.records[point]["name"] + ".")
    if record.get("assistance_contact"):
        lines.append("Help: " + record["assistance_contact"] + ".")
    return lines


def _provenance(record: dict | None, result: RetrievalResult) -> str:
    source = "Source: synthetic knowledge base for a fictional airport"
    if record:
        source += f" (record {record['record_id']}, last verified {record['last_verified']})"
    if result.match_score is not None:
        source += f". Matched by similarity: {BAND_FOR_SCORE.get(result.decision, result.decision)}"
    elif result.stage in ("exact_identifier", "alias_lookup"):
        source += f". Matched by {result.stage.replace('_', ' ')}"
    return source + "."


def render(result: RetrievalResult, gaz) -> str:
    """Turn one cascade result into the text shown to the passenger."""
    lines: list[str] = []
    if is_action_request(result.normalized):
        if "action_request" not in result.flags:
            result.flags.append("action_request")
        lines.append("I cannot book, reserve, print or arrange anything; I can only give "
                     "information about the airport.")
    if asks_live_status(result.normalized):
        if "live_status_request" not in result.flags:
            result.flags.append("live_status_request")
        lines.append("I do not have live queue or waiting times; the terminal displays show them.")

    if result.decision == "redirect":
        record = gaz.records[result.matched_record_id]
        lines.append("I do not hold live flight, gate or delay information.")
        lines.append(record["availability_note"])
        lines.append("Directions: " + record["directions"])
        lines.append(_provenance(record, result))
        return "\n".join(lines)

    if result.decision == "abstain":
        if "grounded_negative" in result.flags:
            lines.append(result.reason + ".")
            lines.append("Please check your boarding pass or ask at an information desk.")
        else:
            lines.append("I could not find anything about that in the airport information I hold.")
            lines.append("An information desk can help; there is one in each terminal.")
        lines.append(_provenance(None, result))
        return "\n".join(lines)

    if result.decision == "clarify":
        if "deictic" in result.flags:
            lines.append("Please add a photo of the sign so I can identify it, or describe where you are.")
        elif result.clarification_field == "terminal":
            category = gaz.records[result.candidates[0]]["category"].replace("_", "-")
            terminals = sorted({gaz.records[rid]["terminal"] for rid in result.candidates})
            lines.append(f"There is more than one {category} location. Are you in {' or '.join(terminals)}? "
                         f"Ask again with the terminal, for example \"{category} in {terminals[0]}\".")
        elif len(result.candidates) == 1:
            lines.append(f"Do you mean {gaz.records[result.candidates[0]]['name']}? "
                         "Please confirm, or say a bit more about what you are looking for.")
        elif result.candidates:
            names = [gaz.records[rid]["name"] for rid in result.candidates]
            lines.append("Which of these do you mean? " + " or ".join(names) + "?")
        else:
            lines.append("Could you say a bit more about what you are looking for?")
        lines.append(_provenance(None, result))
        return "\n".join(lines)

    # answer
    if "grounded_negative" in result.flags:
        category = gaz.records[result.candidates[0]]["category"].replace("_", " ")
        lines.append(f"There is no {category} in {_asked_terminal(result)}.")
        for rid in result.candidates:
            lines.append("Nearest: " + gaz.records[rid]["name"] + " (" + gaz.records[rid]["terminal"] + ").")
        lines.append(_provenance(None, result))
        return "\n".join(lines)

    record = gaz.records[result.matched_record_id]
    if "terminal_mismatch" in result.flags:
        lines.append(f"{record['name']} is not at {_asked_terminal(result)}; it is at {record['terminal']}.")
    if "cross_terminal_service" in result.flags:
        lines.append(f"{record['name']} is in {record['terminal']} and also serves {_asked_terminal(result)}.")
    if "assist_policy" in result.flags:
        lines.append("The nearest designated assistance point is:")
    lines.extend(_record_text(record, gaz))
    if "time_reference_no_clock" in result.flags:
        lines.append("I cannot see the current time, so I cannot say whether it is open right now; "
                     "please compare the hours above with the time where you are.")
    lines.append(_provenance(record, result))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# multimodal outcomes (checkpoint 03.4)
# ---------------------------------------------------------------------------

def _category_label(category: str, gaz) -> str:
    return f"{category.replace('_', ' ')} ({gaz.vocabulary['categories'][category]['description'].lower()})"


def _names(record_ids: list[str], gaz) -> str:
    return "; ".join(f"{gaz.records[rid]['name']} ({gaz.records[rid]['terminal']})" for rid in record_ids)


def _image_provenance(outcome) -> str:
    vision = outcome.vision
    line = f"Identified from the photo: {vision.band}."
    if vision.check.flags:
        line += " The photo looks " + " and ".join(vision.check.flags) + "."
    return line


def _modality_notes(outcome, gaz) -> list[str]:
    """Sentences that say what the other modalities contributed."""
    lines = []
    if outcome.speech is not None:
        if outcome.speech.check.ok and "text" in outcome.modalities:
            lines.append(f'I heard: "{outcome.speech.transcript_raw}", but used your typed question.')
        elif outcome.speech.check.ok:
            lines.append(f'I heard: "{outcome.speech.transcript_raw}".')
        else:
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
        body = render(outcome.text, gaz).split("\n")
        # notes about the other inputs go before the source line, which stays last
        lines.extend(body[:-1] + _modality_notes(outcome, gaz) + body[-1:])
        return "\n".join(lines)

    if outcome.decision == "conflict":
        detail = outcome.conflict_detail
        text_part = (gaz.records[detail["text_record"]]["name"] if detail.get("text_record")
                     else " or ".join(_category_label(c, gaz) for c in detail["text_categories"]))
        lines.append(f"Your words point to {text_part}, but the photo looks like a "
                     f"{_category_label(detail['image_category'], gaz)} sign. "
                     "I will not guess between them: which one do you mean?")
        lines.append("Options: " + _names(outcome.candidates, gaz) + ".")
        lines.extend(_modality_notes(outcome, gaz))
        lines.append(_provenance(None, outcome.text) if outcome.text else
                     "Source: synthetic knowledge base for a fictional airport.")
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
        lines.extend(_modality_notes(outcome, gaz))
        lines.append(_image_provenance(outcome))
        return "\n".join(lines)

    # image-led answer
    record = gaz.records[outcome.matched_record_id]
    if "deictic" in outcome.flags:
        lines.append(f"This sign means: {_category_label(category, gaz)}.")
    else:
        lines.append(f"From the photo this looks like a {_category_label(category, gaz)} sign.")
    if "text_not_understood" in outcome.flags:
        lines.append("I did not understand the words, so the answer below comes from the photo.")
    elif "text_weak" in outcome.flags:
        lines.append("Your words did not match anything closely, so the answer below comes from the photo.")
    lines.extend(_record_text(record, gaz))
    lines.extend(_modality_notes(outcome, gaz))
    lines.append(_image_provenance(outcome))
    lines.append(_provenance(record, outcome.text) if outcome.text else
                 f"Source: synthetic knowledge base for a fictional airport (record {record['record_id']}, "
                 f"last verified {record['last_verified']}).")
    return "\n".join(lines)
