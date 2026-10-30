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
from vaani.pins import SHORTEST, Pins, heard_digits
from vaani.voices import VoiceError
from vaani.waiting import (
    BY_PIN,
    BY_VOICE,
    LONG,
    PLAIN,
    STILL_WORKING,
    Waiting,
    for_the_task,
    judge,
    outcome,
    route,
    spoken_question,
    yes_or_no,
)
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
    pins = Pins(settings.path().parent / "pins")
    page = None
    if conf.page_port:
        page = PageServer(prints, page_token(), host=conf.page_host,
                          port=conf.page_port).start()
        log.info("its page at http://%s:%s/ (`vaani page` prints it with its key)",
                 "127.0.0.1" if conf.page_host in ("0.0.0.0", "::") else conf.page_host,
                 page.port)

    # each puck's turn in flight: a long one, or one stopped on a question
    # (waiting.py); the puck's next words may be the answer to that question
    flying: dict[str, Waiting] = {}
    # the questions already put at each puck: never put twice, whichever
    # turn finds them
    put: dict[str, set[str]] = {}

    # each puck held or not, and why: what `vaani status` and Sarathi's
    # Check say, so "running" is never mistaken for "listening"
    held = {p.name: "not reached yet" for p in conf.pucks}

    def write() -> None:
        (status.state() / "serve.json").write_text(json.dumps({
            "pid": os.getpid(), "answers_at": f"http://{address}:{clips.port}/clip/",
            "page_port": page.port if page else 0,
            "pucks": [p.name for p in conf.pucks], "problems": held,
            # turns still being worked on (a long one, or one on a question)
            "working": {name: w.shown() for name, w in flying.items()},
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
        agents, people, from Sarathi's Settings or `vaani puck`) holds from the next question.
        Where and how it connects stay as they started."""
        try:
            now = settings.load()
            return now, now.puck(puck.name)
        except ConfigError as exc:
            log.warning("vaani.toml can't be read now (%s); going on as before", exc)
            return conf, puck


    async def answer(puck: Puck, text: str, wav: bytes, said: Said) -> str:
        now, puck = fresh(puck)
        held = flying.get(puck.name)
        way = route(held, text, said.follows, len(heard_digits(text)) >= SHORTEST)
        if way == "answer":
            said.person, said.how = held.person, "answering its question"
            said.tell()
            return await replied(puck, held, text, wav, said)
        if way == "busy":
            said.person, said.how = held.person, "a yes while it works"
            said.tell()
            return STILL_WORKING
        asked = await asyncio.to_thread(asking.whose, now, puck, text, wav, prints,
                                        said.follows)
        said.person, said.how = asked.person, asked.how
        said.tell()                    # whose it is, on the page before the answer
        if asked.sample:
            return asked.sample
        new = asking.starts_over(asked.text)
        job = asyncio.ensure_future(asyncio.to_thread(
            dvara.ask, "/new" if new else asked.text, person=asked.person,
            agent=puck.agent_for(asked.person) or now.agent, puck=puck.name,
            url=conf.dvara_url, token=token))
        held = Waiting(asked.person, puck.agent_for(asked.person) or now.agent,
                       dvara.thread(puck.name), job,
                       asked=put.setdefault(puck.name, set()), question=asked.text,
                       since=time.time())
        flying[puck.name] = held
        write()
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
            write()
            words = question_for(puck, held, got)
            if held.ask is None:       # left on the phone: the rest comes later
                asyncio.ensure_future(later(puck, held))
            return words
        asyncio.ensure_future(later(puck, held))
        return "This is taking a while. I'll tell you here when it's done."

    def question_for(puck: Puck, held: Waiting, ask: dict) -> str:
        """The question as the puck puts it, by what must answer it: the
        asker's PIN for a call no standing yes covers, a longer yes in
        their voice when it's known, else a yes. One that can't be
        answered here (no PIN set, or locked) is left on the phone."""
        person = held.person
        if ask.get("always_ask"):
            if not pins.has(person) or pins.locked(person):
                held.ask = None
                write()
                why = ("that needs your PIN, and you haven't set one"
                       if not pins.has(person) else
                       "that needs your PIN, and it's locked here for now")
                return (spoken_question(ask, "").rstrip() + f" But {why}, so it's on "
                        "your phone. I'll tell you here when it's done.")
            return spoken_question(ask, BY_PIN)
        return spoken_question(ask, BY_VOICE if person in prints.known() else PLAIN)

    def voice_of(person: str, wav: bytes) -> str:
        """"them", "someone else", or "unsure": whether the reply is in the
        asker's voice, among every print kept. "unknown" when the asker
        has none, so there's nothing to check it against."""
        known = prints.known()
        if person not in known:
            return "unknown"
        try:
            found = prints.match(wav, tuple(known), threshold=conf.threshold,
                                 margin=conf.margin)
        except VoiceError:
            return "unsure"            # too short to tell: a plain "yes"
        log.info("a yes for %s: in the voice of %s (%.2f)", person,
                 found.person or "nobody sure", found.score)
        if found.person is None:
            return "unsure"
        return "them" if found.person == person else "someone else"

    def left_on_phone(puck: Puck, held: Waiting, why: str) -> str:
        held.ask = None
        write()
        asyncio.ensure_future(later(puck, held))
        return f"{why} I've left it on your phone, and I'll tell you here when it's done."

    async def replied(puck: Puck, held: Waiting, text: str, wav: bytes, said: Said) -> str:
        """The person's answer to the question the puck put: a no is a no;
        a yes counts in the asker's voice (when it's known), and a call no
        standing yes covers needs their PIN."""
        ask, person = held.ask, held.person
        weighty = bool(ask.get("always_ask"))
        verdict = yes_or_no(text)
        if weighty and verdict is not False:
            said.secret = True         # whatever was said, it isn't written down
        # the voice is checked only where it decides something: a yes
        voice = voice_of(person, wav) if verdict is not False else "unknown"
        came, words = judge(weighty=weighty, verdict=verdict, voice=voice,
                            locked=weighty and pins.locked(person),
                            pin_ok=lambda: pins.check(person, heard_digits(text)),
                            again=held.again, person=person)
        if came == "again":
            held.again = True
            return words
        if came == "phone":
            return left_on_phone(puck, held, words)
        verdict = came == "yes"
        # "yes to all": only where Dvara offered it, and only with a yes
        to_all = verdict and bool(ask.get("for_turn")) and for_the_task(text)
        held.ask = None
        write()
        try:
            landed = await asyncio.to_thread(dvara.answer, ask["id"], verdict,
                                             person=held.person, url=conf.dvara_url,
                                             token=token, for_turn=to_all)
        except dvara.DvaraError as exc:
            log.warning("%s: couldn't give Dvara the answer: %s", puck.name, exc)
            landed = False
        log.info("%s: %s said %s at the puck%s", puck.name, held.person,
                 "yes to all" if to_all else "yes" if verdict else "no",
                 "" if landed else " (already answered)")
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
                write()
                words = question_for(puck, held, got)
                await say_later(puck, held, words,
                                held.person if held.ask is not None else "",
                                how="asked while working")
                if held.ask is None:   # left on the phone: keep waiting here
                    continue
                return                 # the reply run carries it on (replied)
            landed(puck, held)
            words = words_of(held, got)
            await say_later(puck, held, words,
                            held.person if asks_back(aloud(words)) else "",
                            how=f"finished after {round((time.time() - held.since) / 60)} min")
            return

    def landed(puck: Puck, held: Waiting) -> None:
        """``held`` is over; a newer turn at the same puck stays."""
        if flying.get(puck.name) is held:
            del flying[puck.name]
            write()

    async def say_later(puck: Puck, held: Waiting, words: str, listen_for: str,
                        how: str = "") -> None:
        sat = next((s for s in satellites if s.puck.name == puck.name), None)
        url = await speak(aloud(words) or "Done.")
        # under the question it answers, so the history reads as one story
        book.add({"puck": puck.name, "woke_by": "said by itself", "answer": words,
                  "heard": held.question, "person": held.person, "how": how,
                  "url": url, "ended": "announced"})
        if sat is None or not await sat.announce(url, words, listen_for=listen_for):
            log.warning("%s: couldn't say it at the puck: %s", puck.name, words[:80])

    async def speak(words: str) -> str:
        wav = await asyncio.to_thread(speaking.speak, words, host=conf.speak_host,
                                      port=conf.speak_port, voice=conf.voice)
        return clips.add(await asyncio.to_thread(flac.from_wav, wav))

    record = runs.record

    def begun(puck: str, woke: str, said: Said) -> None:
        # while a PIN is asked for at this puck, whatever is said there is
        # treated as one: kept out of the record and the log from the start
        held = flying.get(puck)
        said.secret = bool(held is not None and held.ask and held.ask.get("always_ask"))
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
                            agent=current.agent_for(person) or now.agent,
                            puck=current.name,
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
                             begun=begun, noted=write, seconds_of=clips.seconds)
                   for p in conf.pucks]
    try:
        await asyncio.gather(freshen(), *(s.keep() for s in satellites))
    finally:
        clips.close()
        if page is not None:
            page.close()
        lock.close()
    return 0
