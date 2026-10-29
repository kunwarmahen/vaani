"""A spoken PIN, for the things a plain yes shouldn't be enough for.

WHICH THINGS. A call no standing yes covers -- Yantra's ``always_ask``:
a purchase, a send, a phone's pay or send, any change made after the
agent read text the person didn't write -- is marked so on the question
Dvara lists. At the puck, such a question is answered with the asker's
PIN, said one digit at a time; anything else with a yes.

KEPT AS A HASH, PER PERSON. ``pins/NAME.json`` in Vaani's settings folder,
readable by you alone: a salt and scrypt of the digits, never the digits.
The digits are compared here and go nowhere else -- not to Dvara, not to
the log, not to the page (the run's record says "said a PIN").

FEW TRIES. Two at a time at the puck (then the question stays on the
phone), and five wrong in an hour lock that person's PIN at the puck for
the rest of the hour: four digits are ten thousand guesses, and a puck
in a kitchen is something anyone can talk to.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import time
from pathlib import Path

from vaani.config import NAME

DIGITS = {"zero": "0", "oh": "0", "o": "0", "one": "1", "two": "2", "to": "2",
          "too": "2", "three": "3", "four": "4", "for": "4", "five": "5", "six": "6",
          "seven": "7", "eight": "8", "ate": "8", "nine": "9"}
LONGEST, SHORTEST = 8, 4
#: Wrong PINs at the puck in an hour, before that person's PIN is locked there.
WRONG_IN_AN_HOUR = 5
HOUR = 3600.0


class PinError(Exception):
    pass


def heard_digits(text: str) -> str:
    """The digits in what Whisper heard: "1 2 3 4", "one two three four",
    "12 34" -> "1234". Words that aren't digits are left out."""
    out = []
    for word in re.findall(r"[a-z]+|\d+", text.lower()):
        if word.isdigit():
            out.append(word)
        elif word in DIGITS:
            out.append(DIGITS[word])
    return "".join(out)


def _hash(pin: str, salt: bytes) -> bytes:
    return hashlib.scrypt(pin.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)


class Pins:
    def __init__(self, folder: Path) -> None:
        self.folder = Path(folder)

    def _path(self, person: str) -> Path:
        if not NAME.match(person):
            raise PinError(f"{person!r} isn't a person's name, as Dvara has them")
        return self.folder / f"{person}.json"

    def _read(self, person: str) -> dict | None:
        try:
            got = json.loads(self._path(person).read_text())
        except (OSError, ValueError):
            return None
        return got if isinstance(got, dict) and got.get("hash") else None

    def _write(self, person: str, data: dict) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        os.chmod(self.folder, 0o700)
        path = self._path(person)
        spare = path.with_name(path.name + ".new")
        spare.unlink(missing_ok=True)
        with os.fdopen(os.open(spare, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as f:
            json.dump(data, f)
        spare.replace(path)

    def has(self, person: str) -> bool:
        return self._read(person) is not None

    def people(self) -> list[str]:
        if not self.folder.is_dir():
            return []
        return sorted(p.stem for p in self.folder.glob("*.json") if self._read(p.stem))

    def set(self, person: str, pin: str) -> None:
        if not re.fullmatch(rf"\d{{{SHORTEST},{LONGEST}}}", pin):
            raise PinError(f"a PIN is {SHORTEST} to {LONGEST} digits")
        if len(set(pin)) == 1 or pin in "0123456789" or pin in "9876543210":
            raise PinError("pick a PIN that isn't one digit over and over, or a run "
                           "like 1234")
        salt = secrets.token_bytes(16)
        self._write(person, {"salt": salt.hex(), "hash": _hash(pin, salt).hex(),
                             "set_at": time.time(), "wrong": []})

    def forget(self, person: str) -> bool:
        path = self._path(person)
        if not path.exists():
            return False
        path.unlink()
        return True

    def locked(self, person: str, now: float | None = None) -> bool:
        kept = self._read(person) or {}
        now = time.time() if now is None else now
        return len([t for t in kept.get("wrong", []) if now - t < HOUR]) >= WRONG_IN_AN_HOUR

    def check(self, person: str, said: str, now: float | None = None) -> bool:
        """``said`` (digits, as heard) is ``person``'s PIN. A wrong one is
        counted; a locked PIN is never checked, so it can't be guessed."""
        kept = self._read(person)
        if kept is None:
            raise PinError(f"{person} has no PIN yet")
        now = time.time() if now is None else now
        if self.locked(person, now):
            return False
        ok = bool(said) and hmac.compare_digest(
            _hash(said, bytes.fromhex(kept["salt"])), bytes.fromhex(kept["hash"]))
        recent = [t for t in kept.get("wrong", []) if now - t < HOUR]
        kept["wrong"] = [] if ok else [*recent, now]
        self._write(person, kept)
        return ok
