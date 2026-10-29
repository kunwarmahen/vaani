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
import urllib.request

#: How long a turn may take: a tool that reads mail, then a model.
TIMEOUT = 300.0
KIND = "vaani"


class DvaraError(Exception):
    pass


def thread(puck: str) -> str:
    return f"{KIND}:{puck}"


def ask(text: str, *, person: str, agent: str, puck: str, url: str, token: str,
        timeout: float = TIMEOUT) -> dict:
    """The answer, as Dvara gives it: ``text`` and ``ok`` at least."""
    body = json.dumps({"actor": person, "agent": agent, "thread": thread(puck),
                       "text": text, "came_by": KIND}).encode()
    request = urllib.request.Request(f"{url.rstrip('/')}/message", body, {
        "Content-Type": "application/json", "Authorization": f"Bearer {token}"})
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
