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
from vaani.waiting import (BY_PIN, PLAIN, Waiting, for_the_task, outcome,
                           spoken_question, yes_or_no)


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


def test_a_browsers_names_for_a_pages_parts_are_not_read_out():
    assert spoken_question({"summary": "click e14"}) == \
        "Your agent wants to click something on the page. Shall I go ahead?"
    assert "type in a box on the page" in spoken_question({"summary": "Type e3: Phoenix"})


def test_a_reply_is_told_by_timing_not_by_the_wake_word_the_puck_reports(monkeypatch):
    """The puck labels its listening-again run "Okay Nabu" too: a run
    starting just after the question was said is the reply, one minutes
    later a new question."""
    import time as clock

    from vaani import satellite
    from vaani.config import Puck

    class Quiet:
        def send_voice_assistant_event(self, *_a):
            pass

    sat = satellite.Satellite(Puck("kitchen", "h", "k", "owner"), hear=None,
                              answer=None, speak=None)
    sat.client = Quiet()
    starts = []
    monkeypatch.setattr(satellite, "Run", lambda **_k: type("R", (), {
        "said": __import__("vaani.run", fromlist=["Said"]).Said(), "stop": lambda s: None,
        "go": lambda s: asyncio.sleep(3600)})())

    async def go(following_at):
        sat.following = ("owner", following_at)
        sat.run = None
        await sat._start("", 0, None, "Okay Nabu")
        starts.append(sat.run.said.follows)
        sat._job.cancel()

    asyncio.run(go(clock.monotonic() - 2))                 # just said: the reply
    asyncio.run(go(clock.monotonic() - 600))               # ten minutes on: new
    assert starts == ["owner", ""]


def test_a_turn_still_going_is_shown_with_what_it_waits_on(monkeypatch):
    held, _ = run(None, [[{"id": "a9", "thread": "vaani:kitchen",
                           "summary": "open a browser"}]], 5, monkeypatch)
    held.question, held.since = "find me a flight", 100.0
    assert held.shown() == {"person": "mahen", "question": "find me a flight",
                            "since": 100.0, "asking": "open a browser"}


def test_yes_to_all_is_heard_and_a_plain_yes_is_not_it():
    assert for_the_task("Yes to all, one two three four")
    assert for_the_task("yes, the rest too")
    assert not for_the_task("yes")
    assert not for_the_task("yes please go ahead")


def test_yes_to_all_is_offered_only_where_dvara_offers_it():
    offered = spoken_question({"summary": "Fill e3", "for_turn": True}, BY_PIN)
    assert "yes to all" in offered and offered.endswith("Shall I?")
    assert "yes to all" not in spoken_question({"summary": "Fill e3"}, BY_PIN)
    assert "yes to all" in spoken_question({"summary": "x", "for_turn": True}, PLAIN)
