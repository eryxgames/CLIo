# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""A tiny chiptune synthesizer in pure Python.

Music and sound effects are *data* (JSON), rendered to 16-bit mono WAV files:
no audio assets, no third-party packages.  Songs are written in a small
tracker-like notation::

    {
      "tempo": 96, "steps_per_beat": 4,
      "instruments": {
        "lead": {"wave": "square", "duty": 0.25, "attack": 0.01, "decay": 0.1,
                 "sustain": 0.6, "release": 0.1, "vibrato": [5, 0.01], "volume": 0.5},
        "bass": {"wave": "triangle", "volume": 0.8},
        "kit":  {"wave": "drums"}
      },
      "patterns": {
        "A": {"lead": "e4:2 g4:2 a4:4 . . b4:2 a4:2 g4:4",
              "bass": "e2:4 e2:4 a2:4 b2:4",
              "kit":  "k . h . s . h . k k h . s . h h"}
      },
      "sequence": ["A", "A"]
    }

Note tokens: ``c4`` ``d#4`` ``eb3`` (a note, one step long), ``c4:4`` (four
steps), ``.`` or ``r`` (rest), ``-`` (hold the previous note one more step),
``[c4 e4 g4]:8`` (a chord; arpeggiated when the instrument has ``"arp"``),
``|`` (bar line, ignored).  Drum tracks use ``k`` kick, ``s`` snare, ``h``
closed hat, ``o`` open hat, ``t`` tom, ``c`` clap.

Two things can be added to a note (since 2.1); a song without them plays exactly
as before:

``c3>c5:16``     a slide: the pitch travels from ``c3`` to ``c5`` over the note
``c4@5:4``       a level from ``@0`` (silent) to ``@9`` (full, the default)
``c4@2>9:16``    a swell: the level travels from 2 to 9 over the note
``c3>c5@2>9:16`` both at once: a riser

A level also works on a chord (``[c4 e4 g4]@6:8``) and on a drum hit (``k@4``).

Rendering is done with list comprehensions over wavetables and a note cache,
which keeps a 30-second song to well under a second on a laptop and a few
seconds on a phone; results are cached on disk by the audio system.
"""
from __future__ import annotations

import math
import random
import struct
import wave
from array import array

RATE = 22050
TABLE = 2048
MASK = TABLE - 1
TWO_PI = 2.0 * math.pi

_NOTE_INDEX = {"c": 0, "d": 2, "e": 4, "f": 5, "g": 7, "a": 9, "b": 11}
_tables = {}
_noise_table = None


# --------------------------------------------------------------------------- #
# Pitch
# --------------------------------------------------------------------------- #

def note_freq(name):
    """Frequency in Hz of a note name such as ``a4``, ``c#3`` or ``eb5``.

    Numbers are taken as Hz directly.  Returns 0.0 for rests / unknown names.
    """
    if isinstance(name, (int, float)):
        return float(name)
    s = str(name).strip().lower()
    if not s or s in (".", "r", "-"):
        return 0.0
    try:
        return float(s)
    except ValueError:
        pass
    if s[0] not in _NOTE_INDEX:
        return 0.0
    semi = _NOTE_INDEX[s[0]]
    i = 1
    while i < len(s) and s[i] in "#b":
        semi += 1 if s[i] == "#" else -1
        i += 1
    try:
        octave = int(s[i:]) if s[i:] else 4
    except ValueError:
        return 0.0
    midi = 12 * (octave + 1) + semi
    return 440.0 * (2.0 ** ((midi - 69) / 12.0))


# --------------------------------------------------------------------------- #
# Wavetables
# --------------------------------------------------------------------------- #

def _table(wave_name, duty=0.5):
    key = (wave_name, round(duty, 3))
    t = _tables.get(key)
    if t is not None:
        return t
    n = TABLE
    if wave_name == "sine":
        t = [math.sin(TWO_PI * i / n) for i in range(n)]
    elif wave_name == "triangle":
        t = [(4.0 * i / n - 1.0) if i < n / 2 else (3.0 - 4.0 * i / n) for i in range(n)]
    elif wave_name in ("saw", "sawtooth"):
        t = [2.0 * i / n - 1.0 for i in range(n)]
    elif wave_name == "organ":
        t = [(math.sin(TWO_PI * i / n) + 0.5 * math.sin(2 * TWO_PI * i / n)
              + 0.25 * math.sin(4 * TWO_PI * i / n)) / 1.75 for i in range(n)]
    elif wave_name == "soft":            # a rounded square: gentler on small speakers
        t = [math.tanh(3.0 * math.sin(TWO_PI * i / n)) for i in range(n)]
    else:                                # square / pulse
        edge = int(n * max(0.05, min(0.95, duty)))
        t = [1.0 if i < edge else -1.0 for i in range(n)]
    _tables[key] = t
    return t


def _noise():
    global _noise_table
    if _noise_table is None:
        rnd = random.Random(1987)
        _noise_table = [rnd.uniform(-1.0, 1.0) for _ in range(8192)]
    return _noise_table


# --------------------------------------------------------------------------- #
# Voices
# --------------------------------------------------------------------------- #

def _envelope(n, attack, decay, sustain, release, hold):
    """ADSR envelope as a list of ``n`` gains. ``hold`` = samples before release."""
    a = max(1, int(attack * RATE))
    d = max(1, int(decay * RATE))
    r = max(1, int(release * RATE))
    hold = max(1, min(hold, n))
    env = []
    a_n = min(a, hold)
    env.extend(i / a for i in range(a_n))
    d_n = min(d, hold - a_n)
    if d_n > 0:
        step = (1.0 - sustain) / d
        env.extend(1.0 - step * i for i in range(d_n))
    s_n = hold - a_n - d_n
    if s_n > 0:
        env.extend([sustain] * s_n)
    level = env[-1] if env else sustain
    r_n = n - len(env)
    if r_n > 0:
        rr = min(r, r_n)
        env.extend(level * (1.0 - i / rr) for i in range(rr))
        env.extend([0.0] * (r_n - rr))
    return env[:n]


def tone(freq, seconds, wave_name="square", duty=0.5, attack=0.005, decay=0.05,
         sustain=0.7, release=0.05, volume=1.0, vibrato=None, slide_to=None,
         noise_rate=None, tail=True, glide=False, **_ignored):
    """Render one note. Returns a list of floats in roughly [-1, 1].

    ``slide_to`` bends the pitch towards another frequency: by default evenly in
    Hz over the whole sound (good for zaps), with ``glide`` evenly in pitch over
    the held part of the note (a musical slide: every octave takes as long).
    """
    hold = max(1, int(seconds * RATE))
    n = hold + (int(release * RATE) if tail else 0)
    env = _envelope(n, attack, decay, sustain, release, hold)
    if wave_name == "noise":
        tbl = _noise()
        rate = (noise_rate if noise_rate else max(200.0, freq * 8.0)) / RATE
        m = len(tbl) - 1
        if slide_to and glide:
            rate2 = max(200.0, float(slide_to) * 8.0) / RATE
            raw = [tbl[int(ph) & m] for ph in _glide(rate, rate2, hold, n)]
        elif slide_to:
            rate2 = max(200.0, float(slide_to) * 8.0) / RATE
            k = (rate2 - rate) / (2.0 * n)
            raw = [tbl[int(i * rate + i * i * k) & m] for i in range(n)]
        else:
            raw = [tbl[int(i * rate) & m] for i in range(n)]
    else:
        tbl = _table(wave_name, duty)
        inc = freq * TABLE / RATE
        if slide_to and glide and freq > 0:
            raw = [tbl[int(ph) & MASK] for ph in _glide(inc, float(slide_to) * TABLE / RATE, hold, n)]
        elif slide_to:
            inc2 = float(slide_to) * TABLE / RATE
            k = (inc2 - inc) / (2.0 * n)
            raw = [tbl[int(i * inc + i * i * k) & MASK] for i in range(n)]
        elif vibrato and vibrato[0] > 0 and vibrato[1] > 0:
            vrate, vdepth = float(vibrato[0]), float(vibrato[1])
            sine = _table("sine")
            vinc = vrate * TABLE / RATE
            amp = inc * vdepth * RATE / (TWO_PI * vrate)
            raw = [tbl[int(i * inc + amp * sine[int(i * vinc) & MASK]) & MASK] for i in range(n)]
        else:
            raw = [tbl[int(i * inc) & MASK] for i in range(n)]
    v = float(volume)
    return [s * e * v for s, e in zip(raw, env)]


def drum(kind, volume=1.0):
    """One drum hit."""
    kind = kind.lower()
    if kind == "k":                                   # kick: falling sine thump
        return tone(150, 0.11, "sine", attack=0.001, decay=0.1, sustain=0.0, release=0.02,
                    slide_to=38, volume=1.1 * volume)
    if kind == "s":                                   # snare: noise burst + body
        a = tone(0, 0.09, "noise", noise_rate=9000, attack=0.001, decay=0.08, sustain=0.0,
                 release=0.02, volume=0.6 * volume)
        b = tone(190, 0.06, "triangle", attack=0.001, decay=0.05, sustain=0.0, release=0.01,
                 slide_to=120, volume=0.5 * volume)
        return _mix_lists(a, b)
    if kind == "h":                                   # closed hat
        return tone(0, 0.025, "noise", noise_rate=RATE, attack=0.001, decay=0.02, sustain=0.0,
                    release=0.005, volume=0.28 * volume)
    if kind == "o":                                   # open hat
        return tone(0, 0.12, "noise", noise_rate=RATE, attack=0.001, decay=0.11, sustain=0.0,
                    release=0.02, volume=0.25 * volume)
    if kind == "t":                                   # tom
        return tone(180, 0.12, "sine", attack=0.001, decay=0.11, sustain=0.0, release=0.02,
                    slide_to=90, volume=0.8 * volume)
    if kind == "c":                                   # clap
        return tone(0, 0.06, "noise", noise_rate=5000, attack=0.001, decay=0.05, sustain=0.0,
                    release=0.02, volume=0.5 * volume)
    return []


def _mix_lists(a, b):
    if len(a) < len(b):
        a, b = b, a
    out = list(a)
    out[:len(b)] = [x + y for x, y in zip(a, b)]
    return out


def mix_into(buf, pos, samples, gain=1.0):
    """Add ``samples`` into ``buf`` starting at ``pos`` (clipped to the buffer)."""
    if not samples or pos >= len(buf):
        return
    if pos < 0:
        samples = samples[-pos:]
        pos = 0
    end = min(len(buf), pos + len(samples))
    n = end - pos
    seg = buf[pos:end]
    if gain == 1.0:
        buf[pos:end] = [a + b for a, b in zip(seg, samples[:n])]
    else:
        buf[pos:end] = [a + b * gain for a, b in zip(seg, samples[:n])]


def _glide(inc, inc2, hold, n):
    """Phase of an oscillator whose step goes from ``inc`` to ``inc2`` evenly in pitch over ``hold`` samples."""
    if inc <= 0 or inc2 <= 0 or abs(inc2 / inc - 1.0) < 1e-6:
        return [i * inc for i in range(n)]
    ratio = inc2 / inc
    k = inc * hold / math.log(ratio)
    head = [k * (ratio ** (i / float(hold)) - 1.0) for i in range(min(hold, n))]
    last = k * (ratio - 1.0)
    return head + [last + (i - hold) * inc2 for i in range(hold, n)]


def split_note(text):
    """``"c3>c5@2>9"`` -> ``("c3", "c5", 2/9, 1.0)``: note, slide target or None, level at start and end."""
    body, _, level = str(text).partition("@")
    name, _, target = body.partition(">")
    start = end = 1.0
    if level:
        a, _, b = level.partition(">")
        try:
            start = min(9.0, max(0.0, float(a))) / 9.0
            end = min(9.0, max(0.0, float(b))) / 9.0 if b else start
        except ValueError:
            start = end = 1.0
    return name, (target or None), start, end


def _levelled(samples, start, end, hold):
    """``samples`` with a level going from ``start`` to ``end`` over the first ``hold`` of them."""
    if start == end:
        return samples if start == 1.0 else [s * start for s in samples]
    hold = max(1, min(hold, len(samples)))
    step = (end - start) / hold
    return [s * (start + step * i) for i, s in enumerate(samples[:hold])] + [s * end for s in samples[hold:]]


def echo(buf, seconds=0.25, gain=0.3, taps=2):
    """Feed-forward echo (no feedback loop, so it stays a fast comprehension)."""
    out = list(buf)
    for t in range(1, taps + 1):
        d = int(seconds * RATE * t)
        g = gain ** t
        if d <= 0 or d >= len(buf):
            break
        out[d:] = [a + b * g for a, b in zip(out[d:], buf)]
    return out


def lowpass(buf, strength=0.5):
    """One-pole low-pass; ``strength`` 0..1 (higher = darker)."""
    a = max(0.0, min(0.98, strength))
    out = []
    append = out.append
    y = 0.0
    for x in buf:
        y += (1.0 - a) * (x - y)
        append(y)
    return out


# --------------------------------------------------------------------------- #
# Song notation
# --------------------------------------------------------------------------- #

def parse_track(text):
    """Parse a track string into events ``(start_step, steps, [notes])``.

    A note is a name/frequency; an empty list is a rest.
    """
    events = []
    pos = 0
    tokens = []
    buf, depth = "", 0
    for ch in str(text):
        if ch == "[":
            depth += 1
            buf += ch
        elif ch == "]":
            depth = max(0, depth - 1)
            buf += ch
        elif ch.isspace() and depth == 0:
            if buf:
                tokens.append(buf)
            buf = ""
        else:
            buf += ch
    if buf:
        tokens.append(buf)
    for tok in tokens:
        if tok == "|":
            continue
        length = 1
        body = tok
        if ":" in tok and not tok.startswith(":"):
            body, _, ln = tok.rpartition(":")
            try:
                length = max(1, int(float(ln)))
            except ValueError:
                length = 1
        if body == "-":
            if events:
                s, l, n = events[-1]
                events[-1] = (s, l + length, n)
            pos += length
            continue
        if body in (".", "r", "_"):
            pos += length
            continue
        if body.startswith("[") and "]" in body:                # a chord, perhaps with a level: [c4 e4]@5
            chord, _, level = body.partition("]")
            notes = [n + level for n in chord[1:].split()]
        else:
            notes = [body]
        events.append((pos, length, notes))
        pos += length
    return events, pos


def render_song(song, max_seconds=180.0):
    """Render a song dict to a list of float samples (one loop of the sequence)."""
    tempo = float(song.get("tempo", 100))
    spb = int(song.get("steps_per_beat", 4))
    step = 60.0 / tempo / spb                       # seconds per step
    step_n = step * RATE
    instruments = song.get("instruments", {})
    patterns = song.get("patterns", {})
    sequence = song.get("sequence") or list(patterns)
    swing = float(song.get("swing", 0.0))

    # pass 1: lay out patterns to find the total length
    parsed = {}
    plen = {}
    for name, tracks in patterns.items():
        parsed[name] = {}
        longest = 0
        for tname, text in tracks.items():
            if tname.startswith("_"):
                continue
            ev, ln = parse_track(text)
            parsed[name][tname] = ev
            longest = max(longest, ln)
        plen[name] = int(tracks["_length"]) if "_length" in tracks else longest
    total_steps = sum(plen.get(p, 0) for p in sequence)
    total_n = int(min(max_seconds, total_steps * step) * RATE)
    if total_n <= 0:
        return []
    tail = int(0.6 * RATE)
    track_bufs = {}
    cache = {}

    cursor = 0
    for pname in sequence:
        if pname not in parsed:
            continue
        for tname, events in parsed[pname].items():
            if tname.startswith("_"):
                continue
            inst = instruments.get(tname, {})
            buf = track_bufs.get(tname)
            if buf is None:
                buf = track_bufs[tname] = [0.0] * (total_n + tail)
            wave_name = inst.get("wave", "square")
            vol = float(inst.get("volume", 0.6))
            for start, length, notes in events:
                s = cursor + start
                at = int(s * step_n)
                if swing and (s % 2) == 1:
                    at += int(swing * step_n)
                if at >= total_n:
                    continue
                if wave_name == "drums":
                    for nname in notes:
                        nname, _to, level, _end = split_note(nname)
                        key = ("drum", nname, vol)
                        smp = cache.get(key)
                        if smp is None:
                            smp = cache[key] = drum(nname, vol)
                        mix_into(buf, at, smp, level)
                    continue
                gate = float(inst.get("gate", 0.9))
                dur = max(0.02, length * step * gate)
                arp = inst.get("arp")
                if len(notes) > 1 and arp:
                    # arpeggio: cycle the chord notes every `arp` steps
                    astep = max(0.03, float(arp) * step)
                    count = max(1, int(round(length * step / astep)))
                    for i in range(count):
                        nname, _to, level, _end = split_note(notes[i % len(notes)])
                        f = note_freq(nname)
                        if f <= 0:
                            continue
                        key = (tname, round(f, 2), round(astep, 4))
                        smp = cache.get(key)
                        if smp is None:
                            smp = cache[key] = tone(f, astep * 0.9, wave_name, **_inst_args(inst, vol))
                        mix_into(buf, at + int(i * astep * RATE), smp, level)
                    continue
                chord_gain = 1.0 / math.sqrt(len(notes)) if len(notes) > 1 else 1.0
                for nname in notes:
                    nname, target, level, level_end = split_note(nname)
                    f = note_freq(nname)
                    if f <= 0:
                        continue
                    f2 = note_freq(target) if target else 0.0
                    key = (tname, round(f, 2), round(dur, 4), round(f2, 2))
                    smp = cache.get(key)
                    if smp is None:
                        args = _inst_args(inst, vol)
                        if f2 > 0:
                            args.update(slide_to=f2, glide=True, vibrato=None)
                        smp = cache[key] = tone(f, dur, wave_name, **args)
                    if level != 1.0 or level_end != 1.0:
                        smp = _levelled(smp, level, level_end, int(dur * RATE))
                    mix_into(buf, at, smp, chord_gain)
        cursor += plen.get(pname, 0)

    master = [0.0] * (total_n + tail)
    for tname, buf in track_bufs.items():
        inst = instruments.get(tname, {})
        if inst.get("lowpass"):
            buf = lowpass(buf, float(inst["lowpass"]))
        if inst.get("echo"):
            e = inst["echo"]
            if isinstance(e, (int, float)):
                e = [float(e) * step, 0.3]
            buf = echo(buf, float(e[0]), float(e[1]) if len(e) > 1 else 0.3)
        master = [a + b for a, b in zip(master, buf)]
    # fold the tail back to the start so loops are seamless
    head = master[:total_n]
    extra = master[total_n:]
    if song.get("loop", True) and extra:
        head[:len(extra)] = [a + b for a, b in zip(head, extra)]
        master = head
    gain = float(song.get("volume", 0.7))
    if gain != 1.0:
        master = [s * gain for s in master]
    return master


def _inst_args(inst, vol):
    return {
        "duty": float(inst.get("duty", 0.5)),
        "attack": float(inst.get("attack", 0.005)),
        "decay": float(inst.get("decay", 0.08)),
        "sustain": float(inst.get("sustain", 0.6)),
        "release": float(inst.get("release", 0.08)),
        "vibrato": inst.get("vibrato"),
        "volume": vol,
    }


# --------------------------------------------------------------------------- #
# Sound effects
# --------------------------------------------------------------------------- #

def render_sfx(spec):
    """Render a sound-effect spec to float samples.

    A spec is a dict (one voice), a list of voices mixed together, or a dict
    with ``"notes"`` (a short melody in track notation).  Voice keys: ``wave``,
    ``freq`` (Hz or note name, or ``[from, to]`` for a slide), ``dur``,
    ``delay`` (seconds before it starts), ``vol`` and the ADSR keys.
    """
    if isinstance(spec, dict) and "notes" in spec:
        song = {
            "tempo": spec.get("tempo", 240), "steps_per_beat": spec.get("steps_per_beat", 2),
            "instruments": {"v": dict(spec.get("inst", {"wave": spec.get("wave", "square")}),
                                      volume=spec.get("vol", 0.5))},
            "patterns": {"A": {"v": spec["notes"]}}, "sequence": ["A"], "loop": False, "volume": 1.0,
        }
        if "duty" in spec:
            song["instruments"]["v"]["duty"] = spec["duty"]
        return render_song(song, max_seconds=8.0)
    voices = spec if isinstance(spec, list) else [spec]
    out = []
    for v in voices:
        if not isinstance(v, dict):
            continue
        if "notes" in v:
            smp = render_sfx(v)
        elif "drum" in v:
            smp = drum(str(v["drum"]), float(v.get("vol", 0.8)))
        else:
            freq = v.get("freq", 440)
            slide = None
            if isinstance(freq, (list, tuple)):
                f0 = note_freq(freq[0])
                slide = note_freq(freq[1]) if len(freq) > 1 else None
            else:
                f0 = note_freq(freq)
            smp = tone(f0, float(v.get("dur", 0.15)), v.get("wave", "square"),
                       duty=float(v.get("duty", 0.5)), attack=float(v.get("attack", 0.003)),
                       decay=float(v.get("decay", 0.05)), sustain=float(v.get("sustain", 0.6)),
                       release=float(v.get("release", 0.04)), volume=float(v.get("vol", 0.5)),
                       vibrato=v.get("vibrato"), slide_to=slide, noise_rate=v.get("noise_rate"))
        delay = int(float(v.get("delay", 0)) * RATE)
        need = delay + len(smp)
        if len(out) < need:
            out.extend([0.0] * (need - len(out)))
        mix_into(out, delay, smp)
    return out


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #

def to_pcm(samples, gain=1.0):
    """Float samples -> 16-bit signed PCM ``array('h')`` with hard limiting."""
    s = 32767.0 * gain
    return array("h", [32767 if v > 32767 else (-32768 if v < -32768 else v)
                       for v in [int(x * s) for x in samples]])


def write_wav(path, samples, gain=1.0, repeat=1):
    """Write float samples as a mono 16-bit WAV file."""
    pcm = to_pcm(samples, gain)
    if struct.pack("=h", 1) != struct.pack("<h", 1):
        pcm.byteswap()
    data = pcm.tobytes()
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        for _ in range(max(1, repeat)):
            w.writeframes(data)
    return path


def duration(samples):
    return len(samples) / float(RATE)
