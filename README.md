# vaani — a voice puck that talks to your agents

"Okay Nabu, what's on my calendar tomorrow?"
"Okay Nabu, did the bank write back?" … "Want me to reply?" "Yes, go ahead."

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

* **Tells who is speaking**, when a puck lists `people`: a voice print
  per person, made by saying three sentences at the puck, matched on
  this computer by a small speaker model. A clear match answers as that
  person, with their own agents and accounts; unsure, the puck's own
  `person` (make it one with the house's accounts only) answers, and the
  puck says it wasn't sure. *"This is Asha, …"* works with no model.
* **Listens again when it asks you something**, no wake word, and
  starts a conversation over on *"new conversation"* or after a quiet
  spell.
* **Puts your agent's questions to you at the puck**: a yes in your own
  voice, and your spoken PIN for buying, sending or acting on what a web
  page said. A long job is finished out loud when it's done.
* **Has a page of its own**: each puck, its questions step by step as
  they happen, voices and PINs.

Not yet: a different agent per person on a shared puck; telling real
family voices apart is untried (the numbers so far are synthetic
voices); and *Hey Jarvis*, though the puck switches to it, never woke
ours (firmware 26.9.0). See [notes/01](notes/01-a-voice-for-the-house.md)
and [notes/02](notes/02-whose-question.md); the page's conversations,
[notes/03](notes/03-the-conversations-on-the-page.md).

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
sudo setfacl -m u:$USER:rw /dev/ttyACM0   # may open the puck's USB port, until unplugged
sudo usermod -aG dialout $USER            # ... or for good, from the next log-in
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
Assistant holds it, Vaani is ignored. Deleting it there also wipes the
puck's key; the first time Vaani reaches it, it gives it a new one.
Then:

```
vaani serve
```

**A yes at the puck, and long turns.** While the agent works, Vaani
looks for its questions on the puck's conversation (Dvara's `GET
/asks`) and puts each to the person: *"Your agent wants to open
google.com. Shall I go ahead?"*. Their clear yes or no goes back
(`POST /asks/ID`); Telegram has it too, and the first answer counts.
After a minute the puck says it's still working; the answer, and any
question on the way, come later as announcements (the puck listens
after a question). A yes counts in the asker's voice when the puck knows
it ("yes, go ahead": a plain "yes" is too short to tell), and a call no
standing yes covers (Yantra's `always_ask`, which Dvara's /asks now
says) needs the asker's spoken PIN: `vaani pin set NAME`, kept as a
scrypt hash in `pins/`, two tries at a time, five wrong an hour locks
it, never in the record or the log. Where Dvara offers it (a change asked
only because the agent read something, its notes/72), the puck says so,
and *"yes to all"* with the PIN covers the rest of that task's such
questions (`waiting.for_the_task`).

**The wake word** is the puck's own (Okay Nabu, Hey Jarvis, Hey
Mycroft); `wake_word = "hey_jarvis"` on a puck, or `vaani puck kitchen
--wake-word hey_jarvis`, switches it, within a minute and again on every
reconnect. Only the client holding the puck's voice is told its wake
words, so Vaani reads and sets them on its own connection.

**Talking back, starting over.** An answer that ends with a question
keeps the puck listening, no wake word: the reply is the same person's,
in the same conversation. *"New conversation"* or *"start over"* starts
the puck's conversation with that person afresh (Dvara's `/new`), and
so does a quiet spell: `fresh_after` minutes (30; 0 for never) with no
question from them there, done in the background so the next question
doesn't wait.

**Its page.** `vaani serve` also serves a page of its own on
127.0.0.1:8797 (`vaani page` prints its address with its key; with
Sarathi, its card under Your pages). **Conversations**, its first tab,
is what was asked at each puck and what was said back, read as a chat:
one conversation per puck per person, until a quiet spell started the
next, each answer's steps folded under it; to carry one on in writing,
it's in the person's list on Sarathi's home page, marked 🔊, which
picks it up by itself within about 20 seconds
([notes/03](notes/03-the-conversations-on-the-page.md)). **Setup** has
each puck listening or why not, the last questions step by step, live
from the wake word (woken, heard, whose, each step's time, played or
never fetched), a turn still being worked on, and the voices and PINs,
set and forgotten there.
`vaani runs` lists the same questions in a terminal.

**Several people at one puck.** List them on the puck (`vaani puck
kitchen --people mahen,asha --person house`, names from Dvara's actors
file; `person` is who answers when it isn't sure; read at the next
question), then:

```
uv sync --extra voices        # the speaker model's runtime (sherpa-onnx), CPU only
vaani voices fetch            # the model itself, 40 MB, once
vaani voices enroll asha --at-puck kitchen
```

and Asha says the wake word and any sentence at the kitchen puck, three
times; the puck counts down, then *"Thanks. I know asha's voice now."*
`vaani voices list`, `vaani voices forget asha`, and `vaani voices who
FILE.wav --puck kitchen` to see whose a recording is.

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

[page]                        # Vaani's own page; port = 0 for none
host = "127.0.0.1"
port = 8797

[[puck]]
name = "kitchen"
host = "192.168.1.55"
key_file = "~/.config/vaani/kitchen.key"     # chmod 600, or Vaani refuses it
person = "mahen"                             # from Dvara's actors file; unsure: this one
agent = "minder"                             # an agent every one of its people may use
# people = ["mahen", "asha"]                 # voices it tells apart
fresh_after = 30              # minutes quiet, then a new conversation (0: never)
# wake_word = "hey_jarvis"    # one the puck has (okay_nabu, hey_jarvis, hey_mycroft)

# [voices]
# threshold = 0.6                            # this close to a print to be that person
# margin = 0.15                              # and this much closer than to anyone else
```

Unknown keys are errors. `VAANI_CONFIG` names another folder;
`VAANI_DVARA_TOKEN` gives the token instead of the file. A harness (Sarathi)
says where the rest are with `VAANI_DVARA_URL`, `VAANI_HEAR_URL`,
`VAANI_SPEAK_HOST`, `VAANI_SPEAK_PORT`, `VAANI_ADDRESS`, `VAANI_PORT`,
`VAANI_PAGE_HOST` and `VAANI_PAGE_PORT`
(`VAANI_LOCALHOST`: what 127.0.0.1 is called from inside a container);
the pucks are only ever the file's. `vaani status --json` (`vaani.status.v1`)
says whether it's running and, per puck, whether it's listening (or
why not), never a key; `vaani runs --json` (`vaani.runs.v1`) the last
questions, the pucks' people and the voices known; `vaani keeps
--json` names the settings folder for a backup. One `vaani serve` at a
time (a lock in `$VAANI_STATE`, default `~/.local/state/vaani`). Open port
**8799** to the puck (`sudo ufw allow from 192.168.1.0/24 to any port 8799`):
it fetches each answer from there.

## The source

```
src/vaani/
├── cli.py        the commands
├── config.py     vaani.toml, read strictly; keys in files of their own
├── satellite.py  a puck held over ESPHome's API, kept up, a run per wake word;
│                 a puck with no key (let go by Home Assistant) given a new one
├── run.py        one run: the puck's events, Whisper, Dvara, Piper, in order
├── listening.py  the end of a question, from loudness alone
├── hearing.py    Whisper, over the OpenAI transcription road
├── speaking.py   Piper, over Wyoming; what an answer sounds like read aloud
├── dvara.py      the words to the person's agent (POST /message)
├── voices.py     who is speaking: a print per person, a small model, sure or the house
├── asking.py     whose question it is, or a sample for a print made at the puck
├── clips.py      answers kept a few minutes, served by name to the puck
├── flac.py       an answer as the puck plays it: FLAC, 48 kHz, no library
├── pins.py       spoken PINs: kept as hashes, heard as digits, few tries
├── waiting.py    a turn that asks or takes long: the question put, the answer said later,
│                 "yes to all" for the rest of a task where Dvara offers it
├── runs.py       the last fifty questions, step by step, for `vaani runs`
├── page.py       its own page (8797): pucks, questions, voices; a key, always
├── static/       the page itself: Conversations (the runs read as a chat) and Setup (notes/03)
├── keys.py       a puck's key, out of a backup of its flash
├── serving.py    `vaani serve`: every puck, and the answers they fetch
├── status.py     `vaani status --json`, `vaani keeps --json`; a lock, not a pid
└── version.py    the day of the last commit and that day's count
```

([notes/01](notes/01-a-voice-for-the-house.md) argues each of these.)

## Tests

```
uv run pytest -q        # 52 passed
```

## License

Apache-2.0.
