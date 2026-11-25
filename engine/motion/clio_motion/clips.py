# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Daniel Sandner
"""CLIo Motion in Python: clips recorded from the core.

For a game that does not run the core every frame: a named clip is a list of poses, in place, that plays in a loop
(idle, walk, run, sneak, gallop, fly, swim...) or once (attack, hit, turn, die, jump...).

    clip = record(ch, "walk", frames=12)        # None if this character has no such clip
    clip["frames"]                              # the poses, the body over the origin
    clip["duration"], clip["loop"]              # seconds one playing takes; whether it goes round
    clip["speed"]                               # metres a second the body would cover (0 for a clip on the spot)
    names(ch)                                   # the clips this character has

A looping clip is exactly one cycle: its last pose runs into its first.  A pose is what ``step`` returns, so
``rig.skeleton`` and ``rig.parts`` take it.

A port of ``record`` in js/bake.js; checked against the numbers in spec/clips.txt.
"""
from __future__ import annotations

import math

from .body import KITS, PUNCH
from .ground import DIR_KEYS, STYLE, create_state
from .kernel import G, idle_period, wrap_pi
from .modes import Ladder, enter_fly, enter_ladder, enter_swim, grab_ledge, step

DT = 1 / 120


def _round(x):
    return math.floor(x + 0.5)


def walk_speed(ch):
    return _round(math.sqrt(0.22 * G * ch["L"]) * 20) / 20


def run_speed(ch):
    return min(ch["vmax"], _round(math.sqrt(1.7 * G * ch["L"]) * 20) / 20) if ch["gait"].get("run") else ch["vmax"]


def _base(ch):
    if ch.get("octo"):
        return ["idle", "walk", "sneak", "attack", "swim", "hover", "hit", "turn", "die"]
    if ch.get("arthro"):
        return ["idle", "walk", "run", "sneak", "attack", "sting", "hit", "turn", "die"]
    if ch.get("beast"):
        return ["idle", "walk", "run", "gallop", "sneak", "jump", "attack", "pounce", "hit", "turn", "die"]
    if ch["kind"] == "biped":
        return ["idle", "walk", "run", "sneak", "jump", "attack", "reload", "chop", "thrust", "block", "throw", "pickup", "carry", "putdown", "guard", "jab",
                "cross", "hook", "hit", "turn", "climb", "hang", "climbup", "die"]
    return ["idle", "walk", "run", "sneak", "jump", "attack", "hit", "turn", "die"]


def names(ch):
    """The clips a character can be asked for.  A few are still refused by ``record`` (None): gallop for one that
    does not gallop, the sword's swings without the sword, reload with it."""
    n = [c for c in _base(ch) if c != "sting" or ch.get("tail")]
    n[n.index("walk") + 1:n.index("walk") + 1] = ["back", "left", "right"]
    at = n.index("hit")
    if ch.get("fly"):
        n.insert(at, "fly")
        if ch["fly"].get("hover"):
            n.insert(at + 1, "hover")
    return n


def shift_pose(o, dx, dy, dz=0.0, key=None):
    """A pose moved by (dx, dy, dz): points are moved, directions are not."""
    if isinstance(o, list):
        if len(o) == 3 and isinstance(o[0], (int, float)) and not isinstance(o[0], bool):
            return o if key in DIR_KEYS else [o[0] + dx, o[1] + dy, o[2] + dz]
        return [shift_pose(v, dx, dy, dz, key) for v in o]
    if isinstance(o, dict):
        return {k: shift_pose(v, dx, dy, dz, k) for k, v in o.items()}
    return o


def _flat(x, z):
    return 0.0


def record(ch, name, frames=8, fps=None, kit=None, style=None, armed=True, impulse=None, hit_impulse=None, dt=DT):
    """One clip: ``{"name", "frames", "duration", "loop", "speed", "travel", "rise", "ladder"}``, or None if the
    character has none of that name.  frames: how many poses a looping clip is cut into; fps: poses a second for a
    clip played once (12; the punches 24).  kit: a soldier's weapons ("rifle", "pistols", "sword").  impulse: the
    blow that floors the body in "die" (in the world: the body faces +x), hit_impulse the one that staggers it in
    "hit".  dt: the step the core is run at (1/120 s, which is what the reference records at and what is checked;
    1/60 halves the work)."""
    DT = dt
    st = style or STYLE
    N = frames or 8
    S = create_state(ch, _flat)
    box = {"y0": None, "last_carry": None}
    inp = {"speed": 0, "crouch": 0, "aim": None, "fire": False, "armed": armed is not False, "jump": False, "die": None, "hit": None, "heading": None,
           "reload": False, "kit": None}

    def stp(dt):
        step(S, ch, inp, st, _flat, dt)
        del S.events[:]

    def run(sec):
        for _ in range(_round(sec / DT)):
            stp(DT)

    def grab():
        if box["y0"] is None:
            box["y0"] = S.y
        dy = box["y0"] - S.y if name in ("climb", "hang", "climbup") else 0
        p = shift_pose(S.pose, -S.px, dy, -S.pz)
        p["ladderShift"] = dy
        # a crate that has been set down stays in the picture to the end of the clip
        if p.get("carry"):
            box["last_carry"] = p["carry"]
        elif box["last_carry"] and name == "putdown":
            lc = box["last_carry"]
            p["carry"] = {"c": lc["c"], "f": lc["f"], "u": lc["u"], "side": lc["side"], "size": lc["size"], "held": False}
        return p

    def cycle(T):
        sub = max(1, _round(T / N / DT))
        dt = T / (N * sub)
        fr = []
        for _ in range(N):
            fr.append(grab())
            for _j in range(sub):
                stp(dt)
        return fr

    def to_wrap():
        guard = 0
        while True:
            prev = S.phase
            stp(DT)
            if not (S.phase >= prev and guard < 4000):
                break
            guard += 1

    def timed(sec, rate):
        fr, per = [], _round(1 / rate / DT)
        for _ in range(_round(sec * rate)):
            fr.append(grab())
            for _j in range(per):
                stp(DT)
        return fr

    def until_done(done, extra, rate=None):
        # record at a steady rate until done() says so, plus a few frames more
        fr, per, end = [], _round(1 / (fps or rate or 12) / DT), 0
        while len(fr) < 80 and end <= extra:
            fr.append(grab())
            for _j in range(per):
                stp(DT)
            if done():
                end += 1
        return fr

    def level_weapons():
        inp["aim"] = [1e4, 0]
        run(2)
        inp["aim"] = [1e4, S.y + 0.3 * ch["L"]]
        run(1)

    def once(key, value):
        inp[key] = value
        stp(DT)
        inp[key] = None

    out, dur, loop, speed, travel, rise = None, 0.0, True, 0, 0, 0
    if kit and kit in KITS and S.kit and kit != S.kit:      # put the default weapons away and bring this kit up
        inp["kit"] = kit
        run(1.5)
    if name == "idle":
        run(4)
        dur = idle_period(ch["L"])
        out = cycle(dur)
    elif name in ("walk", "run", "sneak", "gallop", "back", "left", "right"):
        if name == "gallop" and not ch["gait"].get("gallop"):
            return None
        # walking backwards and stepping sideways are asked for at the walking pace; the core itself slows them
        if name == "back":
            inp["dir"] = math.pi
        elif name == "left":
            inp["dir"] = -math.pi / 2
        elif name == "right":
            inp["dir"] = math.pi / 2
        inp["speed"] = 0.75 * ch["vmax"] if name == "gallop" else run_speed(ch) if name == "run" else 0.7 * walk_speed(ch) if name == "sneak" else walk_speed(ch)
        inp["crouch"] = 0.6 if name == "sneak" else 0
        run(8)
        to_wrap()
        dur, speed = S.stats["period"], S.v
        out = cycle(dur)
    elif name == "jump":
        run(3)
        inp["jump"] = True
        stp(DT)
        inp["jump"] = False
        rate = fps or 12
        per, tail, out = _round(1 / rate / DT), 0, []
        while len(out) < 40 and tail < 2:
            out.append(grab())
            for _j in range(per):
                stp(DT)
            if not S.jump:
                tail += 1
        dur, loop = len(out) / rate, False
    elif name == "attack":
        level_weapons()
        if ch.get("beast"):                                # an animal's attack is its bite
            once("bite", {})
        elif ch.get("arthro") and ch["arthro"].get("claw"):  # a scorpion's is its claw, a mantis's both forelegs
            once("pinch", {})
        elif ch.get("arthro"):                             # a wasp's is its sting
            once("sting", {})
        elif ch.get("octo"):                               # an octopus's is an arm shot out to grab
            once("grab", {})
        elif S.kit == "sword":
            once("swing", {"kind": "slash"})
        else:
            inp["fire"] = True
            stp(DT)
            inp["fire"] = False
        dur = 0.75 if S.kit == "sword" else 0.5
        out, loop = timed(dur, fps or 12), False
    elif name in ("chop", "thrust", "block"):
        # only with sword and shield: the other two swings, and the shield brought up and held
        if S.kit != "sword":
            return None
        run(2)
        if name == "block":
            inp["block"] = True
            out, dur, loop = timed(0.5, fps or 12), 0.5, False
        else:
            once("swing", {"kind": name})
            out, dur, loop = timed(0.75, fps or 12), 0.75, False
    elif name == "fly" or (name == "hover" and ch.get("fly")):
        # in the air: one wingbeat at cruising speed, or (for those that can) one hanging in place
        if not ch.get("fly"):
            return None
        run(1)
        enter_fly(S, ch)
        inp["height"] = 0.8 * ch["fly"]["height"]
        inp["speed"] = 0.55 * ch["fly"]["vmax"] if name == "fly" else 0
        run(8)
        to_wrap()
        dur, speed = S.stats["period"], S.v
        out = cycle(dur)
        box["y0"] = None
    elif name in ("swim", "hover"):
        # in the water: one jet cycle at cruising speed, or hanging in place with the arms spread
        if not ch.get("octo"):
            return None
        run(1)
        enter_swim(S, ch)
        inp["depth"] = 0.9
        inp["speed"] = 0.55 * ch["octo"]["vswim"] if name == "swim" else 0
        run(8)
        if name == "swim":
            to_wrap()
            dur, speed = S.stats["period"], inp["speed"]
        else:
            dur = 5.2
        out = cycle(dur)
    elif name == "sting":
        if not ch.get("arthro"):
            return None
        run(3)
        once("sting", {})
        out = until_done(lambda: not S.act, 2)
        dur, loop = len(out) / (fps or 12), False
    elif name == "pounce":
        # a leap of about three and a half leg lengths; the clip is in place, and its travel is given with it
        if not ch.get("beast"):
            return None
        run(3)
        px0 = S.px
        once("pounce", {})
        out = until_done(lambda: not S.jump and S.v < 0.05, 2)
        dur, loop, travel = len(out) / (fps or 12), False, S.px - px0
    elif name == "reload":
        # with empty magazines, so every weapon of the kit is reloaded in turn
        if not (S.ammo or ch["mount"].get("kit")) or (S.kit and KITS[S.kit].get("melee")):
            return None
        level_weapons()                                    # weapons up and level, as when firing
        S.ammo = [0 for _ in S.ammo]
        inp["reload"] = True
        stp(DT)
        inp["reload"] = False
        rate = fps or 12
        per, end, out = _round(1 / rate / DT), 0, []
        while len(out) < 60 and end < 2:
            out.append(grab())
            for _j in range(per):
                stp(DT)
            if not S.act:
                end += 1
        dur, loop = len(out) / rate, False
    elif name == "throw":
        if ch["kind"] != "biped":
            return None
        level_weapons()
        once("throw", {"target": [9 * ch["L"], 0, 0]})
        out = until_done(lambda: not S.act, 2)
        dur, loop = len(out) / (fps or 12), False
    elif name in ("pickup", "carry", "putdown"):
        # a crate from the ground in front: squat, lift, walk with it, set it down again
        if ch["kind"] != "biped":
            return None
        run(2)
        once("pickup", {})
        if name == "pickup":
            out = until_done(lambda: not S.act, 2)
            dur, loop = len(out) / (fps or 12), False
        else:
            run(2.5)
            if name == "carry":
                inp["speed"] = walk_speed(ch)
                run(8)
                to_wrap()
                dur, speed = S.stats["period"], S.v
                out = cycle(dur)
            else:
                inp["putdown"] = True
                stp(DT)
                inp["putdown"] = False
                out = until_done(lambda: not S.act and not S.carry and S.armed.x > (0.97 if inp["armed"] else -1), 2)
                dur, loop = len(out) / (fps or 12), False
    elif name == "guard" or name in PUNCH:
        # fists up in a fighting stance; the punches go straight ahead at head height and come back to the guard
        if ch["kind"] != "biped" or not ch.get("fight"):
            return None
        inp["guard"] = True
        run(4)
        if name == "guard":
            dur = idle_period(ch["L"])
            out = cycle(dur)
        else:
            once("punch", {"kind": name})
            out = until_done(lambda: not S.act, 1, 24)
            dur, loop = len(out) / (fps or 24), False
    elif name == "hit":
        # a blow from the front that staggers but does not floor: recorded until the body has settled
        run(3)
        once("hit", {"impulse": hit_impulse or [-1.6, 0, 0]})
        out = timed(1.0 * math.sqrt(ch["L"] / 0.92), fps or 12)
        dur, loop = len(out) / (fps or 12), False
    elif name == "turn":
        # turn round on the spot: ends facing the other way
        run(3)
        inp["heading"] = math.pi
        rate = fps or 12
        per, settled, out = _round(1 / rate / DT), 0, []
        while len(out) < 60 and settled < 3:
            out.append(grab())
            for _j in range(per):
                stp(DT)
            if abs(wrap_pi(math.pi - S.h)) < 0.02 and not any(leg.swing for leg in S.legs):
                settled += 1
        dur, loop = len(out) / rate, False
    elif name == "die":
        # a blow from the front, then the ragdoll runs until it lies still
        run(2)
        once("die", {"impulse": impulse or [-2.4, 1.0]})
        rate = fps or 12
        per, rest, out = _round(1 / rate / DT), 0, []
        while len(out) < 48 and rest < 3:
            out.append(grab())
            for _j in range(per):
                stp(DT)
            if S.rag and S.rag["asleep"]:
                rest += 1
        dur, loop = len(out) / rate, False
    elif name in ("hang", "climbup"):
        # hanging from a ledge, and the climb up on to it.  Both are in place: travel and rise say how far the climb
        # moves the body, forwards and up
        if ch["kind"] != "biped":
            return None
        run(2)
        grab_ledge(S, ch, [S.px + 0.38, 2.3, S.pz])
        run(2)
        box["y0"] = None
        if name == "hang":
            dur = 2.6
            out = cycle(dur)
        else:
            hx, hy = S.px, S.y
            inp["climb"] = True
            stp(DT)
            inp["climb"] = False
            out = until_done(lambda: S.mode != "ledge" or S.ledge["t"] > 0.95 * 1.5 * math.sqrt(ch["L"] / 0.92), 0)
            dur, loop, travel, rise = len(out) / (fps or 12), False, S.px - hx, S.y - hy
    elif name == "climb":
        if ch["kind"] != "biped":
            return None
        run(0.5)
        enter_ladder(S, ch, Ladder(0.36, 0, 0.3, lambda k: k * 0.3))
        inp["speed"] = 2.5
        run(4)
        to_wrap()
        dur, speed = S.stats["period"], S.v
        out = cycle(dur)
    else:
        return None
    return {"name": name, "frames": out, "duration": dur, "loop": loop, "speed": speed, "travel": travel, "rise": rise, "ladder": name == "climb"}


def record_all(ch, clips=None, **how):
    """Every clip the character has (or those named), in the order of ``names``."""
    out = []
    for n in names(ch):
        if clips is None or n in clips:
            c = record(ch, n, **how)
            if c:
                out.append(c)
    return out


def sample(clip, t):
    """Where a clip is at time ``t`` (seconds): ``(i, j, k)``, the poses to blend, pose ``i`` weighing 1 - k and
    pose ``j`` weighing k.  A looping clip goes round; one played once holds its last pose."""
    n = len(clip["frames"])
    if n < 2 or clip["duration"] <= 0:
        return 0, 0, 0.0
    u = t / clip["duration"] * n
    if clip["loop"]:
        u %= n
        i = int(u)
        return i, (i + 1) % n, u - i
    u = min(max(u, 0.0), n - 1.0)
    i = min(int(u), n - 2)
    return i, i + 1, u - i
