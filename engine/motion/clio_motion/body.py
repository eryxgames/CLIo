# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Daniel Sandner
"""CLIo Motion in Python, stage 3: upper bodies, weapons and actions, for every character on the ground.

For bipeds (the soldier): spine, head, arms, sideways aim, the kits (rifle, two pistols, sword and shield) held and
stowed, firing and recoil, reloading, the sword's swings and the shield's block, throwing, lifting and carrying a
crate, the fighting stance and punches.  For the mech: the hull, its turn towards the aim, and its guns.
A port of ``upperBody``, ``actTick`` and ``fireControl`` in js/core.js, statement for statement; checked against the
replays in spec/body/.

    S = create_state(ch, terrain)
    pose = step(S, ch, {"speed": 1.4, "armed": True, "aim": [8, 1.4, 2]}, STYLE, terrain, 1 / 60)

Animals: the spine that bends in a gallop, neck, head and jaw, the tail as a chain, bite and pounce.  Arthropods:
claws, the pinch, the sting.  The octopus: mantle, arms, grab and ink.  The quadruped robot and the spider mech.
"""
from __future__ import annotations

import math

from .ground import step_ground
from .kernel import G, TAU, clamp, decay, idle_noise, ik2, lerp, lob, reach_chain, smooth, wrap_pi

PROPS = {
    "rifle": {"len": 0.91, "body": 0.57, "grip": [0.24, -0.06], "gripLow": [0.225, -0.115], "fore": [0.53, -0.035], "magA": [0.35, -0.035],
              "magB": [0.35, -0.15], "kick": 1.5, "rise": 5, "rounds": 30, "reload": 1.7, "seat": 0.80},
    "pistol": {"len": 0.20, "body": 0.12, "grip": [0.025, -0.03], "gripLow": [0.0, -0.11], "fore": None, "magA": [0.012, -0.045],
               "magB": [0.012, -0.12], "kick": 1.6, "rise": 3, "rounds": 12, "reload": 1.1, "seat": 0.60},
    # a sword: 'muzzle' is its point, 'body' where the blade starts.  A shield: a board held by a grip behind its middle
    "sword": {"len": 0.95, "body": 0.15, "grip": [0.07, 0], "gripLow": [0.13, -0.09], "fore": None, "magA": [0.13, 0.09], "magB": [0.13, -0.09],
              "kick": 0, "rise": 0, "rounds": 0, "reload": 0, "seat": 0},
    "shield": {"len": 0.62, "body": 0.31, "grip": [0.31, 0.06], "gripLow": [0.31, 0.02], "fore": None, "magA": [0.26, 0.0], "magB": [0.36, 0.0],
               "kick": 0, "rise": 0, "rounds": 0, "reload": 0, "seat": 0},
    # what people who are not soldiers carry. A case by its handle: 'o' and 'muzzle' are its top corners, 'magA' and 'magB' its bottom
    # ones. A case on wheels pulled by its handle: 'o' is the axle, 'body' where the case ends and the handle's rods begin, 'muzzle'
    # the grip; 'magA' to 'magB' is the middle line of the case itself, which lies on the side of the rods away from the ground.
    "case": {"len": 0.42, "body": 0.21, "grip": [0.21, 0.035], "gripLow": [0.21, 0], "fore": None, "magA": [0, -0.30], "magB": [0.42, -0.30],
             "kick": 0, "rise": 0, "rounds": 0, "reload": 0, "seat": 0},
    "trolley": {"len": 0.98, "body": 0.56, "grip": [0.98, 0], "gripLow": [0.90, 0], "fore": None, "magA": [0.03, 0.11], "magB": [0.56, 0.11],
                "kick": 0, "rise": 0, "rounds": 0, "reload": 0, "seat": 0, "wheel": 0.035},
    # a gunner's: a chaingun carried at the hip by its rear grip and the handle on top, its barrels from 'body' to the muzzle and
    # its ammunition in a box under it ('magA' to 'magB'); and the same gun as one of a pair, one in each hand
    "chaingun": {"len": 1.05, "body": 0.50, "grip": [0.10, -0.07], "gripLow": [0.08, -0.16], "fore": [0.42, 0.11], "magA": [0.30, -0.07],
                 "magB": [0.30, -0.24], "kick": 0.32, "rise": 0.5, "rounds": 200, "reload": 3.2, "seat": 0.80},
    "sidegun": {"len": 1.05, "body": 0.50, "grip": [0.10, -0.07], "gripLow": [0.08, -0.16], "fore": None, "magA": [0.30, -0.07],
                "magB": [0.30, -0.24], "kick": 0.32, "rise": 0.5, "rounds": 150, "reload": 3.2, "seat": 0.80},
}
# civil: a kit for people who are not soldiers (and only for them); it is in the hand whether or not weapons are asked for.
# pace: the fastest it can be taken along, as a Froude number's root (1 is a hurried jog)
KITS = {"rifle": {"props": ["rifle"], "rate": 9}, "pistols": {"props": ["pistol", "pistol"], "rate": 7},
        "sword": {"props": ["sword", "shield"], "rate": 0, "melee": True},
        "hands": {"props": [], "rate": 0, "melee": True, "civil": True}, "case": {"props": ["case"], "rate": 0, "melee": True, "civil": True},
        "trolley": {"props": ["trolley"], "rate": 0, "melee": True, "civil": True, "pace": 1.0},
        # spin: seconds a chaingun's barrels take to come up to speed once the trigger is pulled - let go of it and they must
        # come up again. bodyKick: how hard each round pushes the body back, where that is not the body's own (0.5)
        "chaingun": {"props": ["chaingun"], "rate": 22, "spin": 0.35, "pace": 0.85, "bodyKick": 0.10},
        "chainguns": {"props": ["sidegun", "sidegun"], "rate": 30, "spin": 0.35, "pace": 0.70, "bodyKick": 0.10}}


def kit_fits(ch, name):
    """Any body that bears arms carries any weapon; people who are not soldiers carry their own things, and only those."""
    return ch["mount"].get("type") == "held" and name in KITS and (not KITS[name].get("civil")) == (not ch["mount"].get("civil"))


def kits_of(ch):
    """The kits a character can carry; none for one that holds nothing in its hands."""
    return [k for k in KITS if kit_fits(ch, k)] if ch["mount"].get("type") == "held" else []
SWINGS = {"slash": {"dur": 0.62}, "chop": {"dur": 0.70}, "thrust": {"dur": 0.55}}
CRATE = {"d": 0.44, "h": 0.36, "w": 0.50}
PUNCH = {"jab": {"hand": 1, "dur": 0.34, "hit": 0.36}, "cross": {"hand": 0, "dur": 0.50, "hit": 0.42}, "hook": {"hand": 1, "dur": 0.56, "hit": 0.46}}
PROP_PTS = ("o", "muzzle", "body", "grip", "gripLow", "fore", "magA", "magB")


def _add(a, b):
    return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]


def _sub(a, b):
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def _mul(a, s):
    return [a[0] * s, a[1] * s, a[2] * s]


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _len(a):
    return math.sqrt(_dot(a, a))


def _lerp3(a, b, t):
    return [lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t)]


def full_ammo(kit_name):
    return [PROPS[k]["rounds"] for k in KITS[kit_name]["props"]]


def held_kit(S, ch):
    return KITS[S.kit] if ch["mount"]["type"] == "held" and S.kit else None


def prop_at(kind, o, th, z):
    """A prop at a place: o is its rear end, th its angle in the body's forward-up plane, z how far to the side."""
    D = PROPS[kind]
    d = [math.cos(th), math.sin(th), 0]
    n = [-math.sin(th), math.cos(th), 0]

    def pt(a):
        return [o[0] + d[0] * a[0] + n[0] * a[1], o[1] + d[1] * a[0] + n[1] * a[1], z]

    return {"kind": kind, "o": [o[0], o[1], z], "muzzle": pt([D["len"], 0]), "body": pt([D["body"], 0]), "grip": pt(D["grip"]),
            "gripLow": pt(D["gripLow"]), "fore": pt(D["fore"]) if D["fore"] else None, "magA": pt(D["magA"]), "magB": pt(D["magB"]),
            "dir": d, "up": n, "flash": 0, "stow": 0}


def _stow_place(kind, k, root, u, f, zc):
    down = math.atan2(-u[1], -u[0])
    if kind == "rifle":         # muzzle down across the back
        return {"o": [root[0] + 0.65 * u[0] - 0.22 * f[0], root[1] + 0.65 * u[1] - 0.22 * f[1]], "th": down, "z": zc - 0.02}
    if kind == "chaingun":      # the same, and more of it
        return {"o": [root[0] + 0.72 * u[0] - 0.25 * f[0], root[1] + 0.72 * u[1] - 0.25 * f[1]], "th": down, "z": zc - 0.02}
    if kind == "sidegun":
        return {"o": [root[0] + 0.72 * u[0] - 0.25 * f[0], root[1] + 0.72 * u[1] - 0.25 * f[1]], "th": down, "z": zc + (0.11 if k == 0 else -0.11)}
    if kind == "sword":         # in a scabbard on the left hip, point down and back
        return {"o": [root[0] + 0.10 * u[0] + 0.06 * f[0], root[1] + 0.10 * u[1] + 0.06 * f[1]], "th": down - 0.45, "z": root[2] - 0.17}
    if kind == "shield":        # slung on the back, face outwards
        return {"o": [root[0] + 0.10 * u[0] - 0.20 * f[0], root[1] + 0.10 * u[1] - 0.20 * f[1]], "th": down + math.pi, "z": zc}
    if kind == "case":          # let go of: against the right thigh
        return {"o": [root[0] - 0.12 * u[0] - 0.21 * f[0], root[1] - 0.12 * u[1] - 0.21 * f[1]], "th": math.atan2(f[1], f[0]), "z": root[2] + 0.20}
    if kind == "trolley":       # let go of: standing behind
        return {"o": [root[0] - 0.80 * u[0] - 0.34 * f[0], root[1] - 0.80 * u[1] - 0.34 * f[1]], "th": down + math.pi, "z": zc + 0.22}
    return {"o": [root[0] + 0.05 * u[0] + 0.03 * f[0], root[1] + 0.05 * u[1] + 0.03 * f[1]], "th": down + 0.2,
            "z": root[2] + (0.15 if k == 0 else -0.15)}                 # hip holsters


def _ready_place(kind, k, chest, u, f, W, kick):
    if kind == "rifle":
        a = kick - 0.15                                      # the butt sits in the shoulder pocket
        return {"o": [chest[0] - 0.11 * u[0] + 0.10 * f[0] + math.cos(W) * a, chest[1] - 0.11 * u[1] + 0.10 * f[1] + math.sin(W) * a],
                "th": W, "z": chest[2] + 0.04}
    # a chaingun is fired from the hip: it turns about a point in front of the right hip, and recoil drives it straight back.
    # One of a pair is out at its own side
    if kind == "chaingun":
        return {"o": [chest[0] - 0.36 * u[0] + 0.10 * f[0] + math.cos(W) * (kick - 0.30), chest[1] - 0.36 * u[1] + 0.10 * f[1] + math.sin(W) * (kick - 0.30)],
                "th": W, "z": chest[2] + 0.13}
    if kind == "sidegun":
        return {"o": [chest[0] - 0.34 * u[0] + 0.06 * f[0] + math.cos(W) * (kick - 0.26), chest[1] - 0.34 * u[1] + 0.06 * f[1] + math.sin(W) * (kick - 0.26)],
                "th": W, "z": chest[2] + (0.25 if k == 0 else -0.25)}
    if kind == "sword":         # held low at the right side, point up and forward
        return {"o": [chest[0] - 0.24 * u[0] + 0.20 * f[0], chest[1] - 0.24 * u[1] + 0.20 * f[1]], "th": 0.95 + 0.3 * W, "z": chest[2] + 0.21}
    if kind == "shield":        # upright on the left forearm, in front of the body
        return {"o": [chest[0] - 0.36 * u[0] + 0.30 * f[0], chest[1] - 0.36 * u[1] + 0.30 * f[1]], "th": math.atan2(u[1], u[0]) - 0.12,
                "z": chest[2] - 0.20}
    # a case hangs level from the right hand at the end of a straight arm; a case on wheels leans from its axle up to the hand held low behind
    if kind == "case":
        return {"o": [chest[0] - 0.04 * u[0] - 0.19, chest[1] - 0.04 * u[1] - 0.565], "th": 0, "z": chest[2] + 0.25}
    if kind == "trolley":
        return {"o": [chest[0] - 0.04 * u[0] - 0.20 - 0.98 * math.cos(0.85), chest[1] - 0.04 * u[1] - 0.50 - 0.98 * math.sin(0.85)],
                "th": 0.85, "z": chest[2] + 0.22}
    r = 0.50 + kick                                          # arm's length; recoil also flips the muzzle up
    return {"o": [chest[0] + 0.03 * u[0] + math.cos(W) * r, chest[1] + 0.03 * u[1] + math.sin(W) * r], "th": W - 8 * kick,
            "z": chest[2] + (0.08 if k == 0 else -0.08)}


def _belt_place(k, root, u, f):                              # a pistol brought down to the magazine holder on the belt
    return {"o": [root[0] + 0.20 * u[0] + 0.16 * f[0], root[1] + 0.20 * u[1] + 0.16 * f[1]], "th": 0.1, "z": root[2] + (0.12 if k == 0 else -0.12)}


def _mix_place(a, b, t):
    return {"o": [lerp(a["o"][0], b["o"][0], t), lerp(a["o"][1], b["o"][1], t)], "th": a["th"] + wrap_pi(b["th"] - a["th"]) * t,
            "z": lerp(a["z"], b["z"], t)}


def start_reload(S, ch, asked=False):
    """asked: the player asked for it, so full weapons are reloaded too; otherwise only those that are short."""
    kit = held_kit(S, ch)
    if not kit or kit.get("melee") or S.act or S.armed.x < 0.8 or S.mode not in ("ground", "ride"):
        return False
    q = [i for i in range(len(kit["props"])) if S.ammo[i] < PROPS[kit["props"][i]]["rounds"]]
    if not q and asked:
        q = list(range(len(kit["props"])))
    if not q:
        return False
    S.act = {"name": "reload", "queue": q, "gun": q[0], "t": 0.0, "done": False, "dur": PROPS[kit["props"][q[0]]]["reload"] * math.sqrt(ch["L"] / 0.92)}
    S.events.append({"type": "reload", "gun": q[0]})
    return True


def _fire_control(S, ch, inp, dt):
    m = ch["mount"]
    kit = held_kit(S, ch)
    n = len(kit["props"]) if kit else (m.get("n") or 1)
    if kit and kit.get("melee"):                             # blades are swung, not fired
        S.flash[0] = S.flash[1] = 0
        return
    S.cool -= dt
    if kit and kit.get("spin") and not inp.get("fire"):      # a chaingun's barrels come up to speed before the first round
        S.cool = kit["spin"]
    for i in range(2):
        S.flash[i] = max(0, S.flash[i] - dt / 0.06)
        S.kick[i].step(0, m["omega"], 0.6, dt)
    S.rise.step(0, m["omega"] * 0.7, 0.7, dt)
    if not inp.get("fire") or S.cool > 0 or S.mode not in ("ground", "ride") or (S.act and S.act["name"] != "reload") or m["type"] == "jaw":
        return
    g = -1
    if kit:
        if S.armed.x < 0.8:
            return
        # the next gun in turn that has rounds and is not being reloaded; with none left, fire starts a reload
        for i in range(1, n + 1):
            c = (S.gun + i) % n
            if S.ammo[c] > 0 and not (S.act and S.act["gun"] == c):
                g = c
                break
        if g < 0:
            start_reload(S, ch)
            return
        S.ammo[g] -= 1
    else:
        g = 1 - S.gun if n == 2 else 0
    S.gun = g
    D = PROPS[kit["props"][g]] if kit else m
    S.cool = 1 / (kit["rate"] if kit else m["rate"])
    S.flash[g] = 1
    S.kick[g].v -= D["kick"]
    S.rise.v += D["rise"]
    S.lean.v -= (kit and kit.get("bodyKick")) or m.get("bodyKick") or 0.5
    S.events.append({"type": "fire", "gun": g})


def _fold_half(a):
    a = wrap_pi(a)
    return a - math.pi if a > math.pi / 2 else a + math.pi if a < -math.pi / 2 else a


def _act_tick(S, ch, inp, dt, B):
    """Timed actions for upright characters.  Each one takes over the hands and adds to the lean, the turn of the
    torso and the crouch, while the legs carry on underneath."""
    AC = {"lean": 0.0, "tw": 0.0, "ext": 0.0, "load": 0.0, "wind": 0.0, "hit": 0.0}
    a = S.act
    k = math.sqrt(ch["L"] / 0.92)
    ground = S.mode in ("ground", "ride")
    idle = not a and ground and not S.jump
    S.guard.step(1 if inp.get("guard") and not S.carry and ground and not (a and a["name"] == "throw") else 0, 16, 1, dt)
    S.block.step(1 if inp.get("block") and (inp.get("guard") or (S.kit == "sword" and S.armed.x > 0.5)) else 0, 24, 1, dt)
    g = clamp(S.guard.x, 0, 1)
    S.act_crouch = 0.12 * g + 0.10 * clamp(S.block.x, 0, 1)
    S.act_back = 0.0
    swing = inp.get("swing")
    if swing and S.kit == "sword" and S.armed.x > 0.8 and ground and not S.carry and not S.jump and (not a or (a["name"] == "swing" and a["t"] > 0.8 * a["dur"])):
        sk0 = swing.get("kind") if swing.get("kind") in SWINGS else "slash"
        a = S.act = {"name": "swing", "kind": sk0, "t": 0.0, "dur": SWINGS[sk0]["dur"] * k, "done": False, "live": False, "prevTip": None}
    throw = inp.get("throw")
    if throw is not None and throw is not False and idle and not S.carry and g < 0.3:
        tg = throw.get("target") if isinstance(throw, dict) else None
        a = S.act = {"name": "throw", "t": 0.0, "dur": 1.25 * k, "done": False, "target": list(tg) if tg else None}
    pickup = inp.get("pickup")
    if pickup is not None and pickup is not False and idle and not S.carry and S.standing and g < 0.3:
        pk = pickup if isinstance(pickup, dict) else {}
        sz = pk.get("size") or CRATE
        at = pk.get("at")
        if at:
            at = list(at)
        else:
            lx = S.x + 0.20 * k + sz["d"] / 2
            at = B["to_w"]([lx, B["terrain"](lx, 0) + sz["h"] / 2, 0])
        S.carry = {"at": at, "size": sz, "yaw": _fold_half(pk["heading"] - S.h) if pk.get("heading") is not None else 0, "ca": 0, "hk": 0, "held": False}
        a = S.act = {"name": "pickup", "t": 0.0, "dur": 1.7 * k, "done": False}
    if inp.get("putdown") and idle and S.carry and S.carry["held"] and S.standing:
        c = S.carry
        c["yaw"] = 0
        lx = S.x + 0.20 * k + c["size"]["d"] / 2
        c["at"] = B["to_w"]([lx, B["terrain"](lx, 0) + c["size"]["h"] / 2, 0])
        a = S.act = {"name": "putdown", "t": 0.0, "dur": 1.5 * k, "done": False}
    punch = inp.get("punch")
    if punch is not None and punch is not False and g > 0.5 and ground and not S.carry and (not a or (a["name"] == "punch" and a["t"] > 0.7 * a["dur"])):
        pu = punch if isinstance(punch, dict) else {}
        kind = pu.get("kind") if pu.get("kind") in PUNCH else "jab"
        pk2 = PUNCH[kind]
        # a punch may follow another before that one is quite finished: start from where the hands and shoulders are
        a = S.act = {"name": "punch", "kind": kind, "hand": pk2["hand"], "hit": pk2["hit"], "t": 0.0, "dur": pk2["dur"] * k, "done": False,
                     "target": list(pu["target"]) if pu.get("target") else None, "prev": None, "tw0": S.ac_tw or 0, "rel0": list(S.ho_rel) if S.ho_rel else None}
    if a and a["name"] != "reload":
        a["t"] += dt
        q = min(a["t"] / a["dur"], 1)
        name = a["name"]
        if name == "throw":
            # wind up turning away and leaning back, then whip round and through
            AC["tw"] = 0.55 * smooth(0.24, 0.50, q) - 1.0 * smooth(0.56, 0.70, q) + 0.45 * smooth(0.78, 1, q)
            AC["lean"] = -0.14 * smooth(0.24, 0.50, q) + 0.36 * smooth(0.56, 0.70, q) - 0.22 * smooth(0.78, 1, q)
        elif name in ("pickup", "putdown"):
            c = S.carry
            # how far down the handles are decides how deep the squat is: a crate on a table needs none
            dk = clamp((0.95 - (c["at"][1] + 0.25 * c["size"]["h"] - S.g_ref.x) / ch["L"]) / 0.66, 0.1, 1)
            if name == "pickup":
                down = smooth(0, 0.34, q) * (1 - smooth(0.48, 0.95, q))
                c["hk"] = smooth(0.08, 0.36, q)
                c["ca"] = smooth(0.45, 1, q)
                if not c["held"] and q >= 0.42:
                    c["held"] = True
                    S.events.append({"type": "grab"})
            else:
                down = smooth(0.04, 0.46, q) * (1 - smooth(0.66, 1, q))
                c["ca"] = 1 - smooth(0.14, 0.58, q)
                c["hk"] = 1 - smooth(0.66, 0.95, q)
                if c["held"] and q >= 0.60:
                    c["held"] = False
                    S.events.append({"type": "putdown", "pos": list(c["at"]), "heading": S.h})
            # a proper squat: hips go back as they go down, and the back leans over the load
            S.act_crouch = 1.25 * dk * down
            S.act_back = 0.24 * k * dk * down
            AC["lean"] = 0.47 * dk * down
        elif name == "swing":
            # wind up, land, recover
            AC["wind"] = smooth(0, 0.26, q) * (1 - smooth(0.28, 0.42, q))
            AC["hit"] = smooth(0.28, 0.42, q) * (1 - smooth(0.56, 1, q))
            a["live"] = 0.28 < q < 0.50
            if a["kind"] == "slash":
                AC["tw"] = 0.80 * AC["wind"] - 0.70 * AC["hit"]
                AC["lean"] = 0.08 * AC["hit"]
            elif a["kind"] == "chop":
                AC["tw"] = 0.15 * AC["wind"] - 0.12 * AC["hit"]
                AC["lean"] = -0.08 * AC["wind"] + 0.20 * AC["hit"]
            else:
                AC["tw"] = 0.20 * AC["wind"] - 0.22 * AC["hit"]
                AC["lean"] = 0.16 * AC["hit"]
            S.act_back = -0.08 * k * AC["hit"]              # the weight goes into it
        elif name == "punch":
            track = inp.get("track")
            if track and q < 0.7 * a["hit"]:
                a["target"] = list(track)                   # still on its way out: follow the target
            if a["kind"] == "jab":
                AC["ext"] = smooth(0, 0.36, q) * (1 - smooth(0.46, 1, q))
                AC["tw"] = 0.22 * AC["ext"]
                AC["lean"] = 0.05 * AC["ext"]
            elif a["kind"] == "cross":
                # the hips and shoulders turn first and the fist follows
                AC["ext"] = smooth(0.10, 0.42, q) * (1 - smooth(0.52, 1, q))
                AC["tw"] = -0.85 * smooth(0, 0.40, q) * (1 - smooth(0.52, 1, q))
                AC["lean"] = 0.12 * AC["ext"]
            else:
                sw = smooth(0.22, 0.46, q)
                ret = smooth(0.60, 1, q)
                AC["load"] = smooth(0, 0.22, q) * (1 - ret)
                AC["ext"] = sw * (1 - ret)
                AC["tw"] = 0.2 * smooth(0, 0.22, q) * (1 - sw) - 0.6 * AC["ext"]
                AC["lean"] = 0.04 * AC["ext"]
            if a["t"] < 0.1:
                AC["tw"] = lerp(a["tw0"], AC["tw"], smooth(0, 0.1, a["t"]))
        if a["t"] >= a["dur"]:
            if name == "putdown":
                S.carry = None
            S.act = None
    S.ac_tw = AC["tw"]
    if S.carry:
        AC["lean"] -= 0.08 * S.carry["ca"]                  # lean back against the load
    AC["tw"] += 0.35 * g
    AC["lean"] += (0.05 - 0.10 * clamp(S.block.x, 0, 1)) * g
    return AC


def upper_body(S, ch, inp, st, dt, legs, B):
    kind_ch = ch["kind"]
    root, m = B["root"], ch["mount"]
    pose = {"kind": kind_ch, "root": root, "pitch": B["pitch"], "legs": legs, "crouch": S.crouch}
    if S.ammo is None and m.get("kit"):
        S.ammo = full_ammo(m["kit"])
    # kits: the weapons are put away before changing to another set, then the new ones come up
    kit_want = (inp.get("kit") if inp.get("kit") and kit_fits(ch, inp.get("kit")) else S.kit) if m["type"] == "held" else None
    if kind_ch == "biped":
        AC = _act_tick(S, ch, inp, dt, B)
    elif ch.get("beast"):
        AC = _beast_tick(S, ch, inp, dt)
    elif ch.get("arthro"):
        AC = _arthro_tick(S, ch, inp, dt)
    elif ch.get("octo"):
        AC = _octo_tick(S, ch, inp, dt)
    else:
        AC = {"lean": 0.0, "tw": 0.0, "ext": 0.0, "load": 0.0}
    # hands that are busy with a load or a fight cannot hold weapons: those are put away first
    busy = bool(S.carry) or S.guard.x > 0.05 or (kind_ch == "biped" and bool(inp.get("guard")))
    ready = (bool(inp.get("armed")) or bool(m.get("civil"))) and kit_want == S.kit and not busy
    if kit_want != S.kit and S.armed.x < 0.04:
        S.kit = kit_want
        S.ammo = full_ammo(S.kit)
        S.gun = 0
    if not ready and S.act and S.act["name"] == "reload":
        S.act = None
    if inp.get("reload"):
        start_reload(S, ch, True)
    _fire_control(S, ch, inp, dt)
    S.lean.step((B["leanBase"] + AC["lean"]) * (1 if kind_ch == "biped" else 0.45), 38 / B["Tn"], 0.8, dt)
    S.armed.step(1 if ready else 0, 14, 1, dt)
    S.flinch.step(0, 27 / B["Tn"], 0.5, dt)
    lean = S.lean.x
    FL = clamp(S.flinch.x, -0.3, 1.2)
    bank = B["bank"] or 0
    sway0 = B["sway0"] or 0
    u = [math.sin(lean), math.cos(lean), 0]
    f = [math.cos(lean), -math.sin(lean), 0]
    pose["lean"] = lean
    pose["pack"] = clamp(S.pack.x, -0.06 * ch["L"], 0.06 * ch["L"])

    def twd(v, a):          # turn a direction round the body's own long axis (u); a positive angle turns forward towards the right
        c, s = math.cos(a), math.sin(a)
        q = _dot(u, v) * (1 - c)
        return [v[0] * c + (v[1] * u[2] - v[2] * u[1]) * s + u[0] * q, v[1] * c + (v[2] * u[0] - v[0] * u[2]) * s + u[1] * q,
                v[2] * c + (v[0] * u[1] - v[1] * u[0]) * s + u[2] * q]

    def twp(p, c0, a):
        return _add(c0, twd(_sub(p, c0), a))

    def aim_from(pivot, share):
        """Where the weapon points.  Up and down: a spring chases the aim point and recoil is added on top.  Sideways:
        the upper body turns towards the point, as far as its limit allows; a point behind the body is let go."""
        lim = m["yaw"] if m.get("yaw") is not None else 1
        round_ = lim >= math.pi
        want = -0.5 * smooth(0.8, 2.2, S.idle_t) if m["type"] == "held" else 0.12 * (B["idle"] or 0) * idle_noise(S.t, B["P"] or 4, 6.0)
        yw = S.twist.x - wrap_pi(S.twist.x) if round_ else 0
        aim = B["aim"]
        if aim:
            dx, dz = aim[0] - pivot[0], aim[2] - pivot[2]
            y = math.atan2(dz, dx)
            reach = 1
            if round_:
                yw = S.twist.x + wrap_pi(y - S.twist.x)
            else:
                reach = 1 - smooth(lim + 0.25, lim + 0.8, abs(y))
                yw = clamp(y, -lim, lim) * reach * share
            want = reach * math.atan2(aim[1] - pivot[1], max(math.sqrt(dx * dx + dz * dz), 0.05 * ch["L"]))
        S.aim.step(clamp(want, m["min"], m["max"]), m["aimOmega"], 0.9, dt)
        S.twist.step(yw, m["aimOmega"] * 0.7, 1, dt)
        return S.aim.x + S.rise.x

    if kind_ch == "mech":
        P = ch["pod"]
        pc = _add(root, _mul(u, P["h"]))
        pc[2] += bank * P["h"]
        Wm = aim_from(_add(pc, [0.1, -0.3, 0]), 1)
        tm = S.twist.x                                       # the hull turns on the hips
        dm = twd([math.cos(Wm), math.sin(Wm), 0], tm)
        pose["chest"] = pc
        pose["u"] = u
        pose["f"] = twd(f, tm)
        pose["side"] = twd([0, 0, 1], tm)
        pose["mounts"] = []
        for g in range(2):
            sd = 1 if g == 0 else -1
            base = _add(pc, twd([0.1 * f[0] - 0.3 * u[0], 0.1 * f[1] - 0.3 * u[1], sd * P["gunZ"]], tm))
            b = _add(base, _mul(dm, S.kick[g].x))
            pose["mounts"].append({"joint": base, "base": _add(b, _mul(dm, -0.35)), "tip": _add(b, _mul(dm, P["gunLen"])), "dir": dm,
                                   "flash": S.flash[g], "side": sd})
        return pose

    if kind_ch != "biped":
        return _horizontal(S, ch, inp, dt, legs, B, pose, AC, lean, FL, aim_from)

    T, A, gp, kit, e = ch["torso"], ch["arms"], B["gp"], held_kit(S, ch), S.armed.x
    breath = 0.007 * ch["L"] * B["idle"] * math.sin(TAU * S.t / B["P"])
    chest = [root[0] + u[0] * T["len"], root[1] + u[1] * T["len"] + breath, root[2] - 0.5 * sway0 + bank * T["len"]]
    hl = lean * 0.35 + 0.5 * FL * S.flinch_dir
    hr_ = T["neck"] + T["headR"] * 0.7
    head = [chest[0] + math.sin(hl) * hr_, chest[1] + math.cos(hl) * hr_, chest[2] + bank * hr_]
    W = aim_from(_add(chest, _add(_mul(u, -0.11), _mul(f, 0.10))), lerp(0.5, 1, e)) + st["bounce"] * 0.012 * gp["moving"] * math.sin(2 * TAU * S.phase) + 0.25 * FL
    # the turn of everything above the hips: sideways aim plus whatever the action adds
    tws = S.twist.x + AC["tw"]

    # the action in progress: rs is how far through the reload of gun act.gun we are, q how far through any other
    act, rs = S.act, -1
    if act and act["name"] == "reload" and kit:
        act["t"] += dt
        rs = act["t"] / act["dur"]
        AD = PROPS[kit["props"][act["gun"]]]
        if not act["done"] and rs >= AD["seat"]:
            act["done"] = True
            S.ammo[act["gun"]] = AD["rounds"]
            S.kick[act["gun"]].v += 0.6
            S.events.append({"type": "loaded", "gun": act["gun"]})
        if rs >= 1:
            act["queue"].pop(0)
            if act["queue"]:
                act["gun"] = act["queue"][0]
                act["t"] = 0.0
                act["done"] = False
                act["dur"] = PROPS[kit["props"][act["gun"]]]["reload"] * math.sqrt(ch["L"] / 0.92)
                rs = 0
            else:
                S.act = act = None
                rs = -1
    an = act["name"] if act else None
    q = min(act["t"] / act["dur"], 1) if act else 0

    # eP: how far each prop is out of its holster; eH: how much each hand is on its weapon.
    # A throw takes the right hand away: the rifle is left to the other hand, a pistol goes back in its holster.
    eP, eH, tk = [e, e], [e, e], 0
    if an == "throw":
        tk = smooth(0, 0.16, q) * (1 - smooth(0.82, 1, q))
        eH[0] = e * (1 - tk)
        if kit and kit["props"][0] == "pistol":
            eP[0] = eH[0]

    props, hold = [], [None, None]
    if kit:
        for i, kind in enumerate(kit["props"]):
            rel = rs if an == "reload" and act["gun"] == i else -1
            Wi, slide = W, 0
            if kind == "rifle" and rel >= 0:                 # muzzle dips while the hand is away
                Wi -= 0.32 * smooth(0, 0.12, rel) * (1 - smooth(0.84, 1, rel))
            if kind == "rifle":
                Wi -= 0.45 * tk
            if kind in ("chaingun", "sidegun") and rel >= 0:     # a new belt: the muzzle goes down while it is fed in
                Wi -= 0.5 * smooth(0, 0.15, rel) * (1 - smooth(0.8, 1, rel))
            place = _ready_place(kind, i, chest, u, f, Wi, S.kick[i].x)
            if kind == "pistol" and rel >= 0:
                # one-handed: the pistol comes down to the belt, the magazine drops into the holder and a fresh one is pushed home
                place = _mix_place(place, _belt_place(i, root, u, f), smooth(0, 0.3, rel) * (1 - smooth(0.66, 1, rel)))
                slide = 0.10 * (smooth(0.30, 0.42, rel) - smooth(0.48, 0.60, rel))
            if kind == "sword" and an == "swing":
                wd, ht = AC["wind"], AC["hit"]
                if act["kind"] == "slash":
                    place["th"] = lerp(place["th"], 0.30 - 0.2 * ht, max(wd, ht))
                    so = [-0.05 * wd + 0.20 * ht, 0.14 * wd + 0.16 * ht]
                elif act["kind"] == "chop":
                    place["th"] = lerp(lerp(place["th"], 2.35, wd), -0.30, ht)
                    so = [-0.06 * wd + 0.22 * ht, 0.30 * wd + 0.12 * ht]
                else:
                    place["th"] = lerp(place["th"], 0.05, max(wd, ht))
                    so = [-0.14 * wd + 0.30 * ht, 0.14 * wd + 0.20 * ht]
                    place["z"] = lerp(place["z"], chest[2] + 0.12, ht)
                place["o"] = [place["o"][0] + f[0] * so[0] + u[0] * so[1], place["o"][1] + f[1] * so[0] + u[1] * so[1]]
            if kind == "case":
                # it swings a little with the arm that holds it, against the leg on that side
                cs = -0.09 * st["arm"] * gp["moving"] * S.legs[0].fwd
                place["o"] = [place["o"][0] + cs, place["o"][1] + 0.8 * cs * cs]
                place["th"] = 0.5 * cs
            if kind == "trolley":
                # the hand stays where it is; the axle is put on the ground behind, wherever the ground is there
                PT = PROPS["trolley"]
                hx = place["o"][0] + PT["len"] * math.cos(place["th"])
                hy = place["o"][1] + PT["len"] * math.sin(place["th"])
                for _pass in range(2):                  # twice: where the axle comes to rest depends on how high the ground is there
                    gw = B["terrain"](place["o"][0], place["z"])
                    if gw > hy - 1.3 * PT["len"]:
                        tt = math.asin(clamp((hy - gw - PT["wheel"]) / PT["len"], 0.12, 0.97))
                        place = {"o": [hx - PT["len"] * math.cos(tt), hy - PT["len"] * math.sin(tt)], "th": tt, "z": place["z"]}
            if kind == "shield":
                # blocking brings the shield up and across in front of the face and chest; a swing of the sword opens it a little
                bk2 = clamp(S.block.x, 0, 1)
                opn = 0.5 * AC["hit"] if an == "swing" else 0
                place["o"] = [place["o"][0] + f[0] * (0.08 * bk2 - 0.06 * opn) + u[0] * 0.20 * bk2,
                              place["o"][1] + f[1] * (0.08 * bk2 - 0.06 * opn) + u[1] * 0.20 * bk2]
                place["z"] = lerp(place["z"], chest[2] - 0.04, bk2) - 0.08 * opn
            place = _mix_place(_stow_place(kind, i, root, u, f, chest[2]), place, eP[i])
            w = prop_at(kind, place["o"], place["th"], place["z"])
            w["flash"] = S.flash[i]
            w["stow"] = 1 - eP[i]
            if slide:
                w["magA"] = [w["magA"][0] - w["up"][0] * slide, w["magA"][1] - w["up"][1] * slide, w["magA"][2]]
                w["magB"] = [w["magB"][0] - w["up"][0] * slide, w["magB"][1] - w["up"][1] * slide, w["magB"][2]]
            props.append(w)
    # hands: the right hand holds prop 0; the left holds prop 1, or the foregrip of a two-handed prop
    if props:
        hold[0] = props[0]["grip"]
        hold[1] = props[1]["grip"] if len(props) > 1 else props[0]["fore"]
    if an == "reload" and act["gun"] == 0 and props and props[0]["kind"] == "rifle":
        # reloading the rifle: the off hand leaves the foregrip, takes the magazine to the pouch on the hip, comes back
        # with a fresh one, seats it and returns.  Every waypoint is a live point, so it works on the move.
        w0 = props[0]
        nn, seat, mlen, kq, mag_held = w0["up"], w0["magB"], 0.115, 0, True
        pouch = [root[0] + 0.10 * u[0] + 0.12 * f[0], root[1] + 0.10 * u[1] + 0.12 * f[1], root[2] - 0.16]
        below = [seat[0] - 0.07 * nn[0], seat[1] - 0.07 * nn[1], seat[2]]
        if rs < 0.16:
            hp = _lerp3(w0["fore"], seat, smooth(0, 0.16, rs))
            mag_held = False
        elif rs < 0.40:
            kq = smooth(0.16, 0.40, rs)
            hp = _lerp3(seat, pouch, kq)
            pull = 0.06 * math.sin(math.pi * kq)
            hp[0] -= nn[0] * pull
            hp[1] -= nn[1] * pull
        elif rs < 0.50:
            kq = 1
            hp = [pouch[0], pouch[1] - 0.025 * math.sin(math.pi * (rs - 0.40) / 0.10), pouch[2]]
        elif rs < 0.74:
            kq = 1 - smooth(0.50, 0.74, rs)
            hp = _lerp3(below, pouch, kq)
        elif rs < 0.80:
            hp = _lerp3(below, seat, smooth(0.74, 0.80, rs))
        else:
            hp = _lerp3(seat, w0["fore"], smooth(0.80, 1, rs))
            mag_held = False
        hold[1] = hp
        if mag_held:
            mx, my = lerp(nn[0], u[0], kq), lerp(nn[1], u[1], kq)
            ml = math.sqrt(mx * mx + my * my) or 1
            w0["magB"] = list(hp)
            w0["magA"] = [hp[0] + mx / ml * mlen, hp[1] + my / ml * mlen, hp[2]]

    # Hands taken over by an action.  Each entry is a target for that hand, how firmly it applies (k) and which way the
    # elbow points.  Targets are worked out before the torso's turn is applied; a point that must stay put in the world
    # or on the hips is turned back first (unturn), so that it ends up there.
    HO, gA, crate = [None, None], clamp(S.guard.x, 0, 1), S.carry

    def unturn(p):
        return twp(p, chest, -tws)

    def from_chest(fw, up2, right):
        return [chest[0] + f[0] * fw + u[0] * up2, chest[1] + f[1] * fw + u[1] * up2, chest[2] + right]

    if gA > 0.01:
        # on guard: lead (left) fist out in front of the chin, rear fist by the jaw; blocking pulls both in and up
        bk = clamp(S.block.x, 0, 1)
        HO[0] = {"p": from_chest(lerp(0.17, 0.15, bk), lerp(0.03, 0.12, bk), 0.08), "k": gA, "pole": [-0.2, -1, 0.5]}
        HO[1] = {"p": from_chest(lerp(0.27, 0.20, bk), lerp(0.05, 0.13, bk), -0.09), "k": gA, "pole": [-0.2, -1, -0.5]}
        if an == "punch":
            ph = act["hand"]
            PT = unturn(B["to_l"](act["target"])) if act["target"] else from_chest(0.62, 0.06, 0)
            sd2 = 1 if ph == 0 else -1
            if act["kind"] == "hook":
                # the fist goes out to the side with the elbow raised, then the turn of the body brings it round
                HO[ph]["p"] = _lerp3(_lerp3(HO[ph]["p"], from_chest(0.20, 0.02, sd2 * 0.36), AC["load"]), PT, AC["ext"])
                HO[ph]["pole"] = _lerp3(HO[ph]["pole"], [0, 0.3, sd2], AC["load"])
            else:
                HO[ph]["p"] = _lerp3(HO[ph]["p"], PT, AC["ext"])
        # remember where the fists are, measured from the chest, so that the next punch can start from there
        for i in range(2):
            hx2, hy2 = HO[i]["p"][0] - chest[0], HO[i]["p"][1] - chest[1]
            hr = [hx2 * f[0] + hy2 * f[1], hx2 * u[0] + hy2 * u[1], HO[i]["p"][2] - chest[2]]
            if an == "punch" and act["rel0"] and act["rel0"][i] and act["t"] < 0.1:
                hr = _lerp3(act["rel0"][i], hr, smooth(0, 0.1, act["t"]))
                HO[i]["p"] = from_chest(hr[0], hr[1], hr[2])
            S.ho_rel[i] = hr
    else:
        S.ho_rel = [None, None]
    if an == "throw":
        # right hand: to the belt for the grenade, back behind the shoulder, over the top, and through
        belt = unturn([root[0] + 0.10 * u[0] + 0.06 * f[0], root[1] + 0.10 * u[1] + 0.06 * f[1], root[2] + 0.17])
        back, fol = from_chest(-0.22, 0.16, 0.30), from_chest(0.42, -0.06, 0.02)
        if q < 0.24:
            tp = belt
        elif q < 0.56:
            tp = _lerp3(belt, back, smooth(0.24, 0.52, q))
        elif q < 0.72:
            sq = smooth(0.56, 0.72, q)
            arc = 0.34 * math.sin(math.pi * sq)
            tp = _lerp3(back, fol, sq)
            tp[0] += u[0] * arc
            tp[1] += u[1] * arc
        else:
            tp = fol
        HO[0] = {"p": tp, "k": smooth(0, 0.18, q) * (1 - smooth(0.80, 1, q)), "pole": [-0.6, 0.1, 0.8]}
    if crate:
        # the crate: resting at its place in the world, or held in front of the hips, or on the way between the two
        cz = crate["size"]
        cb = [root[0] + f[0] * (0.12 + cz["d"] / 2) + u[0] * 0.17, root[1] + f[1] * (0.12 + cz["d"] / 2) + u[1] * 0.17, root[2]]
        cc = _lerp3(B["to_l"](crate["at"]), cb, crate["ca"])
        yr = crate["yaw"] * (1 - crate["ca"])
        if crate["held"] and act:
            # while it is in the hands it cannot be further from the shoulders than the arms are long
            sm = [chest[0] - 0.04 * u[0], chest[1] - 0.04 * u[1], root[2]]
            hm = [cc[0], cc[1] + 0.25 * cz["h"], cc[2]]
            lat2 = max(0, cz["w"] / 2 + 0.015 - T["shoulderW"])
            hmax = math.sqrt(math.pow(0.99 * (A["upper"] + A["lower"]), 2) - lat2 * lat2)
            hd2 = _sub(hm, sm)
            hdl = _len(hd2)
            if hdl > hmax:
                cc = _add(cc, _mul(hd2, hmax / hdl - 1))
        # it is kept nearly level: only a third of the body's lean reaches it
        fbx, fby = lerp(1, f[0], 0.33 * crate["ca"]), lerp(0, f[1], 0.33 * crate["ca"])
        fbl = math.sqrt(fbx * fbx + fby * fby)
        cf = [fbx / fbl * math.cos(yr), fby / fbl, fbx / fbl * math.sin(yr)]
        cs = [-math.sin(yr), 0, math.cos(yr)]
        cu = [cs[1] * cf[2] - cs[2] * cf[1], cs[2] * cf[0] - cs[0] * cf[2], cs[0] * cf[1] - cs[1] * cf[0]]
        for i in range(2):
            sd2 = 1 if i == 0 else -1
            HO[i] = {"p": unturn(_add(cc, _add(_mul(cu, 0.25 * cz["h"]), _mul(cs, sd2 * (cz["w"] / 2 + 0.015))))), "k": crate["hk"],
                     "pole": [-0.5, -0.7, sd2 * 0.7]}
        pose["carry"] = {"c": cc, "f": cf, "u": cu, "side": cs, "size": cz, "held": crate["held"]}
    else:
        pose["carry"] = None

    if B.get("hands"):                                       # reins or handles, unless the hand is busy
        for i in range(2):
            if not HO[i] or not HO[i]["k"] > 0:
                HO[i] = {"p": unturn(B["hands"][i]), "k": 1 - eH[i], "pole": [-0.2, -1, 0.5 if i == 0 else -0.5]}
    swing = st["arm"] * 0.2 * gp["moving"] * legs[0]["side"] * S.legs[0].fwd * (1 - 0.7 * e)
    arms = []
    for s in range(2):
        side = 1 if s == 0 else -1
        sh = _add(chest, _mul(u, -0.04))
        sh[0] -= side * swing * T["shoulderW"]
        sh[2] = chest[2] + side * T["shoulderW"]
        # nothing in the hand: the arm swings against the leg on its own side
        th = -st["arm"] * (0.42 + 0.45 * gp["run"]) * gp["moving"] * S.legs[s].fwd + lean * 0.3 + 0.9 * S.air_b - 0.6 * B["prep"] - 0.6 * FL * S.flinch_dir
        el = 0.22 + 1.25 * gp["run"] + 0.35 * max(0, th) + 0.3 * S.crouch + 0.4 * S.air_b + 0.6 * abs(FL)
        eb = [sh[0] + math.sin(th) * A["upper"], sh[1] - math.cos(th) * A["upper"], sh[2] + side * 0.03]
        free = [eb[0] + math.sin(th + el) * A["lower"], eb[1] - math.cos(th + el) * A["lower"], eb[2]]
        hk = eH[s] if hold[s] else 0
        hand = _lerp3(free, hold[s], hk) if hold[s] else free
        pole = _lerp3([-1, -0.25, side * 0.2], [-0.5, -0.9, side * 0.6], hk)
        if HO[s] and HO[s]["k"] > 0:
            hand = _lerp3(hand, HO[s]["p"], HO[s]["k"])
            pole = _lerp3(pole, HO[s]["pole"], HO[s]["k"])
        mid, end = ik2(sh, hand, A["upper"], A["lower"], pole)
        arms.append({"shoulder": sh, "elbow": mid, "hand": end, "side": side})
    # sideways aim: everything above the hips turns about the spine
    head = twp(head, chest, tws)
    for a_ in arms:
        a_["shoulder"] = twp(a_["shoulder"], chest, tws)
        a_["elbow"] = twp(a_["elbow"], chest, tws)
        a_["hand"] = twp(a_["hand"], chest, tws)
    for i, pw in enumerate(props):
        ta = tws * eP[i] if pw["kind"] in ("pistol", "sword") else tws       # holstered pistols and a sheathed sword stay with the hips
        for key in PROP_PTS:
            if pw[key]:
                pw[key] = twp(pw[key], chest, ta)
        pw["dir"] = twd(pw["dir"], ta)
        pw["up"] = twd(pw["up"], ta)
    gz = W * 0.6 * e * (1 - gA) + 0.3 * B["idle"] * idle_noise(S.t, B["P"], 5.0)
    pose["chest"] = chest
    pose["head"] = head
    pose["gaze"] = twd([math.cos(gz), math.sin(gz), 0], tws)
    pose["arms"] = arms
    pose["props"] = props
    pose["u"] = u
    pose["f"] = twd(f, tws)
    pose["side"] = twd([0, 0, 1], tws)

    # the grenade: on the belt until the hand has it, and let go at the top of the swing
    in_hand = an == "throw" and q >= 0.20 and not act["done"]
    fa = _sub(arms[0]["hand"], arms[0]["elbow"])
    fal = _len(fa) or 1
    pose["grenade"] = {
        "p": _add(arms[0]["hand"], _mul(fa, 0.05 / fal)) if in_hand
        else [root[0] + 0.09 * u[0] + 0.07 * f[0], root[1] + 0.09 * u[1] + 0.07 * f[1], root[2] + 0.185],
        "held": in_hand}
    if in_hand and q >= 0.635:
        act["done"] = True
        gw = B["to_w"](pose["grenade"]["p"])
        tgt = act["target"] or B["to_w"]([S.x + 9 * ch["L"], S.g_ref.x, 0])
        S.events.append({"type": "throw", "pos": gw, "vel": lob(gw, tgt, 15 * math.sqrt(ch["L"] / 0.92)), "target": list(tgt)})
    if an == "swing" and not act["done"] and q >= 0.40:
        # as it lands, tell the game where the blade is (hilt and point) and which way it is travelling
        act["done"] = True
        bh, bp = B["to_w"](props[0]["body"]), B["to_w"](props[0]["muzzle"])
        bd = _sub(bp, act["prevTip"]) if act["prevTip"] else [0, 0, 0]
        bl = _len(bd) or 1
        S.events.append({"type": "strike", "kind": act["kind"], "hilt": bh, "point": bp, "dir": _mul(bd, 1 / bl)})
    if an == "swing":
        act["prevTip"] = B["to_w"](props[0]["muzzle"])
    if an == "punch":
        # at full reach, tell the game where the fist is and which way it was going: it decides what was hit
        fw = B["to_w"](arms[act["hand"]]["hand"])
        if not act["done"] and q >= act["hit"]:
            act["done"] = True
            pd = _sub(fw, act["prev"]) if act["prev"] else None
            pl2 = _len(pd) if pd else 0
            if pl2 < 1e-6:
                pd = _sub(fw, B["to_w"](arms[act["hand"]]["shoulder"]))
                pl2 = _len(pd) or 1
            S.events.append({"type": "punch", "kind": act["kind"], "hand": act["hand"], "pos": fw, "dir": _mul(pd, 1 / pl2),
                             "miss": _len(_sub(fw, act["target"])) if act["target"] else 0})
        act["prev"] = fw
    return pose


def _target(v):
    """The target of an input like {"target": [x, y, z]}, or None."""
    t = v.get("target") if isinstance(v, dict) else None
    return list(t) if t else None


def _asked(v):
    return v is not None and v is not False


def _beast_tick(S, ch, inp, dt):
    """A beast's own actions.  bite: the neck shoots out, the jaws snap ('bite' event).  A pounce (handled with the
    jump) leaps onto a target with the jaws open ('pounce' event on landing)."""
    AC = {"lean": 0.0, "tw": 0.0, "ext": 0.0, "load": 0.0, "jaw": 0.0, "alert": 0.0}
    a, k, J = S.act, math.sqrt(ch["L"] / 0.7), S.jump
    S.act_back = 0.0
    S.act_crouch = 0.0
    bite = inp.get("bite")
    if _asked(bite) and not a and S.mode in ("ground", "fly") and not J:
        a = S.act = {"name": "bite", "t": 0.0, "dur": 0.46 * k, "done": False, "target": _target(bite)}
    if a and a["name"] == "bite":
        a["t"] += dt
        q = min(a["t"] / a["dur"], 1)
        AC["ext"] = smooth(0.05, 0.34, q) * (1 - smooth(0.42, 1, q))
        AC["jaw"] = 0.9 * smooth(0, 0.22, q) * (1 - smooth(0.33, 0.37, q))
        AC["alert"] = 1
        AC["lean"] = 0.10 * AC["ext"]
        S.act_back = -0.12 * k * AC["ext"]
        S.act_crouch = 0.2 * AC["ext"]
        if a["t"] >= a["dur"]:
            S.act = None
    if J and J.pounce:
        AC["alert"] = 1
        AC["jaw"] = 0.85 if J.stage == "air" else 0.85 * (1 - smooth(0, 0.07, J.t)) if J.stage == "land" else 0.25
        AC["ext"] = 0.7 if J.stage == "air" else 0.7 * (1 - smooth(0, 0.3, J.t)) if J.stage == "land" else 0
    return AC


def _arthro_tick(S, ch, inp, dt):
    """An arthropod's own actions.  pinch: the nearer claw shoots out and shuts ('pinch' event).  sting: the tail rears
    back, then whips over the head onto the target ('sting' event)."""
    AC = {"lean": 0.0, "tw": 0.0, "ext": 0.0, "load": 0.0, "jaw": 0.0, "alert": 0.0, "sting": 0.0, "rear": 0.0, "shut": 0.0}
    a, az = S.act, ch["arthro"]
    free = not a and S.mode in ("ground", "fly")
    S.act_back = 0.0
    S.act_crouch = 0.0
    if az.get("rock") and S.standing and S.mode == "ground":
        S.act_back = az["rock"] * math.sin(TAU * S.t / 1.4)         # a mantis rocks like a leaf in the wind
    pinch, sting = inp.get("pinch"), inp.get("sting")
    if _asked(pinch) and free:
        a = S.act = {"name": "pinch", "t": 0.0, "dur": az.get("strike") or 0.5, "done": False, "target": _target(pinch), "side": 0}
    elif _asked(sting) and free and ch.get("tail"):
        a = S.act = {"name": "sting", "t": 0.0, "dur": 0.72, "done": False, "target": _target(sting)}
    if a and a["name"] in ("pinch", "sting"):
        a["t"] += dt
        q = min(a["t"] / a["dur"], 1)
        AC["alert"] = 1
        if a["name"] == "pinch":
            AC["ext"] = smooth(0.05, 0.36, q) * (1 - smooth(0.52, 1, q))
            AC["jaw"] = smooth(0, 0.2, q)
            AC["shut"] = smooth(0.36, 0.41, q) * (1 - smooth(0.62, 0.92, q))
            S.act_back = -0.06 * AC["ext"]
        else:
            AC["rear"] = smooth(0, 0.20, q) * (1 - smooth(0.22, 0.32, q))
            AC["sting"] = smooth(0.22, 0.40, q) * (1 - smooth(0.52, 1, q))
            S.act_back = -0.14 * AC["sting"]
            AC["lean"] = 0.3 * AC["sting"]
        if a["t"] >= a["dur"]:
            S.act = None
    return AC


def _octo_tick(S, ch, inp, dt):
    """grab: the nearest arm lifts off the ground, shoots out and curls round the target ('grab' event).
    ink: a puff of ink ('ink' event)."""
    AC = {"lean": 0.0, "tw": 0.0, "ext": 0.0, "load": 0.0, "jaw": 0.0, "alert": 0.0, "ink": False}
    a = S.act
    S.act_back = 0.0
    S.act_crouch = 0.0
    S.ink_t = max(0, (S.ink_t or 0) - dt)
    grab = inp.get("grab")
    if _asked(grab) and not a and S.mode == "ground":
        a = S.act = {"name": "grab", "t": 0.0, "dur": 0.8, "done": False, "target": _target(grab), "arm": -1}
    if a and a["name"] == "grab":
        a["t"] += dt
        q = min(a["t"] / a["dur"], 1)
        AC["alert"] = 1
        AC["ext"] = smooth(0.04, 0.40, q) * (1 - smooth(0.62, 1, q))
        AC["lean"] = 0.15 * AC["ext"]
        S.act_back = -0.05 * AC["ext"]
        if a["t"] >= a["dur"]:
            S.act = None
    if inp.get("ink") and S.ink_t <= 0:
        S.ink_t = 1.2
        AC["ink"] = True
        S.jaw.v += 9
    S.jaw.step(0, 14, 0.6, dt)                              # the mantle's squeeze, shared by ink and jets
    return AC


def chain_step(S, key, T, l_size, B, base, body_ang, ctl, dt):
    """A tail (or any trailing chain) as a row of links, each with its own direction and turning speed.  A spring turns
    a link to carry on from the one before it, bent by 'curl', so a movement at the root runs down the chain and
    reaches the tip late.  Each link is also a pendulum on a moving pivot: when the body speeds up, stops, bounces or
    turns, the links swing the other way.  ctl: lift, yaw, curl, and pull = {"pts", "k"} to pass through given points
    (a strike).  Returns the n + 1 points, in the body's frame."""
    n, C = T["n"], S.chains.get(key)
    sz = math.sqrt(l_size / 0.7)
    om0 = T["omega"] / sz
    zeta = T.get("zeta") or 0.45
    soft = T["soft"] if T.get("soft") is not None else 0.5
    th0 = body_ang + math.pi + T["rest"] - ctl["lift"]
    ps0 = clamp(ctl["yaw"], -1.2, 1.2)
    curl = T["curl"] + (ctl.get("curl") or 0)
    sag = T["sag"] if T.get("sag") is not None else 0.2
    dr = B.get("drift") or [0, 0]
    if not C or C["n"] != n:
        C = S.chains[key] = {"n": n, "th": [th0 + k * curl for k in range(n)], "ps": [ps0] * n, "vth": [0.0] * n, "vps": [0.0] * n,
                             "by": base[1], "vy": 0.0, "ay": 0.0, "dr": list(dr), "ax": 0.0, "az": 0.0}
    # how the root of the tail is being thrown about: forwards, up and down (the gait's bounce), sideways (a turn, a shove)
    vy = (base[1] - C["by"]) / dt
    kf = decay(25, dt)
    C["ay"] += (clamp((vy - C["vy"]) / dt, -3 * G, 3 * G) - C["ay"]) * kf
    C["vy"] = vy
    C["by"] = base[1]
    C["ax"] += (clamp(S.a + (dr[0] - C["dr"][0]) / dt, -4 * G, 4 * G) - C["ax"]) * kf
    C["az"] += (clamp(S.v * S.om + (dr[1] - C["dr"][1]) / dt, -4 * G, 4 * G) - C["az"]) * kf
    C["dr"] = list(dr)
    # worked in steps of 1/120 s at most, so that a game running at 30 steps a second gets the same tail
    nsub = max(1, math.ceil(dt * 120 - 1e-6))
    hdt = dt / nsub
    inert = T["inert"] if T.get("inert") is not None else 1
    pull = ctl.get("pull")
    pulling = bool(pull) and pull["k"] > 0
    seg, bend = T["seg"], T.get("bend") or 1.3
    pts = None
    for _ in range(nsub):
        pts = [list(base)]
        pth, pps, pvt, pvp = th0 - curl, ps0, 0.0, 0.0
        for k in range(n):
            om = om0 * (1 - soft * k / max(n - 1, 1))
            ell = max(0.5 * seg * (n - k), seg) * 2.2 / inert
            th, ps, tt = C["th"][k], C["ps"][k], pth + curl
            tp = pps if k == 0 else 0.94 * pps
            cps = math.cos(ps)
            fth = -(-C["ax"] * math.sin(th) + (C["ay"] + sag * G) * math.cos(th)) / ell
            fps = -(C["az"] * cps - C["ax"] * math.cos(th) * math.sin(ps)) / ell
            C["vth"][k] += (om * om * wrap_pi(tt - th) - 2 * zeta * om * (C["vth"][k] - pvt) + fth) * hdt
            C["vps"][k] += (om * om * (tp - ps) - 2 * zeta * om * (C["vps"][k] - pvp) + fps) * hdt
            th += C["vth"][k] * hdt
            ps += C["vps"][k] * hdt - S.om * hdt * math.cos(th) * 0.8       # the body turns under a tail that would rather keep pointing where it did
            if pulling:
                a, b = pull["pts"][k], pull["pts"][k + 1]
                dx, dy, dz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
                dl = math.sqrt(dx * dx + dy * dy + dz * dz) or 1
                th += wrap_pi(math.atan2(dy, dx) - th) * pull["k"]
                ps += (math.asin(clamp(dz / dl, -1, 1)) - ps) * pull["k"]
                C["vth"][k] *= 1 - pull["k"]
                C["vps"][k] *= 1 - pull["k"]
            # a link bends only so far from the one before, and does not go through the ground
            bmax = 2.5 if pulling else bend
            off = wrap_pi(th - tt)
            if abs(off) > bmax:
                th = tt + clamp(off, -bmax, bmax)
                C["vth"][k] = 0.0
            smax = 1.35 if k == 0 else abs(pps) + bend
            if abs(ps) > smax:
                ps = clamp(ps, -smax, smax)
                C["vps"][k] = 0.0
            cps = math.cos(ps)
            prev = pts[k]
            q = [prev[0] + seg * math.cos(th) * cps, prev[1] + seg * math.sin(th) * cps, prev[2] + seg * math.sin(ps)]
            gy = B["terrain"](q[0], q[2]) + 0.03
            if q[1] < gy and prev[1] >= gy - 1e-6:
                sv = clamp((gy - prev[1]) / (seg * max(cps, 0.2)), -1, 1)
                a1 = math.asin(sv)
                a2 = math.pi - a1
                th = a1 if abs(wrap_pi(a1 - th)) < abs(wrap_pi(a2 - th)) else a2
                if C["vth"][k] * math.cos(th) < 0:
                    C["vth"][k] = 0.0
                q = [prev[0] + seg * math.cos(th) * cps, prev[1] + seg * math.sin(th) * cps, prev[2] + seg * math.sin(ps)]
            C["th"][k] = th
            C["ps"][k] = ps
            pts.append(q)
            pth, pps, pvt, pvp = th, ps, C["vth"][k], C["vps"][k]
    return pts


def _arm_curve(hip, knee, foot, seg):
    """An octopus arm through its leg: seven points on a curve from hip to tip, with links of one length."""
    c = [2 * knee[i] - 0.5 * (hip[i] + foot[i]) for i in range(3)]
    pts = []
    for i in range(7):
        u = i / 6
        w = 1 - u
        pts.append([w * w * hip[j] + 2 * w * u * c[j] + u * u * foot[j] for j in range(3)])
    return reach_chain(pts, hip, foot, seg, 1)


def wing_pose(ch, root, ax, up, fa, fa2, fold):
    """Two wings of two bones each.  fa, fa2: how far the arm and the hand are raised; fold: 0 spread, 1 folded like a Z
    along the body (so no bone changes length)."""
    F, out = ch["fly"], []
    sw0 = F.get("sweep") or 0.15
    for s in (1, -1):
        wr = [root[0] + ax[0] * F["at"][0] + up[0] * F["at"][1], root[1] + ax[1] * F["at"][0] + up[1] * F["at"][1], root[2] + s * F["at"][2]]

        def direction(a, sweep):
            c, sn, ss = math.cos(a), math.sin(a), math.sin(sweep)
            return [up[0] * sn - ax[0] * ss * c, up[1] * sn - ax[1] * ss * c, s * c * math.cos(sweep)]

        def hang(dv):       # which way the membrane hangs from a bone: behind it when spread, in against the body when folded
            t = [s * (dv[1] * up[2] - dv[2] * up[1]), s * (dv[2] * up[0] - dv[0] * up[2]), s * (dv[0] * up[1] - dv[1] * up[0])]
            return _mul(t, 1 / (_len(t) or 1))

        d1 = direction(lerp(fa, 0.22, fold), lerp(sw0, 1.40, fold))
        d2 = direction(lerp(fa2, 0.30, fold), lerp(sw0 + 0.2, 1.5 if F.get("zfold") is False else -1.25, fold))
        mid = _add(wr, _mul(d1, F["w1"]))
        tip = _add(mid, _mul(d2, F["w2"]))
        out.append({"root": wr, "mid": mid, "tip": tip, "t1": hang(d1), "t2": hang(d2), "chord": F["chord"], "side": s})
    return out


def _horizontal(S, ch, inp, dt, legs, B, pose, AC, lean, FL, aim_from):
    """Horizontal bodies: animals, the quadruped robot, arthropods, the octopus, the spider mech."""
    root = B["root"]
    cp, sn = math.cos(B["pitch"] + lean * 0.3), math.sin(B["pitch"] + lean * 0.3)
    idle, P = B["idle"], B["P"]

    def loc(x, y, z=0):
        return [root[0] + x * cp - y * sn, root[1] + x * sn + y * cp, root[2] + z]

    pose["axis"] = [cp, sn, 0]
    pose["up"] = [-sn, cp, 0]
    if ch["kind"] == "quad" and ch.get("beast"):
        # An animal's body: the spine bends in the middle (flex), the neck carries the head high at rest and low and
        # forward at speed, the head turns to what it watches, the jaw is hinged, the tail is a chain.
        Bz, flex, gq = ch["beast"], B["flex"] or 0, B["gp"]
        pa = B["pitch"] + lean * 0.3 + (Bz.get("tilt") or 0)
        fa2 = pa - flex

        def loc_b(x, y, z=0):
            a2 = pa + (flex if x < 0 else -flex)
            c2, s2 = math.cos(a2), math.sin(a2)
            return [root[0] + x * c2 - y * s2, root[1] + x * s2 + y * c2, root[2] + z]

        nb = loc_b(Bz["half"] + 0.03, 0.10)
        Wb = aim_from(nb, 1)
        tb2 = S.twist.x
        S.jaw.step(AC["jaw"], 60, 0.75, dt)
        carry = Bz["neckUp"] * (1 - 0.55 * gq["run"] - 0.3 * (gq["gal"] or 0)) - 0.35 * AC["ext"] + 0.12 * idle * idle_noise(S.t, P, 5.0) - 0.4 * max(0, FL)
        na = fa2 + carry + 0.5 * Wb
        nlen = Bz["neck"] * (1 + 0.28 * AC["ext"])
        hdp = [nb[0] + nlen * math.cos(na) * math.cos(0.6 * tb2), nb[1] + nlen * math.sin(na), nb[2] + nlen * math.cos(na) * math.sin(0.6 * tb2)]
        ga2 = 0.35 * fa2 + 0.9 * Wb - 0.10 * (1 - AC["alert"]) + 0.10 * idle * idle_noise(S.t, P, 6.0)
        gzb = [math.cos(ga2) * math.cos(tb2), math.sin(ga2), math.cos(ga2) * math.sin(tb2)]
        act_b = S.act if S.act and S.act["name"] == "bite" else None
        if act_b and act_b["target"] and AC["ext"] > 0:
            # biting at something: the head goes to it as far as the neck will stretch, muzzle first
            tl = B["to_l"](act_b["target"])
            want = _sub(tl, _mul(gzb, Bz["skull"]))
            wd = _sub(want, nb)
            wl = _len(wd) or 1
            wmax = Bz["neck"] * 1.45
            if wl > wmax:
                want = _add(nb, _mul(wd, wmax / wl))
            hdp = _lerp3(hdp, want, AC["ext"])
            td2 = _sub(tl, hdp)
            tl2 = _len(td2)
            if tl2 > 1e-4:
                gzb = _lerp3(gzb, _mul(td2, 1 / tl2), 0.8 * AC["ext"])
                gzb = _mul(gzb, 1 / (_len(gzb) or 1))
        sdb = [-math.sin(tb2), 0, math.cos(tb2)]
        # keep the head's side vector square to where it looks
        sdb = _sub(sdb, _mul(gzb, _dot(sdb, gzb)))
        sdb = _mul(sdb, 1 / (_len(sdb) or 1))
        gub = [sdb[1] * gzb[2] - sdb[2] * gzb[1], sdb[2] * gzb[0] - sdb[0] * gzb[2], sdb[0] * gzb[1] - sdb[1] * gzb[0]]
        jo = clamp(S.jaw.x, 0, 1.1)
        hinge = _add(hdp, _add(_mul(gzb, 0.02), _mul(gub, -0.035)))
        jd = _add(_mul(gzb, math.cos(jo)), _mul(gub, -math.sin(jo)))
        jtip = _add(hinge, _mul(jd, Bz["jaw"]))
        pose["back"] = loc_b(-(Bz.get("back") or Bz["half"]), 0)
        pose["front"] = loc_b(Bz["half"], 0)
        pose["neck"] = nb
        pose["head"] = hdp
        pose["gaze"] = gzb
        pose["side"] = sdb
        pose["mounts"] = [{"joint": hdp, "base": hinge, "tip": jtip, "dir": jd, "flash": 0, "side": 0}]
        pose["jaw"] = jo
        pose["alert"] = AC["alert"]
        pose["flex"] = flex
        if act_b and not act_b["done"] and act_b["t"] >= 0.365 * act_b["dur"]:
            act_b["done"] = True
            mz = B["to_w"](_add(hdp, _mul(gzb, Bz["skull"])))
            ch_, sh_ = math.cos(S.h), math.sin(S.h)
            S.events.append({"type": "bite", "pos": mz, "dir": [gzb[0] * ch_ - gzb[2] * sh_, gzb[1], gzb[0] * sh_ + gzb[2] * ch_],
                             "miss": _len(_sub(mz, act_b["target"])) if act_b["target"] else 0})
        Jb = S.jump
        if Jb and Jb.pounce and Jb.stage == "land" and not Jb.struck:
            Jb.struck = True
            S.events.append({"type": "pounce", "pos": B["to_w"](_add(hdp, _mul(gzb, Bz["skull"])))})
        Tl = ch.get("tail")
        if Tl:
            # the tail streams out at speed, goes up when the animal is roused, tucks under after a blow, and wags at rest
            wag = Tl["wag"] * idle * math.sin(4 * TAU * S.t / P) + 0.6 * Tl["wag"] * AC["alert"] * math.sin(19 * S.t) + Tl["sway"] * gq["moving"] * math.sin(TAU * S.phase)
            pose["tailPts"] = chain_step(S, "tail", Tl, ch["L"], B, loc_b(Tl["at"][0], Tl["at"][1]), pa + flex,
                                         {"lift": Tl["lift"] * (0.45 * gq["run"] + 0.75 * (gq["gal"] or 0)) + Tl["alert"] * AC["alert"] - 0.7 * abs(FL), "yaw": wag}, dt)
            pose["tail"] = pose["tailPts"][Tl["n"]]
        else:
            pose["tail"] = loc_b(-Bz["half"] - 0.2, 0.05)
    elif ch["kind"] == "quad":
        neck, hd = loc(0.40, 0.08), loc(0.60, 0.22)
        Wq = (aim_from(hd, 1) + 0.2 * idle * idle_noise(S.t, P, 5.0)) * 0.8
        tq = S.twist.x                                       # the head turns on the neck
        dq = [math.cos(Wq) * math.cos(tq), math.sin(Wq), math.cos(Wq) * math.sin(tq)]
        qs = [-math.sin(tq), 0, math.cos(tq)]
        pose["back"] = loc(-0.36, 0.02)
        pose["front"] = loc(0.36, 0.02)
        pose["neck"] = neck
        pose["head"] = hd
        pose["gaze"] = dq
        pose["side"] = qs
        pose["tail"] = loc(-0.72, 0.16 + pose["pack"] * 2.2, 0.09 * idle * math.sin(4 * TAU * S.t / P))
        # the gun hangs under the head, fixed to it
        qup = [qs[1] * dq[2] - qs[2] * dq[1], qs[2] * dq[0] - qs[0] * dq[2], qs[0] * dq[1] - qs[1] * dq[0]]
        hb = _add(_add(hd, _mul(dq, S.kick[0].x)), _mul(qup, -0.07))
        pose["mounts"] = [{"joint": hd, "base": hb, "tip": _add(hb, _mul(dq, 0.34)), "dir": dq, "flash": S.flash[0], "side": 0}]
    elif ch.get("octo"):
        # crawling: the mantle sits behind the head and wobbles after it; each arm is a curve through its leg
        Oq = ch["octo"]
        act_o = S.act if S.act and S.act["name"] == "grab" else None
        breathe = 1 + 0.05 * math.sin(TAU * S.t / 1.9) - 0.2 * clamp(S.jaw.x, 0, 1)
        aim_from(loc(0.15, 0.1), 1)
        pose["back"] = loc(-0.2, 0)
        pose["front"] = loc(0.2, 0)
        pose["eye"] = loc(0.10, 0.12)
        mc = loc(-0.10, 0.13)
        pose["mantle"] = {"c": mc, "tip": loc(-0.40, 0.20 + pose["pack"] * 2.5, 0.05 * idle * math.sin(2 * TAU * S.t / P)), "r": Oq["mantle"] * breathe}
        pose["dome"] = mc
        seg7 = Oq["arm"]["seg"]
        pose["arms"] = [_arm_curve(l["hip"], l["knee"], l["ankle"], seg7) for l in legs]
        if act_o:
            # the arm nearest the target leaves the ground and reaches for it, link by link
            gT = B["to_l"](act_o["target"]) if act_o["target"] else loc(0.85, 0.35, 0.2)
            if act_o["arm"] < 0:
                best = 1e9
                for k, l in enumerate(legs):
                    dq2 = _len(_sub(gT, l["hip"]))
                    if dq2 < best:
                        best = dq2
                        act_o["arm"] = k
            la, cur = legs[act_o["arm"]], pose["arms"][act_o["arm"]]
            guess7 = [[q[0], q[1] + 0.25 * math.sin(math.pi * k / 6), q[2]] for k, q in enumerate(cur)]
            rc7 = reach_chain(guess7, la["hip"], gT, seg7)
            aq = [_lerp3(q, rc7[k], AC["ext"]) for k, q in enumerate(cur)]
            for ak in range(1, 7):                           # on the way out and back its links keep their length
                ad = _sub(aq[ak], aq[ak - 1])
                aq[ak] = _add(aq[ak - 1], _mul(ad, seg7 / (_len(ad) or 1)))
            pose["arms"][act_o["arm"]] = aq
            if not act_o["done"] and act_o["t"] >= 0.42 * act_o["dur"]:
                act_o["done"] = True
                gw7 = B["to_w"](aq[6])
                S.events.append({"type": "grab", "pos": gw7, "arm": act_o["arm"], "miss": _len(_sub(gw7, act_o["target"])) if act_o["target"] else 0})
        if AC.get("ink"):
            S.events.append({"type": "ink", "pos": B["to_w"](loc(-0.3, 0.1)), "dir": [-math.cos(S.h), 0.2, -math.sin(S.h)]})
        pose["tail"] = pose["arms"][0][6]
        pose["mounts"] = [{"joint": root, "base": root, "tip": pose["eye"], "dir": [cp, sn, 0], "flash": 0, "side": 0}]
    elif ch.get("arthro"):
        # A scorpion-like body: a low carapace, two clawed arms held out in front, and a tail curled up over the back.
        # The claws drift towards what is being watched; one shoots out to pinch.  The tail is the same chain as any
        # other tail, with a rest shape that curls forward, and a strike that drags it onto a target.
        Az = ch["arthro"]
        Cw = Az.get("claw")
        act_a = S.act if S.act and S.act["name"] in ("pinch", "sting") else None
        aim_from(loc(Az["half"], 0.05), 1)
        S.jaw.step(AC["jaw"], 60, 0.8, dt)
        pose["back"] = loc(-Az["half"], 0)
        pose["front"] = loc(Az["half"], 0)
        pose["dome"] = loc(0.04, 0.05)
        pose["eye"] = loc(Az["head"][0], Az["head"][1]) if Az.get("head") else loc(Az["half"] + 0.02, 0.07)
        if Az.get("thorax"):
            tx = Az["thorax"]
            pose["thorax"] = [loc(tx[0], tx[1]), loc(tx[2], tx[3])]
        pT = None
        if Cw and act_a and act_a["name"] == "pinch":
            if act_a["target"]:
                pT = B["to_l"](act_a["target"])
            elif Cw.get("strikeAt"):
                pT = loc(Cw["strikeAt"][0], Cw["strikeAt"][1], Cw["strikeAt"][2])
            else:
                pT = loc(Cw["rest"][0] + 0.28, Cw["rest"][1] + 0.05, 0.12)
        if pT and not act_a["side"]:
            act_a["side"] = 1 if pT[2] - root[2] >= 0 else -1
        pose["claws"] = []
        aim = B["aim"]
        for cs in range(2 if Cw else 0):
            sg = 1 if cs == 0 else -1
            shc = loc(Cw["at"][0], Cw["at"][1], sg * Cw["at"][2])
            tip_t = loc(Cw["rest"][0], Cw["rest"][1] + 0.03 * idle * idle_noise(S.t, P, 3 + cs), sg * Cw["rest"][2])
            opn = 0.4 + 0.25 * AC["alert"]
            if aim:
                tip_t[1] += clamp(0.3 * (aim[1] - tip_t[1]), -0.08, 0.3)
                tip_t[2] += clamp(0.3 * (aim[2] - tip_t[2]), -0.18, 0.18)
            mine = bool(pT) and (bool(Az.get("both")) or act_a["side"] == sg)
            if mine:
                tip_t = _lerp3(tip_t, [pT[0], pT[1], pT[2] + sg * 0.06] if Az.get("both") else pT, AC["ext"])
                opn = (0.4 + 0.8 * clamp(S.jaw.x, 0, 1)) * (1 - 0.9 * AC["shut"])
            # the hand points mostly forwards, turning towards what it reaches for
            rd = _sub(tip_t, shc)
            rl = _len(rd) or 1
            hdv = [0.5 * cp + 0.5 * rd[0] / rl, 0.5 * sn + 0.5 * rd[1] / rl, 0.5 * rd[2] / rl]
            hdv = _mul(hdv, 1 / (_len(hdv) or 1))
            mid, wr = ik2(shc, _sub(tip_t, _mul(hdv, Cw["hand"])), Cw["upper"], Cw["lower"], [0, 1, sg * 0.8])
            tip_c = _add(wr, _mul(hdv, Cw["hand"]))
            inw = [0, 0, -sg]
            inw = _sub(inw, _mul(hdv, _dot(inw, hdv)))
            inw = _mul(inw, 1 / (_len(inw) or 1))
            fa3 = _add(wr, _mul(hdv, 0.30 * Cw["hand"]))
            fd3 = _add(_mul(hdv, math.cos(opn)), _mul(inw, math.sin(opn)))
            pose["claws"].append({"shoulder": shc, "elbow": mid, "wrist": wr, "tip": tip_c, "fingerA": fa3, "fingerB": _add(fa3, _mul(fd3, 0.72 * Cw["hand"])),
                                  "side": sg, "open": opn})
            if mine and not act_a["done"] and act_a["t"] >= 0.41 * act_a["dur"]:
                act_a["done"] = True
                cw2 = B["to_w"](tip_c)
                S.events.append({"type": "pinch", "pos": cw2, "claw": cs, "miss": _len(_sub(cw2, act_a["target"])) if act_a["target"] else 0})
        Ts = ch.get("tail")
        if Ts:
            tb3, pull = loc(Ts["at"][0], Ts["at"][1]), None
            n_t, seg_t = Ts["n"], Ts["seg"]
            if act_a and act_a["name"] == "sting":
                if act_a["target"]:
                    sT = B["to_l"](act_a["target"])
                elif Az.get("stingAt"):
                    sT = loc(Az["stingAt"][0], Az["stingAt"][1], 0)
                else:
                    sT = loc(Az["half"] + 0.42, 0.02, 0)
                if AC["sting"] > 0:
                    # a first guess that arches over the back, then links of the right length fitted to it
                    # (a wasp's sting curls round from below)
                    top = min(tb3[1], sT[1]) - 0.3 * n_t * seg_t if Az.get("under") else max(tb3[1], sT[1]) + 0.42 * n_t * seg_t
                    guess = []
                    for gk in range(n_t + 1):
                        gt = gk / n_t
                        g1 = 1 - gt
                        guess.append([g1 * g1 * tb3[0] + 2 * g1 * gt * (0.5 * tb3[0] + 0.5 * sT[0]) + gt * gt * sT[0],
                                      g1 * g1 * tb3[1] + 2 * g1 * gt * top + gt * gt * sT[1],
                                      g1 * g1 * tb3[2] + 2 * g1 * gt * 0.5 * (tb3[2] + sT[2]) + gt * gt * sT[2]])
                    # it must go over the body, not through it: links above the back are kept clear of it
                    rp = reach_chain(guess, tb3, sT, seg_t, 0.86)
                    clear_y = root[1] + 0.40
                    if not Az.get("under"):
                        for rk in range(1, n_t):
                            if rp[rk][0] < root[0] + Az["half"] + 0.12 and rp[rk][1] < clear_y:
                                rp[rk][1] = clear_y
                    for rk in range(1, n_t + 1):
                        rd2 = _sub(rp[rk], rp[rk - 1])
                        rp[rk] = _add(rp[rk - 1], _mul(rd2, seg_t / (_len(rd2) or 1)))
                    pull = {"pts": rp, "k": AC["sting"]}
            pose["tailPts"] = chain_step(S, "tail", Ts, ch["L"], B, tb3, B["pitch"] + lean * 0.3,
                                         {"lift": -0.45 * AC["rear"] - 0.25 * abs(FL), "curl": -0.10 * AC["rear"],
                                          "yaw": Ts["wag"] * idle * math.sin(2 * TAU * S.t / P) + Ts["sway"] * B["gp"]["moving"] * math.sin(TAU * S.phase) + 0.4 * S.twist.x,
                                          "pull": pull}, dt)
            tN, tM = pose["tailPts"][n_t], pose["tailPts"][n_t - 1]
            sd3 = _sub(tN, tM)
            pose["tail"] = tN
            pose["mounts"] = [{"joint": tM, "base": tM, "tip": tN, "dir": _mul(sd3, 1 / (_len(sd3) or 1)), "flash": 0, "side": 0}]
            if act_a and act_a["name"] == "sting" and not act_a["done"] and act_a["t"] >= 0.42 * act_a["dur"]:
                act_a["done"] = True
                sw3 = B["to_w"](tN)
                S.events.append({"type": "sting", "pos": sw3, "miss": _len(_sub(sw3, act_a["target"])) if act_a["target"] else 0})
        else:
            pose["tail"] = pose["back"]
            pose["mounts"] = [{"joint": root, "base": root, "tip": pose["eye"], "dir": [cp, sn, 0], "flash": 0, "side": 0}]
    else:
        tb = loc(0.05, 0.72)
        Wh = aim_from(tb, 1)
        tt = S.twist.x                                       # the turret goes all the way round
        dh = [math.cos(Wh) * math.cos(tt), math.sin(Wh), math.cos(Wh) * math.sin(tt)]
        bb = _add(tb, _mul(dh, S.kick[0].x))
        pose["back"] = loc(-0.5, 0.12)
        pose["front"] = loc(0.5, 0.12)
        pose["dome"] = loc(-0.05, 0.36)
        pose["eye"] = loc(1.0, 0.08)
        pose["mounts"] = [{"joint": tb, "base": bb, "tip": _add(bb, _mul(dh, 1.45)), "dir": dh, "flash": S.flash[0], "side": 0}]
    return pose


def _upper(S, ch, inp, st, dt, legs, B):
    pose = upper_body(S, ch, inp, st, dt, legs, B)
    if ch.get("fly"):                                        # on the ground the wings are folded along the body
        pose["wings"] = wing_pose(ch, pose["root"], pose["axis"], pose["up"], 0, 0, 1)
    return pose


def step(S, ch, inp, st, terrain, dt):
    """One step of a whole character on the ground: legs and hips, then the upper body.  Returns the pose in world
    coordinates (the same keys as the JavaScript reference).  Read ``S.events``, then clear it."""
    return step_ground(S, ch, inp, st, terrain, dt, _upper)
