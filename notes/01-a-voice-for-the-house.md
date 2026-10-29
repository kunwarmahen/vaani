# 01 — A voice for the house

## The problem, as you would meet it

A Home Assistant Voice puck sits on the kitchen counter. Say its wake
word and it lights up and listens; what it can then do is whatever Home
Assistant's assistant can: lights, timers, the weather. Your agents --
the ones that read your mail, keep your schedules, know your accounts --
are behind Dvara, reachable from Telegram and a page, and not from the
one thing in the room you can just talk to.

## The puck keeps its firmware

The puck runs ESPHome. After its wake word it asks whoever is
subscribed to its voice assistant to take a run, streams its microphone
over the same encrypted connection, and follows the events it is sent:
its light ring is those events. Home Assistant is one such subscriber.
**Vaani subscribes the same way**, so nothing on the puck changes: no new
firmware, no build, nothing to flash back. What it needs is the puck's
key.

**THE KEY IS ON THE PUCK.** Home Assistant gives a puck its key when it
adopts it and keeps its own copy where its API doesn't hand it out. The
puck keeps one too, in its settings, so the key survives a restart. A
backup of the puck's whole flash -- worth having anyway before anything
is changed -- holds it. `vaani backup` reads the flash twice over USB and
keeps it only if both reads match; `vaani key` reads ESP-IDF's settings
format out of it and takes the one 32-byte value ESPHome keeps. A backup
with none or several says so instead of guessing, and `vaani check`
proves a key by connecting with it.

**ONE LISTENER AT A TIME.** A puck gives its voice to one client. While
Home Assistant holds it, Vaani connects and is ignored. Taking the puck
out of Home Assistant's ESPHome integration hands it over; adding it
back hands it back.

## A run, in the puck's own steps

```
wake word -> RUN_START, STT_START
sound     -> EndOfSpeech, until a pause
          -> STT_VAD_END, STT_END {text}        Whisper
          -> INTENT_START ... INTENT_END         Dvara
          -> TTS_START {text}, TTS_END {url}    Piper; the puck fetches the URL
          -> RUN_END
```

**THE LISTENER DECIDES WHEN THE QUESTION ENDED.** The puck streams until
told. Home Assistant uses a voice-activity model; a question to an
agent is a sentence or two in a room, so loudness does here: 30 ms
frames, the room's level from the first quarter second, speech when a
frame is three times that, and the end after 0.9 s of quiet. Nobody
speaking for five seconds ends it with nothing sent anywhere. Twenty
seconds ends it whatever is talking, so a television never holds a
puck open.

**A PUCK PLAYS AN ADDRESS.** The answer is not streamed into the puck:
it is told where the answer is, and its media player fetches it, as it
does from Home Assistant. So each spoken answer is kept a few minutes
under a long random name and served by that name alone (`clips.py`).
The address is this computer's own on the way to the puck, unless
`[serve] address` says otherwise, and the port (8799) must be open to
the puck.

**EVERY FAILURE IS SAID, OUT LOUD WHEN IT CAN BE.** Nobody reads a
kitchen puck's log. Whisper hearing nothing, Dvara not answering: the
puck says so ("I couldn't reach your agent just now"). If Piper is down
too, the error event still ends the run, so the ring never stays lit.

## Vaani knows the puck; Dvara knows the people

Which agents a person may use, their accounts, allowance, rules and the
questions waiting on them are all Dvara's. Vaani calls Dvara's
`POST /message` with its token, naming the person and the agent -- a
trusted caller, as Samay is -- and reads out what comes back. Each puck
has its own conversation per person (`vaani:<puck>`), beside Telegram's
and the home page's: "and the one before?" works at the counter.

**HEARING AND SPEAKING ARE SERVERS, NOT LIBRARIES.** Whisper is any
server with the OpenAI transcription road (`faster-whisper-server`,
whisper.cpp's, LocalAI's); Piper any on the Wyoming road
(`wyoming-piper`, which a Home Assistant house often runs already).
Each is an address in `vaani.toml`. Vaani's one dependency is ESPHome's
own client.

## Live receipt

Against a real Voice PE (ESPHome 2026.6.0, firmware 26.9.0) while Home
Assistant still held it, so read-only, and the house's own Whisper
(`faster-whisper-server`, `Systran/faster-whisper-small`), Piper
(`wyoming-piper`, `en_US-lessac-medium`) and Dvara with
`qwen3.8:latest`:

```
$ vaani backup        # by hand with esptool: two reads, sha256 9e8f861f…c5c6a9 both
$ vaani key ~/puck-backup/puck-flash-2026-10-28.bin
wrote its key into …/kitchen.key (only you can read it); `vaani check` tries it
$ vaani check
kitchen: home-assistant-voice-091194 at 192.168.1.55, ESPHome 2026.6.0, Nabu Casa.Home Assistant Voice PE 26.9.0; answers as owner with minder

$ vaani say "What's on my calendar **tomorrow**? See [the list](https://example.com/x)." --out q.wav
$ vaani hear q.wav
What's on my calendar tomorrow? See the list.

$ vaani ask "In one short sentence: what day of the week is it today?"
Today is Wednesday.                                  (48.8 s, qwen3.8:latest)
```

A whole run with a stand-in puck: Piper's "What is two plus two? Answer
in a few words." at 16 kHz with a pause each side, fed in 32 ms chunks
as the puck sends them:

```
('RUN_START', {})
('STT_START', {})
('STT_VAD_END', {})
('STT_END', {'text': 'What is 2 plus 2? Answer in a few words.'})
('INTENT_START', {})
('INTENT_END', {'continue_conversation': '0'})
('TTS_START', {'text': '4'})
('TTS_END', {'url': 'http://127.0.0.1:39985/clip/Lxj3HJQ7MiqbM947PTXRFy31.wav'})
('RUN_END', {})
fetched 24620 bytes of b'RIFF' | ended: speech
```

Not run yet: the puck itself taking a run. That needs it out of Home
Assistant, and a person in the room to hear it.

## What is not here yet

* **Who is speaking.** One puck, several people, each with their own
  accounts. Planned: a voice print per person, made once from a few
  sentences, kept in their folder, matched on this computer by a small
  speaker model. A sure match is that person; not sure, or nobody
  enrolled, is the house (house accounts only), and the puck says it
  isn't sure who's asking. "This is Asha" before a question works with
  no model at all.
* **A yes at the puck, with a PIN.** A turn that needs a yes waits for
  it on the person's phone today. Planned: the puck reads the question,
  the same voice answers yes or no, and money or anything sent outside
  the house also needs the person's spoken PIN.
* **A follow-up without the wake word** (`continue_conversation`).
* **Sarathi** starting Vaani with everything else, and its settings on
  the home page.
