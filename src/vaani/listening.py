"""When they stopped talking: the end of a question, from the sound alone.

THE PUCK DOESN'T KNOW; WHOEVER LISTENS DECIDES. After the wake word a
puck streams its microphone until it is told the speech has ended, so
the listener must hear the end itself. Home Assistant does it with a
voice-activity model. A question to an agent is a sentence or two in a
quiet room, so loudness is enough here: frames of 30 ms, speech when one
is well above the room's own level (the quietest of the first frames),
and the end after a pause long enough to be one.

THREE WAYS IT ENDS, AND EACH IS SAID. ``speech`` ended after a pause;
``silence`` when nobody spoke at all after the wake word (nothing is
sent to anyone); ``long`` when it ran past the longest question, so a
puck left open by a television never streams forever.
"""

from __future__ import annotations

import array
import math

from vaani.hearing import RATE, WIDTH

FRAME = int(RATE * 0.03) * WIDTH          # 30 ms of 16-bit samples, in bytes
#: Louder than the room by this factor is speech.
ABOVE = 3.0
#: The quietest a room is taken to be, so a dead-silent one still works.
FLOOR = 120.0
#: A pause this long after speech ends the question.
PAUSE = 0.9
#: Nobody spoke for this long after the wake word: nothing was asked.
WAIT = 5.0
#: The longest question.
LONGEST = 20.0


def loudness(frame: bytes) -> float:
    samples = array.array("h", frame[: len(frame) - len(frame) % 2])
    if not samples:
        return 0.0
    return math.sqrt(sum(s * s for s in samples) / len(samples))


class EndOfSpeech:
    """Fed the puck's sound as it comes; says when the question is over."""

    def __init__(self, *, pause: float = PAUSE, wait: float = WAIT,
                 longest: float = LONGEST) -> None:
        self.pause, self.wait, self.longest = pause, wait, longest
        self.heard = bytearray()
        self._pending = b""
        self._levels: list[float] = []
        self._room: float | None = None
        self._spoke = False
        self._quiet = 0.0
        self.ended: str | None = None

    @property
    def seconds(self) -> float:
        return len(self.heard) / (RATE * WIDTH)

    def feed(self, chunk: bytes) -> str | None:
        """Take more sound; "speech", "silence" or "long" once it's over."""
        if self.ended:
            return self.ended
        self.heard += chunk
        data = self._pending + chunk
        whole = len(data) - len(data) % FRAME
        self._pending = data[whole:]
        for at in range(0, whole, FRAME):
            level = loudness(data[at:at + FRAME])
            if self._room is None:
                self._levels.append(level)
                if len(self._levels) == 8:          # the first quarter second
                    self._room = max(FLOOR, min(self._levels))
                continue
            if level > self._room * ABOVE:
                self._spoke, self._quiet = True, 0.0
            elif self._spoke:
                self._quiet += 0.03
                if self._quiet >= self.pause:
                    self.ended = "speech"
                    return self.ended
        if not self._spoke and self.seconds >= self.wait:
            self.ended = "silence"
        elif self.seconds >= self.longest:
            self.ended = "long"
        return self.ended
