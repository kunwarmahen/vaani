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


#: "Yes to all": the rest of this task's questions too, where Dvara offers
#: it (a question asked only because the agent read something you didn't
#: write). Said with the yes, or with the PIN.
ALL = re.compile(r"\b(?:to all|for all|all of (?:it|them)|the rest|everything)\b")


def for_the_task(text: str) -> bool:
    """The reply asked for the rest of this task too: "yes to all"."""
    words = re.sub(r"[^\w' ]", " ", text.lower()).split()
    return bool(ALL.search(" ".join(words)))


def yes_or_no(text: str) -> bool | None:
    """True for a clear yes, False for a clear no, None otherwise."""
    words = re.sub(r"[^\w' ]", " ", text.lower()).split()
    said = " ".join(words)
    if NO.match(said):
        return False
    if YES.match(said):
        return True
    return None


#: How the puck asks, by what the answer must be. Each ends with a
#: question mark: that is what keeps the puck listening (run.asks_back).
PLAIN = "Shall I go ahead?"
BY_VOICE = "To say yes, say: yes, go ahead. Shall I?"
BY_PIN = "That needs your PIN, said one digit at a time. Shall I?"
#: Said to a yes or a no heard while a turn works with no question put:
#: it answers nothing, and it starts nothing either.
STILL_WORKING = ("I'm still working on that. If I need a yes, I'll ask you here.")
#: Added before the end of a question Dvara lets one yes cover the rest of.
TO_ALL = "Say yes to all to stop asking for the rest of this."


#: How often a watch looks, as Prahari writes it ("6h"), said.
_STEP = {"m": "minute", "h": "hour", "d": "day"}


def _every(step: str) -> str:
    match = re.fullmatch(r"(\d+)\s*([mhd])", step.strip())
    if not match:
        return f"every {step}"
    n, unit = int(match.group(1)), _STEP[match.group(2)]
    return f"every {unit}" if n == 1 else f"every {n} {unit}s"


def watch_words(card: str) -> str | None:
    """A watch's card (Yantra's ``New watch:`` form), said in a sentence:
    its name, the site it looks at and how often, and when it tells you.
    None for anything else.

    A CARD IS FOR READING; A SENTENCE IS FOR HEARING. The card is a form
    of several lines -- the exact call, its JSON, what a yes allows -- and
    read out it is noise: "new watch, no name, every 6h, browser open,
    curly brace url...". At a puck the person can't see the card, so what
    they say yes to is this sentence, and the card stays on their phone."""
    lines = [line.strip() for line in card.splitlines()]
    if not lines or not lines[0].startswith("New watch:"):
        return None
    name = lines[0].removeprefix("New watch:").strip()

    def after(head: str) -> str:
        return lines[lines.index(head) + 1] if head in lines[:-1] else ""

    looks = after("What it looks at, with no model")
    step, _, call = looks.partition(": ")
    site = re.search(r"https?://(?:www\.)?([^/\s\"?#]+)", call)
    where = site.group(1) if site else "something"
    heard = after("What it listens for")
    when = after("Tells you when")
    said = "set up a watch" + (f" called {name}" if name and name != "(no name)" else "")
    if heard:
        said += ": it listens for what's sent to it"
    elif step.startswith("every "):
        said += f": it looks at {where} {_every(step.removeprefix('every '))}"
    if when:
        said += f", and tells you when {when.removeprefix('now:').strip()}"
    raw = card.splitlines()
    if "How long" in raw:
        span = []
        for line in raw[raw.index("How long") + 1:]:
            if not line.startswith("  "):
                break
            span.append(line.strip().replace(", then it ends by itself", ""))
        if span:
            said += ". It runs " + ", and ".join(span)
    return said


def spoken_question(ask: dict, how: str = PLAIN) -> str:
    """The question as the puck says it: a link is its site's name; ``how``
    says what answers it (a yes, a longer yes in the asker's voice, a PIN)."""
    summary = str(ask.get("summary") or ask.get("tool") or "do something")
    summary = watch_words(summary) or summary
    summary = re.sub(r"https?://(?:www\.)?([^/\s]+)\S*", r"\1", summary)
    # a browser names a page's parts e14, e7: said, that's noise
    summary = re.sub(r"\b(click|press|tap|select|check)\s+e\d+\b", r"\1 something on the page",
                     summary, flags=re.I)
    summary = re.sub(r"\b(fill|type)\s+e\d+\b", r"\1 in a box on the page", summary,
                     flags=re.I)
    summary = re.sub(r"\be\d+\b", "something on the page", summary)
    summary = summary.strip().rstrip(".")
    if ask.get("for_turn") and how:
        # before the question it ends on, which keeps the puck listening
        head, sep, last = how.rpartition(". ")
        how = f"{head}. {TO_ALL} {last}" if sep else f"{TO_ALL} {how}"
    return f"Your agent wants to {summary[:1].lower()}{summary[1:]}. {how}"


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
    #: what was asked, and when: what the page shows while it's worked on
    question: str = ""
    since: float = 0.0

    def shown(self) -> dict:
        """The page's line for it: whose, what, since when, waiting on what."""
        return {"person": self.person, "question": self.question, "since": self.since,
                "asking": str((self.ask or {}).get("summary") or "")}


def route(held: Waiting | None, text: str, follows: str = "",
          digits: bool = False) -> str:
    """What the puck's next words are: "answer" (to the question it put),
    "busy" (a yes or a no while a turn works, with no question put), or
    "new" (a question of their own).

    A YES WITH NOTHING TO ANSWER IS NOT A NEW TURN. A turn still working
    may ask next; sent as a turn of its own on the same conversation,
    "yes, yes, yes" does again what the first turn is doing -- it made a
    second watch on the same flights page. So it is said and dropped."""
    if held is None:
        return "new"
    if held.ask is not None and (follows == held.person or yes_or_no(text) is not None
                                 or (held.ask.get("always_ask") and digits)):
        return "answer"
    if not held.job.done() and yes_or_no(text) is not None:
        return "busy"
    return "new"


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


def judge(*, weighty: bool, verdict: bool | None, voice: str, locked: bool,
          pin_ok: Callable[[], bool], again: bool, person: str) -> tuple[str, str]:
    """What a reply to the puck's question comes to:

        ("yes", "") | ("no", "") | ("again", words) | ("phone", why)

    ``weighty``: a call no standing yes covers -- the asker's PIN answers
    it. ``verdict``: the words' yes or no (None: neither). ``voice``:
    "them", "someone else", "unsure" or "unknown" (no print to check).
    ``pin_ok`` is asked only when the PIN is what decides, since asking it
    counts a wrong one. ``again``: the puck has already asked once more.

    A NO IS ALWAYS A NO, whoever says it: refusing is never the risk."""
    if verdict is False:
        return "no", ""
    if weighty:
        if voice == "someone else":
            return "phone", f"That didn't sound like {person}."
        if locked:
            return "phone", "Your PIN is locked here for now."
        if pin_ok():
            return "yes", ""
        if again:
            return "phone", "That PIN wasn't right."
        return "again", "That's not right. Say your PIN once more, one digit at a time?"
    if verdict is None:
        if again:
            return "phone", "I didn't catch a yes or a no."
        return "again", "Sorry, was that a yes or a no?"
    if voice == "someone else":
        return "phone", f"Only {person} can say yes to that."
    if voice == "unsure":
        if again:
            return "phone", f"I couldn't tell that was {person}."
        return "again", f"I couldn't tell that was you, {person}. Say: yes, go ahead?"
    return "yes", ""
