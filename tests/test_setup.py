"""Bias: a key that leaks, a setting that's quietly ignored, a wrong key found.

The puck's key opens its microphone. The failures here are the ones that
give it away or lose it without a word: a key file others can read, a
misspelt setting that makes a puck answer as nobody, a backup read that
picks the wrong 32 bytes, and an answer's address that serves anything
but the answer it was made for.
"""

from __future__ import annotations

import base64
import struct
import urllib.error
import urllib.request

import pytest

from vaani import keys
from vaani.clips import Clips
from vaani.config import ConfigError, parse

GOOD = '''
[[puck]]
name = "kitchen"
host = "192.168.1.55"
key_file = "{key}"
person = "mahen"
'''


def test_a_misspelt_setting_is_refused_not_ignored(tmp_path):
    with pytest.raises(ConfigError, match="unknown key persn"):
        parse(GOOD.format(key="k").replace("person", "persn"))
    with pytest.raises(ConfigError, match="unknown table"):
        parse("[pucks]\n")
    with pytest.raises(ConfigError, match="a word"):
        parse(GOOD.format(key="k").replace('"mahen"', '"../x"'))
    assert parse(GOOD.format(key="k")).pucks[0].person == "mahen"


def test_a_key_others_can_read_is_refused(tmp_path):
    key = tmp_path / "kitchen.key"
    key.write_text("c2VjcmV0\n")
    key.chmod(0o644)
    puck = parse(GOOD.format(key=key)).pucks[0]
    with pytest.raises(ConfigError, match="chmod 600"):
        puck.key()
    key.chmod(0o600)
    assert puck.key() == "c2VjcmV0"


def flash(*values: tuple[str, str, bytes]) -> bytes:
    """A 16 KB 'flash': a partition table at 0x8000 and one NVS page."""
    nvs_at = 0x9000
    out = bytearray(b"\xff" * 0xB000)
    entry = b"\xaa\x50" + bytes([1, 2]) + struct.pack("<II", nvs_at, 0x2000) \
        + b"nvs".ljust(16, b"\0") + bytes(4)
    out[0x8000:0x8020] = entry
    page = bytearray(b"\xff" * 4096)
    page[:32] = bytes(32)                                  # a used page's header
    rows = []

    def row(space, kind, span, name, data8):
        rows.append(bytes([space, kind, span, 0xff]) + bytes(4)
                    + name.encode().ljust(16, b"\0") + data8)

    spaces = {}
    for space_name, _, _ in values:
        if space_name not in spaces:
            spaces[space_name] = len(spaces) + 1
            row(0, 0x01, 1, space_name, bytes([spaces[space_name]]) + bytes(7))
    for space_name, name, data in values:
        chunks = (len(data) + 31) // 32
        row(spaces[space_name], 0x42, chunks + 1, name, struct.pack("<H", len(data)) + bytes(6))
        rows.extend(data.ljust(chunks * 32, b"\xff")[i:i + 32] for i in range(0, chunks * 32, 32))
    bitmap = 0
    for i in range(len(rows)):
        bitmap |= 2 << (i * 2)
    page[32:64] = (bitmap | (((1 << 256) - 1) ^ ((1 << (len(rows) * 2)) - 1))).to_bytes(32,
                                                                                    "little")
    for i, r in enumerate(rows):
        page[64 + i * 32:96 + i * 32] = r
    out[nvs_at:nvs_at + 4096] = page
    return bytes(out)


def test_the_key_is_the_one_32_byte_esphome_value():
    secret = bytes(range(32))
    found = keys.key_from_flash(flash(("phy", "cal_mac", b"\x01" * 6),
                                      ("esphome", "88491486", secret),
                                      ("esphome", "88491487", b"x" * 98),
                                      ("bt_config", "k", b"y" * 32)))
    assert base64.b64decode(found) == secret


def test_a_backup_with_no_key_or_two_says_so():
    with pytest.raises(keys.NoKey, match="no key"):
        keys.key_from_flash(flash(("esphome", "1", b"x" * 4)))
    with pytest.raises(keys.NoKey, match="2 values"):
        keys.key_from_flash(flash(("esphome", "1", b"a" * 32), ("esphome", "2", b"b" * 32)))
    with pytest.raises(keys.NoKey, match="whole backup"):
        keys.key_from_flash(bytes(0x10000))


def test_an_answer_is_served_by_its_name_and_nothing_else_is():
    clips = Clips(host="127.0.0.1", port=0, address="127.0.0.1").start()
    try:
        url = clips.add(b"RIFF answer")
        assert urllib.request.urlopen(url).read() == b"RIFF answer"
        base = url.rsplit("/clip/", 1)[0]
        for path in ("/", "/clip/", "/clip/guess.wav", "/../etc/passwd"):
            with pytest.raises(urllib.error.HTTPError):
                urllib.request.urlopen(base + path)
    finally:
        clips.close()


def test_a_harness_says_where_things_are_but_never_which_pucks(monkeypatch):
    from vaani.config import from_env
    conf = parse(GOOD.format(key="k"))
    monkeypatch.setenv("VAANI_DVARA_URL", "http://sarathi-dvara:8770/")
    monkeypatch.setenv("VAANI_SPEAK_PORT", "10201")
    got = from_env(conf)
    assert got.dvara_url == "http://sarathi-dvara:8770" and got.speak_port == 10201
    assert got.pucks == conf.pucks
    monkeypatch.setenv("VAANI_LOCALHOST", "host.containers.internal")
    inside = from_env(conf)
    assert inside.hear_url == "http://host.containers.internal:11435"
    assert inside.speak_host == "host.containers.internal"
    assert inside.dvara_url == "http://sarathi-dvara:8770"       # named, so left alone
    monkeypatch.setenv("VAANI_PORT", "eighty")
    with pytest.raises(ConfigError, match="VAANI_PORT is a port number"):
        from_env(conf)


def test_status_names_a_key_file_and_never_reads_it_out(tmp_path, monkeypatch):
    import json

    from vaani import status
    key = tmp_path / "kitchen.key"
    key.write_text("c2VjcmV0\n")
    key.chmod(0o600)
    (tmp_path / "vaani.toml").write_text(GOOD.format(key=key))
    monkeypatch.setenv("VAANI_CONFIG", str(tmp_path))
    monkeypatch.setenv("VAANI_STATE", str(tmp_path / "state"))
    said = status.report()
    assert said["format"] == "vaani.status.v1" and said["serving"] is False
    assert said["pucks"][0]["key"] == "readable" and "c2VjcmV0" not in json.dumps(said)
    held = status.hold()
    try:
        assert status.report()["serving"] is True and status.hold() is None
    finally:
        held.close()
    assert status.keeps()["keeps"][0]["path"] == str(tmp_path.resolve())
