"""Who is speaking: a voice print per person, matched on this computer.

ONE PUCK, SEVERAL PEOPLE, EACH THEIR OWN. A kitchen puck is everyone's,
and "what's on my calendar" means a different calendar for each of
them. So a puck may list ``people``: a few seconds of a person's voice
are kept as their print, and each question is matched against the
prints of the people that puck may hear. The answer comes from that
person's agent, with their accounts, through Dvara as always.

SURE, OR THE HOUSE. A match is believed only when it is clearly that
person: close enough to their print (``threshold``) and clearly closer
than to anyone else's (``margin``). Anything less is the puck's own
``person`` -- set it to a person in Dvara with the house's accounts
only -- and the puck says it isn't sure who's asking. A wrong guess
would read one person's mail to another; an unsure "the house" costs
one sentence.

"THIS IS ASHA" NEEDS NO MODEL. A question that starts with "this is
<name>" or "it's <name>", for a name the puck may hear, is that
person's, prints or not. A voice can be imitated and a name can be
said by anyone, so neither is a key: Dvara's own rules, and a PIN for
money (not here yet), are what keep a person's things theirs.

THE MODEL IS SMALL AND LOCAL. NeMo's TitaNet-small speaker model (40 MB,
ONNX), through sherpa-onnx on the CPU: no PyTorch, nothing sent out.
It's an extra (``uv sync --extra voices``); without it a puck answers
as its one ``person``, as before. Told apart in a test: four Piper
voices, enrolled from one sentence and asked another, matched 0.82-0.90
to their own print and at most 0.25 to any other.

A PRINT IS A FILE OF THE PERSON'S OWN, in Vaani's settings folder
(``voices/NAME.json``, readable by you alone): an average of a few
samples' embeddings, never the recordings.
"""

from __future__ import annotations

import io
import json
import os
import re
import urllib.request
import wave
from dataclasses import dataclass
from pathlib import Path

from vaani.config import NAME

MODEL = "nemo_en_titanet_small.onnx"
MODEL_URL = ("https://github.com/k2-fsa/sherpa-onnx/releases/download/"
             f"speaker-recongition-models/{MODEL}")
#: Close enough to a print to be that person.
THRESHOLD = 0.6
#: And closer to it than to anyone else's by this much.
MARGIN = 0.15
#: Samples a print is made of, when it's made at a puck.
SAMPLES = 3

SAID_NAME = re.compile(r"^\s*(?:this is|it's|it is|hi,? it's)\s+([A-Za-z][\w-]*)[\s,.!:;-]*",
                       re.I)


class VoiceError(Exception):
    pass


def models() -> Path:
    named = os.environ.get("VAANI_MODELS", "").strip()
    return Path(named).expanduser() if named else Path.home() / ".local/share/vaani/models"


def fetch(folder: Path | None = None) -> Path:
    """The speaker model, downloaded once."""
    folder = folder or models()
    target = folder / MODEL
    if target.is_file():
        return target
    folder.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(".part")
    try:
        with urllib.request.urlopen(MODEL_URL, timeout=120) as got, open(partial, "wb") as out:
            while chunk := got.read(1 << 20):
                out.write(chunk)
    except OSError as exc:
        raise VoiceError(f"the speaker model couldn't be fetched from {MODEL_URL}: {exc}") \
            from None
    partial.replace(target)
    return target


def said_name(text: str, people: tuple[str, ...]) -> tuple[str | None, str]:
    """(the person a "this is NAME" opening names, the question without
    it), or (None, text) when it names nobody this puck may hear."""
    match = SAID_NAME.match(text)
    if match:
        named = match.group(1).lower()
        for person in people:
            if person.lower() == named:
                return person, text[match.end():].strip() or text
    return None, text


@dataclass
class Match:
    person: str | None
    score: float
    runner_up: float


class Prints:
    """Every print in ``folder``, and the model that makes and matches them."""

    def __init__(self, folder: Path, model: Path | None = None) -> None:
        self.folder = folder
        self.model = model or models() / MODEL
        self._extractor = None

    def _extract(self):
        if self._extractor is None:
            try:
                import sherpa_onnx
            except ImportError:
                raise VoiceError("telling voices apart needs the voices extra: "
                                 "`uv sync --extra voices`") from None
            if not self.model.is_file():
                raise VoiceError(f"no speaker model at {self.model}: `vaani voices fetch`")
            self._extractor = sherpa_onnx.SpeakerEmbeddingExtractor(
                sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(self.model),
                                                            num_threads=2))
        return self._extractor

    def embed(self, wav: bytes) -> list[float]:
        import numpy as np

        with wave.open(io.BytesIO(wav)) as w:
            rate, width = w.getframerate(), w.getsampwidth()
            raw = w.readframes(w.getnframes())
        if width != 2:
            raise VoiceError("a voice sample is 16-bit WAV")
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768
        if len(samples) < rate:
            raise VoiceError("a voice sample is a second or more of someone talking")
        if rate != 16000:
            # the puck sends 16 kHz; a file may not (Piper's are 22 kHz)
            at = np.linspace(0, len(samples) - 1, int(len(samples) * 16000 / rate))
            samples = np.interp(at, np.arange(len(samples)), samples).astype(np.float32)
            rate = 16000
        extractor = self._extract()
        stream = extractor.create_stream()
        stream.accept_waveform(rate, samples)
        stream.input_finished()
        vector = np.array(extractor.compute(stream), dtype=np.float32)
        return (vector / (np.linalg.norm(vector) or 1)).tolist()

    def path(self, person: str) -> Path:
        if not NAME.match(person):
            raise VoiceError(f"{person!r} isn't a person's name, as Dvara has them")
        return self.folder / f"{person}.json"

    def known(self) -> dict[str, dict]:
        out = {}
        for file in sorted(self.folder.glob("*.json")) if self.folder.is_dir() else []:
            try:
                out[file.stem] = json.loads(file.read_text())
            except (OSError, ValueError):
                continue
        return out

    def enroll(self, person: str, wavs: list[bytes], *, add: bool = False) -> int:
        """``person``'s print from ``wavs`` (or more samples into it); the
        number of samples it is now made of."""
        import numpy as np

        vectors = [self.embed(w) for w in wavs]
        target = self.path(person)
        count = len(vectors)
        if add and target.is_file():
            kept = json.loads(target.read_text())
            vectors.append([x * kept["samples"] for x in kept["print"]])
            count += kept["samples"]
        mean = np.sum(np.array(vectors, dtype=np.float32), axis=0)
        mean = mean / (np.linalg.norm(mean) or 1)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.folder.chmod(0o700)
        target.touch(mode=0o600, exist_ok=True)
        target.write_text(json.dumps({"model": self.model.name, "samples": count,
                                      "print": [round(float(x), 6) for x in mean]}))
        return count

    def forget(self, person: str) -> bool:
        target = self.path(person)
        if target.is_file():
            target.unlink()
            return True
        return False

    def match(self, wav: bytes, people: tuple[str, ...], *, threshold: float = THRESHOLD,
              margin: float = MARGIN) -> Match:
        """Who of ``people`` is speaking in ``wav``, if it's clear."""
        import numpy as np

        known = {p: v for p, v in self.known().items() if p in people}
        if not known:
            return Match(None, 0.0, 0.0)
        heard = np.array(self.embed(wav), dtype=np.float32)
        scores = sorted(((float(heard @ np.array(v["print"], dtype=np.float32)), p)
                         for p, v in known.items()), reverse=True)
        best, who = scores[0]
        second = scores[1][0] if len(scores) > 1 else -1.0
        sure = best >= threshold and best - second >= margin
        return Match(who if sure else None, best, second)
