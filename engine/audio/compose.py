# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Generative music: a seed and a mood in, a complete song out.

The composer writes ordinary song data (see :mod:`engine.audio.synth`), so a
generated tune can be dumped to JSON and edited by hand afterwards.  The same
seed always gives the same tune - a dungeon floor can have *its* music.

Two things are for a game's designer to choose, and neither changes the notes:

``sound``   ``"chip"`` (the default: square, triangle and soft waves, as CLIo has
            always sounded) or ``"rich"`` - the same tune on instruments made with
            the synthesizer's newer settings: strings, a horn or a trumpet, a
            clarinet, plucked strings, an overdriven guitar, a synthesizer in a
            large room, as the mood has them (``RICH``).
``form``    how the tune's two halves, ``A`` and ``B``, are laid out.  Without it
            they are played ``A A B A``.  A mark says how a half is played:
            ``(A)`` without the tune, ``A-`` quietly (no bass, no drums), ``A+`` a
            tone higher.  ``"long"`` is ``(A) A A B A B- A A+``: an introduction,
            the tune, a quiet stretch, the tune again and once more a tone
            higher - more than twice as long before it comes round.
"""
from __future__ import annotations

import random
import re

_NAMES = ["c", "c#", "d", "d#", "e", "f", "f#", "g", "g#", "a", "a#", "b"]

SCALES = {
    "minor": [0, 2, 3, 5, 7, 8, 10],
    "major": [0, 2, 4, 5, 7, 9, 11],
    "dorian": [0, 2, 3, 5, 7, 9, 10],
    "phrygian": [0, 1, 3, 5, 7, 8, 10],
    "harmonic": [0, 2, 3, 5, 7, 8, 11],
    "pentatonic": [0, 3, 5, 7, 10],
    "lydian": [0, 2, 4, 6, 7, 9, 11],
}

# mood -> (scales, tempo range, progressions (scale degrees), drums, lead wave, density)
MOODS = {
    "calm":    (["major", "lydian", "dorian"], (72, 88), [[0, 4, 5, 3], [0, 5, 3, 4]], "soft", "triangle", 0.45),
    "mystery": (["dorian", "minor"], (76, 92), [[0, 5, 3, 4], [0, 2, 5, 4]], "sparse", "soft", 0.4),
    "dark":    (["phrygian", "minor", "harmonic"], (66, 84), [[0, 1, 0, 5], [0, 5, 1, 0], [0, 3, 1, 0]], "sparse", "square", 0.35),
    "tense":   (["harmonic", "phrygian"], (104, 124), [[0, 0, 5, 4], [0, 1, 5, 4]], "drive", "square", 0.55),
    "battle":  (["minor", "harmonic"], (132, 152), [[0, 5, 6, 4], [0, 3, 5, 4], [0, 6, 5, 4]], "drive", "square", 0.7),
    "heroic":  (["major", "dorian"], (108, 126), [[0, 3, 4, 0], [0, 4, 5, 3], [0, 5, 3, 4]], "march", "square", 0.65),
    "shop":    (["major", "pentatonic"], (100, 116), [[0, 3, 4, 3], [0, 5, 3, 4]], "soft", "triangle", 0.6),
    "space":   (["lydian", "dorian", "minor"], (64, 80), [[0, 4, 3, 5], [0, 2, 5, 3]], "none", "soft", 0.35),
    "victory": (["major"], (116, 132), [[0, 3, 4, 0]], "march", "square", 0.75),
    "defeat":  (["minor", "phrygian"], (60, 72), [[0, 5, 3, 0]], "none", "triangle", 0.4),
}

# The same tunes on other instruments (``sound="rich"``), mood by mood.  The volumes are set so that each voice is
# as loud as its chip counterpart: what a designer balanced by ear stays balanced.
_STRINGS = {"wave": "saw", "detune": 9, "attack": 0.3, "decay": 0.2, "sustain": 0.85, "release": 0.6, "gate": 1.0,
            "filter": [500, 2400, 0.1, 0.6], "room": [0.5, 1.5]}
_CHOIR = {"wave": "saw", "detune": 12, "attack": 0.4, "decay": 0.3, "sustain": 0.85, "release": 1.0, "gate": 1.0,
          "filter": [700, 1000, 0.5, 0.5], "room": [0.7, 2.0]}
_SYNTH = {"wave": "saw", "detune": 10, "attack": 0.35, "decay": 0.3, "sustain": 0.85, "release": 1.2, "gate": 1.0,
          "filter": [350, 2200, 0.25, 0.7], "room": [0.6, 2.0]}
_SPICCATO = {"wave": "saw", "detune": 7, "attack": 0.008, "decay": 0.12, "sustain": 0.3, "release": 0.08, "gate": 0.7,
             "filter": [2400, 700, 0.1, 0.1], "room": 0.4}
_PIZZ = {"wave": "saw", "detune": 5, "attack": 0.003, "decay": 0.16, "sustain": 0.0, "release": 0.1, "gate": 1.0,
         "filter": [2600, 500, 0.1, 0.08], "room": 0.4}
_CHUG = {"wave": "saw", "attack": 0.004, "decay": 0.12, "sustain": 0.6, "release": 0.05, "gate": 0.7, "drive": 0.8,
         "lowpass": 0.45}
_FLUTE = {"wave": "sine", "attack": 0.05, "decay": 0.1, "sustain": 0.8, "release": 0.3, "vibrato": [5, 0.005],
          "room": 0.4, "echo": [0.28, 0.3]}
_GLASS = {"wave": "soft", "attack": 0.02, "decay": 0.15, "sustain": 0.6, "release": 0.4, "vibrato": [5, 0.004],
          "room": [0.5, 1.5], "echo": [0.28, 0.35]}
_HORN = {"wave": "saw", "attack": 0.06, "decay": 0.15, "sustain": 0.8, "release": 0.3, "vibrato": [4.5, 0.003],
         "filter": [300, 1500, 0.15, 0.25], "room": [0.5, 1.5]}
_OBOE = {"wave": "square", "duty": 0.2, "attack": 0.03, "decay": 0.1, "sustain": 0.8, "release": 0.3, "lowpass": 0.4,
         "vibrato": [5.5, 0.004], "room": 0.4, "echo": [0.28, 0.3]}
_CLARINET = {"wave": "square", "duty": 0.5, "attack": 0.04, "decay": 0.1, "sustain": 0.8, "release": 0.2,
             "lowpass": 0.45, "vibrato": [5, 0.003], "room": 0.4}
_TRUMPET = {"wave": "saw", "attack": 0.02, "decay": 0.1, "sustain": 0.8, "release": 0.15, "vibrato": [5.5, 0.004],
            "filter": [700, 3000, 0.2, 0.08], "room": [0.5, 1.5]}
_BRASSY = {"wave": "saw", "attack": 0.01, "decay": 0.1, "sustain": 0.7, "release": 0.12,
           "filter": [900, 2600, 0.2, 0.1], "room": 0.3}
_SOLO = {"wave": "saw", "attack": 0.01, "decay": 0.1, "sustain": 0.8, "release": 0.12, "vibrato": [5.5, 0.006],
         "drive": 0.5, "lowpass": 0.3}
_AIRY = {"wave": "sine", "attack": 0.1, "decay": 0.2, "sustain": 0.7, "release": 0.9, "vibrato": [4, 0.004],
         "room": [0.6, 2.0], "echo": [0.45, 0.4]}
_LOW = {"wave": "triangle", "attack": 0.05, "decay": 0.1, "sustain": 0.9, "release": 0.3, "room": 0.3}
_LOW_STRINGS = {"wave": "saw", "detune": 7, "attack": 0.05, "decay": 0.15, "sustain": 0.8, "release": 0.25,
                "filter": [200, 900, 0.1, 0.3], "room": 0.4}
_LOW_BRASS = {"wave": "saw", "attack": 0.04, "decay": 0.15, "sustain": 0.85, "release": 0.25,
              "filter": [250, 1100, 0.15, 0.15], "room": [0.5, 1.5]}
_GROWL = {"wave": "saw", "attack": 0.005, "decay": 0.1, "sustain": 0.8, "release": 0.06, "drive": 0.4, "lowpass": 0.6}
_HALL = {"room": [0.6, 2.0]}
# mood -> (lead, arp or pad, bass, what the drums gain), each with the volume that makes it as loud as the chip's
RICH = {
    "calm":    (dict(_FLUTE, volume=0.20), dict(_STRINGS, volume=0.15), dict(_LOW, volume=0.42), {"room": 0.3}),
    "mystery": (dict(_GLASS, volume=0.29), dict(_CHOIR, volume=0.18), dict(_LOW, volume=0.45), _HALL),
    "dark":    (dict(_HORN, volume=0.72), dict(_STRINGS, volume=0.15), dict(_LOW_STRINGS, volume=0.68), _HALL),
    "tense":   (dict(_BRASSY, volume=0.76), dict(_SPICCATO, volume=0.40), dict(_LOW_STRINGS, volume=0.80), {"room": 0.3}),
    "battle":  (dict(_SOLO, volume=0.19), dict(_CHUG, volume=0.13), dict(_GROWL, volume=0.21), {}),
    "heroic":  (dict(_TRUMPET, volume=0.66), dict(_SPICCATO, volume=0.40), dict(_LOW_BRASS, volume=0.48), {"room": [0.5, 1.5]}),
    "shop":    (dict(_CLARINET, volume=0.16), dict(_PIZZ, volume=0.40), dict(_PIZZ, volume=1.25), {"room": 0.3}),
    "space":   (dict(_AIRY, volume=0.29), dict(_SYNTH, volume=0.16), dict(_LOW, volume=0.40), {}),
    "victory": (dict(_TRUMPET, volume=0.64), dict(_SPICCATO, volume=0.40), dict(_LOW_BRASS, volume=0.58), {"room": [0.5, 1.5]}),
    "defeat":  (dict(_OBOE, volume=0.09), dict(_STRINGS, volume=0.15), dict(_LOW, volume=0.47), {}),
}
SOUNDS = ("chip", "rich")
LONG = "(A) A A B A B- A A+"                              # form="long"
_PART = re.compile(r"(\()?\s*([ABab])\s*(\))?\s*([+-]*)")
_PITCH = re.compile(r"(?<![a-z])([a-g])(#?)(-?\d)")
LIFT = 2                                                    # semitones: a tone


def _plan(form):
    """'(A) A B- A+' -> ``[("A", "t"), ("A", ""), ("B", "q"), ("A", "l")]``; None for a form that cannot be read."""
    text = LONG if str(form).strip().lower() == "long" else str(form).strip()
    out, at = [], 0
    for found in _PART.finditer(text):
        opened, letter, closed, signs = found.groups()
        if text[at:found.start()].strip(" ,|") or bool(opened) != bool(closed):
            return None
        out.append((letter.upper(), ("t" if opened else "") + ("q" if "-" in signs else "") + ("l" if "+" in signs else "")))
        at = found.end()
    return out if out and not text[at:].strip(" ,|") and len(out) <= 64 else None


def _lifted(text, semitones=LIFT):
    """A track's notes moved up: 'c4:2 [a3 c4]:8 .' -> 'd4:2 [b3 d4]:8 .'."""
    def up(found):
        midi = 12 * (int(found.group(3)) + 1) + _NAMES.index(found.group(1) + found.group(2)) + semitones
        return "%s%d" % (_NAMES[midi % 12], midi // 12 - 1)
    return _PITCH.sub(up, text)


def _played(pattern, how):
    """A pattern as a part of the form plays it: without the tune, quietly, a tone higher."""
    out = dict(pattern)
    if "t" in how:
        out.pop("lead", None)
    if "q" in how:
        out.pop("bass", None)
        out.pop("kit", None)
    if "l" in how:
        out = {name: text if name == "kit" else _lifted(text) for name, text in out.items()}
    if not out:                                             # nothing left to play: the stretch still takes its time
        out = {"lead": ".:64"}
    return out


_DRUMS = {
    "none": ". . . . . . . . . . . . . . . .",
    "soft": "k . . . h . . . k . . . h . h .",
    "sparse": "k . . . . . . . . . . . t . . .",
    "drive": "k . h . s . h k k . h . s . h h",
    "march": "k . h . s . h . k k h . s . s h",
}


def _note(root, scale, degree, octave):
    """Note name for a scale degree (degrees may run past the octave)."""
    n = len(scale)
    octave += degree // n
    semi = root + scale[degree % n]
    octave += semi // 12
    return "%s%d" % (_NAMES[semi % 12], octave)


def compose(seed=0, mood="mystery", bars=8, length=None, sound="chip", form=None):
    """Return a song dict for the given seed and mood.

    ``sound``: ``"chip"`` or ``"rich"`` - the same notes on other instruments.  ``form``: how the two halves of the
    tune are laid out, such as ``"(A) A B- A+"``, or ``"long"``; one that cannot be read is ignored."""
    if mood not in MOODS:
        mood = "mystery"
    scales, (t_lo, t_hi), progressions, drum_kind, lead_wave, density = MOODS[mood]
    rnd = random.Random("clio-music:%s:%s" % (seed, mood))
    scale = SCALES[rnd.choice(scales)]
    root = rnd.randrange(12)
    tempo = rnd.randrange(t_lo, t_hi + 1)
    prog = rnd.choice(progressions)
    n = len(scale)

    def chord(deg):
        return [deg, deg + 2, deg + 4]

    def make_pattern(variation):
        bass, arp, lead, kit = [], [], [], []
        degree = rnd.randrange(n)                       # melody position
        for bar in range(4):
            deg = prog[(bar + (1 if variation and bar == 3 else 0)) % len(prog)]
            ch = chord(deg)
            # --- bass: root on the beat, with an occasional fifth / octave
            style = rnd.choice(("long", "pulse", "walk")) if mood not in ("space", "calm", "defeat") else "long"
            if style == "long":
                bass.append("%s:16" % _note(root, scale, deg, 2))
            elif style == "pulse":
                r = _note(root, scale, deg, 2)
                bass.append("%s:3 . %s:3 . %s:3 . %s:2 %s:2" % (r, r, r, r, _note(root, scale, deg + 4, 2)))
            else:
                r, f, o = _note(root, scale, deg, 2), _note(root, scale, deg + 4, 2), _note(root, scale, deg + 7, 2)
                bass.append("%s:4 %s:4 %s:4 %s:4" % (r, f, o, f))
            # --- arpeggio / pad
            tones = " ".join(_note(root, scale, d, 3) for d in ch)
            if mood in ("space", "calm", "mystery", "defeat", "dark"):
                arp.append("[%s]:16" % tones)
            else:
                order = rnd.choice(([0, 1, 2, 1], [0, 2, 1, 2], [2, 1, 0, 1]))
                names = [_note(root, scale, ch[i], 3) for i in order]
                arp.append(" ".join("%s:2" % names[i % 4] for i in range(8)))
            # --- melody: a random walk that lands on chord tones on strong beats
            pos = 0
            while pos < 16:
                dur = rnd.choice((2, 2, 2, 4, 4, 1, 1, 6) if density > 0.5 else (4, 4, 2, 2, 8, 6))
                dur = min(dur, 16 - pos)
                if rnd.random() > density and pos != 0:
                    lead.append(".:%d" % dur)
                else:
                    if pos % 8 == 0:
                        target = rnd.choice(ch)
                        while target - degree > 3:
                            target -= n
                        while degree - target > 3:
                            target += n
                        degree = target
                    else:
                        degree += rnd.choice((-2, -1, -1, 1, 1, 2))
                    degree = max(-2, min(n + 4, degree))
                    lead.append("%s:%d" % (_note(root, scale, degree, 4), dur))
                pos += dur
            kit.append(_DRUMS[drum_kind] if not (variation and bar == 3 and drum_kind in ("drive", "march"))
                       else "k . s . s . s s k s s s s s s s")
        return {"lead": " | ".join(lead), "arp": " | ".join(arp), "bass": " | ".join(bass),
                "kit": " | ".join(kit)}

    slow = mood in ("space", "calm", "mystery", "defeat", "dark")
    song = {
        "title": "%s #%s" % (mood, seed),
        "tempo": tempo, "steps_per_beat": 4, "loop": True, "volume": 0.6,
        "instruments": {
            "lead": {"wave": lead_wave, "duty": rnd.choice((0.25, 0.5, 0.125)), "attack": 0.02 if slow else 0.005,
                     "decay": 0.12, "sustain": 0.55, "release": 0.25 if slow else 0.08,
                     "vibrato": [5, 0.006], "volume": 0.34, "echo": [0.28, 0.35] if slow else [0.18, 0.2]},
            "arp": {"wave": "soft" if slow else "square", "duty": 0.25, "attack": 0.3 if slow else 0.004,
                    "decay": 0.2, "sustain": 0.5 if slow else 0.3, "release": 0.4 if slow else 0.05,
                    "volume": 0.14 if slow else 0.16, "gate": 1.0 if slow else 0.8},
            "bass": {"wave": "triangle", "attack": 0.01, "decay": 0.1, "sustain": 0.8, "release": 0.08,
                     "volume": 0.5},
            "kit": {"wave": "drums", "volume": 0.55},
        },
        "patterns": {"A": make_pattern(False), "B": make_pattern(True)},
        "sequence": ["A", "A", "B", "A"] if bars >= 16 else ["A", "B"],
    }
    if drum_kind == "none":
        for p in song["patterns"].values():
            p.pop("kit", None)
        song["instruments"].pop("kit", None)
    if sound == "rich" and mood in RICH:
        lead, arp, bass, kit = RICH[mood]
        made = song["instruments"]
        made["lead"], made["arp"], made["bass"] = dict(lead), dict(arp), dict(bass)
        if "kit" in made:
            made["kit"] = dict(made["kit"], **kit)
    plan = _plan(form) if form else None
    if plan:                                                # the same two halves, laid out and played as the form says
        halves = song["patterns"]
        song["patterns"], song["sequence"] = {}, []
        for letter, how in plan:
            name = ("(%s)" % letter if "t" in how else letter) + ("-" if "q" in how else "") + ("+" if "l" in how else "")
            song["patterns"].setdefault(name, _played(halves[letter], how))
            song["sequence"].append(name)
    if length:
        song["sequence"] = list(length)
    return song
