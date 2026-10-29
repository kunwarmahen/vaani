"""Whose question it is, and what's done with it: answered, or a sample.

The step between hearing and Dvara. For a puck with ``people``, the
speaker is a person it may hear (``voices.py``: a name said, else a
voice print that clearly matches) or, unsure, the puck's own
``person``, and the puck says it wasn't sure. For a puck without, it is
the puck's ``person`` as always.

A PRINT IS MADE AT THE PUCK ITSELF. `vaani voices enroll asha --at-puck
kitchen` leaves a note in Vaani's state folder; the next three times
someone at that puck says the wake word and a sentence, the sentence is
a sample of Asha's voice, not a question, and nobody is asked anything.
The puck says how many are left, and when the print is made. The
person stands where they'll stand when they ask, in the room's own
sound, which beats a recording made somewhere else.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from vaani import status
from vaani.config import Config, Puck
from vaani.voices import SAMPLES, Prints, VoiceError, said_name

log = logging.getLogger("vaani")

UNSURE = "I'm not sure who's asking, so I'm answering for {person}."
SAMPLE_MORE = "Got it. {left} more: say the wake word, then any sentence."
SAMPLE_DONE = "Thanks. I know {person}'s voice now."
ENROLLING = "enrolling.json"
STARTED_OVER = "Starting fresh. What would you like to ask?"

#: The whole of what was said, give or take "please": a new conversation.
#: Only the whole: "tell me about the new conversation with Ravi" is a question.
NEW_WORDS = re.compile(
    r"^(?:ok(?:ay)?,? )?(?:let'?s |please |can we |can you )?"
    r"(?:start (?:a )?(?:new|fresh|over)(?: conversation| chat| topic)?"
    r"|new (?:conversation|chat|topic)|fresh start|start again|forget (?:all )?that)"
    r"(?:,? please)?$")


def starts_over(text: str) -> bool:
    """"New conversation", "start over", "let's start fresh, please"."""
    words = re.sub(r"[^\w' ,]", "", text.lower()).strip(" ,")
    return bool(NEW_WORDS.match(words))


@dataclass
class Asked:
    person: str
    text: str
    before: str = ""            # said before the answer ("I'm not sure who's asking")
    sample: str = ""            # a sample was taken instead: what to say back
    how: str = ""               # why it is this person, in a few words


def enrolling_file() -> Path:
    return status.state() / ENROLLING


def start_enrolling(puck: str, person: str, samples: int = SAMPLES) -> None:
    target = enrolling_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"puck": puck, "person": person, "left": samples,
                                  "first": True}))


def enrolling() -> dict | None:
    """Whose samples are being taken, at which puck, how many left."""
    try:
        note = json.loads(enrolling_file().read_text())
    except (OSError, ValueError):
        return None
    return note if isinstance(note, dict) and note.get("left", 0) > 0 else None


def _enrolling(puck: str) -> dict | None:
    note = enrolling()
    return note if note and note.get("puck") == puck else None


def whose(conf: Config, puck: Puck, text: str, wav: bytes, prints: Prints,
          follows: str = "") -> Asked:
    """``follows``: the person whose answer asked something back, when this
    is the puck listening again without its wake word -- their reply."""
    if follows and (follows == puck.person or follows in puck.people):
        return Asked(follows, text, how="replying to the puck")
    note = _enrolling(puck.name)
    if note is not None:
        count = prints.enroll(note["person"], [wav], add=not note.get("first"))
        note.update(left=note["left"] - 1, first=False)
        if note["left"] > 0:
            enrolling_file().write_text(json.dumps(note))
            return Asked(note["person"], text, sample=SAMPLE_MORE.format(left=note["left"]),
                         how=f"a voice sample ({note['left']} more)")
        enrolling_file().unlink(missing_ok=True)
        log.info("%s: %s's voice print made from %d samples", puck.name, note["person"], count)
        return Asked(note["person"], text, sample=SAMPLE_DONE.format(person=note["person"]),
                     how="the last voice sample")
    if not puck.people:
        return Asked(puck.person, text, how="the puck's person")
    named, rest = said_name(text, puck.people)
    if named is not None:
        return Asked(named, rest, how="said their name")
    try:
        found = prints.match(wav, puck.people, threshold=conf.threshold, margin=conf.margin)
    except VoiceError as exc:
        log.warning("%s: can't tell voices apart: %s", puck.name, exc)
        return Asked(puck.person, text, how=f"couldn't tell voices apart: {exc}")
    log.info("%s: voice %s (%.2f, next %.2f)", puck.name, found.person or "unsure",
             found.score, found.runner_up)
    if found.person is not None:
        return Asked(found.person, text, how=f"their voice ({found.score:.2f})")
    return Asked(puck.person, text, before=UNSURE.format(person=puck.person),
                 how=f"unsure of the voice ({found.score:.2f})")
