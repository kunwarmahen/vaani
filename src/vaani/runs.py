"""What the pucks were asked, kept short: ``vaani runs``, Sarathi's Vaani tab.

NOBODY READS A KITCHEN PUCK'S LOG. When a ring spins and goes out with
nothing said, the question is which step stopped: was it woken, what did
Whisper hear, whose question was it taken to be, how long did the agent
take, was there an answer, did the puck come for it. Each run is one
record of exactly those, so a silent puck says where it went silent.

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

    def add(self, run: dict[str, Any]) -> None:
        with self._lock:
            self._runs = [*self._runs, {"at": time.time(), **run}][-KEEP:]
            self._write()

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
