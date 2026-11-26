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
CLIPS = ("idle", "walk", "run", "attack", "hit", "die")      # what a model has unless it names its own,
ALOFT = ("fly", "hover", "swim")                             # with these where the character has them
CLEAR = 0.12                                                 # metres under a body in the air or the water, as a clip is kept
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


def fast():
    """The library's C core, loaded under Python (engine/motion/clio_motion/native.py), or None: bodies run live
    are stepped in it when it is there - many times as fast, and the same to nine digits. It is looked for in
    ``CLIO_MOTION_LIB`` (``none`` for none), then in engine/motion/lib/, then where the system keeps libraries; it
    is checked against the Python before it is used."""
    try:
        from .clio_motion import native
        return native if native.load() is not None else None
    except Exception:                                    # a Python with no ctypes, a library that will not load
        return None


def status():
    """What runs live bodies, in a line."""
    try:
        from .clio_motion import native
        return native.status() if native.load() is not None else "Python (the C core: %s)" % native.status()
    except Exception as e:
        return "Python (%s)" % e


def version():
    return lib().__version__


def rig_named(name):
    """One of the library's skeletons by its name - a character's, or a soldier's with a kit (``soldier``,
    ``soldier_pistols``, ``soldier_sword``): what its templates for artists are called."""
    _characters()
    rigs = lib().rig.rigs()
    if name not in rigs:
        raise ValueError("CLIo Motion has no skeleton called '%s' (there are: %s)" % (name, ", ".join(sorted(rigs))))
    return rigs[name]


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
        try:
            groups = {p["group"] for p in Moves(spec).model["parts"]}
        except ValueError as e:
            return ["%s: model '%s': %s" % (where, name, e)]
    for key in (spec.get("colors") or {}) if isinstance(spec.get("colors"), dict) else ():
        if not out and key not in groups and not str(key).startswith("#"):
            out.append("%s: model '%s': colors names '%s', which is neither a colour of the %s nor one of its groups (%s)"
                       % (where, name, key, cid, ", ".join(sorted(groups))))
    return out


def _flat(x, z):
    return 0.0


def shown(mdl, m, fx, clip, t, heading, fast=False, deep=False):
    """What a level's view shows of a monster whose model (``mdl``) is moved by CLIo Motion, for the frame
    ``fx`` (engine/firstperson.py: FX): ``(clip, beats into it, the way it faces, how far it has sunk out of
    the air 0..1, whether it is falling or lies)``. ``clip``, ``t`` and ``heading`` are what the view would show
    of any model."""
    mv = mdl.motion
    dissolve = getattr(fx, "dissolve", None) or {}
    ending = mdl.breaks == "fall" and (m.dead or m.id in dissolve)
    if ending:                                             # it lies the way it faced when it fell
        heading = mv.falls.setdefault(m.id, heading)
    else:
        mv.falls.pop(m.id, None)
    biting = m.id in (getattr(fx, "lunge", None) or {})    # a bite, a claw: its attack played through
    falling = dissolve.get(m.id) if ending else None
    clip, t = mv.playing(m.id, "attack" if biting else clip, t, tick=getattr(fx, "tick", 0.0) or 0.0,
                         firing=biting or m.id in (getattr(fx, "emuzzle", None) or ()),
                         struck=m.id in (getattr(fx, "flash", None) or ()) and not ending, fast=fast,
                         falling=falling, dead=ending and m.dead, aloft=getattr(m, "float", 0) > 0, afloat=deep)
    sinks = 0.0
    if ending:                                             # out of the air, on to the floor
        sinks = 1.0 if falling is None else min(1.0, 2.0 * falling)
    return clip, t, heading, sinks, ending


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
        self.clip_names = [c for c in (asked if asked is not None else CLIPS + ALOFT) if c in has]
        self.flies = bool(ch.get("fly")) and "fly" in self.clip_names
        self.swims = bool(ch.get("octo")) and "swim" in self.clip_names
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
        self._lines = None                                # the same body for a display that draws lines, when asked for
        self._bound = {}                                  # made ready for the C core: "mesh", "lines", "skin"
        self.skin = None                                  # a model of the game's own on this skeleton: its corners' joints
        if spec.get("skin") is not None:
            self.skin = self._skin(spec)
            self.shape = self.shape + (id(self.skin),)
            self.materials = {}
            self.mesh_spec = spec["mesh"]
            self.rest = [tuple(float(c) for c in p[:3]) for p in spec["mesh"]["v"]]
        else:
            self.rest = self.corners(standing, None)[0]
            self.mesh_spec = {"v": [list(p) for p in self.rest], "faces": {k: v for k, v in faces.items() if v}, "parts": spans}

    def _skin(self, spec):
        """A model's ``"skin"`` checked and made ready: for each corner of its mesh, the joints that carry it and
        how much each (``[(joint of the rig, weight), ...]``)."""
        skin, mesh = spec["skin"], spec.get("mesh")
        if not isinstance(skin, dict) or not isinstance(mesh, dict) or not mesh.get("v"):
            raise ValueError("a skin needs the model's mesh")
        index = {j["name"]: k for k, j in enumerate(self.rig["joints"])}
        joints = []
        for name in skin.get("joints") or []:
            if name not in index:
                raise ValueError("the skin names a joint '%s' that the %s has not" % (name, self.rig["name"]))
            joints.append(index[name])
        rows = skin.get("weights") or []
        if len(rows) != len(mesh["v"]):
            raise ValueError("the skin should say what carries each of the mesh's %d corners (it says it for %d)"
                             % (len(mesh["v"]), len(rows)))
        out = []
        for row in rows:
            pairs = [(joints[int(row[k])], float(row[k + 1])) for k in range(0, len(row) - 1, 2) if float(row[k + 1]) > 0]
            total = sum(w for _j, w in pairs)
            if not pairs or total <= 0:
                raise ValueError("a corner of the skin is carried by no joint")
            out.append([(j, w / total) for j, w in pairs])
        return out

    def bound(self, native, what):
        """The model made ready for the C core (clio_motion.native): ``"mesh"``, its ``"lines"`` or its ``"skin"``."""
        got = self._bound.get(what)
        if got is None:
            if what == "skin":
                s = self.metre
                got = native.Skin([(-x / s, z / s, y / s) for x, y, z in self.rest], self.skin)
            elif what == "lines":
                self.lines()
                got = native.bind(self._lines)
            else:
                got = native.bind(self.model, self.order)
            self._bound[what] = got
        return got

    def lines(self):
        """The body for a display that draws lines: ``(edges, faces)`` between the corners that ``pose`` gives
        with ``lines=True`` - outlines of its thick parts, a line for each thin one."""
        if self._lines is None:
            self._lines = lib().mesh.lines(self.rig)
        return self._lines["edges"], self._lines["faces"]

    def corners(self, pose, before, lines=False):
        """The model's corners (or its lines' corners) for a pose of the library's, in the model's space; and the
        skeleton, to hand back."""
        cm = lib()
        sk = cm.rig.skeleton(self.ch, pose, before)
        s = self.metre
        if lines:
            self.lines()
            return [(p[2] * s, p[0] * s, p[1] * s) for p in cm.mesh.place(self._lines, sk)], sk
        if self.skin is not None:
            # each joint's move from the template pose, on the model's axes: three rows of four numbers
            moves = []
            for j in range(len(self.rig["joints"])):
                m = cm.rig.joint_move(sk, j)              # glTF's axes, column after column
                moves.append((m[0], -m[8], -m[4], -m[12] * s, -m[2], m[10], m[6], m[14] * s, -m[1], m[9], m[5], m[13] * s))
            out = []
            for (x, y, z), carried in zip(self.rest, self.skin):
                if len(carried) == 1:
                    a = moves[carried[0][0]]
                    out.append((a[0] * x + a[1] * y + a[2] * z + a[3], a[4] * x + a[5] * y + a[6] * z + a[7],
                                a[8] * x + a[9] * y + a[10] * z + a[11]))
                    continue
                px = py = pz = 0.0
                for j, w in carried:
                    a = moves[j]
                    px += w * (a[0] * x + a[1] * y + a[2] * z + a[3])
                    py += w * (a[4] * x + a[5] * y + a[6] * z + a[7])
                    pz += w * (a[8] * x + a[9] * y + a[10] * z + a[11])
                out.append((px, py, pz))
            return out, sk
        pts = cm.mesh.place(self.model, sk)
        return [(pts[k][2] * s, pts[k][0] * s, pts[k][1] * s) for k in self.order], sk

    def clip(self, name, lines=False):
        """A clip made ready: ``(seconds, loops, its poses as corners)``, or None if the model has none of that
        name. ``die2`` and ``die3`` are ``die`` from other blows. ``lines``: the corners of its lines instead."""
        base, fall = name, 0
        if name in ("die2", "die3"):
            base, fall = "die", int(name[3]) - 1
        if base not in self.clip_names:
            return None
        mine = (self.shape if not lines else self.key + ("lines",), self.metre, name)
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
            elif base in ALOFT:                           # in the air, in the water: how high is the level's to say
                self.lines()
                sk, low = None, 1e9
                for pose in rec["frames"]:
                    sk = cm.rig.skeleton(self.ch, pose, sk)
                    low = min(low, min(p[1] for p in cm.mesh.place(self._lines, sk)))
                rec["frames"] = [cm.clips.shift_pose(pose, 0.0, CLEAR - low, 0.0) for pose in rec["frames"]]
            _recorded[key] = rec
        if rec is False:
            return None
        sk, poses = None, []
        for pose in rec["frames"]:
            pts, sk = self.corners(pose, sk, lines)
            poses.append(pts)
        made = _posed[mine] = (rec["duration"], rec["loop"], poses)
        return made

    def beats(self, name):
        """How long a clip is: a beat is a second of the motion."""
        c = self.clip(name)
        return c[0] if c else 0.0

    def pose(self, name, t, lines=False):
        """The corners ``t`` beats into a clip. One that goes round goes round; one played once is played again
        every whole number of beats it fits in (an attack every beat), and holds its end in between. ``lines``:
        the corners of its lines (see ``lines``) instead of its mesh's."""
        c = self.clip(name, lines) or self.clip("idle", lines)
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

    def playing(self, mid, clip, t, tick=0.0, firing=False, struck=False, fast=False, falling=None, dead=False,
                aloft=False, afloat=False):
        """What a level's monster shows: ``(clip, beats into it)`` for what the level says it is doing. ``clip``
        is the level's own choice (idle, walk, attack) and ``t`` its clock; ``tick`` is how far the beat's
        animation is (0..1). It runs if it is ``fast`` and can; an attack is held at its start while it aims
        and played while it fires; ``struck``, it staggers; ``falling`` (0..1: how far its end has come) or
        ``dead``, it falls - each monster by one of three blows, always the same one - and lies. ``aloft`` (it
        floats over the floor) one that flies beats its wings - hanging in the air where it can, when it is not
        going anywhere; ``afloat`` (it is in deep water) one that swims swims."""
        if falling is not None or dead:
            name = ("die", "die2", "die3")[mid % 3]
            c = self.clip(name)
            if c is not None:
                return name, c[0] * (1.0 if falling is None else max(0.0, min(1.0, falling))) * 0.999999
        if struck and self.clip("hit") is not None:
            return "hit", min(0.999999, 0.15 + tick) * self.clip("hit")[0]
        if clip == "attack" and self.clip("attack") is not None:
            return "attack", (min(tick, 0.999999) * 1.0 if firing else 0.0)
        if aloft and self.flies and clip in ("walk", "idle"):
            return ("hover" if clip == "idle" and self.clip("hover") is not None else "fly"), t
        if afloat and self.swims and clip in ("walk", "idle"):
            return ("hover" if clip == "idle" and self.clip("hover") is not None else "swim"), t
        if clip == "walk":
            if fast and self.clip("run") is not None:
                return "run", t
            if self.clip("walk") is not None:
                return "walk", t
        return (clip if self.clip(clip) is not None else "idle"), t


# ---------------------------------------------------------------- live: the core run for each body -------
MOST = 1 / 30.0                                              # the longest step the core is given at once


class Actor:
    """One body run live by the motion core, in place of clips: it is told how fast to go and which way, and
    what to do, and steps on its own feet - every one its own, none in step with another.

        a = Actor(model, x, y, heading)            # a Model with "motion"; where it stands, in cells
        a.step(dt, speed=1.4, heading=0.5)         # seconds; metres a second; radians (0 east, pi/2 south)
        a.step(dt, attack=True)                    # its attack, once; hit=(x, y) a blow from there; die=True
        a.x, a.y, a.heading                        # where it has got to
        a.corners()                                # its model's corners about that spot (the view: verts=)

    ``ground(x, y)``: the floor's height in cells, if it is not flat. A level's monster with ``actor`` set to
    one is drawn where the actor is, as it is (engine/firstperson.py); nothing in the rules knows."""

    def __init__(self, mdl, x=0.0, y=0.0, heading=0.0, ground=None):
        mv = mdl.motion
        if mv is None:
            raise ValueError("the model is not moved by CLIo Motion")
        cm = lib()
        self.model, self.moves, self.cm = mdl, mv, cm
        self.cells = mv.metre * mdl.scale                # cells to a metre, all told
        k = self.cells
        self.ground = ground
        self.terrain = (lambda X, Z: ground(X * k, Z * k) / k) if ground is not None else _flat
        self.body, self.S = None, None
        native = fast() if ground is None else None       # (a ground of its own: in Python, which can ask it)
        if native is not None:
            self.native = native
            self.body = native.Body(mv.character, mv.style)
            self.body.place(x / k, y / k, heading)
        else:
            self.S = cm.create_state(mv.ch, self.terrain)
            cm.place(self.S, mv.ch, self.terrain, x / k, y / k, heading)
        self.inp = {"speed": 0.0, "armed": mv.armed, "kit": mv.kit, "heading": heading}
        self.sk, self.events, self.down, self.pose = None, [], False, None
        self._again = True                                # the inputs have changed since the C core was last given them
        self.step(MOST)
        if mv.kit:                                        # its other weapons brought up
            for _ in range(45):
                self.step(MOST)

    @property
    def x(self):
        return (self.body.x if self.body is not None else self.S.px) * self.cells

    @property
    def y(self):
        return (self.body.z if self.body is not None else self.S.pz) * self.cells

    @property
    def heading(self):
        return self.body.heading if self.body is not None else self.S.h

    @property
    def speed(self):
        """Metres a second, as it is going."""
        return self.body.speed if self.body is not None else self.S.v

    def step(self, dt, speed=None, heading=None, attack=False, hit=None, die=None, aim=None, **more):
        """On by ``dt`` seconds. ``speed`` (metres a second) and ``heading`` stay as they were when not said.
        ``attack``: its attack (a bite, a claw, a sting, a shot, a swing), once. ``hit``: a blow, from the way
        ``(x, y)`` points (cells; its length is how hard, 1 an ordinary one). ``die``: it falls (True, or the
        way the blow goes, as ``hit``). ``aim``: a point ``(x, y, height)`` in cells its weapons are turned on.
        Anything else is an input of the library's (``crouch``, ``jump``, ``reload``...)."""
        cm, mv, S, inp = self.cm, self.moves, self.S, self.inp
        if dt <= 1e-6 and (self.pose is not None or self.body is not None):   # no time has passed
            return
        dt = max(dt, 1e-4)
        if speed is not None and speed != inp["speed"]:
            inp["speed"], self._again = float(speed), True
        if heading is not None and heading != inp["heading"]:
            inp["heading"], self._again = float(heading), True
        aim = [aim[0] / self.cells, aim[2] / self.cells, aim[1] / self.cells] if aim else None
        if aim != inp.get("aim"):
            inp["aim"], self._again = aim, True
        once = dict(more)
        if attack:
            ch = mv.ch
            if ch.get("beast"):
                once["bite"] = {}
            elif ch.get("arthro"):
                once["pinch" if ch["arthro"].get("claw") else "sting"] = {}
            elif ch.get("octo"):
                once["grab"] = {}
            elif (mv.kit or ch["mount"].get("kit")) == "sword":
                once["swing"] = {"kind": "slash"}
            else:
                once["fire"] = True
        if hit:
            once["hit"] = {"impulse": [1.6 * hit[0], 0.0, 1.6 * hit[1]]}
        if die and not self.down:
            push = die if isinstance(die, (tuple, list)) else (-math.cos(self.heading), -math.sin(self.heading))
            once["die"] = {"impulse": [2.4 * push[0], 1.0, 2.4 * push[1]]}
            self.down = True
        n = max(1, int(math.ceil(dt / MOST - 1e-9)))
        if self.body is not None:                          # in C: the inputs are handed over only when they change
            b = self.body
            for k in range(n):
                if k == 0 and (once or self._again):
                    b.step(dt / n, dict(inp, **once) if once else inp)
                    self._again = bool(once)               # (what is done once has to be taken back at the next step)
                elif self._again:
                    b.step(dt / n, inp)
                    self._again = False
                else:
                    b.step(dt / n)
            got = b.events()
            if got:
                self.events += got
                del self.events[:-16]
            return
        for k in range(n):
            if k == 0 and once:
                inp.update(once)
            self.pose = cm.step(S, mv.ch, inp, mv.style, self.terrain, dt / n)
            if k == 0:
                for key in once:
                    inp.pop(key, None)
            if S.events:
                self.events += [e["type"] if isinstance(e, dict) else e for e in S.events]
                del S.events[:]
        del self.events[:-16]

    def stand(self):
        """Up again (a switch: there is no getting up)."""
        if self.down:
            if self.body is not None:
                self.body.call("stand")
            else:
                self.cm.stand(self.S, self.moves.ch, self.terrain)
            self.down = False

    def corners(self, lines=False):
        """Its model's corners as it is now, about the spot it stands on, on the model's axes for a model that
        faces east (the view draws them with ``heading`` 0); ``lines``: its lines' corners."""
        if self.body is not None:
            flat = self.packed(lines)
            return list(zip(flat[0::3], flat[1::3], flat[2::3]))
        pts, self.sk = self.moves.corners(self.pose, self.sk, lines)
        m, k = self.model.scale, self.cells
        ox, oy = self.S.pz * k, self.S.px * k
        oz = self.ground(self.x, self.y) if self.ground is not None else 0.0
        if m == 1.0:
            return [(p[0] - ox, p[1] - oy, p[2] - oz) for p in pts]
        return [(p[0] * m - ox, p[1] * m - oy, p[2] * m - oz) for p in pts]

    def packed(self, lines=False):
        """``corners`` as one row of numbers (x y z x y z...), an ``array('d')``: what CLIo Picture takes as it is.
        With the C core it is that core's own row, written again at the next call: use it before."""
        b = self.body
        if b is None:
            from array import array
            from itertools import chain
            return array("d", chain.from_iterable(self.corners(lines)))
        mv, k = self.moves, self.cells
        if mv.skin is not None and not lines:              # from glTF's axes: x to the left, z forward
            return b.skin(mv.bound(self.native, "skin"), (-k, 0.0, 0.0, 0.0, 0.0, k, 0.0, k, 0.0, -b.z * k, -b.x * k, 0.0))
        return b.points(mv.bound(self.native, "lines" if lines else "mesh"),
                        (0.0, 0.0, k, k, 0.0, 0.0, 0.0, k, 0.0, -b.z * k, -b.x * k, 0.0))


class Crowd:
    """Bodies wandering about a yard, each run live (``Actor``): they stroll, stand, trot, turn back at the
    edge and now and then strike at nothing. ``step(dt)`` moves them all on; ``actors`` are they. The same
    ``seed`` gives the same wandering."""

    def __init__(self, mdl, spots, bounds, seed=1):
        import random
        self.rng = random.Random(seed)
        self.bounds = bounds                              # (x0, y0, x1, y1), in cells
        cm = lib()
        ch = mdl.motion.ch
        self.walk, self.run = cm.clips.walk_speed(ch), min(cm.clips.run_speed(ch), 2.2 * cm.clips.walk_speed(ch))
        self.actors = [Actor(mdl, x, y, self.rng.uniform(-math.pi, math.pi)) for x, y in spots]
        self.minds = [{"until": self.rng.uniform(0.0, 2.0), "speed": 0.0, "heading": a.heading} for a in self.actors]
        self.t = 0.0

    def step(self, dt):
        self.t += dt
        x0, y0, x1, y1 = self.bounds
        rng = self.rng
        for a, mind in zip(self.actors, self.minds):
            attack = False
            out = a.x < x0 or a.x > x1 or a.y < y0 or a.y > y1
            if out and not mind.get("back"):               # at the edge: back towards the middle
                mind.update(heading=math.atan2((y0 + y1) / 2 - a.y, (x0 + x1) / 2 - a.x) + rng.uniform(-0.5, 0.5),
                            speed=self.walk, until=self.t + 2.0, back=True)
            elif self.t >= mind["until"]:
                roll = rng.random()
                mind["back"] = False
                if roll < 0.3:
                    mind.update(speed=0.0, until=self.t + rng.uniform(1.0, 3.0))
                    attack = rng.random() < 0.4
                else:
                    mind.update(speed=self.run if roll > 0.85 else self.walk, heading=mind["heading"] + rng.uniform(-1.6, 1.6),
                                until=self.t + rng.uniform(1.5, 4.0))
            a.step(dt, speed=mind["speed"], heading=mind["heading"], attack=attack)
