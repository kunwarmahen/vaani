"""A puck, held: its ESPHome connection, kept up, with a run per wake word.

THE ROAD THE PUCK ALREADY SPEAKS. A Home Assistant Voice puck runs
ESPHome, whose API is a small encrypted protocol on port 6053. Its own
firmware hears the wake word; then it asks whoever is subscribed to its
voice assistant to take a run, streams its microphone, and follows the
events it is sent (``run.py``). Vaani subscribes the way Home Assistant
does, so no new firmware is needed -- only the puck's key.

ONE LISTENER AT A TIME. A puck gives its voice assistant to one client.
While Home Assistant still holds it, Vaani connects and is ignored; the
puck is taken out of Home Assistant first (its ESPHome integration), and
then it is Vaani's.

KEPT UP. Wi-Fi drops and pucks restart. The connection is tried again
every few seconds for as long as Vaani runs, and each try is one line
in its log, never a crash.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from aioesphomeapi import APIClient, APIConnectionError, VoiceAssistantAudioSettings

from vaani.config import Puck
from vaani.run import Run

log = logging.getLogger("vaani")

#: Seconds between tries when a puck can't be reached.
RETRY = 5.0


class Satellite:
    def __init__(self, puck: Puck, *, hear: Callable[[bytes], Awaitable[str]],
                 answer: Callable[[Puck, str, bytes], Awaitable[str]],
                 speak: Callable[[str], Awaitable[str]]) -> None:
        self.puck = puck
        self.hear, self.answer, self.speak = hear, answer, speak
        self.client: APIClient | None = None
        self.run: Run | None = None
        self._job: asyncio.Task | None = None
        self.connected = asyncio.Event()

    async def keep(self) -> None:
        """Connect, listen, and connect again, until cancelled."""
        while True:
            lost = asyncio.Event()
            try:
                await self._connect(lost)
                await lost.wait()
                log.warning("%s: the connection dropped; trying again", self.puck.name)
            except (APIConnectionError, OSError) as exc:
                # the library's own sentence ends with the reason; the rest
                # is its address list, said once already by the host
                log.warning("%s: can't reach it at %s: %s", self.puck.name,
                            self.puck.host, str(exc).rsplit(": ", 1)[-1])
            finally:
                self.connected.clear()
            await asyncio.sleep(RETRY)

    async def _connect(self, lost: asyncio.Event) -> None:
        client = APIClient(self.puck.host, self.puck.port, None,
                           noise_psk=self.puck.key(), client_info="vaani")

        async def on_stop(_expected: bool) -> None:
            lost.set()

        await client.connect(on_stop=on_stop, login=True)
        info = await client.device_info()
        client.subscribe_voice_assistant(handle_start=self._start, handle_stop=self._stop,
                                         handle_audio=self._audio)
        self.client = client
        self.connected.set()
        log.info("%s: listening (%s, %s %s), answering as %s", self.puck.name,
                 info.name, info.project_name, info.project_version, self.puck.person)

    async def _start(self, conversation_id: str, flags: int,
                     audio: VoiceAssistantAudioSettings, wake_word: str | None) -> int | None:
        if self.run is not None:
            self.run.stop()
        run = Run(send=self._send, hear=self.hear,
                  answer=lambda text, wav: self.answer(self.puck, text, wav),
                  speak=self.speak)
        self.run = run
        log.info("%s: woken%s", self.puck.name, f" by {wake_word!r}" if wake_word else "")

        async def go() -> None:
            said = await run.go()
            log.info("%s: %s -- heard %r, answered %r%s", self.puck.name, said.ended,
                     said.heard, said.answer[:80], f" ({said.error})" if said.error else "")
            if self.run is run:
                self.run = None

        self._job = asyncio.create_task(go())
        return 0                       # the sound comes over this connection

    async def _audio(self, data: bytes, _ended: bytes | None = None) -> None:
        if self.run is not None:
            self.run.feed(data)

    async def _stop(self, _abort: bool) -> None:
        if self.run is not None:
            self.run.stop()

    def _send(self, event, data: dict | None) -> None:
        if self.client is not None:
            self.client.send_voice_assistant_event(event, {k: str(v) for k, v in
                                                           (data or {}).items()})
