"""A turn that takes a while, or stops to ask: said at the puck, not dropped.

THE PROBLEM, AS IT WAS MET. "Find me a flight to Phoenix on Sunday."
The agent opened a browser, and a browser needs the person's yes; Dvara
put the question in their Telegram chat and held the turn. Vaani waited
five minutes for an answer that couldn't come until someone looked at a
phone, gave up, and the puck said it couldn't reach the agent. The yes
was given on Telegram, the flights were found -- and went nowhere.

WHILE THE AGENT WORKS, VAANI LOOKS FOR ITS QUESTIONS. Dvara lists the
questions waiting on a person (``GET /asks``), each with its
conversation; one on this puck's conversation is put to the person at
the puck -- "Your agent wants to open google.com. Shall I go ahead?" --
and the puck listens again, no wake word. Their yes or no goes back to
Dvara (``POST /asks/ID``), and the same run then waits for the answer.
Telegram has the question too; whichever is answered first counts.

A LONG TURN IS FINISHED OUT LOUD. After ``LONG`` seconds the puck says
it is still working and stops spinning. Vaani keeps waiting, and when
the answer comes the puck says it as an announcement. A question that
comes up meanwhile is asked the same way, and the puck listens after
it.

YES AND NO ARE THE PERSON'S WORDS, READ STRICTLY. Only a clear yes is a
yes; anything else that isn't a clear no is asked again, once -- "was
that a yes or a no?" -- and a question nobody answers stays on the
phone, where it was anyway.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

#: Seconds a puck spins before it says it's still working.
LONG = 60.0
#: How often Dvara is asked for questions while a turn runs.
POLL = 2.0

YES = re.compile(r"^(?:yes|yeah|yep|yup|sure|ok(?:ay)?|go ahead|do it|please do|"
                 r"yes please|go for it|approve(?:d)?|that's fine|fine)\b")
NO = re.compile(r"^(?:no|nope|nah|don'?t|do not|stop|cancel|never ?mind|deny|"
                r"no thanks|not now)\b")


def yes_or_no(text: str) -> bool | None:
    """True for a clear yes, False for a clear no, None otherwise."""
    words = re.sub(r"[^\w' ]", " ", text.lower()).split()
    said = " ".join(words)
    if NO.match(said):
        return False
    if YES.match(said):
        return True
    return None


def spoken_question(ask: dict) -> str:
    """The question as the puck says it: a link is its site's name."""
    summary = str(ask.get("summary") or ask.get("tool") or "do something")
    summary = re.sub(r"https?://(?:www\.)?([^/\s]+)\S*", r"\1", summary)
    summary = summary.strip().rstrip(".")
    return f"Your agent wants to {summary[:1].lower()}{summary[1:]}. Shall I go ahead?"


@dataclass
class Waiting:
    """One turn in flight at one puck, for one person."""
    person: str
    agent: str
    thread: str
    job: asyncio.Future
    #: the question being put to the person at the puck, if any
    ask: dict | None = None
    #: questions already put (or answered), never asked twice
    asked: set[str] = field(default_factory=set)
    #: a "was that a yes or a no?" already said for the current question
    again: bool = False


async def outcome(waiting: Waiting, *, asks: Callable[[], Awaitable[list[dict]]],
                  within: float | None) -> tuple[str, Any]:
    """("answer", what Dvara said) | ("ask", a question) | ("slow", None):
    whichever comes first, looking for questions every ``POLL`` seconds."""
    loop = asyncio.get_running_loop()
    until = None if within is None else loop.time() + within
    while True:
        left = None if until is None else max(0.0, until - loop.time())
        await asyncio.wait({waiting.job}, timeout=POLL if left is None else min(POLL, left))
        if waiting.job.done():
            return "answer", waiting.job.result()
        try:
            listed = await asks()
        except Exception:              # noqa: BLE001 -- the answer is what matters
            listed = []
        for ask in listed:
            if ask.get("thread") == waiting.thread and ask.get("id") not in waiting.asked:
                waiting.asked.add(ask["id"])
                waiting.ask, waiting.again = ask, False
                return "ask", ask
        if until is not None and loop.time() >= until:
            return "slow", None
