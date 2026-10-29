"""Bias: one person's question answered as another's.

A shared puck that names the wrong person reads one person's mail to
another. The failures worth a test are the ones that do that quietly:
a close-but-not-clear match believed, a name claimed that this puck
doesn't serve, a sample taken at the wrong puck or sent to an agent as
a question, and a puck with no people suddenly guessing.
"""

from __future__ import annotations

import pytest

from vaani import asking, status
from vaani.config import parse
from vaani.voices import Match, said_name

TOML = '''
[[puck]]
name = "kitchen"
host = "192.168.1.55"
key_file = "k"
person = "house"
agent = "minder"
people = ["mahen", "asha"]

[[puck]]
name = "study"
host = "192.168.1.56"
key_file = "k"
person = "mahen"
'''


class FakePrints:
    def __init__(self, match: Match | None = None) -> None:
        self.found = match or Match(None, 0.0, 0.0)
        self.enrolled: list[tuple[str, bool]] = []

    def match(self, wav, people, *, threshold, margin):
        assert threshold == 0.6 and margin == 0.15
        return self.found

    def enroll(self, person, wavs, *, add=False):
        self.enrolled.append((person, add))
        return len(self.enrolled)


@pytest.fixture
def conf(tmp_path, monkeypatch):
    monkeypatch.setenv("VAANI_STATE", str(tmp_path / "state"))
    return parse(TOML)


def kitchen(conf):
    return conf.puck("kitchen")


def test_a_clear_match_is_that_person(conf):
    got = asking.whose(conf, kitchen(conf), "my calendar?", b"wav",
                       FakePrints(Match("asha", 0.88, 0.12)))
    assert (got.person, got.before) == ("asha", "")


def test_unsure_is_the_house_and_the_puck_says_so(conf):
    got = asking.whose(conf, kitchen(conf), "my calendar?", b"wav", FakePrints())
    assert got.person == "house" and "not sure who's asking" in got.before


def test_a_name_said_is_believed_only_for_this_puck_s_people(conf):
    assert said_name("This is Asha, what's on my calendar?", ("mahen", "asha")) == (
        "asha", "what's on my calendar?")
    assert said_name("It's Ravi. Any mail?", ("mahen", "asha")) == (
        None, "It's Ravi. Any mail?")
    got = asking.whose(conf, kitchen(conf), "this is mahen, any mail?", b"wav",
                       FakePrints(Match("asha", 0.9, 0.1)))
    assert (got.person, got.text) == ("mahen", "any mail?")


def test_a_puck_with_no_people_never_guesses(conf):
    prints = FakePrints(Match("asha", 0.99, 0.0))
    got = asking.whose(conf, conf.puck("study"), "this is asha, any mail?", b"wav", prints)
    assert got.person == "mahen" and got.text == "this is asha, any mail?"


def test_a_print_is_made_at_its_own_puck_and_nobody_is_asked(conf):
    asking.start_enrolling("kitchen", "asha", samples=3)
    prints = FakePrints(Match("mahen", 0.9, 0.1))
    other = asking.whose(conf, conf.puck("study"), "hello", b"wav", prints)
    assert other.sample == "" and prints.enrolled == []          # another puck: a question
    said = [asking.whose(conf, kitchen(conf), f"sentence {n}", b"wav", prints).sample
            for n in range(3)]
    assert said == ["Got it. 2 more: say the wake word, then any sentence.",
                    "Got it. 1 more: say the wake word, then any sentence.",
                    "Thanks. I know asha's voice now."]
    assert prints.enrolled == [("asha", False), ("asha", True), ("asha", True)]
    assert not (status.state() / asking.ENROLLING).exists()
    after = asking.whose(conf, kitchen(conf), "my calendar?", b"wav", prints)
    assert after.sample == "" and after.person == "mahen"


def test_people_and_limits_are_checked(conf):
    from vaani.config import ConfigError
    with pytest.raises(ConfigError, match="people is a list of names"):
        parse(TOML.replace('["mahen", "asha"]', '["mahen", "../x"]'))
    with pytest.raises(ConfigError, match="voices.threshold"):
        parse(TOML + "\n[voices]\nthreshold = 3\n")



def test_a_reply_without_the_wake_word_is_the_person_who_was_asked(conf):
    prints = FakePrints(Match("asha", 0.95, 0.1))
    got = asking.whose(conf, kitchen(conf), "make it 75", b"wav", prints, follows="mahen")
    assert got.person == "mahen" and got.how == "replying to the puck"
    # a follow-up never makes someone the puck doesn't serve the asker
    got = asking.whose(conf, kitchen(conf), "make it 75", b"wav", prints, follows="ravi")
    assert got.person == "asha"
