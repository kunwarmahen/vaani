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
from vaani.speaking import aloud
from vaani.waiting import LONG, Waiting, outcome, spoken_question, yes_or_no
from vaani.run import Said, asks_back
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

    # each puck's turn in flight: a long one, or one stopped on a question
    # (waiting.py); the puck's next words may be the answer to that question
    flying: dict[str, Waiting] = {}

    async def answer(puck: Puck, text: str, wav: bytes, said: Said) -> str:
        now, puck = fresh(puck)
        held = flying.get(puck.name)
        if held is not None and held.ask is not None and said.follows == held.person:
            said.person, said.how = held.person, "answering its question"
            said.tell()
            return await replied(puck, held, text, said)
        asked = await asyncio.to_thread(asking.whose, now, puck, text, wav, prints,
                                        said.follows)
        said.person, said.how = asked.person, asked.how
        said.tell()                    # whose it is, on the page before the answer
        if asked.sample:
            return asked.sample
        new = asking.starts_over(asked.text)
        job = asyncio.ensure_future(asyncio.to_thread(
            dvara.ask, "/new" if new else asked.text, person=asked.person,
            agent=puck.agent or now.agent, puck=puck.name, url=conf.dvara_url, token=token))
        held = Waiting(asked.person, puck.agent or now.agent, dvara.thread(puck.name), job)
        flying[puck.name] = held
        said_now = await follow(puck, held)
        if new and said_now is not None and said_now.get("stop_reason") == "new":
            # Dvara's words are for a chat (/chats); the puck says it plainly
            return f"{asked.before} {asking.STARTED_OVER}".strip()
        return f"{asked.before} {words_of(held, said_now)}".strip()

    def words_of(held: Waiting, got: dict | str | None) -> str:
        if isinstance(got, str):
            return got
        return str((got or {}).get("text") or "")

    async def follow(puck: Puck, held: Waiting) -> dict | str:
        """What to say now: the answer, a question to put, or that it's
        still working (and then the rest is said later, by itself)."""
        kind, got = await outcome(held, asks=lambda: asyncio.to_thread(
            dvara.asks, held.person, url=conf.dvara_url, token=token), within=LONG)
        if kind == "answer":
            landed(puck, held)
            return got
        if kind == "ask":
            log.info("%s: its agent asks %s: %s", puck.name, held.person,
                     got.get("summary", "")[:80])
            return spoken_question(got)
        asyncio.ensure_future(later(puck, held))
        return "This is taking a while. I'll tell you here when it's done."

    async def replied(puck: Puck, held: Waiting, text: str, said: Said) -> str:
        """The person's yes or no to the question the puck put."""
        verdict = yes_or_no(text)
        if verdict is None:
            if held.again:
                held.ask = None        # it stays on the phone, as it was
                asyncio.ensure_future(later(puck, held))
                return ("I didn't catch a yes or a no, so I've left it on your phone. "
                        "I'll tell you here when it's done.")
            held.again = True
            return "Sorry, was that a yes or a no?"
        ask, held.ask = held.ask, None
        try:
            landed = await asyncio.to_thread(dvara.answer, ask["id"], verdict,
                                             person=held.person, url=conf.dvara_url,
                                             token=token)
        except dvara.DvaraError as exc:
            log.warning("%s: couldn't give Dvara the answer: %s", puck.name, exc)
            landed = False
        log.info("%s: %s said %s at the puck%s", puck.name, held.person,
                 "yes" if verdict else "no", "" if landed else " (already answered)")
        before = "" if verdict else "Okay, I won't. "
        got = await follow(puck, held)
        return f"{before}{words_of(held, got)}".strip()

    async def later(puck: Puck, held: Waiting) -> None:
        """A long turn, finished at the puck by itself: each question it
        stops on put there (the puck listens after), and its answer said."""
        while True:
            try:
                kind, got = await outcome(held, asks=lambda: asyncio.to_thread(
                    dvara.asks, held.person, url=conf.dvara_url, token=token), within=None)
            except Exception as exc:   # noqa: BLE001 -- said, never lost
                landed(puck, held)
                await say_later(puck, held, "Sorry, I couldn't finish that just now.", "")
                log.warning("%s: a long turn failed: %s", puck.name, exc)
                return
            if kind == "ask":
                await say_later(puck, held, spoken_question(got), held.person)
                return                 # the reply run carries it on (replied)
            landed(puck, held)
            words = words_of(held, got)
            await say_later(puck, held, words,
                            held.person if asks_back(aloud(words)) else "")
            return

    def landed(puck: Puck, held: Waiting) -> None:
        """``held`` is over; a newer turn at the same puck stays."""
        if flying.get(puck.name) is held:
            del flying[puck.name]

    async def say_later(puck: Puck, held: Waiting, words: str, listen_for: str) -> None:
        sat = next((s for s in satellites if s.puck.name == puck.name), None)
        url = await speak(aloud(words) or "Done.")
        book.add({"puck": puck.name, "woke_by": "said by itself", "answer": words,
                  "person": held.person, "url": url, "ended": "announced"})
        if sat is None or not await sat.announce(url, words, listen_for=listen_for):
            log.warning("%s: couldn't say it at the puck: %s", puck.name, words[:80])

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
