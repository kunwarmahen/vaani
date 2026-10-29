"""``vaani``: the commands.

    vaani init --puck kitchen --host 192.168.1.55 --person mahen --agent minder
                                    writes ~/.config/vaani/vaani.toml
    vaani backup                    the puck's whole flash, read twice, over USB
    vaani key FLASH.bin             its key, from that backup, into a file of yours
    vaani check [PUCK]              connect to each puck and say what it is
    vaani hear FILE.wav             what Whisper hears in a file
    vaani say "words" --out F.wav   what Piper says, into a file (no puck speaks)
    vaani ask "words" [--puck P]    what that puck's person's agent answers, as text
    vaani serve                     every puck, listening, until stopped
    vaani status [--json]           is it here, is it listening, which pucks
    vaani puck NAME [--person P] [--agent A] [--people a,b]
                                    change who a puck answers (read at its next question)
    vaani runs [--json]             the last questions: heard, whose, how long, fetched
    vaani page                      the page's address, with its key
    vaani voices fetch              the speaker model (once), to tell voices apart
    vaani voices enroll NAME --at-puck kitchen   their next 3 sentences there
                                    make their voice print (or: FILE.wav ...)
    vaani voices who FILE.wav --puck kitchen     whose voice that is
    vaani voices list | forget NAME | stop   (stop: an enrolling left undone)
    vaani keeps --json              what a backup takes (Sarathi asks)

Each step of a run can be tried on its own, without a puck speaking:
hear, say and ask are the run's three parts.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

from vaani import config as settings
from vaani import dvara, hearing, keys, speaking, version, voices
from vaani.config import ConfigError, Puck


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vaani", description="a voice puck that talks "
                                     "to your agents, through Dvara")
    parser.add_argument("--version", action=version.Show)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="write vaani.toml with one puck")
    p.add_argument("--puck", required=True, metavar="NAME", help="what you call it: kitchen")
    p.add_argument("--host", required=True, help="its address on your network")
    p.add_argument("--person", required=True, help="who it answers as, from Dvara's people")
    p.add_argument("--agent", default="", help="which of their agents answers")
    p.add_argument("--key-file", default="", help="where its key is (default: beside "
                   "vaani.toml, NAME.key)")
    p.add_argument("--dvara", default="http://127.0.0.1:8770", help="Dvara's address")
    p.add_argument("--whisper", default="http://127.0.0.1:11435", help="Whisper's address")
    p.add_argument("--piper", default="127.0.0.1:10200", help="Piper's (Wyoming) host:port")

    p = sub.add_parser("backup", help="the puck's whole flash, over USB, read twice")
    p.add_argument("--port", default="/dev/ttyACM0")
    p.add_argument("--out", default="~/puck-backup", help="a folder only you can read")

    p = sub.add_parser("key", help="a puck's key, from a backup of its flash")
    p.add_argument("flash", help="the .bin `vaani backup` wrote")
    p.add_argument("--out", default="", help="the key file (default: the puck's "
                   "key_file, or ./puck.key)")
    p.add_argument("--puck", default="", help="whose key_file to write")

    p = sub.add_parser("check", help="connect to each puck and say what it is")
    p.add_argument("puck", nargs="?", default="")

    p = sub.add_parser("hear", help="what Whisper hears in a WAV file")
    p.add_argument("file")

    p = sub.add_parser("say", help="what Piper says, into a WAV file")
    p.add_argument("words")
    p.add_argument("--out", required=True)

    p = sub.add_parser("ask", help="what a puck's person's agent answers, as text")
    p.add_argument("words")
    p.add_argument("--puck", default="")

    p = sub.add_parser("status", help="is it here, is it listening, which pucks")
    p.add_argument("--json", action="store_true", dest="json_out")
    sub.add_parser("page", help="the page's address, with its key")
    p = sub.add_parser("puck", help="change who a puck answers as, and which people it "
                       "tells apart")
    p.add_argument("name")
    p.add_argument("--person", default=None, help="who, when it isn't sure")
    p.add_argument("--agent", default=None)
    p.add_argument("--people", default=None, help="names from Dvara, comma between; "
                   "\"\" for none")
    p = sub.add_parser("runs", help="the last questions: heard, whose, how long, fetched")
    p.add_argument("--json", action="store_true", dest="json_out")
    p.add_argument("--limit", type=int, default=20)
    p = sub.add_parser("keeps", help="what a backup should take")
    p.add_argument("--json", action="store_true", dest="json_out")

    p = sub.add_parser("voices", help="telling voices apart: fetch, enroll, who, list, "
                       "forget")
    p.add_argument("what", choices=("fetch", "enroll", "who", "list", "forget", "stop"))
    p.add_argument("name", nargs="?", default="", help="a person (enroll, forget), or a "
                   "WAV file (who)")
    p.add_argument("files", nargs="*", help="WAV files of them talking (enroll)")
    p.add_argument("--at-puck", dest="at_puck", default="", metavar="PUCK",
                   help="enroll from their next sentences at this puck")
    p.add_argument("--puck", default="", help="whose people to match against (who)")

    p = sub.add_parser("serve", help="every puck, listening, until stopped")
    p.add_argument("--quiet", action="store_true", help="only problems in the log")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init":
            return _init(args)
        if args.command == "backup":
            return _backup(args)
        if args.command == "key":
            return _key(args)
        if args.command in ("status", "keeps"):
            from vaani import status
            got = status.report() if args.command == "status" else status.keeps()
            if args.json_out:
                print(json.dumps(got, indent=2))
            elif args.command == "keeps":
                print("\n".join(f"{k['path']}  {k['what']}" for k in got["keeps"]))
            else:
                print(f"vaani {got['version']}: {'running' if got['serving'] else 'not running'}"
                      + (f" ({got['problem']})" if got.get("problem") else ""))
                for p in got["pucks"]:
                    held = ("" if "listening" not in p else ", listening" if p["listening"]
                            else f", not listening: {p.get('problem', '')}")
                    print(f"  {p['name']:<10} {p['host']:<15} as {p['person']}, "
                          f"key {p['key']}{held}")
            return 0
        if args.command == "runs":
            return _runs(args)
        if args.command == "puck":
            return _puck(args)
        if args.command == "page":
            from vaani.page import page_token
            conf = settings.load()
            if not conf.page_port:
                raise ConfigError("the page is off ([page] port = 0)")
            host = "127.0.0.1" if conf.page_host in ("0.0.0.0", "::") else conf.page_host
            print(f"http://{host}:{conf.page_port}/#token={page_token()}")
            return 0
        if args.command == "voices":
            return _voices(args)
        conf = settings.load()
        if args.command == "check":
            return asyncio.run(_check(conf, args.puck))
        if args.command == "hear":
            print(hearing.hear(Path(args.file).read_bytes(), url=conf.hear_url,
                               model=conf.hear_model, language=conf.language))
            return 0
        if args.command == "say":
            Path(args.out).write_bytes(speaking.speak(
                speaking.aloud(args.words), host=conf.speak_host, port=conf.speak_port,
                voice=conf.voice))
            print(f"wrote {args.out}")
            return 0
        if args.command == "ask":
            puck = conf.puck(args.puck) if args.puck else _only(conf)
            got = dvara.ask(args.words, person=puck.person, agent=puck.agent or conf.agent,
                            puck=puck.name, url=conf.dvara_url, token=conf.dvara_token())
            print(got.get("text", ""))
            print(f"(read aloud: {speaking.aloud(got.get('text', ''))!r})", file=sys.stderr)
            return 0 if got.get("ok", True) else 1
        if args.command == "serve":
            from vaani.serving import serve
            logging.basicConfig(level=logging.WARNING if args.quiet else logging.INFO,
                                format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
            # ESPHome's client says each failed try too; Vaani's line is enough
            logging.getLogger("aioesphomeapi").setLevel(logging.ERROR)
            return asyncio.run(serve(conf))
    except (ConfigError, hearing.HearingError, speaking.SpeakingError,
            dvara.DvaraError, keys.NoKey, voices.VoiceError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
    return 2


def _voices(args) -> int:
    prints = voices.Prints(settings.path().parent / "voices")
    if args.what == "fetch":
        print(f"the speaker model is at {voices.fetch()}")
        return 0
    if args.what == "stop":
        from vaani import asking
        note = asking.enrolling()
        asking.enrolling_file().unlink(missing_ok=True)
        print(f"stopped taking {note['person']}'s samples at the {note['puck']} puck"
              if note else "nobody was being enrolled")
        return 0
    if args.what == "list":
        known = prints.known()
        for person, kept in known.items():
            print(f"{person:<12} from {kept.get('samples')} sample(s), {kept.get('model')}")
        if not known:
            print("no voice prints yet: `vaani voices enroll NAME --at-puck PUCK`")
        return 0
    if not args.name:
        raise ConfigError(f"voices {args.what}: whose? a person's name"
                          + (" or a WAV file" if args.what == "who" else ""))
    if args.what == "forget":
        print(f"forgot {args.name}'s voice print" if prints.forget(args.name)
              else f"there was no print for {args.name}")
        return 0
    if args.what == "who":
        conf = settings.load()
        puck = conf.puck(args.puck) if args.puck else _only(conf)
        people = puck.people or tuple(prints.known())
        found = prints.match(Path(args.name).read_bytes(), people,
                             threshold=conf.threshold, margin=conf.margin)
        print(f"{found.person or 'not sure'} ({found.score:.2f}, next {found.runner_up:.2f})")
        return 0
    if args.at_puck:
        from vaani import asking
        conf = settings.load()
        puck = conf.puck(args.at_puck)
        if puck.people and args.name not in puck.people:
            raise ConfigError(f"{args.name} isn't in the {puck.name} puck's people; add "
                              "them there first")
        prints._extract()                       # the model is there, before anyone talks
        asking.start_enrolling(puck.name, args.name)
        print(f"Now, at the {puck.name} puck, {args.name} says the wake word and any "
              f"sentence, {voices.SAMPLES} times; the puck counts down. (`vaani serve` "
              "must be running.)")
        return 0
    if not args.files:
        raise ConfigError("enroll from what? --at-puck PUCK, or WAV files of them talking")
    count = prints.enroll(args.name, [Path(f).read_bytes() for f in args.files])
    print(f"{args.name}'s voice print made from {count} sample(s)")
    return 0


def _puck(args) -> int:
    changes: dict = {k: getattr(args, k) for k in ("person", "agent") if getattr(args, k)
                     is not None}
    if args.people is not None:
        changes["people"] = [p.strip() for p in args.people.split(",") if p.strip()]
    if not changes:
        raise ConfigError("change what? --person, --agent or --people")
    where = settings.path()
    before = where.read_text()
    after = settings.with_puck(before, args.name, changes)
    where.with_name(where.name + ".bak").write_text(before)
    where.write_text(after)
    print(f"the {args.name} puck: " + "; ".join(
        f"{k} {', '.join(v) or 'nobody' if isinstance(v, list) else v}"
        for k, v in changes.items()) + " (from its next question)")
    return 0


def _runs(args) -> int:
    from vaani import asking, runs
    got = runs.read(max(1, args.limit))
    if args.json_out:
        prints = voices.Prints(settings.path().parent / "voices")
        try:
            pucks = [{"name": p.name, "person": p.person, "people": list(p.people)}
                     for p in settings.load().pucks]
        except ConfigError:
            pucks = []
        print(json.dumps({"format": runs.FORMAT, "runs": got, "pucks": pucks,
                          "voices": [{"person": person, "samples": kept.get("samples")}
                                     for person, kept in prints.known().items()],
                          "enrolling": asking.enrolling()}, indent=2))
        return 0
    if not got:
        print("no questions yet")
    for run in got:
        took = ", ".join(f"{k} {v}s" for k, v in (run.get("took") or {}).items())
        fetched = "fetched" if run.get("fetched") else "NOT fetched" if run.get("url") else ""
        print(f"{run.get('puck')}: heard {run.get('heard')!r} as {run.get('person') or '-'}"
              f" -> {(run.get('answer') or run.get('error') or '')[:60]!r}"
              f" [{took}] {fetched}")
    return 0


def _only(conf: settings.Config) -> Puck:
    if len(conf.pucks) != 1:
        raise ConfigError("which puck? --puck NAME" if conf.pucks
                          else "no pucks yet: `vaani init`")
    return conf.pucks[0]


def _init(args) -> int:
    where = settings.path()
    if where.exists():
        print(f"error: {where} is there already; change it by hand", file=sys.stderr)
        return 2
    host, _, port = args.piper.partition(":")
    key_file = args.key_file or str(where.parent / f"{args.puck}.key")
    text = f'''# Vaani: voice pucks that talk to your agents, through Dvara.

[dvara]
url = "{args.dvara}"
token_file = "{where.parent / 'dvara.token'}"   # Dvara's token, chmod 600

[hear]
url = "{args.whisper}"                     # a Whisper with the OpenAI road
model = "Systran/faster-whisper-small"

[speak]
host = "{host}"                             # a Piper on the Wyoming road
port = {int(port or 10200)}

[[puck]]
name = "{args.puck}"
host = "{args.host}"
key_file = "{key_file}"
person = "{args.person}"
agent = "{args.agent}"
'''
    settings.parse(text, str(where))          # the file is checked before it is written
    where.parent.mkdir(parents=True, exist_ok=True)
    where.write_text(text)
    print(f"wrote {where}\nnext: its key into {key_file} (`vaani key FLASH.bin`), "
          f"Dvara's token into {where.parent / 'dvara.token'}, then `vaani check`")
    return 0


def _esptool() -> list[str]:
    if shutil.which("esptool"):
        return ["esptool"]
    if shutil.which("uvx"):
        return ["uvx", "--from", "esptool", "esptool"]
    raise ConfigError("esptool is needed: `pipx install esptool`, or install uv")


def _backup(args) -> int:
    out = Path(args.out).expanduser()
    out.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not os.access(args.port, os.R_OK | os.W_OK):
        raise ConfigError(f"{args.port} can't be opened: `sudo setfacl -m u:$USER:rw "
                          f"{args.port}` (until unplugged), or `sudo usermod -aG dialout "
                          "$USER` (for good, from your next log-in)")
    reads = []
    for n in (1, 2):
        made = out / f"puck-flash-read{n}.bin"
        print(f"reading the whole flash ({n} of 2): a minute or two; the puck restarts")
        done = subprocess.run([*_esptool(), "-p", args.port, "-b", "921600", "read-flash",
                               "0", "ALL", str(made)], capture_output=True, text=True)
        if done.returncode != 0:
            raise ConfigError(f"esptool: {(done.stderr or done.stdout).strip()[-300:]}")
        reads.append(made)
    a, b = (hashlib.sha256(p.read_bytes()).hexdigest() for p in reads)
    if a != b:
        raise ConfigError("the two reads differ: a loose cable? Nothing is kept; try again")
    kept = out / "puck-flash.bin"
    reads[0].replace(kept)
    reads[1].unlink()
    kept.chmod(0o600)
    print(f"kept {kept} (sha256 {a}); both reads matched.\nIt holds the puck's Wi-Fi "
          f"password: keep it private. To put it back: esptool -p {args.port} -b 921600 "
          f"write-flash 0 {kept}")
    return 0


def _key(args) -> int:
    found = keys.key_from_flash(Path(args.flash).expanduser().read_bytes())
    if args.out:
        target = Path(args.out).expanduser()
    else:
        try:
            conf = settings.load()
            target = Path((conf.puck(args.puck) if args.puck else _only(conf)).key_file)
        except ConfigError:
            target = Path("puck.key")
        target = target.expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.touch(mode=0o600, exist_ok=True)
    target.chmod(0o600)
    target.write_text(found + "\n")
    print(f"wrote its key into {target} (only you can read it); `vaani check` tries it")
    return 0


async def _check(conf: settings.Config, name: str) -> int:
    from aioesphomeapi import APIClient

    pucks = [conf.puck(name)] if name else list(conf.pucks)
    if not pucks:
        raise ConfigError("no pucks yet: `vaani init`")
    bad = 0
    for puck in pucks:
        client = APIClient(puck.host, puck.port, None, noise_psk=puck.key(),
                           client_info="vaani")
        try:
            await asyncio.wait_for(client.connect(login=True), 15)
            info = await client.device_info()
            print(f"{puck.name}: {info.name} at {puck.host}, ESPHome {info.esphome_version}, "
                  f"{info.project_name} {info.project_version}; answers as {puck.person}"
                  f"{' with ' + (puck.agent or conf.agent) if (puck.agent or conf.agent) else ''}")
        except Exception as exc:                  # noqa: BLE001 -- each puck said in turn
            bad += 1
            why = "the key is wrong" if "invalid" in str(exc).lower() else str(exc)
            print(f"{puck.name}: can't connect at {puck.host}: {why}")
        finally:
            await client.disconnect()
    return 1 if bad else 0
