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

`tests/test_run.py` holds the answer the puck failed on as it was said,
a notice that asks and still isn't listened after, and the fill-ins.

## What is not here yet

* **A follow-up from someone else.** It is the person just answered.
  Asha speaking into Mahen's follow-up is taken as Mahen; a voice match
  on follow-ups would tell them apart, at the cost of a sentence's
  wait.
* **How long it listens.** The puck's own listening time decides, not
  Vaani; a setting for it would need the puck's firmware.
