"""An answer in the shape the puck plays: FLAC, 48 kHz, one channel.

THE PUCK PLAYS FLAC, NOT WAV. Its media player names the formats it
takes (``supported_formats``): FLAC at 48 kHz. Handed Piper's WAV it
fetches it and says "Could not determine audio file type", and the ring
just goes out -- which is what a whole night's answers did.

NOTHING TO INSTALL. A FLAC file may keep its samples as they are
("verbatim" subframes), so writing one is headers and two checksums: no
libFLAC, no ffmpeg in the image. It is no smaller than the WAV; a spoken
answer is a few hundred kilobytes on the house's own network.

THE RATE IS THE PUCK'S. Piper speaks at 22 050 Hz; the samples are
stretched to 48 000 by straight lines between neighbours, which a voice
doesn't notice.
"""

from __future__ import annotations

import io
import struct
import wave
from array import array

RATE = 48000
BLOCK = 4096


def _crc8_table() -> list[int]:
    out = []
    for n in range(256):
        c = n
        for _ in range(8):
            c = ((c << 1) ^ 0x07) & 0xFF if c & 0x80 else (c << 1) & 0xFF
        out.append(c)
    return out


def _crc16_table() -> list[int]:
    out = []
    for n in range(256):
        c = n << 8
        for _ in range(8):
            c = ((c << 1) ^ 0x8005) & 0xFFFF if c & 0x8000 else (c << 1) & 0xFFFF
        out.append(c)
    return out


CRC8, CRC16 = _crc8_table(), _crc16_table()


def _crc8(data: bytes) -> int:
    c = 0
    for b in data:
        c = CRC8[c ^ b]
    return c


def _crc16(data: bytes) -> int:
    c = 0
    for b in data:
        c = ((c << 8) & 0xFFFF) ^ CRC16[(c >> 8) ^ b]
    return c


def _number(n: int) -> bytes:
    """A frame's number, in FLAC's UTF-8-like coding."""
    if n < 0x80:
        return bytes([n])
    if n < 0x800:
        return bytes([0xC0 | n >> 6, 0x80 | n & 0x3F])
    if n < 0x10000:
        return bytes([0xE0 | n >> 12, 0x80 | n >> 6 & 0x3F, 0x80 | n & 0x3F])
    return bytes([0xF0 | n >> 18, 0x80 | n >> 12 & 0x3F, 0x80 | n >> 6 & 0x3F,
                  0x80 | n & 0x3F])


def mono16(wav: bytes) -> tuple[array, int]:
    """A WAV's samples, one channel of 16 bits, and its rate."""
    with wave.open(io.BytesIO(wav)) as got:
        if got.getsampwidth() != 2:
            raise ValueError(f"{got.getsampwidth() * 8}-bit sound; 16 expected")
        channels, rate = got.getnchannels(), got.getframerate()
        samples = array("h", got.readframes(got.getnframes()))
    if channels > 1:
        samples = array("h", (sum(samples[i:i + channels]) // channels
                              for i in range(0, len(samples), channels)))
    return samples, rate


def stretch(samples: array, rate: int, to: int = RATE) -> array:
    """``samples`` at ``rate``, as they'd be at ``to``."""
    if rate == to or not samples:
        return samples
    last, step = len(samples) - 1, rate / to
    out = array("h", bytes(2 * int(len(samples) * to / rate)))
    for i in range(len(out)):
        at = i * step
        j = int(at)
        nxt = samples[j + 1] if j < last else samples[j]
        out[i] = int(samples[j] + (nxt - samples[j]) * (at - j))
    return out


def from_wav(wav: bytes) -> bytes:
    """``wav`` as a FLAC the puck plays."""
    samples, rate = mono16(wav)
    samples = stretch(samples, rate)
    info = struct.pack(">HH", BLOCK, BLOCK) + bytes(6) + (
        (RATE << 44) | (0 << 41) | (15 << 36) | len(samples)).to_bytes(8, "big") + bytes(16)
    out = bytearray(b"fLaC" + bytes([0x80, 0, 0, len(info)]) + info)
    for n, start in enumerate(range(0, len(samples), BLOCK)):
        block = samples[start:start + BLOCK]
        # fixed blocks; size given at the end of the header (0111), 48 kHz
        # (1010); one channel (0000), 16 bits (100)
        head = bytes([0xFF, 0xF8, 0x7A, 0x08]) + _number(n) + struct.pack(">H", len(block) - 1)
        head += bytes([_crc8(head)])
        body = array("h", block)
        if body.itemsize == 2 and struct.pack("=h", 1) == b"\x01\x00":
            body.byteswap()                         # FLAC is big-endian
        frame = head + b"\x02" + body.tobytes()      # a verbatim subframe
        out += frame + struct.pack(">H", _crc16(frame))
    return bytes(out)
