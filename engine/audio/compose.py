"""Generative music: a seed and a mood in, a complete song out.

The composer writes ordinary song data (see :mod:`engine.audio.synth`), so a
generated tune can be dumped to JSON and edited by hand afterwards.  The same
seed always gives the same tune - a dungeon floor can have *its* music.
"""
from __future__ import annotations

import random

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


def compose(seed=0, mood="mystery", bars=8, length=None):
    """Return a song dict for the given seed and mood."""
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
    if length:
        song["sequence"] = list(length)
    return song
