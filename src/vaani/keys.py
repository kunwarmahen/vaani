"""A puck's key, found in a backup of its own flash.

THE KEY IS ON THE PUCK. Home Assistant gives a puck its API key when it
adopts it, keeps its copy where no API hands it out, and the puck keeps
its own in its settings (ESP-IDF's NVS, under ``esphome``) so it
survives a restart. A backup of the whole flash -- the one to keep
anyway before anything is changed -- holds it, so the key is read from
there: no Home Assistant token, no screen to copy it from.

WHICH ONE IS THE KEY. ESPHome names its settings by number, not word.
The key is the one 32-byte value; a backup with none or several says so
rather than guessing, and ``vaani check`` proves a key by connecting.

What is read is the NVS format's own: 4 KB pages, each with a header, a
two-bit state per entry, and 32-byte entries; a namespace is an entry
in namespace 0, and a value longer than eight bytes follows its entry.
"""

from __future__ import annotations

import base64
import struct

#: Where the settings live in a Voice PE's flash (its partition table says so).
TABLE = 0x8000
PAGE = 4096
ENTRIES = 126
WRITTEN = 2


class NoKey(Exception):
    pass


def partitions(flash: bytes) -> dict[str, tuple[int, int]]:
    """{name: (offset, size)} from the flash's partition table."""
    out = {}
    for at in range(TABLE, TABLE + 0xC00, 32):
        entry = flash[at:at + 32]
        if entry[:2] != b"\xaa\x50":
            break
        offset, size = struct.unpack("<II", entry[4:12])
        out[entry[12:28].split(b"\0")[0].decode(errors="replace")] = (offset, size)
    return out


def settings(flash: bytes) -> list[tuple[str, str, bytes]]:
    """Every value kept in NVS: (namespace, name, bytes)."""
    if "nvs" not in (found := partitions(flash)):
        raise NoKey("no settings part (nvs) in this flash: is it a whole backup?")
    offset, size = found["nvs"]
    part = flash[offset:offset + size]
    spaces: dict[int, str] = {}
    values: list[tuple[int, str, bytes]] = []
    for at in range(0, len(part), PAGE):
        page = part[at:at + PAGE]
        if page[:4] == b"\xff\xff\xff\xff":
            continue
        states, i = page[32:64], 0
        while i < ENTRIES:
            entry = page[64 + i * 32:96 + i * 32]
            span = max(entry[2], 1)
            if (states[i // 4] >> ((i % 4) * 2)) & 3 != WRITTEN:
                i += 1
                continue
            space, kind = entry[0], entry[1]
            name = entry[8:24].split(b"\0")[0].decode(errors="replace")
            if space == 0 and kind == 0x01:
                spaces[entry[24]] = name
            elif kind in (0x21, 0x41, 0x42):          # text, old blob, blob part
                length = struct.unpack("<H", entry[24:26])[0]
                start = 64 + (i + 1) * 32
                values.append((space, name, page[start:start + length]))
            i += span
    return [(spaces.get(s, str(s)), n, v) for s, n, v in values]


def key_from_flash(flash: bytes) -> str:
    """The puck's API key, as ``noise_psk`` takes it (base64)."""
    found = [v for space, _name, v in settings(flash) if space == "esphome" and len(v) == 32]
    if not found:
        raise NoKey("no key in this backup: the puck may have none (not adopted yet), "
                    "or it isn't an ESPHome puck")
    if len({bytes(v) for v in found}) > 1:
        raise NoKey(f"{len(found)} values could be the key; try each with "
                    "`vaani check`")
    return base64.b64encode(found[0]).decode()
