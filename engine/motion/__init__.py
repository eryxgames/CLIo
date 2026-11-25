# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Daniel Sandner
"""CLIo Motion: models that walk, strike and fall by rule, with no clips kept in the game's files.

A model in ``models.json`` with ``"motion"`` is one of CLIo Motion's characters - a soldier, a walker, a hound,
a horse, a raptor, a spider, a scorpion, a mantis, a wasp, a dragon, an octopus::

    "hound": {"motion": "hyena"}
    "guard": {"motion": {"character": "soldier", "kit": "pistols", "style": {"bounce": 1.3}},
              "colors": {"#c26a1e": "#3b6ea8"}, "materials": {"body": {"rough": 0.5}}}

Its shape is the character's stand-in, a few hundred triangles bound to its joints; its clips (``idle``,
``walk``, ``run``, ``attack``, ``hit``, ``die`` and any other the character has, named in ``"clips"``) are
worked out by the library's motion core when they are first asked for, and kept while the game runs. So a
level's monster with such a model strides while it moves, levels its weapon or bites while it attacks, staggers
when it is hit, and falls as a rag doll when it dies - and stays lying where it fell (``"break": "fall"``, the
default for these; ``shards``, ``parts`` or ``groups`` break it apart as other models).

The library is carried here (``clio_motion/``, a copy of its Python package: pure Python, nothing to install),
as Ballistic's sound engine is carried. Source: https://github.com/eryxgames/clio-motion
"""
from __future__ import annotations

import math

SOURCE = "https://github.com/eryxgames/clio-motion"
CLIPS = ("idle", "walk", "run", "attack", "hit", "die")      # what a model has unless it names its own
DETAIL = ((4, 3), (5, 3), (6, 4), (8, 5))                    # "detail" 0-3: sides of a part, and of a thin one
METRE = 0.4                                                  # cells to a metre: a 2.5 m room is a cell high
RATE = 12.0                                                  # poses kept for a second of a clip
STEP = 1 / 60.0                                              # the step the motion core is run at
# the blows that floor a body, so that not all fall alike: from the front, and from either side of it
FALLS = ((-2.4, 1.0, 0.0), (-2.0, 1.1, 1.3), (-2.0, 1.1, -1.3))
KEYS = ("character", "kit", "style", "clips", "detail", "scale", "armed")

_lib = None
_recorded = {}            # (character, kit, style, armed, clip) -> the clip as the library records it
_models = {}              # (character, kit, style, armed, detail) -> (the library's model, the rig, the standing pose)
_posed = {}               # (those, cells to a metre, clip) -> (seconds, whether it goes round, its poses as corners)


def lib():
    """The library (engine/motion/clio_motion), loaded when the first model asks for it."""
    global _lib
    if _lib is None:
        from . import clio_motion
        _lib = clio_motion
    return _lib


def _characters():
    """The library's characters by name. If the library is not all here, that is said as a model that cannot be
    built is (ValueError), not as a file that is missing."""
    try:
        return lib().characters()
    except (OSError, ImportError) as e:
        raise ValueError("CLIo Motion is not all here (engine/motion/clio_motion): %s" % e)


def characters():
    return sorted(_characters())


def version():
    return lib().__version__


def spec_of(spec):
    """A model's ``"motion"`` as an object: ``"hyena"`` is ``{"character": "hyena"}``."""
    m = spec.get("motion") if isinstance(spec, dict) else None
    if isinstance(m, str):
        return {"character": m}
    return m if isinstance(m, dict) else None


def problems(name, spec, where="models.json"):
    """What is wrong with a model's ``"motion"``, as sentences (for --check)."""
    out = []
    raw = spec.get("motion")
    m = spec_of(spec)
    if m is None:
        return ["%s: model '%s': motion should be a character's name or an object" % (where, name)] if raw is not None else []
    try:
        chars = _characters()
    except ValueError as e:
        return ["%s: model '%s': %s" % (where, name, e)]
    cid = m.get("character")
    if cid not in chars:
        return ["%s: model '%s': motion has no character '%s' (there are: %s)" % (where, name, cid, ", ".join(sorted(chars)))]
    ch = chars[cid]
    for key in m:
        if key not in KEYS:
            out.append("%s: model '%s': motion does not know '%s' (it takes: %s)" % (where, name, key, ", ".join(KEYS)))
    kits = sorted(lib().KITS) if ch["mount"].get("type") == "held" else []
    if m.get("kit") is not None and m["kit"] not in kits:
        carries = "the %s carries one of: %s" % (cid, ", ".join(kits)) if kits else "the %s carries no kit" % cid
        out.append("%s: model '%s': motion kit '%s' - %s" % (where, name, m["kit"], carries))
    has = lib().clips.names(ch)
    clips = m.get("clips")
    if clips is not None and (not isinstance(clips, list) or not all(isinstance(c, str) for c in clips)):
        out.append("%s: model '%s': motion clips should be a list of names" % (where, name))
    else:
        for c in clips or ():
            if c not in has:
                out.append("%s: model '%s': the %s has no clip '%s' (it has: %s)" % (where, name, cid, c, ", ".join(has)))
    style = m.get("style")
    if style is not None and (not isinstance(style, dict) or any(k not in lib().STYLE or not isinstance(v, (int, float))
                                                                 for k, v in style.items())):
        out.append("%s: model '%s': motion style takes numbers for: %s" % (where, name, ", ".join(lib().STYLE)))
    if m.get("detail") is not None and m["detail"] not in (0, 1, 2, 3):
        out.append("%s: model '%s': motion detail should be 0, 1, 2 or 3" % (where, name))
    if m.get("scale") is not None and not (isinstance(m["scale"], (int, float)) and m["scale"] > 0):
        out.append("%s: model '%s': motion scale should be a number above 0 (cells to a metre, %g if not said)"
                   % (where, name, METRE))
    groups = set()
    if not out:
        groups = {p["group"] for p in Moves(spec).model["parts"]}
    for key in (spec.get("colors") or {}) if isinstance(spec.get("colors"), dict) else ():
        if not out and key not in groups and not str(key).startswith("#"):
            out.append("%s: model '%s': colors names '%s', which is neither a colour of the %s nor one of its groups (%s)"
                       % (where, name, key, cid, ", ".join(sorted(groups))))
    return out


def _flat(x, z):
    return 0.0


class Moves:
    """What a model with ``"motion"`` is made of and how it moves: its corners and faces in the model's space
    (x to the right, y forward, z up; cells), and its clips as corners, pose by pose."""

    def __init__(self, spec):
        m = spec_of(spec)
        if m is None:
            raise ValueError("motion should be a character's name or an object")
        chars = _characters()
        cm = lib()
        if m.get("character") not in chars:
            raise ValueError("motion has no character '%s'" % m.get("character"))
        self.character = m["character"]
        self.ch = ch = chars[self.character]
        kit = m.get("kit")
        held = ch["mount"].get("type") == "held"
        if kit is not None and (not held or kit not in cm.KITS):
            raise ValueError("motion kit '%s' is not one the %s carries" % (kit, self.character))
        self.kit = kit if held and kit != ch["mount"].get("kit") else None
        style = dict(cm.STYLE)
        for k, v in (m.get("style") or {}).items():
            if k not in style:
                raise ValueError("motion style does not know '%s'" % k)
            style[k] = float(v)
        self.style = style
        self.armed = m.get("armed", True) is not False
        detail = m.get("detail", 0)
        if detail not in (0, 1, 2, 3):
            raise ValueError("motion detail should be 0, 1, 2 or 3")
        self.metre = float(m.get("scale", METRE))
        if not self.metre > 0:
            raise ValueError("motion scale should be above 0")
        has = cm.clips.names(ch)
        asked = m.get("clips")
        if asked is not None:
            for c in asked:
                if c not in has:
                    raise ValueError("the %s has no clip '%s'" % (self.character, c))
        self.clip_names = [c for c in (asked if asked is not None else CLIPS) if c in has]
        self.key = (self.character, self.kit, tuple(sorted(style.items())), self.armed)
        self.falls = {}                                   # a monster's id -> the way it faced when it fell
        self.shape = self.key + (detail,)
        got = _models.get(self.shape)
        if got is None:
            # the character standing, its weapons in hand: what the model is at rest
            S = cm.create_state(ch, _flat)
            inp = {"speed": 0, "armed": self.armed, "kit": self.kit}
            pose = None
            for _ in range(90 if self.kit else 2):
                pose = cm.step(S, ch, inp, style, _flat, STEP)
                del S.events[:]
            pose = cm.clips.shift_pose(pose, -S.px, 0.0, -S.pz)
            rig = cm.rig.rig_for(ch, pose)
            sides, thin = DETAIL[detail]
            got = _models[self.shape] = (cm.mesh.build(rig, sides=sides, thin=thin), rig, pose)
        self.model, self.rig, standing = got
        # the model's corners, group by group, so that each group is one named part of the mesh
        parts = self.model["parts"]
        names = list(dict.fromkeys(p["group"] for p in parts))
        self.order = [k for g in names for p in parts if p["group"] == g for k in range(p["first"], p["first"] + p["count"])]
        place = {k: i for i, k in enumerate(self.order)}
        spans = {}
        for g in names:
            n = sum(p["count"] for p in parts if p["group"] == g)
            spans[g] = [place[next(p["first"] for p in parts if p["group"] == g)], n]
        colors = spec.get("colors") if isinstance(spec.get("colors"), dict) else {}
        faces = {"body": [], "glow": []}
        own = spec.get("materials") if isinstance(spec.get("materials"), dict) else {}
        for (a, b, c), pi in zip(self.model["faces"], self.model["face_part"]):
            p = parts[pi]
            colour = colors.get(p["group"]) or colors.get(p["color"]) or colors.get(p["color"].lower()) or p["color"]
            mat = p["group"] if p["group"] in own else "glow" if p["glow"] else "body"
            faces.setdefault(mat, []).append([place[a], place[b], place[c], colour])
        machine = ch["kind"] == "mech" or self.character == "spider"
        self.materials = {"body": {"color": "#808080", "metal": 0.55 if machine else 0.0, "rough": 0.45 if machine else 0.75},
                          "glow": {"color": "#ffffff", "glow": 2.5}}
        self.rest = self.corners(standing, None)[0]
        self.mesh_spec = {"v": [list(p) for p in self.rest], "faces": {k: v for k, v in faces.items() if v}, "parts": spans}

    def corners(self, pose, before):
        """The model's corners for a pose of the library's, in the model's space; and the skeleton, to hand back."""
        cm = lib()
        sk = cm.rig.skeleton(self.ch, pose, before)
        pts, s = cm.mesh.place(self.model, sk), self.metre
        return [(pts[k][2] * s, pts[k][0] * s, pts[k][1] * s) for k in self.order], sk

    def clip(self, name):
        """A clip made ready: ``(seconds, loops, its poses as corners)``, or None if the model has none of that
        name. ``die2`` and ``die3`` are ``die`` from other blows."""
        base, fall = name, 0
        if name in ("die2", "die3"):
            base, fall = "die", int(name[3]) - 1
        if base not in self.clip_names:
            return None
        mine = (self.shape, self.metre, name)
        if mine in _posed:
            return _posed[mine]
        key = self.key + (name,)
        rec = _recorded.get(key)
        if rec is None:
            cm = lib()
            seconds = {"idle": cm.idle_period(self.ch["L"])}.get(base, 1.0)
            rec = cm.clips.record(self.ch, base, frames=max(8, int(round(seconds * RATE))), fps=RATE, kit=self.kit,
                                  style=self.style, armed=self.armed, impulse=list(FALLS[fall]), dt=STEP)
            if rec is None:
                rec = False
            _recorded[key] = rec
        if rec is False:
            return None
        sk, poses = None, []
        for pose in rec["frames"]:
            pts, sk = self.corners(pose, sk)
            poses.append(pts)
        made = _posed[mine] = (rec["duration"], rec["loop"], poses)
        return made

    def beats(self, name):
        """How long a clip is: a beat is a second of the motion."""
        c = self.clip(name)
        return c[0] if c else 0.0

    def pose(self, name, t):
        """The corners ``t`` beats into a clip. One that goes round goes round; one played once is played again
        every whole number of beats it fits in (an attack every beat), and holds its end in between."""
        c = self.clip(name) or self.clip("idle")
        if c is None:
            return self.rest
        seconds, loop, poses = c
        n = len(poses)
        if n < 2 or seconds <= 0:
            return poses[0]
        if loop:
            u = (t / seconds * n) % n
            i = int(u)
            j, k = (i + 1) % n, u - i
        else:
            u = min(max(t % max(1.0, math.ceil(seconds - 1e-9) + (1.0 if seconds > 1.5 else 0.0)), 0.0) / seconds * n, n - 1.0)
            i = min(int(u), n - 2)
            j, k = i + 1, u - i
        if k < 1e-6:
            return poses[i]
        a, b, h = poses[i], poses[j], 1.0 - k
        return [(p[0] * h + q[0] * k, p[1] * h + q[1] * k, p[2] * h + q[2] * k) for p, q in zip(a, b)]

    def playing(self, mid, clip, t, tick=0.0, firing=False, struck=False, fast=False, falling=None, dead=False):
        """What a level's monster shows: ``(clip, beats into it)`` for what the level says it is doing. ``clip``
        is the level's own choice (idle, walk, attack) and ``t`` its clock; ``tick`` is how far the beat's
        animation is (0..1). It runs if it is ``fast`` and can; an attack is held at its start while it aims
        and played while it fires; ``struck``, it staggers; ``falling`` (0..1: how far its end has come) or
        ``dead``, it falls - each monster by one of three blows, always the same one - and lies."""
        if falling is not None or dead:
            name = ("die", "die2", "die3")[mid % 3]
            c = self.clip(name)
            if c is not None:
                return name, c[0] * (1.0 if falling is None else max(0.0, min(1.0, falling))) * 0.999999
        if struck and self.clip("hit") is not None:
            return "hit", min(0.999999, 0.15 + tick) * self.clip("hit")[0]
        if clip == "attack" and self.clip("attack") is not None:
            return "attack", (min(tick, 0.999999) * 1.0 if firing else 0.0)
        if clip == "walk":
            if fast and self.clip("run") is not None:
                return "run", t
            if self.clip("walk") is not None:
                return "walk", t
        return (clip if self.clip(clip) is not None else "idle"), t
