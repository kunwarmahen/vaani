# 05 — What a yes is to

A yes at the puck is said to something heard, not something read. Two
things followed from one afternoon at the kitchen puck.

## The problem, as it was met

The person asked for a flight to Phoenix, heard the fares, and said
"Yes!" to *"want me to keep an eye on the price?"*. The agent previewed
a watch and asked to make it. The puck put the question by reading the
card Yantra writes for a screen:

```
Your agent wants to new watch: (no name). What it looks at, with no model every 6h: browser_open {"url": "https://www.google.com/travel/flights?hl=en&tfs=CBwQ…
```

Thirteen seconds after "Yes!", while that turn was still working and no
question was being put, the puck heard *"Yes, yes, yes."* With nothing
to answer, it was sent to Dvara as a turn of its own, on the same
conversation. That turn read the same history — the agent's offer to
watch the price — and made a second watch on the same page. A day later
the person couldn't tell one from the other, and took the second for a
temperature watch.

## What the puck does now

**A WATCH IS ASKED IN A SENTENCE.** A question whose summary is a watch
card (`New watch: …`) is said as one sentence: its name, the site it
looks at and how often, and when it tells you —

```
Your agent wants to set up a watch called Phoenix nonstop under $571: it looks at google.com every 6 hours, and tells you when the fare is below 571. Shall I go ahead?
```

The card, with the exact call and what a yes allows, stays on the phone,
where it can be read. What is said at the puck is what the person can
judge by ear.

**A YES WITH NOTHING TO ANSWER IS NOT A NEW TURN.** While a turn works
at a puck and no question is put, a yes or a no answers nothing and
starts nothing: the puck says *"I'm still working on that. If I need a
yes, I'll ask you here."* Anything else is still a question of the
person's own, as before; and once the turn is done, a yes is a reply to
whatever the agent last said, as it always was.

`waiting.route` makes that call — *answer*, *busy* or *new* — where it
can be tested on its own, away from the puck.

## Tests

`tests/test_waiting.py`: the flights card said as its sentence (no JSON,
no tool name), an unnamed one and a daily one; "Yes, yes, yes." while a
turn works is *busy*, the same words to a question put are *answer*,
and after the turn is done they are *new*. 64 passed (was 62).

## What is not here yet

* **A spoken schedule.** Samay's card would read just as badly; it has
  no sentence yet.
* **Heard for real.** The rules are tested; the kitchen puck hasn't said
  the new sentence yet (it needs the rebuild).
