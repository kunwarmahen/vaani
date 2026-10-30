# 04 — Each their own agent

Continues [02](02-whose-question.md), whose *an agent per person* this
is.

## The problem, as you would meet it

The kitchen puck tells Mahen's voice from Asha's, and answers each of
them as themselves: their own accounts, their own conversation, their
own questions put to them. But a puck had one `agent`, so both reached
the same one. When that was Mahen's own *minder*, Asha's question got
*"you do not have access to the agent 'minder'"* read out to her. When
it was one everyone may use, nobody got the agent they talk to on
Telegram. A shared puck meant a shared agent, or a refused one.

## A line per person

```toml
[[puck]]
name = "kitchen"
person = "mahen"
agent = "minder"
people = ["mahen", "asha"]
agents = { asha = "helper" }
```

Once Vaani knows whose question it is (a voice print, *"This is Asha,
…"*, or the puck's `person` when unsure), it asks that person's agent:
their line in `agents`, else the puck's `agent`, else `[dvara] agent`.
Everything that follows the question goes with it. A question put back
to the person waits on the agent that asked it, and the conversation
started over after a quiet spell is started over with each person's
own agent.

**DVARA STILL DECIDES.** The line says which agent Vaani asks for, not
which one the person may have. If Asha isn't allowed *helper* in
Dvara's actors file, she hears Dvara's refusal, as she would on
Telegram. Nothing here widens what anyone may use.

**A NAME THE PUCK CAN'T HEAR IS REFUSED.** `agents` may only name the
puck's `person` and its `people`. Anyone else is never the one asking
at that puck, so the line would never be used, and a line that does
nothing is far likelier a misspelling than a wish. The file is refused
with the reason, as an unknown key is. So is taking someone out of
`people` while their line is still in `agents`: the change is refused
and the file left as it was.

## Changing it

```
uv run vaani puck kitchen --agent-for asha=helper     # Asha's own
uv run vaani puck kitchen --agent-for asha=           # the puck's again
uv run vaani ask "what's on today?" --person asha     # her road, typed
```

`--agent-for` changes one person's line and keeps everyone else's,
written in place like the puck's other settings and read at its next
question. `vaani ask --person` tries the road a puck would take for
someone it heard, with no puck speaking. The status, `vaani runs
--json`, and Vaani's page (*asha asks helper.*) all show the lines.

## Receipt

A scratch Dvara on 8798 with two packages, *minder* and *helper*, each
told to begin with its own name, `gemma4:e4b` through Ollama. Mahen may
use both, Asha only *helper*. The kitchen puck's person is Mahen, its
agent *minder*, its people both of them:

```
$ vaani puck kitchen --agent-for asha=helper
the kitchen puck: agents asha: helper (from its next question; a wake word within a minute)
$ vaani ask "What is two plus two?" --person asha
helper here: Two plus two equals four.
$ vaani ask "What is two plus two?"
minder here: Two plus two is four.
$ vaani status --json   (its pucks)
[{'name': 'kitchen', 'person': 'mahen', 'agent': 'minder', 'agents': {'asha': 'helper'}}]
```

And with Asha's line taken away, her question goes where every
question used to go:

```
$ vaani puck kitchen --agent-for asha=
the kitchen puck: agents none (the puck's answers everyone) (from its next question; …)
$ vaani ask "What is two plus two?" --person asha
you do not have access to the agent 'minder'
```

A name nobody at the puck has, and a `people` that would leave a line
behind:

```
$ vaani puck kitchen --people mahen
error: vaani.toml: puck kitchen: agents names asha, who isn't its person or in its people, so it never hears them
```

## Tests

`tests/test_agents.py`: each person heard gets their own agent, the
puck's when they have no line, the file's when the puck has none; a
name the puck never hears is refused, and so is a `people` that would
leave one behind; the table is written in place and read back;
`--agent-for` adds one and keeps the others, and `PERSON=` takes one
away; `vaani ask --person` goes to that person's agent.

## What is not here yet

* **Sarathi's Settings.** The Vaani card there sets a puck's person,
  agent and people. Each person's own agent is set here, in
  `vaani.toml` or with `vaani puck`.
* **Telling real family voices apart** is still untried
  ([02](02-whose-question.md)); an agent per person is only as right as
  whose voice it heard.
