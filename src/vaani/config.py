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

    [page]                                   # Vaani's own page (port 0: none)
    host = "127.0.0.1"
    port = 8797

    [[puck]]
    name = "kitchen"
    host = "192.168.1.55"
    key_file = "~/.config/vaani/kitchen.key"
    person = "mahen"                         # who it answers as (when unsure)
    agent = "minder"
    people = ["mahen", "asha"]               # voices it may tell apart (optional)
    agents = { asha = "helper" }             # someone's own agent here (optional)
    fresh_after = 30                         # minutes quiet, then a new conversation (0: never)
    wake_word = "hey_jarvis"                 # one the puck has; unset: as the puck is

    [voices]                                 # telling voices apart (optional)
    threshold = 0.6
    margin = 0.15

A KEY IS A FILE, NEVER A LINE HERE. The puck's key opens its microphone,
so it lives in a file of its own, readable by you alone, and this file
can be shown on a page or pasted in a bug report.

A HARNESS MAY SAY WHERE THINGS ARE. Sarathi starts Vaani beside Dvara,
Whisper and Piper and knows their addresses better than this file can:
``VAANI_DVARA_URL``, ``VAANI_HEAR_URL``, ``VAANI_SPEAK_HOST``,
``VAANI_SPEAK_PORT``, ``VAANI_ADDRESS``, ``VAANI_PORT``,
``VAANI_PAGE_HOST`` and ``VAANI_PAGE_PORT`` win over the file's, and
``VAANI_DVARA_TOKEN`` over its token file. In a container,
``VAANI_LOCALHOST`` says what this computer is called from inside
(``host.containers.internal``), and every 127.0.0.1 or localhost in
the file is read as that. The pucks themselves are only ever the
file's.

EACH PERSON THEIR OWN AGENT. A puck in a shared room answers whoever
it heard, and ``agents`` names the agent each of them gets there: Asha
asks her own helper while Mahen's questions go to minder. Someone not
named gets the puck's ``agent``, then ``[dvara] agent``. Whether that
person may use that agent is still Dvara's to say. A name in ``agents``
that isn't the puck's ``person`` or in its ``people`` is refused: the
puck could never hear them, so the line is a mistake.

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
#: Vaani's own page: each puck, its last questions, the voices.
PAGE_PORT = 8797
#: Minutes quiet before a puck's conversation starts over by itself.
FRESH_AFTER = 30

KNOWN = {
    "dvara": {"url", "token_file", "agent"},
    "hear": {"url", "model", "language"},
    "speak": {"host", "port", "voice"},
    "serve": {"address", "host", "port"},
    "page": {"host", "port"},
    "puck": {"name", "host", "port", "key_file", "person", "agent", "agents", "people",
             "fresh_after", "wake_word"},
    "voices": {"threshold", "margin"},
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
    #: The people this puck may tell apart by voice; ``person`` when unsure.
    people: tuple[str, ...] = ()
    #: Minutes with no question, after which each person's conversation at
    #: this puck starts over by itself (Dvara's /new); 0: never.
    fresh_after: int = FRESH_AFTER
    #: The wake word Vaani switches the puck to when it connects (an id
    #: or a name the puck offers: hey_jarvis, "Hey Jarvis"); "" leaves it.
    wake_word: str = ""
    #: Someone's own agent at this puck, as (person, agent) pairs.
    agents: tuple[tuple[str, str], ...] = ()

    def agent_for(self, person: str) -> str:
        """The agent that answers ``person`` here; "" for the file's."""
        return dict(self.agents).get(person) or self.agent

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
    page_host: str = "127.0.0.1"
    page_port: int = PAGE_PORT
    threshold: float = 0.6
    margin: float = 0.15
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
                      ("VAANI_SPEAK_HOST", "speak_host"), ("VAANI_ADDRESS", "address"),
                      ("VAANI_PAGE_HOST", "page_host")):
        if env.get(name, "").strip():
            changes[key] = env[name].strip().rstrip("/")
    for name, key in (("VAANI_SPEAK_PORT", "speak_port"), ("VAANI_PORT", "port"),
                      ("VAANI_PAGE_PORT", "page_port")):
        if env.get(name, "").strip():
            try:
                changes[key] = (0 if key == "page_port" and int(env[name]) == 0
                                else _port(int(env[name]), name))
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
    pg = data.get("page", {})
    heard = data.get("voices", {})
    for key in ("threshold", "margin"):
        value = heard.get(key, 0.5)
        if isinstance(value, bool) or not isinstance(value, (int, float)) \
                or not 0 <= value <= 1:
            raise ConfigError(f"{where}: voices.{key} is a number from 0 to 1")
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
        people = row.get("people", [])
        if not isinstance(people, list) or not all(isinstance(p, str) and NAME.match(p)
                                                   for p in people):
            raise ConfigError(f"{where}: puck {name}: people is a list of names from "
                              "Dvara's actors file, like [\"mahen\", \"asha\"]")
        pucks.append(Puck(name=name, host=str(row["host"]), key_file=str(row["key_file"]),
                          person=person, agent=str(row.get("agent", "")),
                          agents=_agents(row.get("agents", {}), where, name,
                                         {person, *people}),
                          port=_port(row.get("port", ESPHOME_PORT), where),
                          people=tuple(dict.fromkeys(people)),
                          fresh_after=_minutes(row.get("fresh_after", FRESH_AFTER), where,
                                               name),
                          wake_word=_wake_word(row.get("wake_word", ""), where, name)))
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
        page_host=str(pg.get("host", base.page_host)),
        page_port=0 if pg.get("port") == 0 else _port(pg.get("port", base.page_port), where),
        threshold=float(heard.get("threshold", base.threshold)),
        margin=float(heard.get("margin", base.margin)),
        pucks=tuple(pucks))


def with_puck(text: str, name: str, changes: dict[str, str | int | list[str]]) -> str:
    """vaani.toml's ``text`` with one puck's ``person``, ``agent`` or
    ``people`` changed, every other line (and comment) as it was. The
    result is checked as the file it will be before it is handed back."""
    lines = text.splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if line.strip() == "[[puck]]"]
    block = None
    for start in starts:
        end = next((i for i in range(start + 1, len(lines))
                    if lines[i].lstrip().startswith("[")), len(lines))
        if any(re.match(rf'\s*name\s*=\s*"{re.escape(name)}"', line)
               for line in lines[start:end]):
            block = (start, end)
            break
    if block is None:
        raise ConfigError(f"no puck called {name} in vaani.toml")
    start, end = block
    for key, value in changes.items():
        if key not in ("person", "agent", "agents", "people", "fresh_after", "wake_word"):
            raise ConfigError(f"a puck's {key} isn't changed here")
        table = (", ".join(f'{k} = "{v}"' for k, v in value.items())
                 if isinstance(value, dict) else "")
        said = (f'{key} = [{", ".join(chr(34) + p + chr(34) for p in value)}]\n'
                if isinstance(value, list) else
                f"{key} = {{ {table} }}\n" if isinstance(value, dict) else f"{key} = {value}\n"
                if isinstance(value, int) else f'{key} = "{value}"\n')
        found = next((i for i in range(start, end)
                      if re.match(rf"\s*{key}\s*=", lines[i])), None)
        if found is not None:
            lines[found] = said
        else:
            while end > start + 1 and not lines[end - 1].strip():
                end -= 1
            lines.insert(end, said)
            end += 1
    out = "".join(lines)
    parse(out)                         # refused here, never half-written
    return out


def _agents(value, where: str, puck: str, heard: set[str]) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, dict) or not all(
            isinstance(k, str) and NAME.match(k) and isinstance(v, str) and NAME.match(v)
            for k, v in value.items()):
        raise ConfigError(f"{where}: puck {puck}: agents is a person's name and their "
                          "agent's, like { asha = \"helper\" }")
    stray = sorted(set(value) - heard)
    if stray:
        raise ConfigError(f"{where}: puck {puck}: agents names {', '.join(stray)}, who "
                          "isn't its person or in its people, so it never hears them")
    return tuple(value.items())


def _wake_word(value, where: str, puck: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9 _-]{0,40}", value):
        raise ConfigError(f"{where}: puck {puck}: wake_word is one the puck offers, like "
                          f"hey_jarvis; not {value!r}")
    return value.strip()


def _minutes(value, where: str, puck: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10080:
        raise ConfigError(f"{where}: puck {puck}: fresh_after is minutes, 0 (never) to "
                          f"10080 (a week), not {value!r}")
    return value


def _port(value, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 65535:
        raise ConfigError(f"{where}: a port is a number from 1 to 65535, not {value!r}")
    return value
