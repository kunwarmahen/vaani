"""Bias: a puck that hangs, talks to nobody, or goes quiet when something breaks.

A voice puck has no screen. The failures worth a test are the ones a
person in a kitchen can't see: a run that never ends because a
television kept talking, a wake word with nobody behind it sent to an
agent anyway, Whisper or Dvara down and the puck just stopping, events
out of the order the puck's light ring follows, and the words of an
answer read out with their asterisks and links, and a silent run that
leaves no trace of which step it stopped at.
"""

from __future__ import annotations

import array
import asyncio
import math

from aioesphomeapi import VoiceAssistantEventType as Ev

from vaani.listening import EndOfSpeech
from vaani.run import COULDNT_HEAR, COULDNT_REACH, Run
from vaani.speaking import REST, aloud

QUIET = bytes(960)                                         # 30 ms of silence


def tone(seconds: float, level: int = 6000) -> bytes:
    n = int(16000 * seconds)
    return array.array("h", (int(level * math.sin(i / 5)) for i in range(n))).tobytes()


def drive(sound: bytes, *, hear=None, answer=None, speak=None, follow_up=False,
          open_follow=False, **listen):
    events: list[tuple[str, dict]] = []
    asked: list[str] = []

    async def heard(_wav):
        return "what's the weather"

    async def answered(text, _wav, _said):
        asked.append(text)
        return "**Sunny**, see [the forecast](https://example.com)."

    async def spoken(words):
        return f"http://puck.test/{len(words)}"

    async def go():
        run = Run(send=lambda e, d: events.append((e.name.removeprefix("VOICE_ASSISTANT_"),
                                                   d or {})),
                  hear=hear or heard, answer=answer or answered, speak=speak or spoken,
                  listen=EndOfSpeech(**listen), stall=0.2, follow_up=follow_up)
        run.said.open_follow = open_follow
        task = asyncio.create_task(run.go())
        for at in range(0, len(sound), 960):
            run.feed(sound[at:at + 960])
            await asyncio.sleep(0)
        return await task

    said = asyncio.run(go())
    return said, events, asked


def kinds(events):
    return [k for k, _ in events]


def test_a_question_goes_in_the_order_the_puck_follows():
    said, events, asked = drive(QUIET * 10 + tone(1.0) + QUIET * 40)
    assert kinds(events) == ["RUN_START", "STT_START", "STT_VAD_END", "STT_END",
                             "INTENT_START", "INTENT_END", "TTS_START", "TTS_END", "RUN_END"]
    assert dict(events)["STT_END"] == {"text": "what's the weather"}
    assert asked == ["what's the weather"] and said.ended == "speech"
    assert dict(events)["TTS_START"] == {"text": "Sunny, see the forecast."}


def test_a_wake_word_with_nobody_behind_it_asks_nobody():
    said, events, asked = drive(QUIET * 200, wait=1.0)
    assert asked == [] and said.ended == "silence"
    assert kinds(events)[-2:] == ["ERROR", "RUN_END"]


def test_a_television_never_keeps_it_open():
    said, events, asked = drive(QUIET * 10 + tone(3.0), longest=2.0)
    assert said.ended == "long" and asked == ["what's the weather"]
    assert kinds(events)[-1] == "RUN_END"


def test_a_puck_that_stops_sending_ends_the_run():
    said, events, _ = drive(QUIET * 10)
    assert said.ended == "stopped" and kinds(events)[-2:] == ["ERROR", "RUN_END"]


def test_dvara_down_is_said_out_loud():
    async def down(_text, _wav, _said):
        raise OSError("connection refused")
    said, events, _ = drive(QUIET * 10 + tone(1.0) + QUIET * 40, answer=down)
    assert dict(events)["TTS_START"] == {"text": COULDNT_REACH}
    assert "intent-failed" in said.error and kinds(events)[-1] == "RUN_END"


def test_whisper_hearing_nothing_is_said_too():
    async def nothing(_wav):
        return ""
    _, events, asked = drive(QUIET * 10 + tone(1.0) + QUIET * 40, hear=nothing)
    assert asked == [] and dict(events)["TTS_START"] == {"text": COULDNT_HEAR}


def test_when_piper_is_down_as_well_the_ring_still_stops():
    async def down(_text, _wav, _said):
        raise OSError("no Dvara")

    async def mute(_words):
        raise OSError("no Piper")
    _, events, _ = drive(QUIET * 10 + tone(1.0) + QUIET * 40, answer=down, speak=mute)
    assert kinds(events)[-2:] == ["ERROR", "RUN_END"]


def test_what_is_read_is_what_should_be_heard():
    said = aloud("## Today\n- **Rain** at 3\n```\nrm -rf /\n```\n| a | b |\n|---|---|\n"
                 "More at https://x.example/y")
    assert "**" not in said and "rm -rf" not in said and "|" not in said
    assert "Rain at 3" in said and "a link" in said and "(some code, in the chat)" in said
    long = aloud(" ".join(f"Sentence {n} is here." for n in range(200)), longest=100)
    assert long.endswith(REST) and long[: -len(REST)].rstrip().endswith("here.")


def test_events_are_the_puck_s_own_kinds():
    assert Ev.VOICE_ASSISTANT_TTS_END.name == "VOICE_ASSISTANT_TTS_END"


def test_a_run_says_how_long_each_step_took_and_the_record_shows_the_fetch(tmp_path,
                                                                            monkeypatch):
    from vaani import runs
    said, _, _ = drive(QUIET * 10 + tone(1.0) + QUIET * 40)
    assert set(said.took) == {"hear", "agent", "speak"}
    monkeypatch.setenv("VAANI_STATE", str(tmp_path))
    book = runs.Book()
    book.add({"puck": "kitchen", "heard": said.heard, "url": said.url})
    book.add({"puck": "kitchen", "heard": "later", "url": "http://x/other.flac"})
    assert "fetched" not in runs.read()[1]                   # answered, never came for
    book.fetched(said.url, "192.168.1.55")
    newest, first = runs.read()
    assert newest["heard"] == "later" and first["fetched"]["by"] == "192.168.1.55"
    assert (tmp_path / runs.FILE).stat().st_mode & 0o777 == 0o600



def test_an_answer_that_asks_back_keeps_the_puck_listening():
    async def asks(text, _wav, _said):
        return "Done. It's at 79. Want it set to a different temperature?"
    said, events, _ = drive(QUIET * 10 + tone(1.0) + QUIET * 40, answer=asks)
    assert said.asked_back and dict(events)["INTENT_END"] == {"continue_conversation": "1"}
    said, events, _ = drive(QUIET * 10 + tone(1.0) + QUIET * 40)       # "Sunny, see ..."
    assert not said.asked_back
    assert dict(events)["INTENT_END"] == {"continue_conversation": "0"}


def test_a_puck_that_follows_up_listens_after_every_answer():
    said, events, _ = drive(QUIET * 10 + tone(1.0) + QUIET * 40, follow_up=True)
    assert not said.asked_back and said.listens
    assert dict(events)["INTENT_END"] == {"continue_conversation": "1"}


def test_nothing_heard_after_an_answer_ends_quietly():
    async def nothing(_wav):
        return ""
    said, events, asked = drive(QUIET * 10 + tone(1.0) + QUIET * 40, hear=nothing,
                                open_follow=True)
    assert asked == [] and "TTS_START" not in kinds(events)
    assert said.error.endswith("nothing more was asked")
    # the wake word's own run still says it couldn't make anything out
    said, events, _ = drive(QUIET * 10 + tone(1.0) + QUIET * 40, hear=nothing)
    assert dict(events)["TTS_START"] == {"text": COULDNT_HEAR}


def test_done_talking_is_ended_not_answered():
    async def closing(_text, _wav, said):
        said.closing = True
        return ""
    said, events, _ = drive(QUIET * 10 + tone(1.0) + QUIET * 40, answer=closing,
                            follow_up=True, open_follow=True)
    assert "TTS_START" not in kinds(events) and not said.listens
    assert dict(events)["INTENT_END"] == {"continue_conversation": "0"}


def test_a_question_with_words_after_it_is_still_asked():
    from vaani.run import asks_back
    # what the puck said at 20:29 on 2026-10-31 and then didn't listen after
    said = ("Two things before I set it:\n\n1. Is that the schedule you mean -- a "
            "one-time check at 20:39?\n2. What location should I use for \"outside "
            "temperature\" -- I don't have one saved for you yet.")
    assert asks_back(said)
    assert asks_back("Want it set lower?") and asks_back('He asked "why?" Then left.')
    assert asks_back("A long story. " * 60 + "Shall I go on?")  # past the cut too
    assert not asks_back("It's 61 degrees outside.")
    assert not asks_back("See https://example.com/a?b=c for more.")


def test_no_listening_after_it_says_the_rest_comes_later():
    async def later(_text, _wav, said):
        said.later = True
        return "Shall I? This is taking a while. I'll tell you here when it's done."
    said, events, _ = drive(QUIET * 10 + tone(1.0) + QUIET * 40, answer=later,
                            follow_up=True)
    assert not said.listens
    assert dict(events)["INTENT_END"] == {"continue_conversation": "0"}


def test_whispers_words_for_a_quiet_room_are_filler():
    from vaani.asking import filler
    for said in ("Thanks for watching!", "Thank you for watching.", "Please subscribe",
                 "you", "Thank you so much for watching!"):
        assert filler(said), said
    for said in ("thanks, what about tomorrow?", "you can use Boston", "Thank you."):
        assert not filler(said), said


def test_only_the_whole_of_what_was_said_is_done_talking():
    from vaani.asking import done_talking
    for said in ("Thanks.", "Thank you very much", "That's all", "no, thank you",
                 "Okay, bye", "nothing else", "Never mind", "I'm good"):
        assert done_talking(said), said
    for said in ("thanks, and what about tomorrow?", "stop the music",
                 "no I meant the porch light", "is that all the mail?"):
        assert not done_talking(said), said


def test_only_the_whole_of_what_was_said_starts_over():
    from vaani.asking import starts_over
    for said in ("New conversation.", "Start over", "let's start fresh, please",
                 "Okay, start a new conversation", "start again"):
        assert starts_over(said), said
    for said in ("Tell me about the new conversation with Ravi", "start the dishwasher",
                 "what's new"):
        assert not starts_over(said), said


def test_a_run_is_on_record_from_the_wake_word_and_a_cut_off_one_says_so(tmp_path,
                                                                          monkeypatch):
    from vaani import runs
    from vaani.run import Said
    monkeypatch.setenv("VAANI_STATE", str(tmp_path))
    book = runs.Book()
    said = Said()
    rid = book.add({"puck": "kitchen", "live": True})
    assert runs.read()[0]["live"] is True                  # on the page while it runs
    said.heard, said.person = "what day is it", "mahen"
    book.update(rid, {"heard": said.heard, "person": said.person, "live": True})
    assert runs.read()[0]["heard"] == "what day is it"
    again = runs.Book()                                    # the serve started again
    assert again._runs[-1]["ended"] == "interrupted" and "live" not in again._runs[-1]


def test_a_quiet_conversation_is_started_over_once(tmp_path, monkeypatch):
    from vaani import runs
    monkeypatch.setenv("VAANI_STATE", str(tmp_path))
    book = runs.Book()
    book.add({"puck": "kitchen", "person": "mahen", "heard": "what day"})
    book.add({"puck": "kitchen", "person": "asha", "heard": "any mail", "live": True})
    book.add({"puck": "study", "person": "mahen", "heard": "hi"})
    assert set(book.quiet("kitchen")) == {"mahen"}         # asha is mid-question
    book.started_over("kitchen", "mahen")
    assert book.quiet("kitchen") == {}
    # a restart remembers mahen's start-over; asha's cut-off question is quiet now
    assert set(runs.Book().quiet("kitchen")) == {"asha"}
    book.add({"puck": "kitchen", "person": "mahen", "heard": "and now?"})
    assert set(book.quiet("kitchen")) == {"mahen"}         # a new question, a new clock
