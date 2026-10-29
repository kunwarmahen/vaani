"""What the pucks were asked, kept short: ``vaani runs``, Sarathi's Vaani tab.

NOBODY READS A KITCHEN PUCK'S LOG. When a ring spins and goes out with
nothing said, the question is which step stopped: was it woken, what did
Whisper hear, whose question was it taken to be, how long did the agent
take, was there an answer, did the puck come for it. Each run is one
record of exactly those, so a silent puck says where it went silent.

WRITTEN AS IT HAPPENS. A run's record is made when the puck wakes
(``live``) and filled in as each step ends -- heard, whose, answered,
spoken -- so Vaani's page shows a question while the agent is still
working on it. A record left live by a serve that stopped is marked
``interrupted`` when the next one starts. Each write is the whole file,
fifty small records: nothing a run waits on.

KEPT IN THE STATE FOLDER, LAST FIFTY. ``runs.json``, rewritten whole as
a run ends and again when the puck fetches its answer (that comes after
the run's end). What was heard and answered is in it: the folder is
yours alone, as the conversation itself is in Dvara. Sound is never
kept.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from vaani import status

FORMAT = "vaani.runs.v1"
FILE = "runs.json"
KEEP = 50


def path() -> Path:
    return status.state() / FILE


def read(limit: int = KEEP) -> list[dict[str, Any]]:
    """The newest first."""
    try:
        got = json.loads(path().read_text())
    except (OSError, ValueError):
        return []
    return [r for r in got if isinstance(r, dict)][::-1][:limit] if isinstance(got, list) else []


class Book:
    """The running serve's record of runs; one writer, in the serve."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._runs: list[dict[str, Any]] = list(reversed(read()))
        self._next = 0
        for run in self._runs:          # a serve that stopped mid-run
            if run.pop("live", False):
                run["ended"] = run.get("ended") or "interrupted"

    def add(self, run: dict[str, Any]) -> str:
        """A new run's record; its id, for ``update``."""
        with self._lock:
            self._next += 1
            rid = f"{int(time.time())}-{self._next}"
            self._runs = [*self._runs, {"at": time.time(), **run, "id": rid}][-KEEP:]
            self._write()
            return rid

    def update(self, rid: str, run: dict[str, Any]) -> None:
        """The record ``rid``, with what the run knows now."""
        with self._lock:
            for kept in reversed(self._runs):
                if kept.get("id") == rid:
                    kept.update(run)
                    self._write()
                    return

    def quiet(self, puck: str) -> dict[str, float]:
        """{person: when they last asked something at ``puck``}, for each
        person whose conversation there hasn't started over since."""
        with self._lock:
            out: dict[str, float] = {}
            for run in self._runs:
                if run.get("puck") == puck and run.get("person") and run.get("heard"):
                    if run.get("live") or run.get("started_over"):
                        out.pop(run["person"], None)
                    else:
                        out[run["person"]] = float(run.get("at") or 0)
            return out

    def started_over(self, puck: str, person: str) -> None:
        """Said on ``person``'s newest run at ``puck``: their next question
        there is a new conversation (and a serve that starts again knows)."""
        with self._lock:
            for run in reversed(self._runs):
                if run.get("puck") == puck and run.get("person") == person:
                    run["started_over"] = True
                    self._write()
                    return

    def fetched(self, url: str, by: str) -> None:
        """The puck came for an answer: said on that answer's run."""
        with self._lock:
            for run in reversed(self._runs):
                if run.get("url") == url:
                    run["fetched"] = {"at": time.time(), "by": by}
                    self._write()
                    return

    def _write(self) -> None:
        target = path()
        target.parent.mkdir(parents=True, exist_ok=True)
        spare = target.with_name(FILE + ".new")
        with os.fdopen(os.open(spare, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as out:
            json.dump(self._runs, out)
        spare.replace(target)
