# 02 — Whose question

Continues [01](01-a-voice-for-the-house.md), whose first "not here
yet" this is.

## The problem, as you would meet it

The kitchen puck is everyone's. "What's on my calendar tomorrow?" is a
different calendar for each person who asks it, and "did the bank
write back?" is a different inbox. A puck that answers as one person
reads that person's mail to whoever is in the room; one that answers as
the house can't tell anyone their own day.

## A voice print per person, matched here

A puck may list `people`, names from Dvara's actors file. Each has a
**voice print**: a few seconds of them talking, reduced by a speaker
model to a vector (192 numbers), averaged over the samples and kept in
`voices/NAME.json` in Vaani's settings folder, readable by you alone.
The recordings themselves are not kept. Each question's sound goes
through the same model and is compared with the prints of the people
that puck may hear.

**THE MODEL IS SMALL AND LOCAL.** NeMo's TitaNet-small speaker model
(40 MB, ONNX) through sherpa-onnx on the CPU: no PyTorch, nothing sent
anywhere. It is an extra (`uv sync --extra voices`, `vaani voices
fetch`), so a puck for one person carries none of it. WeSpeaker's
ResNet34 was tried beside it on the same voices and told them apart
too, but held strangers much closer (0.44–0.64 against 0.00–0.25), so
the margin a stranger must be beaten by would have been thin.

**SURE, OR THE HOUSE.** A match is believed when the question is close
to a print (`threshold`, 0.6) and clearly closer to it than to any
other (`margin`, 0.15). Anything less is the puck's own `person`,
which should be someone in Dvara with the house's accounts only, and
the puck begins with *"I'm not sure who's asking, so I'm answering for
house."* A wrong guess reads one person's things to another; an unsure
answer costs a sentence.

**"THIS IS ASHA" NEEDS NO MODEL.** A question that starts "this is
NAME" or "it's NAME", for a name the puck may hear, is that person's,
and the opening is taken off the question. A name can be said by
anyone and a voice can be imitated, so neither is a key: Dvara's rules
for that person still decide what their agent may do, and a step a
plain yes isn't enough for asks for their spoken PIN ([01](01-a-voice-for-the-house.md),
`pins.py`).

## A print is made at the puck

`vaani voices enroll asha --at-puck kitchen` leaves a note in Vaani's
state folder; the running `vaani serve` sees it. The next three times
someone at that puck says the wake word and a sentence, the sentence is
a sample of Asha's voice, not a question: nobody is asked anything, and
the puck says how many are left. The person stands where they will
stand when they ask, in that room's own sound. `vaani voices enroll
asha a.wav b.wav` makes one from files instead.

## Live receipt

Piper's voices standing in for people (`wyoming-piper`), the puck
stood in for by its own 16 kHz stream, the house's Whisper, and Dvara
with `qwen3.8:latest`. Four voices, each enrolled from one sentence and
asked another:

```
                        alan  amy   lessac ryan      (TitaNet-small)
en_GB-alan-medium   ->  0.88  0.15  0.12   0.03   OK
en_US-amy-medium    ->  0.09  0.89  0.10   0.00   OK
en_US-lessac-medium ->  0.14  0.11  0.90   0.20   OK
en_US-ryan-medium   -> -0.04  0.07  0.25   0.82   OK
```

The whole road, a print made at the stand-in puck in alan's voice for
`owner`, then the same question in alan's voice and in ryan's:

```
1 (alan) heard 'The kettle is on and the kitchen is warm.'
   puck says: 'Got it. 2 more: say the wake word, then any sentence.'
2 (alan) heard 'I left my keys by the front door again.'
   puck says: 'Got it. 1 more: say the wake word, then any sentence.'
3 (alan) heard 'Please remember to buy milk on the way home.'
   puck says: "Thanks. I know owner's voice now."
   log: kitchen: voice owner (0.87, next -1.00)
4 (alan) heard 'In a few words, what day of the week is it?'
   puck says: 'Wednesday.'
   log: kitchen: voice unsure (0.02, next -1.00)
5 (ryan) heard 'In a few words, what day of the week is it?'
   puck says: "I'm not sure who's asking, so I'm answering for owner. Wednesday."
```

Synthetic voices are cleaner and more different from each other than a
family's are, so real people will score lower; `threshold` and
`margin` are in `vaani.toml` for that. Not run yet with real people at
the real puck.

## What is not here yet

* ~~**A yes at the puck, with a PIN.**~~ Built (notes/01, `waiting.py`,
  `pins.py`): the question is put at the puck; a yes counts in the
  asker's voice -- "yes, go ahead", since a plain "yes" is too short for
  a print -- and a step no standing yes covers needs their spoken PIN.
* **An agent per person.** A puck has one `agent`, which each of its
  people must be allowed in Dvara.
* **One enrolled person and a stranger.** With a single print, "closer
  than anyone else" is trivially true, so `threshold` alone decides; two
  or more prints make the margin mean something.
