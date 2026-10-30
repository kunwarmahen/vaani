"""Answering: the words, to the person's agent behind Dvara.

VAANI KNOWS THE PUCK; DVARA KNOWS THE PEOPLE. Which agents a person may
use, their accounts, their allowance, their rules and their questions
waiting for a yes are all Dvara's, and stay there. Vaani says who is
asking and which agent, over Dvara's ``POST /message`` with its token
(a trusted caller naming a person, as Samay does), and reads the answer
out. Nothing a voice says is decided here.

ONE CONVERSATION PER PUCK PER PERSON. A turn runs under the thread
``vaani:<puck>``, beside Telegram's and the home page's: "and the one
before?" works at the kitchen puck, without continuing the chat on the
phone. ``came_by`` is ``vaani``, so Dvara's page says which way it came.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

#: How long a turn may take: a tool that reads mail, a question to the
#: person, a model. The puck doesn't wait this long (waiting.LONG): it
#: says it's still working, and says the answer when it comes.
TIMEOUT = 1800.0
KIND = "vaani"


class DvaraError(Exception):
    pass


def words(answer: dict) -> str:
    """What the puck says for an answer: its words, then -- when the agent
    kept something about the person on its own -- one short sentence
    saying so. Dvara sends what was kept beside the words (``kept``), with
    an id that is for a screen; read aloud, the line would be a number
    nobody can use. The facts and the Undo are in the chat."""
    text = str(answer.get("text") or "")
    kept = answer.get("kept") or []
    if not kept:
        return text
    said = ("I've also kept that about you." if len(kept) == 1
            else f"I've also kept {len(kept)} things about you.")
    return f"{text} {said}".strip()


def thread(puck: str) -> str:
    return f"{KIND}:{puck}"


def ask(text: str, *, person: str, agent: str, puck: str, url: str, token: str,
        timeout: float = TIMEOUT) -> dict:
    """The answer, as Dvara gives it: ``text`` and ``ok`` at least."""
    return _call(url, token, "/message", {"actor": person, "agent": agent,
                                          "thread": thread(puck), "text": text,
                                          "came_by": KIND}, timeout)


def asks(person: str, *, url: str, token: str) -> list[dict]:
    """The questions waiting on ``person`` (each with its ``thread``)."""
    return _call(url, token, f"/asks?actor={urllib.parse.quote(person)}", None,
                 10.0).get("asks", [])


def answer(ask_id: str, approve: bool, *, person: str, url: str, token: str,
           for_turn: bool = False) -> bool:
    """A waiting question answered as ``person``; False when it no longer
    waits (answered on the phone, timed out, the turn gone). ``for_turn``:
    the yes covers the rest of this task's after-reading questions."""
    try:
        _call(url, token, f"/asks/{urllib.parse.quote(ask_id)}",
              {"actor": person, "approve": approve is True,
               "for_turn": approve is True and for_turn}, 10.0)
    except DvaraError as exc:
        if "no question with that id" in str(exc):
            return False
        raise
    return True


def _call(url: str, token: str, path: str, body: dict | None, timeout: float) -> dict:
    request = urllib.request.Request(
        f"{url.rstrip('/')}{path}", json.dumps(body).encode() if body is not None else None,
        {"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as answer:
            return json.loads(answer.read())
    except urllib.error.HTTPError as exc:
        try:
            why = json.loads(exc.read()).get("detail") or exc.reason
        except ValueError:
            why = exc.reason
        raise DvaraError(f"Dvara said no: {why}") from None
    except (OSError, ValueError) as exc:
        raise DvaraError(f"Dvara at {url} didn't answer: {exc}") from None
