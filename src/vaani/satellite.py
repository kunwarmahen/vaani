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

THE WAKE WORD IS THE PUCK'S, CHOSEN HERE. The puck's firmware carries a
few (Okay Nabu, Hey Jarvis, Hey Mycroft) and listens for one. Which one
is set by the client that holds its voice -- Home Assistant did -- and
only that client is even told which it has. So once subscribed, Vaani
reads them, and switches to the puck's ``wake_word`` when that is set
and isn't the one listening; again within a minute of it being changed.

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
#: Seconds after the puck has finished saying something that asked back
#: within which its next run is the reply. The puck labels that run with
#: its wake word all the same, so timing is what tells a reply from a
#: new question.
FOLLOW_WITHIN = 15.0
#: The longest an announcement may take to be played.
ANNOUNCE_WITHIN = 120.0


class Satellite:
    def __init__(self, puck: Puck, *, hear: Callable[[bytes], Awaitable[str]],
                 answer: Callable[[Puck, str, bytes], Awaitable[str]],
                 speak: Callable[[str], Awaitable[str]],
                 told: Callable[[str, str], None] = lambda _name, _problem: None,
                 done: Callable[[str, str, Said], None] = lambda _p, _w, _s: None,
                 begun: Callable[[str, str, Said], None] = lambda _p, _w, _s: None,
                 noted: Callable[[], None] = lambda: None,
                 seconds_of: Callable[[str], float] = lambda _url: 0.0) -> None:
        self.seconds_of = seconds_of
        self.puck = puck
        self.noted = noted
        #: {"offers": [names], "on": [names]}: the puck's wake words, as it says
        self.wakes: dict[str, list[str]] = {}
        self.told, self.done, self.begun = told, done, begun
        self.hear, self.answer, self.speak = hear, answer, speak
        self.client: APIClient | None = None
        self.run: Run | None = None
        self._job: asyncio.Task | None = None
        self.connected = asyncio.Event()
        #: (person, when the puck will have finished saying it) after words
        #: that asked something back: a run starting soon after is the reply
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
        await self.wake(self.puck.wake_word)
        self.told(self.puck.name, "")
        log.info("%s: listening (%s, %s %s), answering as %s", self.puck.name,
                 info.name, info.project_name, info.project_version, self.puck.person)

    async def wake(self, wanted: str) -> None:
        """The puck's wake words read, and ``wanted`` (an id or a name it
        offers) made the one it listens for. A word it doesn't have is
        said in the log, and the puck is left as it is."""
        client = self.client
        if client is None:
            return
        try:
            got = await client.get_voice_assistant_configuration(10)
            offers = {w.id: w.wake_word for w in got.available_wake_words}
            on = list(got.active_wake_words)
            if wanted:
                pick = next((i for i, n in offers.items()
                             if wanted.lower() in (i.lower(), n.lower())), None)
                if pick is None:
                    log.warning("%s: it has no wake word %r (it has: %s)", self.puck.name,
                                wanted, ", ".join(offers.values()) or "none it says")
                elif on != [pick]:
                    await client.set_voice_assistant_configuration([pick])
                    log.info("%s: wake word now %s", self.puck.name, offers[pick])
                    on = [pick]
        except (APIConnectionError, OSError, TimeoutError) as exc:
            log.warning("%s: couldn't read its wake words: %s", self.puck.name, exc)
            return
        self.wakes = {"offers": list(offers.values()),
                      "on": [offers.get(i, i) for i in on]}
        self.noted()

    async def announce(self, url: str, words: str, *, listen_for: str = "") -> bool:
        """``url`` played by the puck, not as an answer to anything: what a
        long turn came to. ``listen_for``: a person, when the words ask
        them something -- the puck listens afterwards, no wake word, and
        that run is their reply. False when the puck can't be reached."""
        client = self.client
        if client is None or not self.connected.is_set():
            return False
        if listen_for:                 # until it's said, and then some
            self.following = (listen_for, time.monotonic() + ANNOUNCE_WITHIN)
        try:
            await client.send_voice_assistant_announcement_await_response(
                url, ANNOUNCE_WITHIN, text=words, start_conversation=bool(listen_for))
        except (APIConnectionError, OSError, TimeoutError) as exc:
            log.warning("%s: couldn't say it: %s", self.puck.name, exc)
            return False
        if listen_for and self.following and self.following[0] == listen_for:
            self.following = (listen_for, time.monotonic())    # said: it listens now
        return True

    async def _start(self, conversation_id: str, flags: int,
                     audio: VoiceAssistantAudioSettings, wake_word: str | None) -> int | None:
        if self.run is not None:
            self.run.stop()
        run = Run(send=self._send, hear=self.hear,
                  answer=lambda text, wav, said: self.answer(self.puck, text, wav, said),
                  speak=self.speak)
        following, self.following = self.following, None
        if following and time.monotonic() - following[1] < FOLLOW_WITHIN:
            run.said.follows = following[0]
        self.run = run
        woke = "a reply" if run.said.follows else (wake_word or "")
        log.info("%s: %s", self.puck.name, f"listening again for {run.said.follows}'s reply"
                 if run.said.follows else f"woken{f' by {wake_word!r}' if wake_word else ''}")
        self.begun(self.puck.name, woke, run.said)

        async def go() -> None:
            said = await run.go()
            if said.asked_back and said.person:
                # the puck starts saying it now; it listens once it's done
                self.following = (said.person,
                                  time.monotonic() + self.seconds_of(said.url))
            self.done(self.puck.name, woke, said)
            log.info("%s: %s -- heard %r, answered %r%s", self.puck.name, said.ended,
                     "(a PIN)" if said.secret else said.heard, said.answer[:80],
                     f" ({said.error})" if said.error else "")
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
