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

A PUCK LET GO HAS NO KEY. Deleting it from Home Assistant clears its key,
so it answers unencrypted and the old key is refused. Vaani then does
what Home Assistant does when it adopts one: makes a new key, saves it
in the puck's key file first, and gives it to the puck -- once, over the
plain connection, which is the only one such a puck offers (a newer one
that accepts the all-zero key gets it encrypted instead). From then on
the puck talks only with that key. A fresh key, not the old one, because
Home Assistant still has the old one.

KEPT UP. Wi-Fi drops and pucks restart. The connection is tried again
every few seconds for as long as Vaani runs, and each try is one line
in its log, never a crash.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import secrets
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

from aioesphomeapi import (
    ZERO_NOISE_PSK,
    APIClient,
    APIConnectionError,
    EncryptionPlaintextAPIError,
    VoiceAssistantAudioSettings,
)

from vaani.config import Puck
from vaani.run import Run, Said

log = logging.getLogger("vaani")

#: Seconds between tries when a puck can't be reached.
RETRY = 5.0
#: How long after an answer that asked something back the puck's run
#: without a wake word is taken as the reply: long enough for the answer
#: to be played first.
FOLLOW_WITHIN = 120.0


class Satellite:
    def __init__(self, puck: Puck, *, hear: Callable[[bytes], Awaitable[str]],
                 answer: Callable[[Puck, str, bytes], Awaitable[str]],
                 speak: Callable[[str], Awaitable[str]],
                 told: Callable[[str, str], None] = lambda _name, _problem: None,
                 done: Callable[[str, str, Said], None] = lambda _p, _w, _s: None) -> None:
        self.puck = puck
        self.told, self.done = told, done
        self.hear, self.answer, self.speak = hear, answer, speak
        self.client: APIClient | None = None
        self.run: Run | None = None
        self._job: asyncio.Task | None = None
        self.connected = asyncio.Event()
        #: (person, when) after an answer that asked something back: the
        #: puck's next run without a wake word is their reply
        self.following: tuple[str, float] | None = None

    async def keep(self) -> None:
        """Connect, listen, and connect again, until cancelled."""
        while True:
            lost = asyncio.Event()
            try:
                await self._connect(lost)
                await lost.wait()
                log.warning("%s: the connection dropped; trying again", self.puck.name)
                self.told(self.puck.name, "the connection dropped")
            except EncryptionPlaintextAPIError:
                try:
                    await self._give_key()
                    continue
                except (APIConnectionError, OSError) as exc:
                    self._cannot(f"it has no key and wouldn't take one: {exc}")
            except (APIConnectionError, OSError) as exc:
                # the library's own sentence ends with the reason; the rest
                # is its address list, said once already by the host
                self._cannot(str(exc).rsplit(": ", 1)[-1])
            finally:
                self.connected.clear()
            await asyncio.sleep(RETRY)

    def _cannot(self, why: str) -> None:
        log.warning("%s: can't reach it at %s: %s", self.puck.name, self.puck.host, why)
        self.told(self.puck.name, why)

    async def _give_key(self) -> None:
        """A puck with no key (let go by Home Assistant) is given a new one."""
        new = secrets.token_bytes(32)
        try:                           # encrypted, where the puck allows it
            client = APIClient(self.puck.host, self.puck.port, None,
                               noise_psk=ZERO_NOISE_PSK, client_info="vaani")
            await client.connect(login=True)
        except EncryptionPlaintextAPIError:
            client = APIClient(self.puck.host, self.puck.port, None, client_info="vaani")
            await client.connect(login=True)
        try:
            save_key(Path(self.puck.key_file).expanduser(), new)
            # the puck takes it as text, the way the key file holds it
            if not await client.noise_encryption_set_key(base64.b64encode(new)):
                raise APIConnectionError("the puck said no to the new key")
        finally:
            await client.disconnect()
        log.warning("%s: it had no key (let go by Home Assistant?); gave it a new one, "
                    "kept in %s", self.puck.name, self.puck.key_file)
        await asyncio.sleep(2)         # it changes over, then talks only with the key

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
        self.told(self.puck.name, "")
        log.info("%s: listening (%s, %s %s), answering as %s", self.puck.name,
                 info.name, info.project_name, info.project_version, self.puck.person)

    async def _start(self, conversation_id: str, flags: int,
                     audio: VoiceAssistantAudioSettings, wake_word: str | None) -> int | None:
        if self.run is not None:
            self.run.stop()
        run = Run(send=self._send, hear=self.hear,
                  answer=lambda text, wav, said: self.answer(self.puck, text, wav, said),
                  speak=self.speak)
        following, self.following = self.following, None
        if not wake_word and following and time.monotonic() - following[1] < FOLLOW_WITHIN:
            run.said.follows = following[0]
        self.run = run
        log.info("%s: %s", self.puck.name, f"listening again for {run.said.follows}'s reply"
                 if run.said.follows else f"woken{f' by {wake_word!r}' if wake_word else ''}")

        async def go() -> None:
            said = await run.go()
            if said.asked_back and said.person:
                self.following = (said.person, time.monotonic())
            self.done(self.puck.name, wake_word or ("a reply" if said.follows else ""), said)
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


def save_key(path: Path, key: bytes) -> None:
    """The key, as ``noise_psk`` takes it, in a file only you can read."""
    path.parent.mkdir(parents=True, exist_ok=True)
    spare = path.with_name(path.name + ".new")
    spare.unlink(missing_ok=True)
    with os.fdopen(os.open(spare, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as out:
        out.write(base64.b64encode(key).decode() + "\n")
    spare.replace(path)
