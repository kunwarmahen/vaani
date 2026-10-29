"""What Vaani can tell a harness: is it here, is it listening, which pucks
-- ``vaani status --json``, the shape Setu and Samay set for this family
of programs -- and what it keeps, for a backup (``vaani keeps --json``).

THE SERVE HOLDS A LOCK, NOT A PID, as Samay's clock and Prahari's watch
do: ``vaani serve`` takes an exclusive ``flock`` on ``serve.lock`` in its
state folder for as long as it runs. The kernel lets go of it however
the holder dies, and every process that opens the file sees it, in
whichever container.

NO SECRET IS IN IT: a puck's key file is named and said to be readable
or not, never read out; Dvara's token isn't mentioned at all.

WHAT A BACKUP TAKES is Vaani's settings folder: vaani.toml, each puck's
key and Dvara's token (the backup is locked, and a restored house hears
again without fetching keys from the pucks). The state folder holds only
the running serve's record, which would name a process that isn't there.
"""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
from typing import Any

from vaani import config as settings
from vaani import version

FORMAT = "vaani.status.v1"
KEEPS = "vaani.keeps.v1"
LOCK_FILE = "serve.lock"


def state() -> Path:
    """$VAANI_STATE, else ~/.local/state/vaani."""
    named = os.environ.get("VAANI_STATE", "").strip()
    return Path(named).expanduser() if named else Path.home() / ".local/state/vaani"


def hold() -> Any:
    """The lock, held for this process's life; None when another serve has it."""
    folder = state()
    folder.mkdir(parents=True, exist_ok=True)
    held = open(folder / LOCK_FILE, "a")  # noqa: SIM115 -- held until exit
    try:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        held.close()
        return None
    return held


def serving() -> dict | None:
    """What ``vaani serve`` wrote when it started, if it still runs."""
    try:
        with open(state() / LOCK_FILE) as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError:
                pass
            else:
                return None
    except OSError:
        return None
    try:
        info = json.loads((state() / "serve.json").read_text())
    except (OSError, ValueError):
        info = {}
    return info if isinstance(info, dict) else {}


def report() -> dict[str, Any]:
    out: dict[str, Any] = {"format": FORMAT, "found": True, "version": version.version(),
                           "commit": version.commit(), "config": str(settings.path()),
                           "serving": False, "pucks": []}
    try:
        conf = settings.load()
    except settings.ConfigError as exc:
        out["problem"] = str(exc)
        return out
    running = serving()
    out["serving"] = running is not None
    if running:
        out["answers_at"] = running.get("answers_at")
    for puck in conf.pucks:
        key = Path(puck.key_file).expanduser()
        out["pucks"].append({"name": puck.name, "host": puck.host, "person": puck.person,
                             "agent": puck.agent or conf.agent,
                             "key": "readable" if key.is_file() and os.access(key, os.R_OK)
                             else "missing"})
    return out


def keeps() -> dict[str, Any]:
    folder = settings.path().parent
    return {"format": KEEPS, "keeps": [{
        "id": "settings", "path": str(folder.resolve()), "exists": folder.exists(),
        "what": "your pucks, their keys and Dvara's token", "leave_out": []}]}
