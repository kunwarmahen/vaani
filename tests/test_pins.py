"""Bias: a yes or a PIN that lets the wrong person through, or leaks.

A puck in a kitchen is something anyone in the room can talk to. The
failures worth a test are the ones that approve what the asker didn't:
someone else's yes counted, a wrong PIN accepted, guesses allowed
forever, a PIN asked for the step but answerable by a plain yes -- and
the PIN itself written down anywhere it can be read back.
"""

from __future__ import annotations

import json

import pytest

from vaani.pins import WRONG_IN_AN_HOUR, PinError, Pins, heard_digits
from vaani.waiting import BY_PIN, BY_VOICE, judge, spoken_question


def test_a_pin_is_heard_as_digits_however_whisper_writes_them():
    assert heard_digits("1 2 3 4") == heard_digits("One, two, three, four.") == "1234"
    assert heard_digits("It's 47 oh 9.") == "4709"
    assert heard_digits("yes go ahead") == ""


def test_a_pin_is_kept_as_a_hash_only_you_can_read(tmp_path):
    pins = Pins(tmp_path / "pins")
    pins.set("mahen", "4709")
    kept = (tmp_path / "pins" / "mahen.json")
    assert "4709" not in kept.read_text() and kept.stat().st_mode & 0o777 == 0o600
    assert pins.check("mahen", "4709") and not pins.check("mahen", "4710")
    for weak in ("123", "1111", "1234", "98765", "12345678901"):
        with pytest.raises(PinError):
            pins.set("asha", weak)


def test_guesses_stop_after_five_in_an_hour_even_the_right_one(tmp_path):
    pins = Pins(tmp_path)
    pins.set("mahen", "4709")
    for n in range(WRONG_IN_AN_HOUR):
        assert not pins.check("mahen", f"000{n}", now=1000.0 + n)
    assert pins.locked("mahen", now=1010.0)
    assert not pins.check("mahen", "4709", now=1010.0)           # locked: not even checked
    assert pins.check("mahen", "4709", now=1000.0 + 3700)         # an hour on
    assert json.loads((tmp_path / "mahen.json").read_text())["wrong"] == []


def judged(**kw):
    base = dict(weighty=False, verdict=True, voice="unknown", locked=False,
                pin_ok=lambda: pytest.fail("the PIN wasn't what decided"), again=False,
                person="mahen")
    return judge(**{**base, **kw})


def test_a_no_is_a_no_whoever_says_it():
    assert judged(verdict=False, voice="someone else")[0] == "no"
    assert judged(verdict=False, weighty=True)[0] == "no"


def test_a_yes_counts_only_in_the_askers_voice_when_it_is_known():
    assert judged(voice="them")[0] == "yes"
    assert judged(voice="unknown")[0] == "yes"                    # no print: can't check
    assert judged(voice="someone else") == ("phone", "Only mahen can say yes to that.")
    assert judged(voice="unsure")[0] == "again"                   # "say: yes, go ahead"
    assert judged(voice="unsure", again=True)[0] == "phone"


def test_a_weighty_step_needs_the_pin_and_a_yes_is_not_enough():
    assert judged(weighty=True, pin_ok=lambda: False)[0] == "again"
    assert judged(weighty=True, pin_ok=lambda: False, again=True)[0] == "phone"
    assert judged(weighty=True, pin_ok=lambda: True)[0] == "yes"
    assert judged(weighty=True, verdict=None, pin_ok=lambda: True)[0] == "yes"
    assert judged(weighty=True, voice="someone else")[0] == "phone"   # never even checked
    assert judged(weighty=True, locked=True)[0] == "phone"


def test_each_question_ends_asking_so_the_puck_listens():
    from vaani.run import asks_back
    for how in (BY_PIN, BY_VOICE):
        assert asks_back(spoken_question({"summary": "send the email"}, how))


def test_a_pin_said_at_the_puck_is_never_in_its_record():
    from vaani.run import Said
    from vaani.runs import record
    said = Said(heard="four seven oh nine", secret=True)
    assert record("kitchen", "a reply", said, False)["heard"] == "(said a PIN)"
    assert record("kitchen", "", Said(heard="what day is it"), False)["heard"] == \
        "what day is it"
