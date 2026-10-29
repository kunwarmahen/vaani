"""Bias: a puck that hangs, talks to nobody, or goes quiet when something breaks.

A voice puck has no screen. The failures worth a test are the ones a
person in a kitchen can't see: a run that never ends because a
television kept talking, a wake word with nobody behind it sent to an
agent anyway, Whisper or Dvara down and the puck just stopping, events
out of the order the puck's light ring follows, and the words of an
answer read out with their asterisks and links.
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


def drive(sound: bytes, *, hear=None, answer=None, speak=None, **listen):
    events: list[tuple[str, dict]] = []
    asked: list[str] = []

    async def heard(_wav):
        return "what's the weather"

    async def answered(text, _wav):
        asked.append(text)
        return "**Sunny**, see [the forecast](https://example.com)."

    async def spoken(words):
        return f"http://puck.test/{len(words)}"

    async def go():
        run = Run(send=lambda e, d: events.append((e.name.removeprefix("VOICE_ASSISTANT_"),
                                                   d or {})),
                  hear=hear or heard, answer=answer or answered, speak=speak or spoken,
                  listen=EndOfSpeech(**listen), stall=0.2)
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
    async def down(_text, _wav):
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
    async def down(_text, _wav):
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
