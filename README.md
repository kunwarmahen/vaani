# vaani — a voice puck that talks to your agents

"Okay Nabu, what's on my calendar tomorrow?"
"Hey Jarvis, did the bank write back?"

A Home Assistant Voice puck hears its wake word, lights its ring, and
waits for someone to take the question. **Vaani** is that someone. It
holds the puck the way Home Assistant does, hears the question with a
[Whisper](https://github.com/SYSTRAN/faster-whisper) on your own
computer, hands the words to your agent through
[Dvara](https://github.com/kunwarmahen/dvara), and speaks the answer back
through the puck with [Piper](https://github.com/rhasspy/piper). The
puck keeps its own firmware. Nothing you say leaves the house.

## The name

**vaani** — वाणी (Sanskrit *vāṇī*; said roughly *vaa-nee*).

*Vāṇī* is speech, the voice, the spoken word; it is also a name of
Saraswati, who gave people speech. This program is the household's
voice: it hears what is said to the puck and says the answer.

```
   the puck (ESPHome)          Vaani                      on this computer
  ┌─────────────────┐   ┌──────────────────────┐
  │ wake word heard │──▶│ run.py               │
  │ mic streamed    │──▶│  end of speech?      │──▶ Whisper  :11435  words
  │                 │   │  who's asking (puck) │──▶ Dvara    :8770   the person's agent
  │ ring follows    │◀──│  events              │──▶ Piper    :10200  the answer, spoken
  │ plays the URL   │◀──│ clips.py  :8799      │
  └─────────────────┘   └──────────────────────┘
```

## What it does, and what it doesn't

* **Holds each puck over ESPHome's API**, with the puck's own key, and
  keeps the connection up through Wi-Fi drops and restarts.
* **Hears the end of a question by itself** (a pause after speech), stops
  after twenty seconds whatever is playing nearby, and sends nothing
  anywhere when nobody spoke after the wake word.
* **Answers as a person, through Dvara**: their agents, accounts,
  allowance, rules and questions are Dvara's, and each puck keeps its own
  conversation (`vaani:<puck>`).
* **Reads answers the way they should be heard**: no asterisks, links by
  their words, code and tables left in the chat, long answers cut at a
  sentence.
* **Says what went wrong, out loud**: "I couldn't reach your agent".

Not yet: telling who is speaking (a voice print per person, so one puck
serves everyone with their own accounts), and a yes said at the puck
with a PIN. Today each puck answers as the one person its settings name.
See [notes/01](notes/01-a-voice-for-the-house.md).

## Install

```
git clone https://github.com/kunwarmahen/vaani && cd vaani && uv sync
```

You need, on this computer or the house's network:

* **Whisper** with the OpenAI transcription road, e.g.
  `podman run -d -p 11435:8000 fedirz/faster-whisper-server:latest-cuda`
* **Piper** on the Wyoming road, e.g.
  `podman run -d -p 10200:10200 rhasspy/wyoming-piper --voice en_US-lessac-medium`
* **Dvara**, running, with its token.
* The puck, on your Wi-Fi.

## Set it up

```
vaani backup                       # the puck's whole flash, read twice (USB-C)
vaani key ~/puck-backup/puck-flash.bin   # its key, out of that backup
vaani init --puck kitchen --host 192.168.1.55 --person mahen --agent minder
vaani check
```

`vaani check` connects and says what it found:

```
kitchen: home-assistant-voice-091194 at 192.168.1.55, ESPHome 2026.6.0, Nabu Casa.Home Assistant Voice PE 26.9.0; answers as mahen with minder
```

**Take it from Home Assistant** (Settings → Devices → ESPHome → the
puck → Delete). A puck gives its voice to one listener; while Home
Assistant holds it, Vaani is ignored. Then:

```
vaani serve
```

Each step can be tried on its own, with no puck speaking:

```
vaani say "What's on my calendar tomorrow?" --out q.wav    # Piper
vaani hear q.wav                                           # Whisper
vaani ask "In one sentence: what day is it?"               # Dvara, as the puck's person
```

## Settings: `~/.config/vaani/vaani.toml`

```toml
[dvara]
url = "http://127.0.0.1:8770"
token_file = "~/.config/vaani/dvara.token"    # chmod 600

[hear]
url = "http://127.0.0.1:11435"
model = "Systran/faster-whisper-small"
# language = "en"

[speak]
host = "127.0.0.1"
port = 10200
# voice = "en_US-lessac-medium"

[serve]
# address = "192.168.1.20"   # where a puck fetches answers (default: found)
port = 8799

[[puck]]
name = "kitchen"
host = "192.168.1.55"
key_file = "~/.config/vaani/kitchen.key"     # chmod 600, or Vaani refuses it
person = "mahen"                             # from Dvara's actors file
agent = "minder"
```

Unknown keys are errors. `VAANI_CONFIG` names another folder;
`VAANI_DVARA_TOKEN` gives the token instead of the file. A harness (Sarathi)
says where the rest are with `VAANI_DVARA_URL`, `VAANI_HEAR_URL`,
`VAANI_SPEAK_HOST`, `VAANI_SPEAK_PORT`, `VAANI_ADDRESS` and `VAANI_PORT`;
the pucks are only ever the file's. `vaani status --json` (`vaani.status.v1`)
says whether it's listening and which pucks, never a key; `vaani keeps
--json` names the settings folder for a backup. One `vaani serve` at a
time (a lock in `$VAANI_STATE`, default `~/.local/state/vaani`). Open port
**8799** to the puck (`sudo ufw allow from 192.168.1.0/24 to any port 8799`):
it fetches each answer from there.

## The source

```
src/vaani/
├── cli.py        the commands
├── config.py     vaani.toml, read strictly; keys in files of their own
├── satellite.py  a puck held over ESPHome's API, kept up, a run per wake word
├── run.py        one run: the puck's events, Whisper, Dvara, Piper, in order
├── listening.py  the end of a question, from loudness alone
├── hearing.py    Whisper, over the OpenAI transcription road
├── speaking.py   Piper, over Wyoming; what an answer sounds like read aloud
├── dvara.py      the words to the person's agent (POST /message)
├── clips.py      answers kept a few minutes, served by name to the puck
├── keys.py       a puck's key, out of a backup of its flash
├── serving.py    `vaani serve`: every puck, and the answers they fetch
├── status.py     `vaani status --json`, `vaani keeps --json`; a lock, not a pid
└── version.py    the day of the last commit and that day's count
```

([notes/01](notes/01-a-voice-for-the-house.md) argues each of these.)

## Tests

```
uv run pytest -q        # 16 passed
```

## License

Apache-2.0.
