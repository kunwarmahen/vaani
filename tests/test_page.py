"""Bias: a page that opens a puck's voices to whoever asks.

Vaani's page can start a voice being learned -- the next three things
said at a puck become someone's voice print -- so the failures worth a
test are the ones that let that happen to the wrong person: an /api call
without the page's key, a name that isn't a name, a person the puck
doesn't tell apart, a key file others can read. And a page that shows
nothing of what the serve knows is no use: the state carries the runs.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

from vaani import asking, page, runs, status

TOML = '''
[[puck]]
name = "kitchen"
host = "192.168.1.55"
key_file = "k"
person = "house"
people = ["mahen", "asha"]
'''


class FakePrints:
    def __init__(self):
        self.gone = []

    def known(self):
        return {"mahen": {"samples": 3, "embedding": [0.1] * 192}}

    def forget(self, person):
        self.gone.append(person)
        return True

    def _extract(self):
        return None


@pytest.fixture
def served(tmp_path, monkeypatch):
    monkeypatch.setenv("VAANI_CONFIG", str(tmp_path))
    monkeypatch.setenv("VAANI_STATE", str(tmp_path / "state"))
    monkeypatch.delenv("VAANI_PAGE_TOKEN", raising=False)
    (tmp_path / "vaani.toml").write_text(TOML)
    runs.Book().add({"puck": "kitchen", "heard": "what day is it", "url": "u"})
    prints = FakePrints()
    server = page.PageServer(prints, page.page_token(), host="127.0.0.1", port=0).start()
    yield server
    server.close()


def call(server, path, body=None, token=None):
    req = urllib.request.Request(
        f"http://127.0.0.1:{server.port}{path}", method="POST" if body is not None else "GET",
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {token or server.token}",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as res:
            return res.status, json.loads(res.read() or b"{}")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


def test_the_page_is_open_but_every_api_call_needs_its_key(served):
    with urllib.request.urlopen(f"http://127.0.0.1:{served.port}/", timeout=5) as res:
        assert b"Vaani" in res.read()
    assert call(served, "/api/state", token="wrong-token-wrong")[0] == 401
    assert call(served, "/api/voices/enroll", {"person": "asha", "puck": "kitchen"},
                token="wrong-token-wrong")[0] == 401
    assert asking.enrolling() is None
    kept = status.state() / page.TOKEN_FILE
    assert kept.read_text().strip() == served.token and kept.stat().st_mode & 0o777 == 0o600


def test_the_state_has_the_runs_and_never_a_voice_print(served):
    code, got = call(served, "/api/state")
    assert code == 200 and got["runs"][0]["heard"] == "what day is it"
    assert got["pucks"][0]["people"] == ["mahen", "asha"]
    assert got["voices"] == [{"person": "mahen", "samples": 3}]      # no embedding


def test_a_voice_is_learned_only_for_someone_the_puck_tells_apart(served):
    assert call(served, "/api/voices/enroll", {"person": "../x", "puck": "kitchen"})[0] == 400
    code, said = call(served, "/api/voices/enroll", {"person": "ravi", "puck": "kitchen"})
    assert code == 400 and "isn't one of the people" in said["detail"]
    assert call(served, "/api/voices/enroll", {"person": "asha", "puck": "attic"})[0] == 400
    assert asking.enrolling() is None
    code, said = call(served, "/api/voices/enroll", {"person": "asha", "puck": "kitchen"})
    assert code == 200 and asking.enrolling()["person"] == "asha"
    assert call(served, "/api/voices/stop", {})[1]["said"].startswith("Stopped")
    assert asking.enrolling() is None
    assert call(served, "/api/voices/forget", {"person": "mahen"})[0] == 200
    assert served.prints.gone == ["mahen"]


def test_a_pin_is_set_from_the_page_and_never_shown_back(served):
    code, said = call(served, "/api/pins/set", {"person": "asha", "pin": "4709"})
    assert code == 200 and "4709" not in json.dumps(said)
    code, got = call(served, "/api/state")
    assert got["pins"] == ["asha"] and "4709" not in json.dumps(got)
    assert call(served, "/api/pins/set", {"person": "asha", "pin": "1111"})[0] == 400
    assert call(served, "/api/pins/set", {"person": "asha", "pin": "4709"},
                token="wrong-token-wrong")[0] == 401
    assert call(served, "/api/pins/forget", {"person": "asha"})[0] == 200
    assert call(served, "/api/state")[1]["pins"] == []


def _script() -> str:
    from importlib.resources import files
    html = files("vaani").joinpath("static", "index.html").read_text()
    return html[html.index("<script>") + len("<script>"):html.rindex("</script>")]


def _node():
    import shutil
    node = shutil.which("node", path="/usr/bin:/usr/local/bin:/bin")
    if node is None:
        pytest.skip("node is not installed")
    return node


def test_the_pages_script_parses_and_has_both_tabs(tmp_path):
    import subprocess
    from importlib.resources import files
    script = tmp_path / "page.js"
    script.write_text(_script())
    done = subprocess.run([_node(), "--check", str(script)], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    html = files("vaani").joinpath("static", "index.html").read_text()
    for panel in ('id="talks-view"', 'id="setup-view"', 'data-tab="talks"', 'data-tab="setup"'):
        assert panel in html


def test_a_conversation_is_one_puck_and_one_person_until_it_started_over():
    # The page reads the runs as the puck keeps conversations: per puck, per
    # person, ended by the quiet that starts the next question afresh, and
    # only where something was heard (a silent wake stays in Setup's list).
    import subprocess
    js = _script()
    fn = js[js.index("function conversations("):js.index("function drawTalks(")]
    runs_newest_first = [
        {"id": "6", "at": 6, "puck": "kitchen", "person": "mahen", "heard": "and tomorrow?"},
        {"id": "5", "at": 5, "puck": "kitchen", "person": "mahen", "heard": "weather?",
         "started_over": False},
        {"id": "4", "at": 4, "puck": "kitchen", "person": "asha", "heard": "a timer"},
        {"id": "3", "at": 3, "puck": "kitchen", "person": "mahen", "heard": "bins?",
         "started_over": True},
        {"id": "2", "at": 2, "puck": "kitchen", "person": "mahen", "heard": ""},
        {"id": "1", "at": 1, "puck": "hall", "person": "mahen", "heard": "lights"},
    ]
    probe = (fn + f"const got = conversations({json.dumps(runs_newest_first)}, "
             "[{name: 'kitchen', working: {person: 'mahen'}}]);"
             "process.stdout.write(JSON.stringify(got.map((c) => "
             "[c.puck, c.person, c.runs.map((r) => r.id), Boolean(c.working)])));")
    done = subprocess.run([_node(), "-e", probe], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout) == [
        ["kitchen", "mahen", ["5", "6"], True],
        ["kitchen", "asha", ["4"], False],
        ["kitchen", "mahen", ["3"], False],
        ["hall", "mahen", ["1"], False],
    ]
