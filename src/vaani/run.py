"""One run: from the wake word to the answer out loud.

THE PUCK'S OWN STEPS, IN ITS OWN ORDER. A voice puck shows where a run
is by its light ring, and it learns that from events: run start, speech
to text start, the end of speech, the words, the intent (here: Dvara's
turn), text to speech, and the address to play. Home Assistant sends
the same events, so the puck behaves as it always has; what answers is
different.

    wake word -> RUN_START, STT_START
    sound     -> fed to EndOfSpeech until a pause
              -> STT_VAD_END, STT_END {text}          (Whisper)
              -> INTENT_START ... INTENT_END           (Dvara)
              -> TTS_START {text}, TTS_END {url}      (Piper; the puck fetches it)
              -> RUN_END

EVERY FAILURE IS SAID, OUT LOUD WHEN IT CAN BE. Nobody looks at a
kitchen puck's log. Silence after the wake word ends quietly (an error
event, so the ring stops). Whisper or Dvara not answering is spoken --
"I couldn't reach your agent" -- when Piper can still speak; when it
can't either, the error event is all there is.

The answer is given the sound as well as the words, so who is speaking
can be told from it (``voices.py``) before anyone is asked.

Written apart from the ESPHome connection (``satellite.py``), with the
hearing, answering and speaking passed in, so a run can be driven by a
test with no puck, no Whisper and no model.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from aioesphomeapi import VoiceAssistantEventType as Ev

from vaani.hearing import as_wav
from vaani.listening import EndOfSpeech
from vaani.speaking import aloud

log = logging.getLogger("vaani")

#: The longest a puck's sound may stop arriving before the run gives up.
STALL = 10.0

COULDNT_HEAR = "Sorry, I couldn't make out any words."
COULDNT_REACH = "Sorry, I couldn't reach your agent just now."


@dataclass
class Said:
    """What a run came to, for the log and for tests."""
    ended: str = ""
    heard: str = ""
    answer: str = ""
    url: str = ""
    error: str = ""
    #: whose question it was taken to be, and why (set by the answer step)
    person: str = ""
    how: str = ""
    #: seconds each step took: hear, agent, speak
    took: dict[str, float] = field(default_factory=dict)
    #: whose answer asked something back, when this run is the reply to it
    follows: str = ""
    #: this answer asked something back: the puck listens again, no wake word
    asked_back: bool = False
    #: called as each step ends, so a record can follow the run live
    changed: Callable[[], None] = field(default=lambda: None, repr=False, compare=False)
    record_id: str = ""

    def tell(self) -> None:
        try:
            self.changed()
        except Exception as exc:              # noqa: BLE001 -- a record never stops a run
            log.warning("couldn't record a step: %s", exc)


def asks_back(words: str) -> bool:
    """The answer's last sentence is a question: "Want it set lower?"."""
    return words.rstrip().rstrip("\"'”’)").endswith("?")


class Run:
    """One question at one puck. ``feed`` takes its sound; ``go`` does the rest."""

    def __init__(self, *, send: Callable[[Ev, dict | None], None],
                 hear: Callable[[bytes], Awaitable[str]],
                 answer: Callable[[str, bytes, Said], Awaitable[str]],
                 speak: Callable[[str], Awaitable[str]],
                 listen: EndOfSpeech | None = None, stall: float = STALL) -> None:
        self.send, self.hear, self.answer, self.speak = send, hear, answer, speak
        self.listen = listen or EndOfSpeech()
        self.stall = stall
        self._sound: asyncio.Queue[bytes | None] = asyncio.Queue()
        self.said = Said()

    def feed(self, chunk: bytes) -> None:
        self._sound.put_nowait(chunk)

    def stop(self) -> None:
        """The puck stopped streaming (its button, or it gave up)."""
        self._sound.put_nowait(None)

    async def go(self) -> Said:
        self.send(Ev.VOICE_ASSISTANT_RUN_START, {})
        self.send(Ev.VOICE_ASSISTANT_STT_START, {})
        try:
            ended = await self._until_quiet()
            self.said.ended = ended
            self.said.tell()
            self.send(Ev.VOICE_ASSISTANT_STT_VAD_END, {})
            if ended in ("silence", "stopped"):
                return self._fail("stt-no-text-recognized", "nothing was said")
            wav = as_wav(bytes(self.listen.heard))
            began = time.monotonic()
            try:
                heard = await self.hear(wav)
            except Exception as exc:              # noqa: BLE001 -- said, never lost
                return await self._say_failed("stt-provider-unavailable", exc,
                                              COULDNT_HEAR)
            self.said.heard = heard
            self._took("hear", began)
            self.said.tell()
            if not heard:
                self.send(Ev.VOICE_ASSISTANT_STT_END, {"text": ""})
                return await self._say_failed("stt-no-text-recognized", None, COULDNT_HEAR)
            self.send(Ev.VOICE_ASSISTANT_STT_END, {"text": heard})
            self.send(Ev.VOICE_ASSISTANT_INTENT_START, {})
            began = time.monotonic()
            try:
                said = await self.answer(heard, wav, self.said)
            except Exception as exc:              # noqa: BLE001
                self._took("agent", began)
                return await self._say_failed("intent-failed", exc, COULDNT_REACH)
            self._took("agent", began)
            self.said.answer = said
            # an answer that ends with a question is answered without the wake
            # word: the puck listens again once it has said it
            self.said.asked_back = asks_back(aloud(said))
            self.said.tell()
            self.send(Ev.VOICE_ASSISTANT_INTENT_END,
                      {"continue_conversation": "1" if self.said.asked_back else "0"})
            await self._speak(said)
            return self.said
        finally:
            self.send(Ev.VOICE_ASSISTANT_RUN_END, {})

    async def _until_quiet(self) -> str:
        while True:
            try:
                chunk = await asyncio.wait_for(self._sound.get(), self.stall)
            except TimeoutError:
                return "stopped"
            if chunk is None:
                return "stopped" if not self.listen.heard else "speech"
            ended = self.listen.feed(chunk)
            if ended:
                return ended

    async def _speak(self, text: str) -> None:
        words = aloud(text) or "Done."
        self.send(Ev.VOICE_ASSISTANT_TTS_START, {"text": words})
        began = time.monotonic()
        url = await self.speak(words)
        self._took("speak", began)
        self.said.url = url
        self.send(Ev.VOICE_ASSISTANT_TTS_END, {"url": url})
        self.said.tell()

    def _took(self, step: str, began: float) -> None:
        self.said.took[step] = round(time.monotonic() - began, 1)

    def _fail(self, code: str, message: str) -> Said:
        self.said.error = f"{code}: {message}"
        self.send(Ev.VOICE_ASSISTANT_ERROR, {"code": code, "message": message})
        return self.said

    async def _say_failed(self, code: str, exc: Exception | None, words: str) -> Said:
        self.said.error = f"{code}: {exc}" if exc else code
        log.warning("%s", self.said.error)
        try:
            self.send(Ev.VOICE_ASSISTANT_INTENT_END, {"continue_conversation": "0"})
            await self._speak(words)
        except Exception as again:                # noqa: BLE001 -- Piper is down too
            log.warning("couldn't say so either: %s", again)
            self.send(Ev.VOICE_ASSISTANT_ERROR, {"code": code, "message": str(exc or code)})
        return self.said
