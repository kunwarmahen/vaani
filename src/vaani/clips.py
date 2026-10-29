"""Where a spoken answer waits for the puck to fetch it.

A PUCK PLAYS AN ADDRESS. It is told where the answer is (``TTS_END``
with a URL) and fetches it with its own media player, as it does from
Home Assistant. So each answer is kept here under a long random name for
a few minutes, served to whoever asks for that name, and then forgotten.
Nothing else is served: no list, no index, no other path.

THE ADDRESS IS ONE THE PUCK CAN REACH. ``[serve] address`` says it; left
out, it is this computer's own address on the way to the puck (the one
the system would send from), which is right on a house's one network.
"""

from __future__ import annotations

import logging
import secrets
import socket
import threading
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

log = logging.getLogger("vaani")

#: How long an answer waits to be fetched.
KEEP = 300.0


class Clips:
    def __init__(self, *, host: str, port: int, address: str,
                 fetched: Callable[[str, str], None] = lambda _url, _by: None) -> None:
        self.address, self.port = address, port
        self._kept: dict[str, tuple[float, bytes]] = {}
        self._lock = threading.Lock()
        clips = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:           # noqa: N802 -- the stdlib's name
                name = self.path.removeprefix("/clip/").removesuffix(".flac")
                body = clips.get(name) if self.path.startswith("/clip/") else None
                if body is None:
                    log.warning("a clip was asked for that isn't here (%s, from %s)",
                                self.path[:40], self.client_address[0])
                    self.send_error(404)
                    return
                log.info("answer fetched by %s (%d KB)", self.client_address[0],
                         len(body) // 1024)
                fetched(clips.url(name), self.client_address[0])
                self.send_response(200)
                self.send_header("Content-Type", "audio/flac")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args) -> None:
                pass

        self._server = ThreadingHTTPServer((host, port), Handler)
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True,
                                        name="vaani-clips")

    def start(self) -> Clips:
        self._thread.start()
        return self

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def add(self, flac: bytes) -> str:
        """``flac`` kept; the address the puck fetches it from."""
        name = secrets.token_urlsafe(18)
        now = time.monotonic()
        with self._lock:
            self._kept = {k: v for k, v in self._kept.items() if now - v[0] < KEEP}
            self._kept[name] = (now, flac)
        return self.url(name)

    def seconds(self, url: str) -> float:
        """How long the answer at ``url`` takes to say (0 when unknown)."""
        with self._lock:
            kept = self._kept.get(url.rsplit("/", 1)[-1].removesuffix(".flac"))
        if kept is None or kept[1][:4] != b"fLaC" or len(kept[1]) < 26:
            return 0.0
        info = int.from_bytes(kept[1][18:26], "big")    # FLAC's STREAMINFO
        rate, samples = info >> 44, info & 0xFFFFFFFFF
        return samples / rate if rate else 0.0

    def url(self, name: str) -> str:
        return f"http://{self.address}:{self.port}/clip/{name}.flac"

    def get(self, name: str) -> bytes | None:
        with self._lock:
            kept = self._kept.get(name)
        if kept is None or time.monotonic() - kept[0] >= KEEP:
            return None
        return kept[1]


def address_towards(host: str) -> str:
    """This computer's address on the way to ``host``: no packet is sent."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.connect((host, 9))
        return probe.getsockname()[0]
