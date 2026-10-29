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

**LET GO, THE PUCK HAS NO KEY.** Home Assistant clears a puck's key when
it is deleted there, so the puck talks unencrypted and refuses the key
from the backup. Vaani then does what Home Assistant does on adopting
one: a new random key, written to the key file *first* (a key the puck
took and Vaani lost would lock Vaani out), then given to the puck. This
puck's firmware offers only the plain connection for that, so the key
crosses the house's network once in the clear, as Home Assistant's
would; a newer one that accepts the all-zero key gets it encrypted. A
new key rather than the old one, since Home Assistant still has the
old. ESPHome takes it as base64 text, not the 32 bytes -- given bytes,
it just says no.

**EACH RUN LEAVES A RECORD** (`runs.py`): woken by what, heard what, whose
it was taken to be and why, how long Whisper, the agent and Piper each
took, the answer or the error, and -- added when it happens, after the
run has ended -- whether the puck came for the answer. The last fifty, in
the state folder (yours alone). `vaani runs` reads them, and so does
Vaani's own page. The record is made at the wake word (`live`) and
written again as each step ends, so the page shows a question while
the agent is still on it; it asks every second only while one is live.

**A PAGE OF ITS OWN, ON A PORT OF ITS OWN** (`page.py`). The running
serve knows what no other program can -- each puck held or why not,
each run as it ends, the fetch after it -- so the page is served by it,
as Prahari's is by its watch, with a card on Sarathi's Your pages. Not
on 8799: that port is open to the house so a puck can fetch a sound,
and it serves nothing else. The page is on 8797, on 127.0.0.1 unless a
harness says otherwise, with a key on every `/api` call (made once,
kept in the state folder, read by Sarathi to open it signed in). It
changes voices -- learned at the puck, or forgotten -- and nothing else:
who a puck answers (`person`, `agent`, `people`) is a setting, in
vaani.toml (`vaani puck`; Sarathi's Settings → Vaani), read at each
question, so a change needs no restart.

**THE WAKE WORD IS SET BY WHOEVER HOLDS THE VOICE.** The firmware has
three (Okay Nabu, Hey Jarvis, Hey Mycroft) and listens for one at a
time. Asked by any other client, a puck says it offers none; asked by
the subscriber, it lists all three and which is on (this one said Okay
Nabu *and* Hey Jarvis, with one allowed). So the puck's `wake_word` is
applied on Vaani's own connection, right after subscribing, and again
within a minute of the setting changing. The puck logs
`Enabled wake word: Hey Jarvis`.

**RUNNING IS NOT LISTENING.** The serve records, per puck, whether it is
held and the last reason it isn't; `vaani status` and Sarathi's Check
say that, so a serve retrying a refused puck every five seconds is red,
not green.

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

**IN THE PUCK'S OWN FORMAT.** The puck lists what its player takes:
FLAC at 48 kHz. Given Piper's WAV it fetched it and gave up ("Could
not determine audio file type"), so the ring spun and went out with
nothing said. `flac.py` writes FLAC with no library: the samples kept
as they are ("verbatim"), stretched from 22 050 to 48 000 Hz, plus the
format's headers and two checksums. Each fetch is a line in the log
(`answer fetched by 192.168.1.55`), so a silent puck shows whether it
asked at all.

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
('TTS_END', {'url': 'http://127.0.0.1:39985/clip/Lxj3HJQ7MiqbM947PTXRFy31.wav'})   # FLAC since
('RUN_END', {})
fetched 24620 bytes of b'RIFF' | ended: speech
```

Taken from Home Assistant (2026-10-29): the serve's log said *"The
device is using plaintext protocol"* every five seconds while Sarathi's
Check said *Vaani is listening* -- both now fixed. Then:

```
kitchen: it had no key (let go by Home Assistant?); gave it a new one, kept in ~/.config/vaani/kitchen.key
09:45:36 kitchen: listening (home-assistant-voice-091194, Nabu Casa.Home Assistant Voice PE 26.9.0), answering as owner
11:45:10 kitchen: woken by 'Okay Nabu'
11:46:18 kitchen: speech -- heard 'What day is it?', answered "It's Thursday, October 29, 2026."
```

and the puck said nothing. Its own log (ESPHome's, read over the same
API) told why: `micro_decoder.audio_reader: Could not determine audio
file type from URL or Content-Type`. The same sentence as FLAC at 48 kHz
played.

## What is not here yet

* ~~**Who is speaking.**~~ A voice print per person, made at the puck,
  matched here; unsure is the puck's own person, said so
  ([02](02-whose-question.md)).
* **A yes at the puck, with a PIN.** A turn that needs a yes waits for
  it on the person's phone today. Planned: the puck reads the question,
  the same voice answers yes or no, and money or anything sent outside
  the house also needs the person's spoken PIN.
* ~~**A follow-up without the wake word.**~~ An answer whose last
  sentence is a question ends its intent with `continue_conversation:
  "1"`; the puck says it, then starts a run with no wake word. Within
  two minutes such a run is the reply of whoever was asked -- no voice
  match, the same person, the same Dvara conversation -- and silence is
  just no reply. "New conversation" / "start over" (the whole of what
  was said, nothing else) sends Dvara `/new` and the puck asks what's
  next, so it listens again too. And a quiet spell does it by itself:
  `fresh_after` minutes (30; 0 for never) with no question from a person
  at a puck, checked every minute in the background -- not when the next
  question comes, which would make that question wait for Dvara's look
  back. A start-over is marked on that person's newest record, so a
  serve that starts again doesn't send it twice.
* ~~**Sarathi**~~ starts Vaani with everything else (`[vaani] on`), and
  its Your pages has Vaani's own page (each run, the voices) and its
  Settings → Vaani the puck's people.
