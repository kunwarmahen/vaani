"""``vaani serve``: every puck held, and the answers they fetch served.

The three outside steps -- Whisper, Dvara, Piper -- are plain blocking
requests, so each runs in a thread beside the loop that holds the pucks:
one kitchen question that takes a minute never stops the bedroom puck
from hearing its wake word.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

from vaani import asking, dvara, flac, hearing, runs, speaking, status
from vaani import config as settings
from vaani.clips import Clips, address_towards
from vaani.config import Config, ConfigError, Puck
from vaani.run import Said
from vaani.satellite import Satellite
from vaani.voices import Prints

log = logging.getLogger("vaani")


async def serve(conf: Config) -> int:
    if not conf.pucks:
        raise ConfigError("no pucks yet: `vaani init`")
    lock = status.hold()
    if lock is None:
        raise ConfigError("another `vaani serve` is running (a puck takes one listener)")
    token = conf.dvara_token()
    for puck in conf.pucks:
        puck.key()                     # a key that can't be read is said now, not at 3am
    address = conf.address or address_towards(conf.pucks[0].host)
    book = runs.Book()
    clips = Clips(host=conf.host, port=conf.port, address=address,
                  fetched=book.fetched).start()
    log.info("answers served at http://%s:%s/clip/", address, clips.port)
    # each puck held or not, and why: what `vaani status` and Sarathi's
    # Check say, so "running" is never mistaken for "listening"
    held = {p.name: "not reached yet" for p in conf.pucks}

    def write() -> None:
        (status.state() / "serve.json").write_text(json.dumps({
            "pid": os.getpid(), "answers_at": f"http://{address}:{clips.port}/clip/",
            "pucks": [p.name for p in conf.pucks], "problems": held}))

    def told(name: str, problem: str) -> None:
        if held.get(name) != problem:
            held[name] = problem
            write()

    write()

    async def hear(wav: bytes) -> str:
        return await asyncio.to_thread(hearing.hear, wav, url=conf.hear_url,
                                       model=conf.hear_model, language=conf.language)

    prints = Prints(settings.path().parent / "voices")

    def fresh(puck: Puck) -> tuple[Config, Puck]:
        """vaani.toml as it is now, so who a puck answers (person, agent,
        people, from the page or `vaani puck`) holds from the next question.
        Where and how it connects stay as they started."""
        try:
            now = settings.load()
            return now, now.puck(puck.name)
        except ConfigError as exc:
            log.warning("vaani.toml can't be read now (%s); going on as before", exc)
            return conf, puck

    async def answer(puck: Puck, text: str, wav: bytes, said: Said) -> str:
        now, puck = fresh(puck)
        asked = await asyncio.to_thread(asking.whose, now, puck, text, wav, prints)
        said.person, said.how = asked.person, asked.how
        if asked.sample:
            return asked.sample
        got = await asyncio.to_thread(dvara.ask, asked.text, person=asked.person,
                                      agent=puck.agent or now.agent, puck=puck.name,
                                      url=conf.dvara_url, token=token)
        said = str(got.get("text") or "")
        return f"{asked.before} {said}".strip()

    async def speak(words: str) -> str:
        wav = await asyncio.to_thread(speaking.speak, words, host=conf.speak_host,
                                      port=conf.speak_port, voice=conf.voice)
        return clips.add(await asyncio.to_thread(flac.from_wav, wav))

    def done(puck: str, woke: str, said: Said) -> None:
        book.add({"puck": puck, "woke_by": woke, "ended": said.ended, "heard": said.heard,
                  "person": said.person, "how": said.how, "answer": said.answer,
                  "url": said.url, "error": said.error, "took": said.took})

    satellites = [Satellite(p, hear=hear, answer=answer, speak=speak, told=told, done=done)
                  for p in conf.pucks]
    try:
        await asyncio.gather(*(s.keep() for s in satellites))
    finally:
        clips.close()
        lock.close()
    return 0
