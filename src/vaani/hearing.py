"""Hearing: what was said, as words, from a Whisper server on this computer.

ANY WHISPER THAT SPEAKS THE OPENAI ROAD. ``faster-whisper-server``,
``whisper.cpp``'s server, LocalAI and others all take the same request:
a WAV posted to ``/v1/audio/transcriptions`` with a model's name, and
``{"text": ...}`` back. So the address is the setting, and nothing here
is tied to one of them. The sound never leaves the house.

The puck sends 16 kHz, 16-bit, one channel; that is wrapped as a WAV
here, so the server is told exactly what it is getting.

NOT WORDS IS NOTHING HEARD. For a room with no one talking Whisper can
write a line of brackets or one character over and over
("༼༽༽༽༽༽..."); sent on, the agent was asked it as a question. Text
that is mostly not letters, or one character repeated, is taken as
nothing said (``words``).
"""

from __future__ import annotations

import io
import re
import unicodedata
import json
import urllib.error
import urllib.request
import uuid
import wave

#: What a puck sends: 16 kHz, 16-bit samples, one channel.
RATE, WIDTH, CHANNELS = 16000, 2, 1


#: The same character this many times in a row is not speech (a number
#: may be: "10000000").
REPEATED = re.compile(r"(\D)\1{7,}", re.S)


def words(text: str) -> str:
    """``text`` when it is words; "" for Whisper's noise, which is mostly
    not letters or digits (in any script), or one character repeated."""
    text = text.strip()
    seen = [c for c in text if not c.isspace()]
    if not seen or REPEATED.search(text):
        return ""
    # a Hindi vowel sign is a mark, not a letter, and is as much a word
    letters = sum(c.isalnum() or unicodedata.category(c).startswith("M") for c in seen)
    return text if letters * 2 > len(seen) else ""


class HearingError(Exception):
    pass


def as_wav(pcm: bytes, rate: int = RATE, width: int = WIDTH, channels: int = CHANNELS) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def hear(wav: bytes, *, url: str, model: str, language: str = "",
         timeout: float = 60) -> str:
    """The words in ``wav``, stripped; "" when nothing was said."""
    boundary = uuid.uuid4().hex
    fields = [("model", model)] + ([("language", language)] if language else [])
    body = b"".join(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\""
                    f"\r\n\r\n{v}\r\n".encode() for k, v in fields)
    body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
             f"filename=\"said.wav\"\r\nContent-Type: audio/wav\r\n\r\n").encode()
    body += wav + f"\r\n--{boundary}--\r\n".encode()
    request = urllib.request.Request(
        f"{url.rstrip('/')}/v1/audio/transcriptions", body,
        {"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as answer:
            said = json.loads(answer.read())
    except urllib.error.HTTPError as exc:
        raise HearingError(f"Whisper at {url} said {exc.code}: "
                           f"{exc.read()[:200].decode(errors='replace')}") from None
    except (OSError, ValueError) as exc:
        raise HearingError(f"Whisper at {url} didn't answer: {exc}") from None
    return str(said.get("text", "")).strip()
