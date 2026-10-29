# 03 — The conversations on the page

Vaani's page was built for finding faults. Each question was a row of
chips (*woken → heard 0.8s → as mahen → agent 4.2s → spoken → played*),
so a puck that said nothing showed where it stopped. That's the right
view when something is wrong. When nothing is, it's the wrong one: the
page said a lot about steps and little about what the house asked and
what it was told.

## Two tabs

**CONVERSATIONS** is what was asked and what was said back, read as a
chat. A list of conversations is on the left (the first question, the
puck, whose it was, how long ago) and the one you picked is on the
right: the person's words as bubbles, each answer under them, and
**Steps** folded under each answer for when you want the chips back.
A turn still being worked on ends the conversation with *agent still
working…* or *waiting for a yes*.

**SETUP** is everything the page was before: the pucks, the last
questions step by step, voices, PINs. It's at its own address,
`#setup`, so a reload stays put.

## One puck, one person, until it started over

**A CONVERSATION IS WHAT THE PUCK TREATS AS ONE.** A question at the
kitchen puck carries on that person's conversation there (Dvara's thread
`vaani:kitchen`), until a quiet spell (`fresh_after`) or a spoken
*start over* begins the next one. Vaani marks that on the run
(`started_over`). The page reads the runs the same way: per puck, per
person, ended by that mark. Asha's timer between two of Mahen's weather
questions is her own conversation, not a break in his.

**ONLY WHAT WAS HEARD.** A wake with nothing said is a fault worth
seeing, so it stays in Setup's list, but it isn't part of a
conversation.

**READ HERE, CARRIED ON IN SARATHI.** The page has no box to write in.
The conversation is Dvara's, and it's already in the person's own list
on Sarathi's home page, marked 🔊 *kitchen puck*. Writing there carries
it on, and the next question at the puck follows what was written
(Dvara's notes/71). The page says so under each conversation.

**FROM VAANI'S OWN RECORD, NOT DVARA'S.** The page shows the same runs it
always showed (the last fifty, in Vaani's state folder), now grouped.
It doesn't fetch anyone's conversation from Dvara, so it shows nobody
more than it did. Dvara keeps every conversation in full in each
person's list, and the page says that too.

## Live receipt

A scratch state folder with four made-up runs at the kitchen puck (two
of Mahen's about the weather, Asha's timer between them, an older one
of his that started over after) and a wake with nothing said, served
by the page from this tree on 8795 and opened in headless Chrome at
1280 px (light) and 390 px (dark):

```
40-vaani-wide ["what's the weather tomorrow?🔊 kitchen · mahen · 4 min ago",
               'set a timer for ten minutes🔊 kitchen · asha · 15 min ago',
               'when do the bins go out?🔊 kitchen · mahen · 2 h ago']
errors: []
```

The weather conversation showed both questions and answers, *At the
kitchen puck, as mahen · 2 questions*. On the phone the list came first,
and a tap showed the conversation with *← All conversations*. Setup
showed the pucks and the step-by-step list, the silent wake in red
(*nothing said*).

## Tests

`tests/test_page.py`: the page's script parses and has both tabs; the
runs group per puck and per person, end where one started over, leave
out a wake with nothing heard, and mark the conversation a turn is still
working on.

## What is not here yet

* **More than fifty questions.** The list is as long as Vaani's record.
  Older ones are in Dvara, and in Sarathi's list.
