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


@dataclass
class Asked:
    person: str
    text: str
    before: str = ""            # said before the answer ("I'm not sure who's asking")
    sample: str = ""            # a sample was taken instead: what to say back


def enrolling_file() -> Path:
    return status.state() / ENROLLING


def start_enrolling(puck: str, person: str, samples: int = SAMPLES) -> None:
    target = enrolling_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"puck": puck, "person": person, "left": samples,
                                  "first": True}))


def _enrolling(puck: str) -> dict | None:
    try:
        note = json.loads(enrolling_file().read_text())
    except (OSError, ValueError):
        return None
    return note if note.get("puck") == puck and note.get("left", 0) > 0 else None


def whose(conf: Config, puck: Puck, text: str, wav: bytes, prints: Prints) -> Asked:
    note = _enrolling(puck.name)
    if note is not None:
        count = prints.enroll(note["person"], [wav], add=not note.get("first"))
        note.update(left=note["left"] - 1, first=False)
        if note["left"] > 0:
            enrolling_file().write_text(json.dumps(note))
            return Asked(note["person"], text, sample=SAMPLE_MORE.format(left=note["left"]))
        enrolling_file().unlink(missing_ok=True)
        log.info("%s: %s's voice print made from %d samples", puck.name, note["person"], count)
        return Asked(note["person"], text, sample=SAMPLE_DONE.format(person=note["person"]))
    if not puck.people:
        return Asked(puck.person, text)
    named, rest = said_name(text, puck.people)
    if named is not None:
        return Asked(named, rest)
    try:
        found = prints.match(wav, puck.people, threshold=conf.threshold, margin=conf.margin)
    except VoiceError as exc:
        log.warning("%s: can't tell voices apart: %s", puck.name, exc)
        return Asked(puck.person, text)
    log.info("%s: voice %s (%.2f, next %.2f)", puck.name, found.person or "unsure",
             found.score, found.runner_up)
    if found.person is not None:
        return Asked(found.person, text)
    return Asked(puck.person, text, before=UNSURE.format(person=puck.person))
