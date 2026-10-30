# Vaani, step by step

This takes a Home Assistant Voice puck and makes it talk to your own
agents. You say the wake word, ask your question, and the answer comes
back out of the puck, worked out by the agent that knows your mail,
calendar and accounts. It all happens on your computer.

You need:

* **The puck** (Home Assistant Voice Preview Edition), set up on your
  Wi-Fi once, the usual way. It may still be in Home Assistant for now.
* **Dvara** running, with you in its people list (Sarathi sets this up).
* **Whisper** and **Piper**, the programs that turn speech into words and
  words into speech. If your Home Assistant does voice on this computer,
  you probably have both already.
* A USB-C cable, once, for the backup.

## Step 1 · Install

```
cd ~/Documents/ai/agent
git clone https://github.com/kunwarmahen/vaani
cd vaani && uv sync
```

Check Whisper and Piper are there:

```
curl -s http://127.0.0.1:11435/v1/models | head -c 80     # Whisper
nc -z 127.0.0.1 10200 && echo piper is there              # Piper
```

No Whisper? `podman run -d --name whisper -p 11435:8000
docker.io/fedirz/faster-whisper-server:latest-cpu` (`-cuda` with an
NVIDIA card). No Piper? `podman run -d --name piper -p 10200:10200
docker.io/rhasspy/wyoming-piper --voice en_US-lessac-medium`.

## Step 2 · Back up the puck

Before anything else, keep a copy of everything on the puck. It's how
you'd put it back exactly as it was, and it's also where its key comes
from.

Plug the puck into this computer with USB-C. It shows up as
`/dev/ttyACM0` (`ls /dev/ttyACM*` while it's plugged in; unplug it and
the name goes away). Ordinary users aren't allowed to open it, so
first give yourself permission, one of two ways:

```
sudo setfacl -m u:$USER:rw /dev/ttyACM0     # for now: until you unplug it
sudo usermod -aG dialout $USER              # for good: from your next log-in
```

The first works straight away, but only for this time plugged in. The
second puts you in the group that may use serial ports (`dialout`), so
you never need to do it again, but it only takes effect after you log
out and back in (or restart). Doing both is fine. Without either,
`vaani backup` stops and tells you which line to run.

Then:

```
uv run vaani backup
```

It reads the puck twice (a minute or two each; the puck restarts) and
keeps the copy only if both reads match:

```
kept /home/you/puck-backup/puck-flash.bin (sha256 9e8f861f…); both reads matched.
It holds the puck's Wi-Fi password: keep it private.
```

## Step 3 · Tell Vaani about the puck

Find its address: your router's list, or `avahi-browse -rt
_esphomelib._tcp`. Find your name in Dvara: it's the `[actor.NAME]` in
`~/dvara/actors.toml` (often `owner`).

```
uv run vaani init --puck kitchen --host 192.168.1.55 --person owner --agent minder
uv run vaani key ~/puck-backup/puck-flash.bin
```

Give it Dvara's token (Sarathi keeps it):

```
grep '^DVARA_TOKEN=' ~/.config/sarathi/secrets.env | cut -d= -f2- > ~/.config/vaani/dvara.token
chmod 600 ~/.config/vaani/dvara.token
```

Now check:

```
uv run vaani check
```

You should see the puck by name, its firmware, and who it answers as.
*"the key is wrong"* means the backup's key isn't the one the puck uses:
take a new backup.

## Step 4 · Try each part, quietly

None of these makes the puck speak:

```
uv run vaani say "What's on my calendar tomorrow?" --out q.wav
uv run vaani hear q.wav
uv run vaani ask "In one sentence: what day is it?"
```

`say` makes the sound, `hear` turns it back into words, and `ask` gets
your agent's answer as text. If one fails, it says which program didn't
answer.

## Step 5 · Take the puck from Home Assistant

A puck listens to one helper at a time. In Home Assistant: **Settings →
Devices & services → ESPHome → the puck → ⋮ → Delete**. (Adding it back
later gives it back to Home Assistant; your backup isn't needed for
that.)

Deleting it there also wipes the puck's key, so the key you took from
the backup stops working. You don't have to do anything about it: the
first time Vaani reaches the puck, it gives it a brand-new key and
keeps it in the same key file. The log says so once:

```
kitchen: it had no key (let go by Home Assistant?); gave it a new one, kept in …/kitchen.key
```

Open the port the puck fetches answers from:

```
sudo ufw allow from 192.168.1.0/24 to any port 8799
```

## Step 6 · Talk to it

```
uv run vaani serve
```

```
23:40:02 answers served at http://192.168.1.20:8799/clip/
23:40:03 kitchen: listening (home-assistant-voice-091194, Nabu Casa.Home Assistant Voice PE 26.9.0), answering as owner
```

Say the wake word (*"Okay Nabu"* unless you've changed it, see below),
wait for the ring, and ask *"what's on my calendar
tomorrow?"*. The ring spins while your agent works (a local model can
take half a minute), then the puck says the answer. The log says what
it heard and what it answered:

```
23:41:10 kitchen: woken by 'Okay Nabu'
23:41:42 kitchen: speech -- heard "What's on my calendar tomorrow?", answered 'You have the dentist at 10…'
```

The whole answer is also in Dvara's record of what each message did
(`dvara runs`), marked as come by *vaani*.

**When your agent needs your yes.** Some things an agent does need
your say-so first: opening a browser, sending something, spending. At
the puck, it asks you: *"Your agent wants to open google.com. Shall I go
ahead?"*, then listens. Say *"yes"* or *"no"* (*"go ahead"*, *"sure"*,
*"don't"* work too). Anything else gets *"was that a yes or a no?"*
once. The same question is on your phone as well, and whichever you
answer first counts.

* **Only you can say yes to your question.** Once the puck knows your
  voice (Step 7), it asks you to say *"yes, go ahead"*, which is long
  enough to tell your voice from someone else's. Another person's yes
  isn't counted, and if it can't tell, it asks you once more and then
  leaves the question on your phone. A *"no"* from anyone always counts.
* **The bigger things need your PIN.** Buying, sending, or changing
  something after your agent read a web page or an email: the puck says
  *"…That needs your PIN, said one digit at a time. Shall I?"*. Say it
  like *"four, seven, oh, nine"*. A wrong PIN gets one more try, then
  the question goes to your phone, and five wrong in an hour locks it at
  the puck for the hour. Set a PIN with `uv run vaani pin set mahen`
  (or on Vaani's page, **Setup → PINs**). It's kept only as a scrambled
  hash, never sent to your agent, and never written in the log or on
  the page. Someone in the room can hear you say it, so pick one you
  don't use for your bank card. With no PIN set, those steps are asked
  on your phone. (A web search that types into a page after reading it
  counts as one of these, so a flight search would ask for it a few
  times. When the question is one of those, the puck adds *"Say yes to
  all to stop asking for the rest of this."* Say *"yes to all, four,
  seven, oh, nine"*, and the rest of that search's steps aren't asked,
  unless your agent reads something new. A purchase still asks every
  time.)

**When it takes a while.** After a minute the puck says *"This is
taking a while. I'll tell you here when it's done."* and the ring stops.
When the answer is ready, the puck says it by itself. If the agent
needs your yes in the meantime, the puck asks then, and listens.

**The wake word.** The puck knows three: *Okay Nabu*, *Hey Jarvis* and
*Hey Mycroft*, and listens for one. Choose it with `uv run vaani puck
kitchen --wake-word hey_jarvis` (or with Sarathi in **Settings → Vaani**):
the puck switches within a minute, and Vaani sets it again whenever it
reconnects. Vaani's page says which one it's listening for. Something
close to the wake word (*"OK Jarvis"*) can wake it on a *Very sensitive*
puck; the log and the page then say the wake word the puck thought it
heard. On our puck (firmware 26.9.0) *Hey Jarvis* switched on but never
woke it, however clearly it was said, while *Okay Nabu* works every time;
if a word doesn't wake yours, switch back.

**When it asks you something back**, you can just answer. If the
answer ends with a question (*"…it's at 79. Want it set to a different
temperature?"*), the puck lights up again once it has said it and
listens, with no wake word. Say *"make it 75"* and it's answered as you,
in the same conversation. Say nothing and the ring goes out after a few
seconds.

**To start a new conversation**, say the wake word, then *"new
conversation"* (or *"start over"*, *"start fresh"*). The puck says
*"Starting fresh. What would you like to ask?"* and listens for your
question. It also starts over by itself after 30 minutes with no
questions from you at that puck, so tomorrow's first question isn't
read against today's talk. Change the 30 (or set 0 for never) with
`uv run vaani puck kitchen --fresh-after 60`, or with Sarathi in
**Settings → Vaani**. Until then everything you ask at that puck is one
conversation, so *"and the one before?"* works. The old one isn't lost:
it's in your conversations on Telegram or the home page (`/chats`). Only
those words on their own start over: *"tell me about the new
conversation with Ravi"* is a question like any other.

## When something's off

| You see or hear | Why | What to do |
|---|---|---|
| The ring lights, then nothing, and the log says nothing | Home Assistant still holds the puck | Step 5 |
| `vaani status` says *not listening: …* (Sarathi's Check: *the kitchen puck isn't listening*) | Vaani is running but can't hold the puck; the reason is on the line | the reason says which: the address, the key, or Home Assistant |
| *"Sorry, I couldn't reach your agent just now."* | Dvara isn't running, or the token is wrong | `vaani ask "hi"` says which |
| *"Sorry, I couldn't make out any words."* | Whisper heard nothing, or isn't running | `vaani hear q.wav` |
| The ring finishes but no sound | The puck can't reach port 8799 | no `answer fetched by …` line in the log: the `ufw` line in Step 5; `[serve] address` if this computer has several |
| `… can be read by others; chmod 600 …` | The key file is open to others | run the `chmod` it shows |
| `/dev/ttyACM0 can't be opened` (backup) | you may not open the puck's USB port | the two `sudo` lines in Step 2 |
| The log says *it had no key … gave it a new one* | You deleted the puck from Home Assistant, which wipes its key | nothing: Vaani gave it a new one. The key in your backup's `api-key.txt` is now the old one |
| Vaani's page: a question ends *never fetched* | Vaani answered, the puck never came for the sound | the `ufw` line in Step 5 |

## Watching it: Vaani's page

While `vaani serve` runs, Vaani has a page of its own. Print its
address (it carries the page's key, so keep it to yourself) and open it:

```
uv run vaani page
http://127.0.0.1:8797/#token=…
```

With Sarathi, it's the **Vaani** card under **Your pages**, already
signed in. It opens on **Conversations**: what was asked at each puck
and what your agents said back, like a chat. The list on the left has
one conversation per puck per person (*what's the weather tomorrow? ·
🔊 kitchen · mahen · 4 min ago*); pick one to read it on the right.
**Steps** under an answer shows how it went. You can't write there: to
carry a conversation on in writing, open Sarathi's home page, where
it's in that person's list marked 🔊. It shows there without a reload,
within about 20 seconds of the question: the question first, and the
answer once the puck has it.

The **Setup** tab shows:

* **Each puck**, green while it's listening, red with the reason when
  it isn't (*"The device is using plaintext protocol"*, *not reached
  yet*).
* **The last questions**, newest first, each with its steps: *woken by
  Okay Nabu → heard 0.8s → as owner (the puck's person) → agent 47s →
  spoken 0.4s → played*. The step that stopped is red. *never fetched*
  means Vaani answered but the puck never came for the sound: that's
  the firewall (Step 5).
* **A question still being worked on**, on top: *"find me a flight…" ·
  7 min so far · agent still working…* (or *waiting for your yes*),
  until the puck says the answer.
* **Voices**, with *Learn their voice* and *Forget* (Step 7).
* **PINs**: set or forget each person's spoken PIN (Step 6).

A question shows up the moment the puck wakes, and fills in as each
step ends: *listening… → hearing… → agent working… → speaking… → puck
fetching… → played*. The page checks every second while a question is
going and every few seconds otherwise.

In a terminal, `uv run vaani runs` lists the same questions, one line
each.

## Step 7 · Everyone in the house, each their own

(With Sarathi: tick the people in **Settings → Vaani**, then press
**Learn their voice** on Vaani's page. The commands below do the same.)

So far the puck answers as one person. To have it tell people apart,
so each gets their own calendar and mail:

1. **Make a "house" person in Dvara** with only the house's accounts
   (Sarathi's Settings → People → Add, Accounts: *None* or a shared
   one). The puck answers as them when it isn't sure who's asking.
2. **List the people on the puck**: `uv run vaani puck kitchen --people
   owner,asha --person house`. That's the same as editing
   `~/.config/vaani/vaani.toml` like this (the old file is kept as
   `vaani.toml.bak`), and it applies from the next question:

   ```toml
   [[puck]]
   name = "kitchen"
   ...
   person = "house"                   # when it isn't sure
   agent = "minder"                   # one every person below may use
   people = ["owner", "asha"]
   ```

3. **Get the voice model** (once):

   ```
   uv sync --extra voices
   uv run vaani voices fetch
   ```

4. **Each person teaches it their voice**, with `vaani serve` running.
   On Vaani's page, **Setup → Voices**: pick *asha* and the puck, press
   **Learn their voice**. Or in a terminal:

   ```
   uv run vaani voices enroll asha --at-puck kitchen
   ```

   Asha then says the wake word and any sentence at the puck, three
   times. The puck answers *"Got it. 2 more…"*, *"Got it. 1 more…"*,
   then *"Thanks. I know asha's voice now."*

Now *"what's on my calendar?"* is answered from the calendar of whoever
asked. When the puck isn't sure, it begins *"I'm not sure who's asking,
so I'm answering for house."* Starting with *"This is Asha, …"* always
works. `uv run vaani voices list` shows whose voices it knows;
`uv run vaani voices forget asha` deletes one.

If it often isn't sure about someone, teach them again (more samples
help), or lower `threshold` under `[voices]` a little (0.6 to 0.5).

## What it doesn't do yet

* **A different agent per person.** A puck has one agent, and everyone
  it tells apart must be allowed that agent in Dvara.
* **Real family voices are untried.** The numbers so far come from
  synthetic voices, which differ more than a family's. If it's often
  unsure, teach voices again or lower `threshold` (Step 7).
* **Hey Jarvis** switches on but never woke our puck. If a wake word
  doesn't work on yours, go back to Okay Nabu.
