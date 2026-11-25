# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Daniel Sandner
"""CLIo Motion in Python, stage 4: off the ground.  Swimming (the octopus), flight (the wasp, the dragon), the ladder
and the ledge (the soldier), and ``step``, which sends a character to whichever of these it is in.

A port of ``stepSwim``, ``stepFly``, ``stepLadder``, ``stepLedge`` and their enter and leave functions in js/core.js,
``mountUp``, ``dismount`` and ``stepRide``, statement for statement; checked against the replays in spec/body/.
The ragdoll is in ragdoll.py.

    enter_fly(S, ch)                    # the dragon takes off
    pose = step(S, ch, {"speed": 12, "height": 8, "steer": 0.4}, STYLE, terrain, 1 / 60)
    leave_fly(S, ch, terrain)           # and is put back on its feet
"""
from __future__ import annotations

import math

from . import body as _b
from . import ragdoll as _rag
from .ground import DIR_KEYS, Leg, Spring, pose_to_world, step_ground
from .kernel import G, TAU, clamp, decay, ease, frac, idle_period, ik2, lerp, smooth, wrap_pi

LAD_PH = [0, 0.5, 0.55, 0.05]
LAD_OFF = [0.62, 0.62, -0.60, -0.60]
LAD_DUTY = 0.62


class Ladder:
    """A ladder standing in front of the body: x is how far ahead it is (in the frame the body had when it took
    hold), rung(k) the height of rung k, about y0 + k * spacing (the rungs need not be even)."""

    def __init__(self, x, y0, spacing, rung=None):
        self.x, self.y0, self.spacing = x, y0, spacing
        self.rung = rung or (lambda k: y0 + k * spacing)


def _frame_now(S):
    return (S.x, S.px, S.pz, math.cos(S.h), math.sin(S.h))


def _l2w(fr, p):
    x, z = p[0] - fr[0], p[2]
    return [fr[1] + x * fr[3] - z * fr[4], p[1], fr[2] + x * fr[4] + z * fr[3]]


def _w2l(fr, p):
    x, z = p[0] - fr[1], p[2] - fr[2]
    return [fr[0] + x * fr[3] + z * fr[4], p[1], -x * fr[4] + z * fr[3]]


def let_go(S):
    """Whatever the hands were doing stops: a crate is dropped ('drop' event), an action is given up."""
    if S.carry and S.carry["held"]:
        c = S.pose.get("carry") if S.pose else None
        S.events.append({"type": "drop", "pos": list(c["c"]) if c else list(S.carry["at"]), "heading": S.h})
    S.carry = None
    S.act_crouch = 0.0
    S.act_back = 0.0
    if S.act and S.act["name"] != "reload":
        S.act = None


def leave_ladder(S, ch, terrain):
    """Back to standing on the ground where the body is: every mode ends through here."""
    S.mode = "ground"
    S.lad = None
    S.v = 0.0
    S.standing = True
    S.reach_drop = 0.0
    S.jump = None
    S.hop.x = S.hop.v = 0.0
    S.air_b = 0.0
    S.om = 0.0
    S.kv = [0.0, 0.0]
    S.bank.x = S.bank.v = 0.0
    S.side.x = S.side.v = 0.0
    S.lad_frame = None
    S.mv = [0.0, 0.0]
    S.act_crouch = 0.0
    S.act_back = 0.0
    S.chains = {}
    S.ride = None
    S.vl = None
    S.tv = [1.0, 0.0]
    S.guard.x = S.guard.v = 0.0
    S.stance.x = S.stance.v = 0.0
    hc, hs = math.cos(S.h), math.sin(S.h)
    S.g_ref.x = terrain(S.px, S.pz)
    S.g_ref.v = 0.0
    S.y = S.last_y = S.g_ref.x + ch["rootHeight"]
    for i, ld in enumerate(ch["legs"]):
        r = ld["rest"]
        lg = Leg([S.x + r[0], terrain(S.px + r[0] * hc - r[1] * hs, S.pz + r[0] * hs + r[1] * hc), r[1]], S.g_ref.x)
        lg.hd = S.h
        S.legs[i] = lg


def place(S, ch, terrain, x, z=0.0, heading=0.0):
    """Stand a character somewhere in the world, facing a given way, feet on the ground there."""
    S.px, S.pz, S.h = x, z or 0.0, heading or 0.0
    S.act = None
    S.carry = None
    leave_ladder(S, ch, terrain)


def stand(S, ch, terrain):
    """Back on the feet where the body lies (a switch: it is not a get-up animation)."""
    S.rag = None
    leave_ladder(S, ch, terrain)


# ---------------------------------------------------------------------------------------------------- swimming
def enter_swim(S, ch):
    if not ch.get("octo") or S.mode != "ground":
        return False
    let_go(S)
    S.mode = "swim"
    S.swim = {"vm": 0.0, "depth": 0.6}
    S.v = S.a = S.om = 0.0
    S.chains = {}
    S.pitch.x = S.pitch.v = 0.0
    S.jump = None
    S.kv = [0.0, 0.0]
    S.mv = [0.0, 0.0]
    return True


def leave_swim(S, ch, terrain):
    if S.mode == "swim":
        S.swim = None
        leave_ladder(S, ch, terrain)


def step_swim(S, ch, inp, st, terrain_w, dt):
    """Inputs in the water: speed, steer or heading, depth (metres above the bottom), ink."""
    O, W = ch["octo"], S.swim
    S.t += dt
    heading = inp.get("heading")
    he = wrap_pi(heading - S.h) if heading is not None else 0
    om_t = clamp(he * 3, -1.8, 1.8) if heading is not None else clamp(inp.get("steer") or 0, -1, 1) * 1.8
    S.om += (om_t - S.om) * decay(5, dt)
    S.h = wrap_pi(S.h + S.om * dt)
    hc, hs = math.cos(S.h), math.sin(S.h)

    def to_w(p):
        x, z = p[0] - S.x, p[2]
        return [S.px + x * hc - z * hs, p[1], S.pz + x * hs + z * hc]

    def terrain(lx, lz=0.0):
        return terrain_w(S.px + (lx - S.x) * hc - lz * hs, S.pz + (lx - S.x) * hs + lz * hc)

    AC = _b._octo_tick(S, ch, inp, dt)
    # jets: a stroke takes the first third of the cycle; drag does the rest
    W["vm"] += (clamp(inp.get("speed") or 0, 0, O["vswim"]) - W["vm"]) * decay(1.6, dt)
    k = W["vm"] / O["vswim"]
    P, drag = lerp(1.5, 0.8, k), 2.4
    S.phase = frac(S.phase + dt / P)
    stroke = math.sin(math.pi * S.phase / 0.32) if S.phase < 0.32 else 0
    v0 = S.v
    S.v += (drag * W["vm"] / 0.204 * stroke - drag * S.v) * dt
    if AC.get("ink"):
        S.v += 1.6
    S.a += ((S.v - v0) / dt - S.a) * decay(30, dt)
    # depth: it climbs or sinks towards the height asked for, nose following the path
    floor = terrain(S.x, 0)
    depth = inp.get("depth")
    yT = floor + clamp(1.2 if depth is None else depth, 0.32, 8)
    vy = clamp((yT - S.y) * 1.6, -0.9, 0.9) * (0.35 + 0.65 * min(1, S.v / 0.8 + 0.3))
    S.y = max(S.y + vy * dt, floor + 0.28)
    S.last_y = S.y
    S.pitch.step(clamp(math.atan2(vy, max(S.v, 0.6)), -0.7, 0.7), 6, 1, dt)
    S.bank.step(clamp(S.v * S.om / G * 1.5, -0.5, 0.5), 8, 1, dt)
    cpi, sp2 = math.cos(S.pitch.x), math.sin(S.pitch.x)
    S.x += S.v * cpi * dt
    S.px += hc * S.v * cpi * dt
    S.pz += hs * S.v * cpi * dt
    S.g_ref.x = floor
    S.standing = False
    S.lean.step(0, 10, 1, dt)
    S.flinch.step(0, 14, 0.5, dt)
    # the body: it travels mantle first, so the mantle is ahead and the arms trail behind
    hov = 1 - smooth(0.05, 0.5, W["vm"])
    bob_y = 0.03 * hov * math.sin(TAU * S.t / 2.6)
    root = [S.x, S.y + bob_y, 0.05 * hov * math.sin(TAU * S.t / 3.7)]
    ax, up = [cpi, sp2, 0], [-sp2, cpi, 0]
    squeeze = clamp(0.9 * stroke * (0.3 + 0.7 * k) + S.jaw.x * 0.3, 0, 1)

    def at(f, u2, z=0):
        return [root[0] + ax[0] * f + up[0] * u2, root[1] + ax[1] * f + up[1] * u2, root[2] + z]

    pose = {"kind": "hex", "root": root, "pitch": S.pitch.x, "crouch": 0, "pack": 0, "lean": 0, "legs": [], "axis": ax, "up": up, "swim": True}
    pose["back"], pose["front"], pose["eye"] = at(-0.2, 0), at(0.2, 0), at(0.02, 0.10)
    mc = at(0.16, 0.02)
    pose["mantle"] = {"c": mc, "tip": at(0.16 + 0.34 * (1 + 0.3 * squeeze), 0.03), "r": O["mantle"] * (1 - 0.22 * squeeze + 0.04 * math.sin(TAU * S.t / 1.7) * hov)}
    pose["dome"] = mc
    B = {"drift": [0, 0], "terrain": terrain}
    spread = lerp(0.62, 0.10, smooth(0, 0.6, squeeze)) + 0.5 * hov
    ang = S.pitch.x
    pose["arms"] = []
    for i in range(8):
        ra = TAU * (i + 0.5) / 8
        sw = 0.22 * math.sin(TAU * S.t / 2.3 + 1.9 * i) * (0.4 + 0.6 * hov)
        # hovering, the arms hang below and spread like a skirt; under way they stream straight back
        pose["arms"].append(_b.chain_step(S, "arm%d" % i, O["arm"], ch["L"], B, at(-0.09, 0.05 * math.sin(ra), 0.06 * math.cos(ra)), ang,
                                          {"lift": -(spread * math.sin(ra) + sw) - 0.9 * hov, "yaw": spread * math.cos(ra) * (1 + 0.8 * hov) + 0.5 * sw + 0.3 * S.bank.x}, dt))
    pose["tail"] = pose["arms"][0][O["arm"]["n"]]
    pose["mounts"] = [{"joint": root, "base": root, "tip": pose["eye"], "dir": ax, "flash": 0, "side": 0}]
    if AC.get("ink"):
        S.events.append({"type": "ink", "pos": to_w(at(-0.05, -0.05)), "dir": [-hc * cpi, -sp2, -hs * cpi]})
    pose["heading"] = S.h
    S.local = pose
    S.stats = {"Fr": 0, "stride": S.v * P, "period": P, "duty": 0.32, "run": 0, "phases": [0], "v": S.v, "gait": "Swim" if W["vm"] > 0.08 else "Hover",
               "steps": 60 / P, "air": 0, "heading": S.h, "turn": S.om, "action": None}
    S.pose = pose_to_world(pose, (S.x, S.px, S.pz, hc, hs))
    return S.pose


# ------------------------------------------------------------------------------------------------------ flying
def roll_pose(o, c, ax, ang, key=None):
    """Roll a whole pose about a line (the body's long axis): points turn about it, directions just turn."""
    if isinstance(o, list):
        if len(o) == 3 and isinstance(o[0], (int, float)) and not isinstance(o[0], bool):
            is_dir = key in _b_dirs
            v = o if is_dir else [o[0] - c[0], o[1] - c[1], o[2] - c[2]]
            cs, sn = math.cos(ang), math.sin(ang)
            dp = (ax[0] * v[0] + ax[1] * v[1] + ax[2] * v[2]) * (1 - cs)
            r = [v[0] * cs + (ax[1] * v[2] - ax[2] * v[1]) * sn + ax[0] * dp, v[1] * cs + (ax[2] * v[0] - ax[0] * v[2]) * sn + ax[1] * dp,
                 v[2] * cs + (ax[0] * v[1] - ax[1] * v[0]) * sn + ax[2] * dp]
            return r if is_dir else [c[0] + r[0], c[1] + r[1], c[2] + r[2]]
        return [roll_pose(q, c, ax, ang, key) for q in o]
    if isinstance(o, dict):
        return {k: roll_pose(v, c, ax, ang, k) for k, v in o.items()}
    return o


from .ground import DIR_KEYS as _b_dirs  # noqa: E402


def enter_fly(S, ch):
    if not ch.get("fly") or S.mode != "ground":
        return False
    let_go(S)
    S.mode = "fly"
    S.fly = {"vy": 0.0, "effort": 0.6}
    S.om = 0.0
    S.jump = None
    S.kv = [0.0, 0.0]
    S.mv = [0.0, 0.0]
    S.a = 0.0
    S.reach_drop = 0.0
    return True


def leave_fly(S, ch, terrain):
    if S.mode == "fly":
        S.fly = None
        leave_ladder(S, ch, terrain)


def step_fly(S, ch, inp, st, terrain_w, dt):
    """Inputs in the air: speed, steer or heading, height (metres above the ground), aim, and the creature's attacks."""
    F, W, L = ch["fly"], S.fly, ch["L"]
    S.t += dt
    heading = inp.get("heading")
    he = wrap_pi(heading - S.h) if heading is not None else 0
    om_t = clamp(he * 2.5, -F["turn"], F["turn"]) if heading is not None else clamp(inp.get("steer") or 0, -1, 1) * F["turn"]
    S.om += (om_t - S.om) * decay(4, dt)
    S.h = wrap_pi(S.h + S.om * dt)
    hc, hs = math.cos(S.h), math.sin(S.h)

    def to_w(p):
        x, z = p[0] - S.x, p[2]
        return [S.px + x * hc - z * hs, p[1], S.pz + x * hs + z * hc]

    def to_l(p):
        x, z = p[0] - S.px, p[2] - S.pz
        return [S.x + x * hc + z * hs, p[1], -x * hs + z * hc]

    def terrain(lx, lz=0.0):
        return terrain_w(S.px + (lx - S.x) * hc - lz * hs, S.pz + (lx - S.x) * hs + lz * hc)

    # speed: a big flier cannot go slower than its wings will carry it
    vT = clamp(inp.get("speed") or 0, 0 if F["hover"] else F["vmin"], F["vmax"])
    dv = clamp(vT - S.v, -F["acc"] * dt, F["acc"] * dt)
    S.a += (dv / dt - S.a) * decay(12, dt)
    S.v += dv
    floor = terrain(S.x, 0)
    height = inp.get("height")
    yT = floor + clamp(F["height"] if height is None else height, F["low"], 40)
    W["vy"] += (clamp((yT - S.y) * 1.3, -F["sink"], F["climb"]) - W["vy"]) * decay(3, dt)
    S.y = max(S.y + W["vy"] * dt, floor + F["low"] * 0.8)
    S.last_y = S.y
    S.g_ref.x = floor
    S.standing = False
    # how hard the wings work: more to climb and to fly slowly, less at speed or coming down, where a glider stops beating
    slow = 1 - 0.4 * S.v / F["vmax"] if F["hover"] else 1 - (S.v - F["vmin"]) / (F["vmax"] - F["vmin"])
    W["effort"] += (clamp(0.35 + 0.5 * slow + 0.6 * W["vy"] / F["climb"], 0, 1.3) - W["effort"]) * decay(4, dt)
    glide = 1 - smooth(0.18, 0.42, W["effort"]) if F["glide"] else 0
    amp_k = (0.55 + 0.45 * min(W["effort"], 1)) * (1 - 0.88 * glide)
    freq = F["beat"] * (0.75 + 0.45 * W["effort"])
    S.phase = frac(S.phase + dt * freq)
    ph = TAU * S.phase
    fa = F["amp"] * amp_k * math.sin(ph) + 0.14 * glide
    fa2 = F["amp"] * amp_k * 1.15 * math.sin(ph - 0.8) - 0.3 * amp_k * max(0, math.cos(ph)) + 0.05 * glide
    heave = -F["heave"] * amp_k * math.cos(ph - TAU / 4)        # the body rises through each downstroke
    S.pitch.step(clamp(F["pitch0"] + 0.7 * math.atan2(W["vy"], max(S.v, 0.4 * F["vmax"])) + (F.get("slowPitch") or 0) * smooth(0.55, 1, slow), -0.8, 1.0), 5, 1, dt)
    S.bank.step(clamp(math.atan(S.v * S.om / G) + 0.25 * S.om, -1.0, 1.0), 6, 1, dt)
    cp, sn = math.cos(S.pitch.x), math.sin(S.pitch.x)
    S.x += S.v * dt
    S.px += hc * S.v * dt
    S.pz += hs * S.v * dt
    hov = 1 - smooth(0.05, 0.5, S.v / F["vmax"]) if F["hover"] else 0
    root = [S.x, S.y + heave + 0.02 * L * hov * math.sin(TAU * S.t / 1.9), 0.05 * L * hov * math.sin(TAU * S.t / 2.7)]
    ax, up = [cp, sn, 0], [-sn, cp, 0]
    # legs: they hang (or are held tucked) under the body and swing back when it speeds up
    legs = []
    for k, ld in enumerate(ch["legs"]):
        at, len2 = ld["attach"], ld["upper"] + ld["lower"]
        hip = [root[0] + ax[0] * at[0] + up[0] * at[1], root[1] + ax[1] * at[0] + up[1] * at[1], at[2]]
        lag = clamp(-0.03 * S.a, -0.2, 0.2) + 0.03 * math.sin(TAU * S.t / 1.3 + 1.7 * k)
        hx, hy = (F["hang"][0] + lag) * len2, F["hang"][1] * len2
        foot = [hip[0] + hx, hip[1] + hy, at[2] + ld["side"] * 0.3 * abs(ld["rest"][1] - at[2])]
        mid, end = ik2(hip, foot, ld["upper"], ld["lower"], list(ld["pole"]))
        legs.append({"hip": hip, "knee": mid, "ankle": end, "ball": end, "heel": None, "toe": None, "planted": False, "target": None, "side": ld["side"]})
    Tn0 = TAU * math.sqrt(L / G)
    aim = inp.get("aim")
    pose = _b.upper_body(S, ch, inp, st, dt, legs, {
        "root": root, "pitch": S.pitch.x, "gp": {"run": 0.3 if F["hover"] else 1, "gal": 0, "moving": 1 - hov, "Tn": Tn0, "Fr": 0}, "Tn": Tn0, "idle": hov,
        "P": idle_period(L), "bank": 0, "sway0": 0, "aim": to_l([aim[0], aim[1], aim[2] if len(aim) > 2 else S.pz]) if aim else None, "prep": 0, "leanBase": 0,
        "to_l": to_l, "to_w": to_w, "terrain": terrain, "flex": 0, "drift": [0, 0]})
    pose["wings"] = _b.wing_pose(ch, root, ax, up, fa, fa2, 0)
    pose["flying"] = True
    S.local = roll_pose(pose, root, ax, S.bank.x)
    S.local["heading"] = S.h
    period = 1 / freq
    S.stats = {"Fr": 0, "stride": S.v * period, "period": period, "duty": 0.5, "run": 0, "phases": [0], "v": S.v,
               "gait": "Glide" if glide > 0.6 else "Hover" if S.v < 0.08 * F["vmax"] and F["hover"] else "Fly", "steps": 60 * freq, "air": 1, "heading": S.h,
               "turn": S.om, "action": S.act["name"] if S.act else None}
    S.pose = pose_to_world(S.local, (S.x, S.px, S.pz, hc, hs))
    return S.pose


# ------------------------------------------------------------------------------------------------------ ladder
def _nearest_rung(lad, y, kmin):
    k0 = math.floor((y - lad.y0) / lad.spacing + 0.5)
    best, bd = k0, 1e9
    for k in range(k0 - 2, k0 + 3):
        d = abs(lad.rung(k) - y)
        if d < bd:
            bd, best = d, k
    return max(best, kmin)


def enter_ladder(S, ch, ladder):
    """Take hold of a ladder: it stands where the body faces it; ladder.x is measured in the body's frame now."""
    let_go(S)
    S.ladder = ladder
    S.lad_frame = _frame_now(S)
    S.mode = "ladder"
    S.jump = None
    S.hop.x = S.hop.v = 0.0
    S.air_b = 0.0
    S.om = 0.0
    S.kv = [0.0, 0.0]
    S.act = None
    S.twist.x = S.twist.v = 0.0
    y = ladder.y0 + ch["rootHeight"] + 0.75
    S.lad = {"y": y, "limbs": []}
    for i in range(4):
        k = _nearest_rung(ladder, y + LAD_OFF[i] + (0.15 if i % 2 else -0.15) * (1 if i < 2 else -1), -99)
        S.lad["limbs"].append({"k": k, "swing": None, "psi": frac(S.phase + LAD_PH[i])})
    S.v = 0.0


def _stowed_props(S, ch, root, chest, u, f, zc):
    """The weapons on their way to their stowed places: the rifle across the back, pistols in their holsters."""
    kit, props = _b.held_kit(S, ch), []
    if kit:
        for i, kind in enumerate(kit["props"]):
            pl = _b._mix_place(_b._stow_place(kind, i, root, u, f, zc), _b._ready_place(kind, i, chest, u, f, 0, 0), S.armed.x)
            w = _b.prop_at(kind, pl["o"], pl["th"], pl["z"])
            w["stow"] = 1 - S.armed.x
            props.append(w)
    return props


def step_ladder(S, ch, inp, st, dt):
    """Hands and feet each hold a real rung.  A limb lets go, reaches for the rung nearest to where it wants to be,
    and the body is carried by the other three.  speed climbs."""
    lad, Ld = S.ladder, S.lad
    S.t += dt
    S.crouch += (0 - S.crouch) * decay(6, dt)
    vc = clamp((inp.get("speed") or 0) * 0.3, 0, 1.3)
    S.v += clamp(vc - S.v, -2 * dt, 2 * dt)
    T = 2 * lad.spacing / max(S.v, 0.05)
    moving = S.v > 0.03
    if moving:
        S.phase = frac(S.phase + dt / T)
    Ld["y"] += S.v * dt
    px = lad.x - 0.36 + 0.012 * math.sin(2 * TAU * S.phase)
    pz = 0.02 * math.sin(TAU * S.phase)
    pts = []
    for i in range(4):
        lm, hand, side = Ld["limbs"][i], i < 2, 1 if i % 2 == 0 else -1
        psi = frac(S.phase + LAD_PH[i])
        if not lm["swing"] and moving and psi >= LAD_DUTY and lm["psi"] < LAD_DUTY:
            dur = (1 - LAD_DUTY) * T
            want = Ld["y"] + S.v * dur + LAD_OFF[i] + S.v * LAD_DUTY * T * 0.5
            lm["swing"] = {"s": 0.0, "dur": dur, "from": lm["k"], "to": _nearest_rung(lad, want, lm["k"] + 1)}
        lm["psi"] = psi
        z, x0 = side * (0.13 if hand else 0.11), lad.x
        p = [x0, lad.rung(lm["k"]), z]
        sw = lm["swing"]
        if sw:
            sw["s"] += dt / sw["dur"]
            if sw["s"] >= 1:
                lm["k"] = sw["to"]
                lm["swing"] = None
                p = [x0, lad.rung(lm["k"]), z]
                S.events.append({"type": "grip", "limb": i})
            else:
                e, arc = ease(sw["s"], st["snap"]), math.sin(math.pi * sw["s"])
                p = [x0 - (0.10 if hand else 0.13) * arc * st["step"], lerp(lad.rung(sw["from"]), lad.rung(sw["to"]), e) + 0.02 * arc, z]
        pts.append((p, not lm["swing"]))
    S.x, S.y = px, Ld["y"]
    S.last_y = S.y
    wr = _l2w(S.lad_frame, [px, 0, 0])
    S.px, S.pz = wr[0], wr[2]
    root, legs = [px, Ld["y"], pz], []
    for i in range(2):
        ld = ch["legs"][i]
        F, ball = ld["foot"], pts[2 + i][0]
        hip = [root[0] + ld["attach"][0], root[1] + ld["attach"][1], root[2] + ld["attach"][2]]
        mid, end = ik2(hip, [ball[0] - F["fb"], ball[1] + F["ah"], ball[2]], ld["upper"], ld["lower"], [0.35, 0.1, ld["side"]])
        legs.append({"hip": hip, "knee": mid, "ankle": end, "heel": [ball[0] - F["fb"] - F["hb"], ball[1], ball[2]], "toe": [ball[0] + F["toe"], ball[1], ball[2]],
                     "ball": ball, "planted": pts[2 + i][1], "target": None, "side": ld["side"]})
    _b._fire_control(S, ch, {"fire": False}, dt)
    S.lean.step(0.15, 12, 1, dt)
    S.armed.step(0, 14, 1, dt)
    S.pack.step(0, 30, 0.4, dt)
    lean = S.lean.x
    u, f = [math.sin(lean), math.cos(lean), 0], [math.cos(lean), -math.sin(lean), 0]
    Tt, A = ch["torso"], ch["arms"]
    chest = [root[0] + u[0] * Tt["len"], root[1] + u[1] * Tt["len"], root[2] * 0.5]
    head = [chest[0] + 0.03, chest[1] + Tt["neck"] + Tt["headR"] * 0.7, chest[2]]
    arms = []
    for i in range(2):
        sd = 1 if i == 0 else -1
        sh = [chest[0] + u[0] * -0.04, chest[1] + u[1] * -0.04, chest[2] + sd * Tt["shoulderW"]]
        mid, end = ik2(sh, pts[i][0], A["upper"], A["lower"], [-0.4, -1, sd * 0.7])
        arms.append({"shoulder": sh, "elbow": mid, "hand": end, "side": sd})
    S.local = {"kind": "biped", "heading": S.h, "root": root, "pitch": 0, "lean": lean, "legs": legs, "crouch": 0, "pack": 0, "chest": chest, "head": head,
               "gaze": [math.cos(0.5), math.sin(0.5), 0], "arms": arms, "u": u, "f": f, "props": _stowed_props(S, ch, root, chest, u, f, chest[2])}
    S.pose = pose_to_world(S.local, S.lad_frame)
    S.stats = {"Fr": 0, "stride": 2 * lad.spacing, "period": T, "duty": LAD_DUTY, "run": 0, "phases": LAD_PH, "v": S.v, "gait": "Climb" if moving else "Holding",
               "steps": 240 / T if moving else 0, "air": 0}
    return S.pose


# ------------------------------------------------------------------------------------------------------- ledge
def grab_ledge(S, ch, edge):
    """Take hold of the lip of a ledge at a point of the world (the wall is in front of the body, the top runs on
    ahead).  The ground function must know the top of the ledge, since that is where the feet end up."""
    if ch["kind"] != "biped" or S.mode not in ("ground", "ladder"):
        return False
    let_go(S)
    S.lad_frame = _frame_now(S)
    e = _w2l(S.lad_frame, edge)
    S.mode = "ledge"
    S.jump = None
    S.hop.x = S.hop.v = 0.0
    S.air_b = 0.0
    S.om = 0.0
    S.kv = [0.0, 0.0]
    S.mv = [0.0, 0.0]
    S.act = None
    S.twist.x = S.twist.v = 0.0
    S.vl = None
    S.ledge = {"ex": e[0], "ey": e[1], "stage": "hang", "t": 0.0, "sw": Spring(clamp(0.12 * S.v, 0, 0.5))}
    S.v = S.a = 0.0
    S.events.append({"type": "grab", "what": "ledge"})
    return True


def step_ledge(S, ch, inp, st, terrain, dt):
    """Hanging by the hands with the feet against the wall.  climb (or jump) pulls up: chin to the edge, chest over,
    a knee up, stand.  drop lets go."""
    Lg, T, A, k = S.ledge, ch["torso"], ch["arms"], ch["L"] / 0.92
    ex, ey, q = Lg["ex"], Lg["ey"], 0
    S.t += dt
    Lg["t"] += dt
    S.crouch += (0 - S.crouch) * decay(6, dt)
    if Lg["stage"] == "hang":
        if inp.get("drop"):
            S.ledge = None
            leave_ladder(S, ch, terrain)
            S.events.append({"type": "drop", "what": "ledge"})
            return step_ground(S, ch, {"speed": 0}, st, terrain, dt, _b._upper)
        if (inp.get("climb") or inp.get("jump")) and Lg["t"] > 0.25:
            Lg["stage"] = "up"
            Lg["t"] = 0.0
    dur = 1.5 * math.sqrt(k)
    if Lg["stage"] == "up":
        q = min(Lg["t"] / dur, 1)
    sw = Lg["sw"]
    sw.step(0, 5.5, 0.25, dt)                                # the swing left over from arriving dies away
    # where the chest is, and how far the back leans: hanging; pulled up; over the edge; standing on top
    a, b, c = smooth(0, 0.38, q), smooth(0.33, 0.62, q), smooth(0.56, 1, q)
    sway = 0.02 * math.sin(TAU * S.t / 2.6) * (1 - a)
    lean = lerp(lerp(lerp(0.10, 0.36, a), 0.62, b), 0.06, c) - 0.5 * sw.x * (1 - a)
    u, f = [math.sin(lean), math.cos(lean), 0], [math.cos(lean), -math.sin(lean), 0]
    top = [ex + 0.22 * k + u[0] * T["len"], ey + ch["rootHeight"] + u[1] * T["len"]]
    cx = lerp(lerp(lerp(ex - 0.20 * k, ex - 0.13 * k, a), ex + 0.10 * k, b), top[0], c) - 0.3 * sw.x * (1 - a)
    cy = lerp(lerp(lerp(ey - 0.43 * k, ey + 0.10 * k, a), ey + 0.56 * k, b), top[1], c) + sway
    chest, root = [cx, cy, 0], [cx - u[0] * T["len"], cy - u[1] * T["len"], 0]
    hr = T["neck"] + T["headR"] * 0.7
    head = [chest[0] + math.sin(lean * 0.4) * hr, chest[1] + math.cos(lean * 0.4) * hr, 0]
    # hands: on the lip, pressing down on it as the body comes over, and off it at the end
    arms, legs, off = [], [], smooth(0.68, 0.92, q)
    for i in range(2):
        sd = 1 if i == 0 else -1
        sh = [chest[0] + u[0] * -0.04, chest[1] + u[1] * -0.04, sd * T["shoulderW"]]
        grip, loose = [ex - 0.01, ey + 0.02, sd * 0.17], [sh[0] + 0.05, sh[1] - 0.50 * k, sd * 0.24]
        mid, end = ik2(sh, _b._lerp3(grip, loose, off), A["upper"], A["lower"], _b._lerp3([-0.3, -1, sd * 0.6], [-0.8, 0.6, sd * 0.7], b * (1 - off)))
        arms.append({"shoulder": sh, "elbow": mid, "hand": end, "side": sd})
    # feet: toes on the wall while hanging and pulling; then one foot up onto the top, then the other
    for i in range(2):
        ld = ch["legs"][i]
        F = ld["foot"]
        hip = [root[0] + ld["attach"][0], root[1] + ld["attach"][1], ld["attach"][2]]
        wall = [ex - 0.03 - F["toe"], hip[1] - lerp(0.95, 0.74, a) * ch["L"] + (0.05 if i else 0) * k - 0.25 * sw.x, ld["attach"][2]]
        wall[0] -= 0.35 * max(0, sw.x)
        on = smooth(0.62 if i else 0.40, 0.86 if i else 0.64, q)
        upp = [ex + (0.20 if i else 0.10) * k + (0.02 if i else 0.04), ey, ld["rest"][1]]
        ball = _b._lerp3(wall, upp, on)
        ball[1] += 0.16 * k * math.sin(math.pi * on)
        ball[0] -= 0.12 * k * math.sin(math.pi * on)
        ankle = [ball[0] - F["fb"], ball[1] + F["ah"], ball[2]]
        mid, end = ik2(hip, ankle, ld["upper"], ld["lower"], [1, 0.2, ld["side"] * 0.4])
        if mid[0] > ex - 0.09 * k and mid[1] < ey:           # a knee that would go into the wall turns outwards instead
            lo, hi = 0, 1.45
            for _ in range(7):
                ph = 0.5 * (lo + hi)
                km, _e = ik2(hip, ankle, ld["upper"], ld["lower"], [math.cos(ph), 0.2, ld["side"] * (0.4 + math.sin(ph))])
                if km[0] > ex - 0.09 * k:
                    lo = ph
                else:
                    hi = ph
            mid, end = ik2(hip, ankle, ld["upper"], ld["lower"], [math.cos(hi), 0.2, ld["side"] * (0.4 + math.sin(hi))])
        legs.append({"hip": hip, "knee": mid, "ankle": end, "heel": [ball[0] - F["fb"] - F["hb"], ball[1], ball[2]], "toe": [ball[0] + F["toe"], ball[1], ball[2]],
                     "ball": ball, "planted": on <= 0 or on >= 1, "target": None, "side": ld["side"]})
    _b._fire_control(S, ch, {"fire": False}, dt)
    S.lean.step(lean, 12, 1, dt)
    S.armed.step(0, 14, 1, dt)
    S.pack.step(0, 30, 0.4, dt)
    props = _stowed_props(S, ch, root, chest, u, f, 0)
    S.x, S.y = root[0], root[1]
    S.last_y = S.y
    wr = _l2w(S.lad_frame, [root[0], 0, 0])
    S.px, S.pz = wr[0], wr[2]
    S.local = {"kind": "biped", "heading": S.h, "root": root, "pitch": 0, "lean": lean, "legs": legs, "crouch": 0, "pack": 0, "chest": chest, "head": head,
               "gaze": [math.cos(0.45 * (1 - c)), math.sin(0.45 * (1 - c)), 0], "arms": arms, "u": u, "f": f, "props": props}
    S.pose = pose_to_world(S.local, S.lad_frame)
    S.stats = {"Fr": 0, "stride": 0, "period": dur, "duty": 1, "run": 0, "phases": [0, 0.5], "v": 0, "gait": "Hanging" if Lg["stage"] == "hang" else "Climbing up",
               "steps": 0, "air": 0}
    if q >= 1:                                               # on its feet on the top: the ground code takes over
        S.ledge = None
        leave_ladder(S, ch, terrain)
        S.events.append({"type": "top"})
    return S.pose


# ------------------------------------------------------------------------------------------------------- riding
def mount_up(S, ch, mount):
    """Put a rider on another character.  mount: (the mount's state, the mount's character).  False if that body
    cannot be ridden (it has no saddle) or the rider is not a biped.  From then on step the mount first, then the
    rider with ``step(..., mount=(mount_state, mount_character))``.

    The rider's hips are held to the seat by a spring, so a trot or a gallop lifts him out of the saddle and the
    knees take it up; the feet stay in the stirrups; the back leans with the pace and stays upright when the mount
    pitches; in the air the whole rider rolls with the mount.  The hands hold the reins until a weapon is drawn."""
    if ch["kind"] != "biped" or not mount or not mount[1] or not mount[1].get("saddle") or not mount[0] or S.mode == "ragdoll":
        return False
    let_go(S)
    S.act = None
    S.jump = None
    S.lad = None
    S.ledge = None
    S.lad_frame = None
    S.mode = "ride"
    S.ride = {"d": Spring(0.0), "sy": None, "svy": 0.0, "acc": 0.0, "pv": 0.0}
    S.v = 0.0
    S.a = 0.0
    S.om = 0.0
    S.crouch = 0.0
    S.air_b = 0.0
    S.standing = False
    S.guard.x = S.guard.v = 0.0
    S.stance.x = S.stance.v = 0.0
    S.vl = None
    S.events.append({"type": "mount"})
    return True


def dismount(S, ch, terrain):
    """Stand the rider beside the mount, on its left."""
    if S.mode != "ride":
        return False
    S.px += 0.95 * math.sin(S.h)
    S.pz -= 0.95 * math.cos(S.h)
    let_go(S)
    S.act = None
    leave_ladder(S, ch, terrain)
    S.events.append({"type": "dismount"})
    return True


def _frame_of(S):
    """The frame a body's local pose is in, and the heading that goes with it."""
    if S.mode in ("ladder", "ledge"):
        return S.lad_frame, S.h
    if S.mode == "ragdoll":
        return S.rag["frame"], S.rag["h"]
    return _frame_now(S), S.h


def step_ride(S, ch, inp, st, terrain, dt, mount):
    Sm, cm = mount if mount else (None, None)
    Lm = Sm.local if Sm is not None else None
    sd = cm.get("saddle") if cm else None
    R = S.ride
    if not Lm or not sd or not Lm.get("axis") or not Lm.get("up"):      # nothing to sit on
        dismount(S, ch, terrain)
        return step_ground(S, ch, inp, st, terrain, dt, _b._upper)
    S.t += dt
    # the rider's pose is worked out in the mount's own frame
    fr, S.h = _frame_of(Sm)
    S.x, S.px, S.pz = fr[0], fr[1], fr[2]
    ax, up = Lm["axis"], Lm["up"]
    sv = [ax[1] * up[2] - ax[2] * up[1], ax[2] * up[0] - ax[0] * up[2], ax[0] * up[1] - ax[1] * up[0]]
    at = sd["at"]
    seat = [Lm["root"][j] + ax[j] * at[0] + up[j] * at[1] for j in range(3)]

    # from the seat's frame (forward along the mount, up from its back, to its right) to the mount's frame, and back
    def to_m(p):
        return [seat[j] + ax[j] * p[0] + up[j] * p[1] + sv[j] * p[2] for j in range(3)]

    def dir_m(d):
        return [ax[j] * d[0] + up[j] * d[1] + sv[j] * d[2] for j in range(3)]

    def from_m(q):
        d = [q[0] - seat[0], q[1] - seat[1], q[2] - seat[2]]
        return [d[0] * ax[0] + d[1] * ax[1] + d[2] * ax[2], d[0] * up[0] + d[1] * up[1] + d[2] * up[2], d[0] * sv[0] + d[1] * sv[1] + d[2] * sv[2]]

    def seat_pose(o, key=None):
        if isinstance(o, list):
            if len(o) == 3 and isinstance(o[0], (int, float)) and not isinstance(o[0], bool):
                return dir_m(o) if key in DIR_KEYS else to_m(o)
            return [seat_pose(v, key) for v in o]
        if isinstance(o, dict):
            return {k2: seat_pose(v, k2) for k2, v in o.items()}
        return o

    # the saddle's own rise and fall throws the rider: a spring holds him to it, and he cannot sink into it
    k, Tn, wy = ch["L"] / 0.92, TAU * math.sqrt(ch["L"] / G), seat[1]
    vy = 0.0 if R["sy"] is None else (wy - R["sy"]) / dt
    R["acc"] += (clamp((vy - R["svy"]) / dt, -3 * G, 3 * G) - R["acc"]) * decay(30, dt)
    R["sy"], R["svy"] = wy, vy
    d = R["d"]
    d.v -= 0.9 * R["acc"] * dt
    d.step(0, 13 / math.sqrt(k), 0.45, dt)
    if d.x < -0.012 * k:
        d.x = -0.012 * k
        d.v = max(d.v, 0)
    if d.x > 0.11 * k:
        d.x = 0.11 * k
        d.v = min(d.v, 0)
    hit = inp.get("hit")
    if hit:
        hi = hit["impulse"]
        hz = hi[2] if len(hi) > 2 and hi[2] else 0
        hm, hf = math.sqrt(hi[0] * hi[0] + hz * hz), hi[0] * fr[3] + hz * fr[4]
        S.lean.v += 7 * hf / math.sqrt(k)
        S.rise.v += 8 * hm
        S.flinch.v += 16 * hm
        S.flinch_dir = -1 if hf < 0 else 1
        d.v += 0.6 * hm
        S.events.append({"type": "hit"})
    grounded = Sm.mode == "ground"
    gal = (Sm.gal or 0) if grounded else 0
    run = (Sm.run or 0) if grounded else 0
    still = 1 if grounded and Sm.standing else 0
    S.idle_t = S.idle_t + dt if still else 0
    S.standing = False
    S.v = Sm.v or 0
    S.crouch = 0
    S.air_b = 0
    root, legs = [0, d.x, 0], []
    for i in range(2):
        ld = ch["legs"][i]
        F, sg = ld["foot"], ld["side"]
        hip = [root[0] + ld["attach"][0], root[1] + ld["attach"][1], ld["attach"][2]]
        ball = [sd["stirrup"][0], sd["stirrup"][1], sg * sd["stirrup"][2]]
        mid, end = ik2(hip, [ball[0] - F["fb"], ball[1] + F["ah"], ball[2]], ld["upper"], ld["lower"], [0.6, 0.15, sg])
        legs.append({"hip": hip, "knee": mid, "ankle": end, "heel": [ball[0] - F["fb"] - F["hb"], ball[1], ball[2]], "toe": [ball[0] + F["toe"], ball[1], ball[2]],
                     "ball": ball, "planted": True, "target": None, "side": sg})
        S.legs[i].fwd = 0
        S.legs[i].swing = None
    pv = d.v - R["pv"]
    R["pv"] = d.v
    S.pack.v -= 0.6 * pv
    S.pack.step(0, 60 / Tn, 0.35, dt)
    pitch_seat = math.asin(clamp(ax[1], -1, 1))
    aim = inp.get("aim")
    hands = sd["hands"]
    pose = _b.upper_body(S, ch, inp, st, dt, legs, {
        "root": root, "pitch": 0, "gp": {"moving": 0, "run": 0, "gal": 0, "Fr": 0}, "Tn": Tn, "idle": still, "P": idle_period(ch["L"]),
        "bank": math.tan(0.7 * Sm.bank.x) if grounded and Sm.bank else 0, "sway0": 0, "flex": 0, "drift": [0, 0], "prep": 0,
        "aim": from_m(_w2l(fr, [aim[0], aim[1], aim[2] if len(aim) > 2 else S.pz])) if aim else None,
        "to_l": lambda p: from_m(_w2l(fr, p)), "to_w": lambda p: _l2w(fr, to_m(p)), "terrain": lambda lx, lz=0.0: -1e9,
        "hands": [[hands[0], hands[1], hands[2]], [hands[0], hands[1], -hands[2]]],
        # forward with the pace, back against a climb or a dive, and up out of the saddle with the bounce
        "leanBase": 0.04 + 0.10 * run + 0.22 * gal + (0 if grounded else 0.22) + math.atan((Sm.a or 0) / G) * 0.4 - 0.65 * pitch_seat + 1.2 * d.x / k})
    S.local = seat_pose(pose)
    S.local["heading"] = S.h
    S.local["riding"] = cm["id"]
    if sd.get("reins") and S.armed.x < 0.6 and Lm.get("mounts") and Lm.get("neck"):
        bit = Lm["mounts"][0]["base"] if sd["reins"] == "bit" else [Lm["neck"][j] + 0.2 * up[j] for j in range(3)]
        S.local["reins"] = [[S.local["arms"][0]["hand"], list(bit)], [S.local["arms"][1]["hand"], list(bit)]]
    S.y = S.local["root"][1]
    S.last_y = S.y
    S.stats = {"Fr": 0, "stride": 0, "period": 0, "duty": 1, "run": 0, "phases": [0, 0.5], "v": S.v, "gait": "Riding", "steps": 0, "air": 0, "heading": S.h,
               "turn": Sm.om or 0, "ammo": list(S.ammo) if S.ammo else None, "kit": S.kit, "action": S.act["name"] if S.act else None}
    S.pose = pose_to_world(S.local, fr)
    return S.pose


def step(S, ch, inp, st, terrain, dt, mount=None):
    """One step of a whole character in whatever mode it is in: on the ground, swimming, flying, on a ladder,
    hanging from a ledge, lying as a ragdoll, or riding (then mount is (the mount's state, its character), and
    the mount has been stepped already).  Returns the pose in world coordinates (the same keys as the
    JavaScript reference).  Read ``S.events``, then clear it."""
    die = inp.get("die")
    if die is not None and die is not False:
        if S.mode == "swim":
            leave_swim(S, ch, terrain)
        if S.mode != "ragdoll" and S.local and S.local.get("legs"):
            let_go(S)
            _rag.ragdoll_start(S, ch, S.lad_frame if S.mode in ("ladder", "ledge") else _frame_now(S), S.h, die)
    if S.mode == "ragdoll":
        return _rag.step_ragdoll(S, ch, terrain, dt)
    if S.mode == "ride":
        return step_ride(S, ch, inp, st, terrain, dt, mount)
    if S.mode == "swim":
        return step_swim(S, ch, inp, st, terrain, dt)
    if S.mode == "fly":
        return step_fly(S, ch, inp, st, terrain, dt)
    if S.mode == "ledge":
        return step_ledge(S, ch, inp, st, terrain, dt)
    if S.mode == "ladder":
        return step_ladder(S, ch, inp, st, dt)
    return step_ground(S, ch, inp, st, terrain, dt, _b._upper)
