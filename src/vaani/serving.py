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
import time

from vaani import asking, dvara, flac, hearing, runs, speaking, status
from vaani import config as settings
from vaani.clips import Clips, address_towards
from vaani.config import Config, ConfigError, Puck
from vaani.page import PageServer, page_token
from vaani.run import Said
from vaani.satellite import Satellite
from vaani.voices import Prints

log = logging.getLogger("vaani")

#: How often the pucks' quiet conversations are looked at.
FRESHEN_EVERY = 60.0


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
    prints = Prints(settings.path().parent / "voices")
    page = None
    if conf.page_port:
        page = PageServer(prints, page_token(), host=conf.page_host,
                          port=conf.page_port).start()
        log.info("its page at http://%s:%s/ (`vaani page` prints it with its key)",
                 "127.0.0.1" if conf.page_host in ("0.0.0.0", "::") else conf.page_host,
                 page.port)

    # each puck held or not, and why: what `vaani status` and Sarathi's
    # Check say, so "running" is never mistaken for "listening"
    held = {p.name: "not reached yet" for p in conf.pucks}

    def write() -> None:
        (status.state() / "serve.json").write_text(json.dumps({
            "pid": os.getpid(), "answers_at": f"http://{address}:{clips.port}/clip/",
            "page_port": page.port if page else 0,
            "pucks": [p.name for p in conf.pucks], "problems": held,
            "wake_words": {s.puck.name: s.wakes for s in satellites if s.wakes}}))

    satellites: list[Satellite] = []

    def told(name: str, problem: str) -> None:
        if held.get(name) != problem:
            held[name] = problem
            write()

    write()

    async def hear(wav: bytes) -> str:
        return await asyncio.to_thread(hearing.hear, wav, url=conf.hear_url,
                                       model=conf.hear_model, language=conf.language)

    def fresh(puck: Puck) -> tuple[Config, Puck]:
        """vaani.toml as it is now, so who a puck answers (person, agent,
        people, from Sarathi's Settings or `vaani puck`) holds from the next question.
        Where and how it connects stay as they started."""
        try:
            now = settings.load()
            return now, now.puck(puck.name)
        except ConfigError as exc:
            log.warning("vaani.toml can't be read now (%s); going on as before", exc)
            return conf, puck

    async def answer(puck: Puck, text: str, wav: bytes, said: Said) -> str:
        now, puck = fresh(puck)
        asked = await asyncio.to_thread(asking.whose, now, puck, text, wav, prints,
                                        said.follows)
        said.person, said.how = asked.person, asked.how
        said.tell()                    # whose it is, on the page before the answer
        if asked.sample:
            return asked.sample
        new = asking.starts_over(asked.text)
        got = await asyncio.to_thread(dvara.ask, "/new" if new else asked.text,
                                      person=asked.person, agent=puck.agent or now.agent,
                                      puck=puck.name, url=conf.dvara_url, token=token)
        if new and got.get("stop_reason") == "new":
            # Dvara's words are for a chat (/chats); the puck says it plainly
            return f"{asked.before} {asking.STARTED_OVER}".strip()
        return f"{asked.before} {got.get('text') or ''}".strip()

    async def speak(words: str) -> str:
        wav = await asyncio.to_thread(speaking.speak, words, host=conf.speak_host,
                                      port=conf.speak_port, voice=conf.voice)
        return clips.add(await asyncio.to_thread(flac.from_wav, wav))

    def record(puck: str, woke: str, said: Said, live: bool) -> dict:
        return {"puck": puck, "woke_by": woke, "ended": said.ended, "heard": said.heard,
                "person": said.person, "how": said.how, "answer": said.answer,
                "url": said.url, "error": said.error, "took": dict(said.took),
                "live": live}

    def begun(puck: str, woke: str, said: Said) -> None:
        # the record is made at the wake word and followed step by step
        rid = book.add(record(puck, woke, said, True))
        said.changed = lambda: book.update(rid, record(puck, woke, said, True))
        said.record_id = rid

    def done(puck: str, woke: str, said: Said) -> None:
        if said.record_id:
            book.update(said.record_id, record(puck, woke, said, False))
        else:
            book.add(record(puck, woke, said, False))

    async def freshen() -> None:
        """Once a minute: a wake word changed in vaani.toml is given to its
        puck (and kept for when it next connects), and each person's
        conversation at a puck starts over by itself after its
        ``fresh_after`` minutes of quiet -- done here, in the quiet, so the
        next question doesn't wait for it."""
        while True:
            await asyncio.sleep(FRESHEN_EVERY)
            for sat in satellites:
                _, current = fresh(sat.puck)
                if current.wake_word and current.wake_word != sat.puck.wake_word:
                    sat.puck = current
                    if sat.connected.is_set():
                        await sat.wake(current.wake_word)
            for puck in conf.pucks:
                now, current = fresh(puck)
                if not current.fresh_after:
                    continue
                for person, at in book.quiet(current.name).items():
                    if time.time() - at < current.fresh_after * 60:
                        continue
                    try:
                        got = await asyncio.to_thread(
                            dvara.ask, "/new", person=person,
                            agent=current.agent or now.agent, puck=current.name,
                            url=conf.dvara_url, token=token)
                    except dvara.DvaraError as exc:
                        log.warning("%s: couldn't start %s's conversation over: %s",
                                    current.name, person, exc)
                        continue
                    if got.get("stop_reason") == "new":
                        book.started_over(current.name, person)
                        log.info("%s: %s's conversation started over after %d min quiet",
                                 current.name, person, current.fresh_after)

    satellites += [Satellite(p, hear=hear, answer=answer, speak=speak, told=told, done=done,
                             begun=begun, noted=write) for p in conf.pucks]
    try:
        await asyncio.gather(freshen(), *(s.keep() for s in satellites))
    finally:
        clips.close()
        if page is not None:
            page.close()
        lock.close()
    return 0
