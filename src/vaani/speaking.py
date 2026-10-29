"""Speaking: an answer as sound, from a Piper server on this computer.

THE WYOMING ROAD, AS HOME ASSISTANT USES IT. ``wyoming-piper`` (and any
Wyoming text-to-speech) takes one ``synthesize`` event and answers with
``audio-start``, chunks, and ``audio-stop``. Each event is a line of
JSON, then its data and its payload, their lengths in the line. That is
the whole protocol a voice needs, so it is written here rather than
pulled in.

WHAT IS READ IS NOT WHAT IS WRITTEN. An agent answers in Markdown, with
links and sometimes code. Read out, "asterisk asterisk" and a URL letter
by letter help nobody: marks go, a link is read by its words, code and
tables are named and left in the chat, and a long answer stops at a
sentence (``aloud``), the way Dvara's own voice notes do.
"""

from __future__ import annotations

import json
import re
import socket

from vaani.hearing import as_wav

#: Longest answer read out, in characters; the rest is in the chat.
LONGEST = 600
REST = "The rest is in the chat."


class SpeakingError(Exception):
    pass


def aloud(text: str, longest: int = LONGEST) -> str:
    """``text`` as it should be heard."""
    text = re.sub(r"```.*?```", " (some code, in the chat) ", text, flags=re.S)
    text = re.sub(r"(?m)^\s*\|.*\|\s*$\n?", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"https?://\S+", "a link", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"(?m)^\s*(#+|[-*•]|\d+\.)\s+", "", text)
    text = re.sub(r"[*_~]{1,3}", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= longest:
        return text
    cut = text[:longest]
    end = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
    return (cut[:end + 1] if end > 0 else cut) + " " + REST


def _send(sock: socket.socket, kind: str, data: dict) -> None:
    raw = json.dumps(data).encode()
    sock.sendall(json.dumps({"type": kind, "data_length": len(raw)}).encode() + b"\n" + raw)


def _event(stream) -> tuple[str, dict, bytes]:
    line = stream.readline()
    if not line:
        raise SpeakingError("Piper closed the connection before the end of the audio")
    head = json.loads(line)
    data = head.get("data") or {}
    if head.get("data_length"):
        data = json.loads(stream.read(head["data_length"]))
    payload = stream.read(head["payload_length"]) if head.get("payload_length") else b""
    return head["type"], data, payload


def speak(text: str, *, host: str, port: int, voice: str = "", timeout: float = 60) -> bytes:
    """``text`` spoken, as a WAV."""
    data: dict = {"text": text}
    if voice:
        data["voice"] = {"name": voice}
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            _send(sock, "synthesize", data)
            stream = sock.makefile("rb")
            pcm, fmt = bytearray(), None
            while True:
                kind, got, payload = _event(stream)
                if kind == "audio-start":
                    fmt = got
                elif kind == "audio-chunk":
                    fmt = fmt or got
                    pcm += payload
                elif kind == "audio-stop":
                    break
                elif kind == "error":
                    raise SpeakingError(f"Piper: {got.get('text', got)}")
    except (OSError, ValueError) as exc:
        raise SpeakingError(f"Piper at {host}:{port} didn't answer: {exc}") from None
    if not fmt or not pcm:
        raise SpeakingError("Piper sent no audio")
    return as_wav(bytes(pcm), int(fmt["rate"]), int(fmt["width"]), int(fmt["channels"]))
