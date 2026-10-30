"""Vaani's own page: each puck, what it was last asked, whose voices it knows.

    GET  /                       the page (static; it carries no data)
    GET  /api/state              status, the last questions, the pucks' people,
                                 the voices known, a voice being learned
    POST /api/voices/enroll      {"person", "puck"}: their next sentences there
    POST /api/voices/forget      {"person"}
    POST /api/voices/stop        {}: a learning left undone
    POST /api/pins/set           {"person", "pin"}: their spoken PIN (kept as a hash)
    POST /api/pins/forget        {"person"}

SERVED BY ``vaani serve``, BESIDE THE PUCKS. The page shows what the
running serve knows -- each puck held or why not, each run as it ends,
the puck coming for its answer -- so it is that process's, not another
program's guess at it. Its port is not the answers' port: 8799 is open
to the house so a puck can fetch a sound, and serves nothing else; the
page has a port of its own (``[page]``, 8797), on 127.0.0.1 unless a
harness says otherwise.

A TOKEN, ALWAYS, as every page in this family has: any web page you
visit can send a request to 127.0.0.1, so every ``/api`` call carries
``Authorization: Bearer``. It is ``$VAANI_PAGE_TOKEN``, or one made
once and kept in the state folder (``page.token``, readable by you
alone), which Sarathi reads to open the page already signed in.

WHAT IT CHANGES IS VOICES. Who a puck answers as and which people it
tells apart are settings (vaani.toml; with Sarathi, its Settings →
Vaani). Here a voice is learned or forgotten: the things done at the
puck, with someone standing at it.

Standard library only.
"""

from __future__ import annotations

import hmac
import json
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from urllib.parse import urlparse

from vaani import asking, runs, status
from vaani import config as settings
from vaani.config import NAME, ConfigError
from vaani.pins import PinError, Pins
from vaani.voices import Prints, VoiceError

MAX_BODY = 4096
TOKEN_FILE = "page.token"


def page_token() -> str:
    """``$VAANI_PAGE_TOKEN``, or the one kept in the state folder (made once)."""
    named = os.environ.get("VAANI_PAGE_TOKEN", "").strip()
    if named:
        if len(named) < 16:
            raise ConfigError("VAANI_PAGE_TOKEN must be at least 16 characters")
        return named
    path = status.state() / TOKEN_FILE
    try:
        kept = path.read_text().strip()
        if len(kept) >= 16:
            return kept
    except OSError:
        pass
    made = secrets.token_urlsafe(24)
    path.parent.mkdir(parents=True, exist_ok=True)
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as out:
        out.write(made + "\n")
    return made


def state(prints: Prints) -> dict:
    """Everything the page draws, read fresh each time."""
    try:
        conf = settings.load()
        pucks = [{"name": p.name, "person": p.person, "agent": p.agent or conf.agent,
                  "agents": dict(p.agents), "people": list(p.people)} for p in conf.pucks]
    except ConfigError:
        pucks = []
    return {"status": status.report(), "runs": runs.read(30), "pucks": pucks,
            "pins": Pins(settings.path().parent / "pins").people(),
            "voices": [{"person": person, "samples": kept.get("samples")}
                       for person, kept in prints.known().items()],
            "enrolling": asking.enrolling()}


class PageError(Exception):
    def __init__(self, code: int, detail: str) -> None:
        super().__init__(detail)
        self.code = code


def act(what: str, body: dict, prints: Prints) -> str:
    """A voice learned, forgotten, or a learning stopped; what to say back."""
    person = str(body.get("person") or "")
    if what in ("enroll", "forget") and not NAME.match(person):
        raise PageError(400, "whose voice? a person's name, as Dvara has them")
    if what == "stop":
        note = asking.enrolling()
        asking.enrolling_file().unlink(missing_ok=True)
        return f"Stopped learning {note['person']}'s voice." if note else "Nothing to stop."
    if what == "forget":
        return (f"Forgot {person}'s voice." if prints.forget(person)
                else f"There was no voice for {person}.")
    if what != "enroll":
        raise PageError(404, "not found")
    try:
        puck = settings.load().puck(str(body.get("puck") or ""))
    except ConfigError as exc:
        raise PageError(400, str(exc)) from None
    if puck.people and person not in puck.people:
        raise PageError(400, f"{person} isn't one of the people the {puck.name} puck "
                        "tells apart: tick them for it in its settings first")
    try:
        prints._extract()               # the model is there before anyone talks
    except VoiceError as exc:
        raise PageError(409, str(exc)) from None
    asking.start_enrolling(puck.name, person)
    return (f"At the {puck.name} puck, {person} says the wake word and any sentence, "
            "three times. The puck counts down.")


def pin_act(what: str, body: dict) -> str:
    """A person's PIN set or forgotten; what to say back. Never echoed."""
    person = str(body.get("person") or "")
    if not NAME.match(person):
        raise PageError(400, "whose PIN? a person's name, as Dvara has them")
    pins = Pins(settings.path().parent / "pins")
    if what == "forget":
        return f"Forgot {person}'s PIN." if pins.forget(person) else f"{person} had no PIN."
    if what != "set":
        raise PageError(404, "not found")
    try:
        pins.set(person, str(body.get("pin") or "").strip())
    except PinError as exc:
        raise PageError(400, str(exc)) from None
    return (f"Kept {person}'s PIN. At the puck, a step that needs it asks them to say it, "
            "one digit at a time.")


def _static(name: str) -> bytes:
    return files("vaani").joinpath("static", name).read_bytes()


class PageServer:
    def __init__(self, prints: Prints, token: str, *, host: str, port: int) -> None:
        self.prints, self.token = prints, token
        self.httpd = ThreadingHTTPServer((host, port), _handler(self))
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True,
                                        name="vaani-page")

    def start(self) -> PageServer:
        self._thread.start()
        return self

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


def _handler(server: PageServer):
    class Handler(BaseHTTPRequestHandler):
        server_version = "vaani"

        def log_message(self, *_args) -> None:
            pass

        def _send(self, code: int, body: bytes, kind: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, data: dict) -> None:
            self._send(code, json.dumps(data).encode(), "application/json")

        def _allowed(self) -> bool:
            offered = self.headers.get("Authorization", "")
            offered = offered[7:].strip() if offered.startswith("Bearer ") else ""
            if offered and hmac.compare_digest(offered.encode(), server.token.encode()):
                return True
            self._json(401, {"detail": "missing or wrong token"})
            return False

        def do_GET(self) -> None:  # noqa: N802 -- the stdlib's name
            path = urlparse(self.path).path
            if path in ("/", "/index.html"):
                return self._send(200, _static("index.html"), "text/html; charset=utf-8")
            if path == "/favicon.svg":
                return self._send(200, _static("favicon.svg"), "image/svg+xml")
            if path != "/api/state":
                return self._json(404, {"detail": "not found"})
            if self._allowed():
                self._json(200, state(server.prints))

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if not path.startswith(("/api/voices/", "/api/pins/")):
                return self._json(404, {"detail": "not found"})
            if not self._allowed():
                return None
            size = int(self.headers.get("Content-Length") or 0)
            if size > MAX_BODY:
                return self._json(413, {"detail": "too large"})
            try:
                body = json.loads(self.rfile.read(size) or b"{}") if size else {}
            except ValueError:
                return self._json(400, {"detail": "the body is not JSON"})
            if not isinstance(body, dict):
                return self._json(400, {"detail": "the body is a JSON object"})
            try:
                if path.startswith("/api/pins/"):
                    said = pin_act(path.removeprefix("/api/pins/"), body)
                else:
                    said = act(path.removeprefix("/api/voices/"), body, server.prints)
            except PageError as exc:
                return self._json(exc.code, {"detail": str(exc)})
            self._json(200, {"said": said})

    return Handler
