# 06 — The next question, no wake word

A conversation at the puck went: *"Okay Nabu, what's the weather?"* —
the answer — *"Okay Nabu, and tomorrow?"* — the answer — *"Okay Nabu,
should I take an umbrella?"*. The wake word before every sentence is
how a puck starts listening, not how people talk. The puck already
listened again, with no wake word, after an answer that ended in a
question ([notes/01](01-a-voice-for-the-house.md)); an answer that
didn't ask anything closed the conversation.

## What it does

A puck can **follow up**: `follow_up = true` on it in vaani.toml, `vaani
puck kitchen --follow-up on`, or Sarathi's Settings → Vaani, *Follow-up
questions*. After every answer the puck says it, its ring stays on, and
whatever is said next is the same person's next question, in the same
conversation, with no wake word. Then the answer to that, and the puck
listens again.

It ends three ways, none of them spoken:

* **Silence.** Nothing said within the puck's own listening time: the
  run ends, the ring goes off.
* **Nothing Whisper could make words of** (a cough, a door). After an
  answer, that ends it too. The wake word's own run still says *"Sorry,
  I couldn't make out any words"*: there, somebody meant to ask.
* **Done talking.** *"Thanks"*, *"that's all"*, *"no, thank you"*,
  *"okay, bye"*, *"I'm good"* — the whole of what was said, nothing more
  — end it. Nobody's agent is asked, and nothing is said back.

## Why it is built like this

OFF UNTIL A PUCK IS SET TO IT. A puck that listens after every answer is
a microphone open for a few seconds more each time, and what it hears
in them is taken as a question. A kitchen with a radio on would hand the
agent the radio. So it is a switch per puck, off by default, and the
switch says so where it is set.

THE SAME PERSON, BY TIMING. The puck labels its listening-again run with
its wake word all the same, so a follow-up is told by when it starts:
within fifteen seconds of the puck finishing its answer (`FOLLOW_WITHIN`,
the same rule as a reply to a question). It is the person who was just
answered, with no voice match, as a reply already was: the one standing
at the puck, mid-conversation.

A CLOSING IS ENDED, NEVER ANSWERED. Whisper writes *"Thank you."* for a
quiet room more often than for anything said, so a puck that answered
"you're welcome" would talk to nobody. A closing after an answer is
nothing to say: the run ends, and the puck stops listening. Only the
whole of what was said counts (`asking.done_talking`): *"thanks, and
what about tomorrow?"* and *"stop the music"* are questions.

THE SETTING IS READ EACH QUESTION. As for who a puck answers as, the
switch is read from vaani.toml at each run, so a change in Settings
holds from the next question, with no restart.

## Someone else in the room

**AN OPEN FOLLOW-UP IS CHECKED BY VOICE ON A SHARED PUCK.** By timing
alone, Asha asking *"and my mail?"* into Mahen's follow-up was taken as
Mahen, and her mail question went to his agent. A follow-up after an
answer that asked nothing (`open_follow`) on a puck with `people` now
has its voice matched against their prints, the same match a woken
question gets (`asking.whose`). A CLEAR match to someone else makes the
question theirs (*"a follow-up in their voice (0.91)"* on the page).
Anything less stays with the person just answered: unsure, too short to
tell, nobody enrolled, a one-person puck. The one standing there,
mid-conversation, is still the best guess when the voice can't say.

A reply to a question the puck asked is never moved. It is usually a
*yes* or a number, too short for a print, and a yes is checked by voice
where it decides something (`serving.voice_of`). The match runs on the
recording already taken; what it adds is one voice print's worth of
work, the same as for any woken question on a shared puck.

`tests/test_voices.py`: an open follow-up in someone else's clear voice
is theirs; unsure, the same person, or too short stays with the one
answered; a reply to a question, a one-person puck and a puck with no
prints never match at all.

## Receipt

`tests/test_run.py` drives a run with no puck, no Whisper and no model:
a following-up puck ends its intent with `continue_conversation: "1"`
after a plain *"Sunny"*; a run after an answer where Whisper heard
nothing has no speech and asks nobody, while a wake word's run with the
same nothing still says it couldn't make anything out; a closing has no
speech and `continue_conversation: "0"`. `tests/test_waiting.py`: the
run after a plain answer is the same person's and marked open, the run
after an answer that asked back is their reply, as before.

Run at the real puck: see below.

## The first real run, and three gaps it found

At the kitchen puck, with follow-up on: *"Can you tell me outside
temperature in 10 minutes?"* The agent took longer than a minute, so the
puck said *"This is taking a while. I'll tell you here when it's done."*
Three minutes later it said the answer by itself, two numbered
questions, the last ending *"…I don't have one saved for you yet."* —
and didn't listen. The reply needed the wake word.

A QUESTION ANYWHERE IS ASKED. The puck listened only when the last
sentence ended in *"?"*. Agents ask and then explain, or number their
questions with a remark after; and a long answer said aloud is cut with
*"The rest is in the chat"*, which hid a question at its end. Now any
question in the answer, the part cut off too, keeps it listening
(`run.asks_back`). A stray *"?"* costs a few quiet seconds of listening;
a missed one costs the conversation.

AN ANSWER SAID LATER IS AN ANSWER. The one said by itself after a long
turn listened only on a question, whatever the puck's follow-up switch
said. It follows the same rule as any answer now, and after one that
asked nothing, silence ends it quietly.

NEVER AFTER "I'LL TELL YOU HERE WHEN IT'S DONE". Follow-up listened after
that notice too, and heard the room: Whisper wrote *"Thanks for
watching!"*, and it went to the agent as a new question while the real
one was still working. There is nothing to reply to until the rest is
said, so the puck doesn't listen there (`Said.later`). And Whisper's
fill-ins for silence, learned from video subtitles — *"Thanks for
watching"*, *"Please subscribe"*, a lone *"you"* — as the whole of a
reply the puck listened for are nobody talking (`asking.filler`), ended
like a closing.

THEN IT LOOPED. Each made-up line went to the agent, which took a while,
so the puck said so and listened again: *"Thanks for watching!"*, then
a line of *"༼༽༽༽…"*, each a new question in the puck's conversation,
until a silence. Not listening after the notice breaks the loop; and
what Whisper writes that is mostly not letters (in any script, a Hindi
vowel sign counting as one), or one character over and over, is nothing
heard at all, on any run (`hearing.words`). A number may repeat:
*"10000000"* is words.

`tests/test_run.py` holds the answer the puck failed on as it was said,
the bracket line it sent on,
a notice that asks and still isn't listened after, and the fill-ins.

## What is not here yet

* ~~**A follow-up from someone else.**~~ Matched by voice on a shared
  puck, moved only on a clear match (above).
* **A reply from someone else.** A reply to a question the puck asked is
  the asker's by timing; only a *yes* to a change is checked by voice.
* **How long it listens.** The puck's own listening time decides, not
  Vaani; a setting for it would need the puck's firmware.
