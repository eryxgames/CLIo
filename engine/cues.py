# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Cues: what a screen does with the sound - a flash on the kick, sparks on the hats, a new palette
with each section, a darkening that lands on the drop.

A **cue sheet** says what happens when: named actions with a time, a length, an amount and a shape.
It is the cue sheet of Playhead (github.com/eigensoundlab/playhead, ``"format": "playhead-cues"``),
which makes one from a recording by listening to it once, when a game is built::

    playhead analyze music/bridge.wav --profile music --out music/bridge.playhead.json
    playhead cues music/bridge.playhead.json --preset playhead --out music/bridge.cues.json

A sheet beside a sound file (``bridge.cues.json`` next to ``bridge.wav``) is found by itself. A song
written in CLIo's notation needs no listening: its kicks, snares, hats, beats, bars and parts are in
its notes, and :func:`from_song` writes the same kind of sheet from them with the same kind of rules.

Playing is reading: nothing is analysed while a game runs. Each frame a screen asks the sheet for
the levels at the sound's own time (:meth:`engine.audio.Audio.clock`)::

    sheet = game.audio.cues()                  # the sheet of the track that is playing, or None
    now = game.audio.clock()                   # seconds into it
    kick = sheet.level("punch", now)           # 0..1: full on the kick, dying away
    scope.dim = 0.3 + 0.7 * sheet.level("glow", now)
    for name in sheet.events(before, now):     # things that happen once
        ...

A cue's level at time ``t`` is ``amount * shape(u)``, ``u`` from 0 at its start to 1 at its end:
``pulse`` e^(-4u), ``hold`` 1, ``ramp`` u, ``swell`` sin(pi u), ``fade`` 1 - u. Cues of one action
combine by their greatest; a curve of the same name joins them.
"""
from __future__ import annotations

import bisect
import json
import math
import os

FORMAT = "playhead-cues"
SHAPES = ("pulse", "hold", "ramp", "swell", "fade")
# what a song's drums are, heard in three bands
DRUMS = {"k": "hit.low", "t": "hit.low", "s": "hit.mid", "c": "hit.mid", "h": "hit.high", "o": "hit.high"}
# the rules a song gets unless it is given others: Playhead's own first preset, and the bar
RULES = [{"on": "hit.low", "do": "punch", "length": 0.14},
         {"on": "hit.mid", "do": "shockwave", "length": 0.5, "shape": "fade"},
         {"on": "hit.high", "do": "sparks", "length": 0.08},
         {"on": "section", "do": "palette", "length": 1, "shape": "hold"},
         {"on": "bar", "do": "bar", "length": 1, "lengthUnit": "beats", "shape": "fade"},
         {"on": "beat", "do": "beat", "length": 0.5, "lengthUnit": "beats"}]


def shape(name, u):
    """A shape's height at ``u`` (0 at a cue's start, 1 at its end; nothing outside)."""
    if u < 0.0 or u > 1.0:
        return 0.0
    if name == "hold":
        return 1.0
    if name == "ramp":
        return u
    if name == "swell":
        return math.sin(math.pi * u)
    if name == "fade":
        return 1.0 - u
    return math.exp(-4.0 * u)


class Sheet:
    """A cue sheet, ready to be asked. ``loop``: the sound comes round again (as CLIo's music does),
    so time is taken within its length."""

    def __init__(self, doc, loop=True):
        doc = doc if isinstance(doc, dict) else {}
        self.doc = doc
        self.duration = float((doc.get("source") or {}).get("duration") or 0.0)
        self.loop = bool(loop) and self.duration > 0
        self.cues = sorted((c for c in doc.get("cues") or [] if isinstance(c, dict) and "t" in c),
                           key=lambda c: float(c["t"]))
        self.by = {}                                     # action -> (starts, cues, the longest)
        for c in self.cues:
            if c.get("action") == "event":
                continue
            starts, cues, _ = self.by.setdefault(str(c.get("action")), ([], [], [0.0]))
            starts.append(float(c["t"]))
            cues.append(c)
            _[0] = max(_[0], float(c.get("length") or 0.0))
        self.happenings = [(float(c["t"]), str(c.get("name") or "")) for c in self.cues if c.get("action") == "event"]
        curves = doc.get("curves") or {}
        self.rate = float(curves.get("rate") or 30.0)
        self.curves = {k: v for k, v in (curves.get("values") or {}).items() if isinstance(v, list)}
        self.actions = sorted(set(self.by) | set(self.curves))

    def when(self, t):
        return t % self.duration if self.loop else t

    def level(self, action, t):
        """How strongly an action is on at time ``t`` (seconds into the sound): 0 and up."""
        t = self.when(t)
        best = 0.0
        entry = self.by.get(action)
        if entry:
            starts, cues, longest = entry
            i = bisect.bisect_right(starts, t) - 1
            first = t - longest[0]
            while i >= 0 and starts[i] >= first:
                c = cues[i]
                n = float(c.get("length") or 0.0)
                if n > 0:
                    v = float(c.get("amount", 1.0)) * shape(c.get("shape", "pulse"), (t - starts[i]) / n)
                    if v > best:
                        best = v
                i -= 1
        curve = self.curves.get(action)
        if curve:
            v = float(curve[min(len(curve) - 1, max(0, int(t * self.rate)))])
            if v > best:
                best = v
        return best

    def levels(self, t):
        """Every action's level at time ``t``."""
        return {a: self.level(a, t) for a in self.actions}

    def turns(self, action, t):
        """How many cues of an action have begun by ``t``, the newest counted as it comes in over its
        length (2.5: the third is half in). For a palette that changes with each part of the music."""
        entry = self.by.get(action)
        if not entry:
            return 0.0
        t = self.when(t)
        starts, cues, _ = entry
        i = bisect.bisect_right(starts, t)
        if not i:
            return 0.0
        n = float(cues[i - 1].get("length") or 0.0)
        return i - 1 + (min(1.0, (t - starts[i - 1]) / n) if n > 0 else 1.0)

    def events(self, since, now):
        """The names of what happened once between two times (``since`` not counted, ``now`` counted) -
        round the end of a loop as well."""
        if now < since:
            return []
        if self.loop:
            if now - since >= self.duration:
                return [name for _, name in self.happenings]
            a, b = since % self.duration, now % self.duration
            if b < a:
                return [n for t, n in self.happenings if t > a] + [n for t, n in self.happenings if t <= b]
            since, now = a, b
        return [n for t, n in self.happenings if since < t <= now]


def load(path, loop=True):
    """The sheet in a file, or None when there is none or it is not one."""
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(doc, dict) or doc.get("format") != FORMAT:
        return None
    return Sheet(doc, loop)


def beside(sound_path, loop=True):
    """The sheet that goes with a sound file: ``name.cues.json`` next to ``name.wav``."""
    base = os.path.splitext(sound_path)[0]
    for path in (base + ".cues.json", sound_path + ".cues.json"):
        if os.path.isfile(path):
            return load(path, loop)
    return None


# --------------------------------------------------------------------------- #
# From a song's own notes
# --------------------------------------------------------------------------- #
def song_events(song):
    """What happens in a song written in CLIo's notation, from its notes: ``(events, seconds, beat,
    bar)`` - each event ``{"type", "t", "strength", "length", "label"}``, the length of a beat and of a
    bar in seconds."""
    from .audio import synth
    tempo = float(song.get("tempo", 120) or 120)
    spb = max(1, int(song.get("steps_per_beat", 4) or 4))
    step = 60.0 / tempo / spb
    beat = step * spb
    per_bar = max(1, int(song.get("beats_per_bar", 4) or 4))
    drums = {k for k, v in (song.get("instruments") or {}).items() if isinstance(v, dict) and v.get("wave") == "drums"}
    events, at, seen, last = [], 0, set(), None
    for name in song.get("sequence") or []:
        pattern = (song.get("patterns") or {}).get(name)
        if not isinstance(pattern, dict):
            continue
        tracks = {k: synth.parse_track(v) for k, v in pattern.items()}
        steps = max([n for _, n in tracks.values()] or [0])
        if not steps:
            continue
        if name != last:                                 # a part begins (the same part again is no news)
            kind = "section.repeat" if name in seen else "section.new"
            events.append({"type": kind, "t": at * step, "strength": 1.0, "length": steps * step, "label": str(name)})
            seen.add(name)
            last = name
        for track, (notes, _) in tracks.items():
            if track not in drums:
                continue
            for start, _n, hits in notes:
                for hit in hits:
                    body, _slide, level, _end = synth.split_note(hit)
                    kind = DRUMS.get(str(body)[:1])
                    if kind:
                        events.append({"type": kind, "t": (at + start) * step, "strength": float(level),
                                       "length": step, "label": str(body)[:1]})
        at += steps
    total = at * step
    parts = [e for e in events if e["type"].startswith("section")]
    for e, after in zip(parts, parts[1:] + [None]):      # a part lasts until the next one begins
        e["length"] = (after["t"] if after else total) - e["t"]
    n = 0
    while n * beat < total - 1e-9:
        events.append({"type": "bar" if n % per_bar == 0 else "beat", "t": n * beat, "strength": 1.0,
                       "length": beat, "label": ""})
        if n % per_bar == 0:
            events.append({"type": "beat", "t": n * beat, "strength": 1.0, "length": beat, "label": ""})
        n += 1
    events.sort(key=lambda e: (e["t"], e["type"]))
    return events, total, beat, beat * per_bar


def make(events, rules, duration, beat=0.5, bar=2.0, name="", loop=True):
    """A sheet from events and rules (Playhead's rules: ``on``, ``where`` by ``label``, ``every``, ``at``
    and ``unit``, ``do`` (``event`` with ``name``: something that happens once), ``amount``, ``scale``,
    ``length`` and ``lengthUnit``, ``shape``)."""
    unit = {"s": 1.0, "beats": beat, "bars": bar}
    cues = []
    for ri, rule in enumerate(rules or []):
        if not isinstance(rule, dict) or not rule.get("on") or not rule.get("do"):
            continue
        on = str(rule["on"])
        want = (rule.get("where") or {}).get("label")
        want = None if want is None else ([str(x) for x in want] if isinstance(want, list) else [str(want)])
        every = max(1, int(rule.get("every", 1) or 1))
        n = 0
        for e in events:
            if e["type"] != on and not e["type"].startswith(on + "."):
                continue
            if want is not None and e.get("label") not in want:
                continue
            n += 1
            if (n - 1) % every:
                continue
            lu = rule.get("lengthUnit", "s")
            length = float(rule.get("length", 0.25)) * (e.get("length", 0.0) if lu == "event" else unit.get(lu, 1.0))
            t = e["t"] + float(rule.get("at", 0.0)) * unit.get(rule.get("unit", "s"), 1.0)
            amount = float(rule.get("amount", 1.0)) * (1.0 if rule.get("scale") is False else e.get("strength", 1.0))
            cue = {"t": round(t, 4), "length": round(length, 4), "action": str(rule["do"]), "amount": round(amount, 3),
                   "shape": rule.get("shape", "pulse") if rule.get("shape") in SHAPES else "pulse", "on": e["type"],
                   "rule": ri}
            if cue["action"] == "event":
                cue["name"] = str(rule.get("name") or on)
            if loop and duration > 0:                    # before the start is the end of the round before
                cue["t"] = round(cue["t"] % duration, 4)
            if cue["t"] >= 0:
                cues.append(cue)
    cues.sort(key=lambda c: c["t"])
    return Sheet({"format": FORMAT, "version": 1, "generator": {"name": "clio"},
                  "source": {"name": name, "duration": round(duration, 4)}, "rules": list(rules or []),
                  "mappings": [], "cues": cues}, loop)


def from_song(song, rules=None, loop=True):
    """The sheet of a song written in CLIo's notation, from its notes (its own ``"cues"`` are its rules,
    else :data:`RULES`)."""
    events, total, beat, bar = song_events(song)
    rules = rules if rules is not None else (song.get("cues") if isinstance(song.get("cues"), list) else RULES)
    return make(events, rules, total, beat, bar, str(song.get("title") or ""), loop)


def problems(rules, where="cues"):
    out = []
    if not isinstance(rules, list):
        return ["%s should be a list of rules" % where]
    for i, r in enumerate(rules):
        if not isinstance(r, dict) or not r.get("on") or not r.get("do"):
            out.append("%s rule %d: it needs \"on\" and \"do\"" % (where, i + 1))
            continue
        if r.get("shape") not in (None,) + SHAPES:
            out.append("%s rule %d: unknown shape '%s' (%s)" % (where, i + 1, r.get("shape"), ", ".join(SHAPES)))
        for key in ("unit", "lengthUnit"):
            if r.get(key) not in (None, "s", "beats", "bars") + (("event",) if key == "lengthUnit" else ()):
                out.append("%s rule %d: %s is s, beats or bars%s" % (where, i + 1, key,
                                                                    ", or event" if key == "lengthUnit" else ""))
        if r.get("do") == "event" and not r.get("name"):
            out.append("%s rule %d: an event needs a name" % (where, i + 1))
    return out
