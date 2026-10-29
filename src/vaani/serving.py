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

from vaani import dvara, hearing, speaking, status
from vaani.clips import Clips, address_towards
from vaani.config import Config, ConfigError, Puck
from vaani.satellite import Satellite

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
    clips = Clips(host=conf.host, port=conf.port, address=address).start()
    log.info("answers served at http://%s:%s/clip/", address, clips.port)
    (status.state() / "serve.json").write_text(json.dumps({
        "pid": os.getpid(), "answers_at": f"http://{address}:{clips.port}/clip/",
        "pucks": [p.name for p in conf.pucks]}))

    async def hear(wav: bytes) -> str:
        return await asyncio.to_thread(hearing.hear, wav, url=conf.hear_url,
                                       model=conf.hear_model, language=conf.language)

    async def answer(puck: Puck, text: str) -> str:
        got = await asyncio.to_thread(dvara.ask, text, person=puck.person,
                                      agent=puck.agent or conf.agent, puck=puck.name,
                                      url=conf.dvara_url, token=token)
        return str(got.get("text") or "")

    async def speak(words: str) -> str:
        wav = await asyncio.to_thread(speaking.speak, words, host=conf.speak_host,
                                      port=conf.speak_port, voice=conf.voice)
        return clips.add(wav)

    satellites = [Satellite(p, hear=hear, answer=answer, speak=speak) for p in conf.pucks]
    try:
        await asyncio.gather(*(s.keep() for s in satellites))
    finally:
        clips.close()
        lock.close()
    return 0
