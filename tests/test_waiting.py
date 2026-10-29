"""Bias: a yes nobody gave, and an answer nobody hears.

The puck now puts the agent's questions to the person and passes their
answer to Dvara. The failures worth a test are the ones that approve
something by accident -- "no" heard as yes, a mumble taken for consent,
a question put twice, one from another conversation put here -- and the
one this was built for: a turn that stops on a question, or simply takes
long, ending with nothing said at the puck.
"""

from __future__ import annotations

import asyncio

from vaani import waiting
from vaani.waiting import Waiting, outcome, spoken_question, yes_or_no


def test_only_a_clear_yes_is_a_yes():
    for said in ("Yes.", "yeah go ahead", "Sure", "OK, do it", "Yes please"):
        assert yes_or_no(said) is True, said
    for said in ("No.", "nope", "Don't", "no thanks", "cancel that", "Not now"):
        assert yes_or_no(said) is False, said
    for said in ("what flights are there", "hmm", "nothing", "maybe", ""):
        assert yes_or_no(said) is None, said


def test_the_question_says_a_sites_name_not_its_address():
    said = spoken_question({"summary": "Open https://www.google.com/travel/flights?q=PHX"})
    assert said == "Your agent wants to open google.com. Shall I go ahead?"


def run(job_after, asks_seq, within, monkeypatch):
    monkeypatch.setattr(waiting, "POLL", 0.01)

    async def go():
        loop = asyncio.get_running_loop()
        job = loop.create_future()
        if job_after is not None:
            loop.call_later(job_after, job.set_result, {"text": "Flights found."})
        held = Waiting("mahen", "minder", "vaani:kitchen", job)
        listed = iter(asks_seq)

        async def asks():
            return next(listed, [])
        first = await outcome(held, asks=asks, within=within)
        return held, first
    return asyncio.run(go())


def test_a_question_on_this_conversation_is_put_once(monkeypatch):
    elsewhere = {"id": "a1", "thread": "telegram:42", "summary": "send mail"}
    here = {"id": "a2", "thread": "vaani:kitchen", "summary": "open a browser"}
    held, (kind, got) = run(None, [[elsewhere], [elsewhere, here]], 5, monkeypatch)
    assert (kind, got["id"]) == ("ask", "a2") and held.ask is here
    assert held.asked == {"a2"}                      # never put twice


def test_an_answer_wins_and_a_long_turn_says_so(monkeypatch):
    _, (kind, got) = run(0.02, [], 5, monkeypatch)
    assert kind == "answer" and got["text"] == "Flights found."
    _, (kind, _) = run(None, [], 0.05, monkeypatch)
    assert kind == "slow"                            # said, then finished later
