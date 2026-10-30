"""Bias: everyone at a shared puck answered by one person's agent.

A puck in the kitchen hears Mahen and Asha. Before ``agents``, Asha's
question went to the agent named on the puck, minder, which is Mahen's.
These tests are against the ways that comes back: a person heard but sent
to the puck's agent anyway, a name in ``agents`` the puck could never hear
(a line that does nothing, quietly), a change that drops everyone else's,
and ``vaani ask`` trying only the puck's own person's road.
"""

from __future__ import annotations

import pytest

from vaani import cli, dvara
from vaani.config import ConfigError, parse, with_puck

SHARED = '''
[dvara]
agent = "everyday"

[[puck]]
name = "kitchen"
host = "192.168.1.55"
key_file = "k"
person = "mahen"
agent = "minder"
people = ["mahen", "asha", "ravi"]
'''


def test_each_person_heard_is_answered_by_their_own_agent():
    puck = parse(SHARED + 'agents = { asha = "helper" }\n').puck("kitchen")
    assert puck.agent_for("asha") == "helper"
    assert puck.agent_for("mahen") == "minder"          # not named: the puck's
    assert puck.agent_for("ravi") == "minder"


def test_with_no_agent_on_the_puck_the_files_is_used():
    conf = parse(SHARED.replace('agent = "minder"\n', "") + 'agents = { asha = "helper" }\n')
    puck = conf.puck("kitchen")
    assert puck.agent_for("asha") == "helper"
    assert (puck.agent_for("mahen") or conf.agent) == "everyday"


def test_a_name_the_puck_never_hears_is_refused():
    with pytest.raises(ConfigError, match="agents names maya, who isn't its person"):
        parse(SHARED + 'agents = { maya = "helper" }\n')
    with pytest.raises(ConfigError, match="agents is a person's name and their agent's"):
        parse(SHARED + 'agents = { asha = "../x" }\n')
    with pytest.raises(ConfigError, match="agents is a person's name"):
        parse(SHARED + 'agents = ["asha"]\n')


def test_agents_are_written_in_place_and_read_back():
    after = with_puck(SHARED, "kitchen", {"agents": {"asha": "helper", "ravi": "tutor"}})
    assert 'agents = { asha = "helper", ravi = "tutor" }\n' in after
    assert dict(parse(after).puck("kitchen").agents) == {"asha": "helper", "ravi": "tutor"}
    with pytest.raises(ConfigError, match="who isn't its person"):
        with_puck(after, "kitchen", {"people": ["mahen"]})     # asha would be unheard


@pytest.fixture
def config(tmp_path, monkeypatch):
    monkeypatch.setenv("VAANI_CONFIG", str(tmp_path))
    (tmp_path / "vaani.toml").write_text(SHARED)
    return tmp_path / "vaani.toml"


def test_agent_for_adds_one_and_keeps_the_others(config):
    assert cli.main(["puck", "kitchen", "--agent-for", "asha=helper"]) == 0
    assert cli.main(["puck", "kitchen", "--agent-for", "ravi=tutor"]) == 0
    assert dict(parse(config.read_text()).puck("kitchen").agents) == {
        "asha": "helper", "ravi": "tutor"}
    assert cli.main(["puck", "kitchen", "--agent-for", "asha="]) == 0      # back to minder
    assert dict(parse(config.read_text()).puck("kitchen").agents) == {"ravi": "tutor"}


def test_ask_as_someone_else_goes_to_their_agent(config, monkeypatch, capsys):
    config.write_text(SHARED + 'agents = { asha = "helper" }\n')
    monkeypatch.setenv("VAANI_DVARA_TOKEN", "t")
    asked = []
    monkeypatch.setattr(dvara, "ask", lambda text, **kw: asked.append(kw) or {"text": "hi"})
    assert cli.main(["ask", "what's on today", "--person", "asha"]) == 0
    assert cli.main(["ask", "what's on today"]) == 0
    assert [(a["person"], a["agent"]) for a in asked] == [("asha", "helper"),
                                                          ("mahen", "minder")]
