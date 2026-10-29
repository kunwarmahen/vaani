"""vaani.toml: which pucks, who each one is for, and where the voices are.

ONE FILE, READ THE WAY ``serve`` READS IT. Each puck is an ESPHome voice
device on the house's network: where it is, the file its key is kept in,
and whose it is. Hearing is a Whisper server's (any that speaks the
OpenAI transcription API), speaking a Piper server's (the Wyoming
protocol Home Assistant uses), and answering Dvara's -- each an address,
never a library pulled in here.

    [dvara]
    url = "http://127.0.0.1:8770"
    token_file = "~/.config/vaani/dvara.token"

    [hear]
    url = "http://127.0.0.1:11435"          # faster-whisper-server
    model = "Systran/faster-whisper-small"

    [speak]
    host = "127.0.0.1"                       # wyoming-piper
    port = 10200

    [serve]
    address = "192.168.1.20"                 # where a puck fetches an answer
    port = 8799

    [[puck]]
    name = "kitchen"
    host = "192.168.1.55"
    key_file = "~/.config/vaani/kitchen.key"
    person = "mahen"                         # who it answers as
    agent = "minder"

A KEY IS A FILE, NEVER A LINE HERE. The puck's key opens its microphone,
so it lives in a file of its own, readable by you alone, and this file
can be shown on a page or pasted in a bug report.

A HARNESS MAY SAY WHERE THINGS ARE. Sarathi starts Vaani beside Dvara,
Whisper and Piper and knows their addresses better than this file can:
``VAANI_DVARA_URL``, ``VAANI_HEAR_URL``, ``VAANI_SPEAK_HOST``,
``VAANI_SPEAK_PORT``, ``VAANI_ADDRESS`` and ``VAANI_PORT`` win over the
file's, and ``VAANI_DVARA_TOKEN`` over its token file. In a container,
``VAANI_LOCALHOST`` says what this computer is called from inside
(``host.containers.internal``), and every 127.0.0.1 or localhost in
the file is read as that. The pucks themselves are only ever the
file's.

UNKNOWN KEYS ARE ERRORS, as everywhere in this family: a misspelt
``persn`` must not quietly make a puck answer as nobody.
"""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path

#: A puck's or a person's name: a word, as Dvara's actors file has them.
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
#: ESPHome's own port for its API.
ESPHOME_PORT = 6053
#: Where answers wait for a puck to fetch them.
SERVE_PORT = 8799

KNOWN = {
    "dvara": {"url", "token_file", "agent"},
    "hear": {"url", "model", "language"},
    "speak": {"host", "port", "voice"},
    "serve": {"address", "host", "port"},
    "puck": {"name", "host", "port", "key_file", "person", "agent"},
}


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Puck:
    name: str
    host: str
    key_file: str
    person: str
    agent: str = ""
    port: int = ESPHOME_PORT

    def key(self) -> str:
        """The key, read when it's needed: a file only you can read."""
        path = Path(self.key_file).expanduser()
        try:
            text = path.read_text().strip()
        except OSError as exc:
            raise ConfigError(f"{self.name}: its key file {path} can't be read: {exc}") \
                from None
        if os.name == "posix" and path.stat().st_mode & 0o077:
            raise ConfigError(f"{self.name}: {path} can be read by others; "
                              f"chmod 600 {path}")
        return text


@dataclass(frozen=True)
class Config:
    dvara_url: str = "http://127.0.0.1:8770"
    dvara_token_file: str = "~/.config/vaani/dvara.token"
    agent: str = ""
    hear_url: str = "http://127.0.0.1:11435"
    hear_model: str = "Systran/faster-whisper-small"
    language: str = ""
    speak_host: str = "127.0.0.1"
    speak_port: int = 10200
    voice: str = ""
    address: str = ""
    host: str = "0.0.0.0"
    port: int = SERVE_PORT
    pucks: tuple[Puck, ...] = field(default_factory=tuple)

    def dvara_token(self) -> str:
        env = os.environ.get("VAANI_DVARA_TOKEN", "").strip()
        if env:
            return env
        path = Path(self.dvara_token_file).expanduser()
        try:
            return path.read_text().strip()
        except OSError:
            raise ConfigError(f"Dvara's token: put it in {path} (chmod 600), or "
                              "VAANI_DVARA_TOKEN") from None

    def puck(self, name: str) -> Puck:
        for p in self.pucks:
            if p.name == name:
                return p
        names = ", ".join(p.name for p in self.pucks) or "none yet"
        raise ConfigError(f"no puck called {name!r} (yours: {names})")


def path() -> Path:
    """$VAANI_CONFIG (a folder), else ~/.config/vaani/: vaani.toml."""
    folder = os.environ.get("VAANI_CONFIG", "").strip()
    return (Path(folder).expanduser() if folder
            else Path.home() / ".config" / "vaani") / "vaani.toml"


def load(where: Path | None = None) -> Config:
    where = where or path()
    try:
        text = where.read_text()
    except FileNotFoundError:
        raise ConfigError(f"no {where} yet: `vaani init` writes one") from None
    return from_env(parse(text, str(where)))


def from_env(conf: Config) -> Config:
    """The harness's addresses over the file's (Sarathi's, on its roads)."""
    env = os.environ
    changes: dict = {}
    for name, key in (("VAANI_DVARA_URL", "dvara_url"), ("VAANI_HEAR_URL", "hear_url"),
                      ("VAANI_SPEAK_HOST", "speak_host"), ("VAANI_ADDRESS", "address")):
        if env.get(name, "").strip():
            changes[key] = env[name].strip().rstrip("/")
    for name, key in (("VAANI_SPEAK_PORT", "speak_port"), ("VAANI_PORT", "port")):
        if env.get(name, "").strip():
            try:
                changes[key] = _port(int(env[name]), name)
            except ValueError:
                raise ConfigError(f"{name} is a port number, not {env[name]!r}") from None
    conf = replace(conf, **changes) if changes else conf
    inside = env.get("VAANI_LOCALHOST", "").strip()
    if inside:
        here = re.compile(r"(?<![\w.])(127\.0\.0\.1|localhost)(?![\w.])")
        conf = replace(conf, dvara_url=here.sub(inside, conf.dvara_url),
                       hear_url=here.sub(inside, conf.hear_url),
                       speak_host=here.sub(inside, conf.speak_host))
    return conf


def parse(text: str, where: str = "vaani.toml") -> Config:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{where}: {exc}") from None
    for table, value in data.items():
        if table not in KNOWN:
            raise ConfigError(f"{where}: unknown table [{table}]; known: "
                              f"{', '.join(sorted(KNOWN))}")
        rows = value if isinstance(value, list) else [value]
        for row in rows:
            wrong = sorted(set(row) - KNOWN[table])
            if wrong:
                raise ConfigError(f"{where}: [{table}] unknown key {', '.join(wrong)}; "
                                  f"known: {', '.join(sorted(KNOWN[table]))}")
    if not isinstance(data.get("puck", []), list):
        raise ConfigError(f"{where}: pucks are [[puck]] tables, one per puck")
    d, h, s, v = (data.get(k, {}) for k in ("dvara", "hear", "speak", "serve"))
    pucks = []
    for row in data.get("puck", []):
        name, person = str(row.get("name", "")), str(row.get("person", ""))
        for what, word in (("name", name), ("person", person)):
            if not NAME.match(word):
                raise ConfigError(f"{where}: a [[puck]] {what} is a word, like kitchen "
                                  f"or mahen; not {word!r}")
        if not row.get("host") or not row.get("key_file"):
            raise ConfigError(f"{where}: puck {name}: host and key_file, both")
        if name in {p.name for p in pucks}:
            raise ConfigError(f"{where}: two pucks called {name}")
        pucks.append(Puck(name=name, host=str(row["host"]), key_file=str(row["key_file"]),
                          person=person, agent=str(row.get("agent", "")),
                          port=_port(row.get("port", ESPHOME_PORT), where)))
    base = Config()
    return Config(
        dvara_url=str(d.get("url", base.dvara_url)).rstrip("/"),
        dvara_token_file=str(d.get("token_file", base.dvara_token_file)),
        agent=str(d.get("agent", "")),
        hear_url=str(h.get("url", base.hear_url)).rstrip("/"),
        hear_model=str(h.get("model", base.hear_model)),
        language=str(h.get("language", "")),
        speak_host=str(s.get("host", base.speak_host)),
        speak_port=_port(s.get("port", base.speak_port), where),
        voice=str(s.get("voice", "")),
        address=str(v.get("address", "")),
        host=str(v.get("host", base.host)),
        port=_port(v.get("port", base.port), where),
        pucks=tuple(pucks))


def _port(value, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 65535:
        raise ConfigError(f"{where}: a port is a number from 1 to 65535, not {value!r}")
    return value
