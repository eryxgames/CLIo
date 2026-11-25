# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Daniel Sandner
"""CLIo Motion in Python, stage 4b: the ragdoll.

A body that is knocked down.  Its joints become point masses held together by their bone lengths; gravity, ground
contact and a few joint limits do the rest.  Each particle moves in the character's forward-up plane and keeps its
sideways offset, which is what a side-view game needs.  Tails and claws go limp and fall with the body.
A port of ``ragdollStart``, ``stepRagdoll`` and ``ragPose`` in js/core.js, statement for statement; checked against
the replays in spec/body/.

    pose = step(S, ch, {"die": {"impulse": [-2, 1, 0.5]}}, STYLE, terrain, dt)      # the body falls from wherever it is
    stand(S, ch, terrain)                                                             # back on its feet where it lies
"""
from __future__ import annotations

import math

from . import body as _b
from .ground import pose_to_world
from .kernel import G, clamp, decay, idle_period, reach_chain


class _P:
    """A particle: p its place in the plane (forward, up), z its sideways offset, q where it was a step ago."""
    __slots__ = ("p", "z", "r", "w", "hit", "q")

    def __init__(self, pos, r, w, vx0, vy0, dt0):
        self.p = [pos[0], pos[1]]
        self.z = pos[2] if len(pos) > 2 else 0.0
        self.r = r
        self.w = w
        self.hit = False
        self.q = [self.p[0] - vx0 * dt0, self.p[1] - vy0 * dt0]


def _d2(a, b, dz=None):
    x, y = a.p[0] - b.p[0], a.p[1] - b.p[1]
    z = a.z - b.z if dz is None else dz
    return math.sqrt(x * x + y * y + z * z)


def _cross_at(a, b, c):
    return (b.p[0] - a.p[0]) * (c.p[1] - b.p[1]) - (b.p[1] - a.p[1]) * (c.p[0] - b.p[0])


def ragdoll_start(S, ch, frame, heading, hit):
    """Hand the body, as it is this moment, to its ragdoll.  frame: the frame its pose was worked out in."""
    p, L = S.local, ch["L"]
    sc = math.sqrt(L / 0.92)
    P, bones, mins, maxs, signs = {}, [], [], [], []
    vy0 = S.jump.vy if S.jump and S.jump.stage == "air" else 0
    vx0 = S.v if S.mode == "ground" else 0
    dt0 = 1 / 120

    def add(name, pos, r, w):
        P[name] = _P(pos, r, w, vx0, vy0, dt0)

    def bone(a, b, dz=None, rest=None):
        bones.append((P[a], P[b], rest or _d2(P[a], P[b], dz), dz))

    def mn(a, b, f, dz=None):
        mins.append((P[a], P[b], f, dz))

    def mx(a, b, f):
        maxs.append((P[a], P[b], f))

    def sign(a, b, c, dflt):            # the joint keeps bending the way it bends now
        cr = _cross_at(P[a], P[b], P[c])
        signs.append((P[a], P[b], P[c], (1 if cr > 0 else -1) if abs(cr) > 1e-3 * L * L else dflt))

    def legs(hip_of, knee_r, foot_r, bend_default):
        for i, l in enumerate(p["legs"]):
            ld = ch["legs"][i]
            hip, ln, F = hip_of(i), ld["upper"] + ld["lower"], ld.get("foot")
            kn, an = "knee%d" % i, "ankle%d" % i
            add(kn, l["knee"], knee_r, 0.6)
            add(an, l["ankle"] if F else [l["ankle"][0], l["ankle"][1] + foot_r, l["ankle"][2]], foot_r, 0.8)
            hz = ld["attach"][2] - l["knee"][2]                 # the hip sits at its body particle, offset sideways
            bone(hip, kn, hz, ld["upper"])
            bone(kn, an)
            mn(hip, an, 0.3 * ln, ld["attach"][2] - l["ankle"][2])
            if abs(ld["rest"][1] - ld["attach"][2]) < 0.3 * ln:  # legs splayed sideways have no bend side in this plane
                sign(hip, kn, an, bend_default)
            if F:
                fl, tn = F["fb"] + F["toe"], "toe%d" % i
                add(tn, [l["toe"][0], l["toe"][1] + 0.4 * F["ah"], l["toe"][2]], 0.45 * F["ah"], 1.2)
                bone(an, tn)
                sign(kn, an, tn, 1)
                # the ankle stays between about 65 and 150 degrees
                mn(kn, tn, math.sqrt(ld["lower"] * ld["lower"] + fl * fl - 2 * ld["lower"] * fl * math.cos(1.15)))
                mx(kn, tn, math.sqrt(ld["lower"] * ld["lower"] + fl * fl - 2 * ld["lower"] * fl * math.cos(2.6)))

    R = {"frame": frame, "h": heading, "P": P, "bones": bones, "mins": mins, "maxs": maxs, "signs": signs, "t": 0.0, "still": 0.0, "asleep": False,
         "base": p, "aim": S.aim.x, "tw": S.twist.x, "limp": {}, "gazeOff": 0.0, "dt": 0.0, "terrain": None}
    kind, beast = ch["kind"], ch.get("beast")
    if kind == "biped":
        add("root", p["root"], 0.11, 0.25)
        add("chest", p["chest"], 0.15, 0.3)
        add("head", p["head"], 0.115, 0.9)
        bone("root", "chest")
        bone("chest", "head")
        mn("root", "head", 0.86 * (_d2(P["root"], P["chest"]) + _d2(P["chest"], P["head"])))
        legs(lambda k: "root", 0.07, 0.075, -1)
        for i in range(2):
            add("elbow%d" % i, p["arms"][i]["elbow"], 0.055, 1)
            add("hand%d" % i, p["arms"][i]["hand"], 0.05, 1.3)
            bone("chest", "elbow%d" % i)
            bone("elbow%d" % i, "hand%d" % i)
            sign("chest", "elbow%d" % i, "hand%d" % i, 1)
            mn("chest", "hand%d" % i, 0.2 * (ch["arms"]["upper"] + ch["arms"]["lower"]))
            mn("chest", "knee%d" % i, 0.9 * ch["torso"]["len"])
        for k, w in enumerate(p.get("props") or []):            # whatever is in the hands is let go and falls on its own
            if w["stow"] > 0.5:
                continue
            zm, a, b = (w["o"][2] + w["muzzle"][2]) / 2, "w%dS" % k, "w%dM" % k
            add(a, [w["o"][0], w["o"][1], zm], 0.035, 1)
            add(b, [w["muzzle"][0], w["muzzle"][1], zm], 0.03, 1)
            bone(a, b)
            P[a].q[1] -= 0.8 * dt0
            P[b].q[0] -= 0.6 * dt0
            P[b].q[1] -= 1.6 * dt0
        upper, R["center"] = ["chest", "head"], ["root"]
    elif kind == "mech":
        add("root", p["root"], 0.3, 0.3)
        add("chest", p["chest"], ch["pod"]["r"], 0.25)
        bone("root", "chest")
        legs(lambda k: "root", 0.3, 0.26, 1)
        for i in range(2):
            mn("chest", "knee%d" % i, 0.6 * ch["pod"]["h"])
        upper, R["center"] = ["chest"], ["root"]
    elif kind == "quad":
        add("back", p["back"], 0.15, 0.3)
        add("front", p["front"], 0.15, 0.3)
        add("head", p["head"], 0.09, 0.9)
        bone("back", "front")
        bone("front", "head")
        mn("back", "head", 0.88 * (_d2(P["back"], P["front"]) + _d2(P["front"], P["head"])))
        R["gazeOff"] = math.atan2(p["gaze"][1], p["gaze"][0]) - math.atan2(p["head"][1] - p["front"][1], p["head"][0] - p["front"][0])
        mid = bool(beast and beast.get("mid"))
        if mid:
            add("mid", p["root"], 0.15, 0.3)
            bone("back", "mid")
            bone("mid", "front")
        legs(lambda k: "mid" if mid else "back" if ch["legs"][k]["attach"][0] < 0 else "front", 0.05, 0.045, 1)
        upper, R["center"] = ["front", "head"], ["back", "front"]
    else:
        add("back", p["back"], 0.5, 0.3)
        add("front", p["front"], 0.5, 0.3)
        add("mid", [(p["back"][0] + p["front"][0]) / 2, (p["back"][1] + p["front"][1]) / 2, 0], 0.5, 0.3)
        bone("back", "mid")
        bone("mid", "front")
        bone("back", "front")

        def hip_of(k):
            ax = ch["legs"][k]["attach"][0]
            return "front" if ax > 0.3 else "back" if ax < -0.3 else "mid"

        legs(hip_of, 0.13, 0.06, 1)
        upper, R["center"] = ["front", "mid"], ["mid"]
    R["list"] = list(P.values())
    # the blow: a push on the upper body, scaled so that big and small bodies fall alike
    imp_w = hit.get("impulse") if isinstance(hit, dict) else None
    wi = imp_w if imp_w else [-2.4 * frame[3], 1.0, -2.4 * frame[4]]       # given in the world; default: from straight ahead
    imp = [wi[0] * frame[3] + (wi[2] if len(wi) > 2 else 0) * frame[4], wi[1]]
    for n in upper:
        P[n].q[0] -= imp[0] * sc * dt0
        P[n].q[1] -= imp[1] * sc * dt0
    S.mode = "ragdoll"
    S.rag = R
    S.jump = None
    S.lad = None
    S.v = 0.0
    S.om = 0.0
    S.kv = [0.0, 0.0]
    S.act = None
    S.events.append({"type": "die"})


def _pull(A, B, rest, d):
    """Move two particles within the plane so that their true distance becomes rest."""
    x, y = B.p[0] - A.p[0], B.p[1] - A.p[1]
    pl2 = x * x + y * y
    if pl2 < 0.01 * d * d:                 # almost purely sideways: nothing to do in the plane
        return
    k = clamp((d - rest) * d / pl2, -0.5, 0.5) / (A.w + B.w)
    A.p[0] += x * k * A.w
    A.p[1] += y * k * A.w
    B.p[0] -= x * k * B.w
    B.p[1] -= y * k * B.w


def _limp_step(Lc, anchor, ground, dt):
    """A limp chain: points on links of fixed length, hanging from wherever its first point is put."""
    p, q, seg = Lc["p"], Lc["q"], Lc["seg"]
    n, h = len(p), min(dt, 1 / 60)
    p[0] = list(anchor)
    for i in range(1, n):
        a, b = p[i], q[i]
        v = [(a[0] - b[0]) * 0.97, (a[1] - b[1]) * 0.97, (a[2] - b[2]) * 0.9]
        q[i] = list(a)
        a[0] += v[0]
        a[1] += v[1] - G * h * h
        a[2] += v[2]
    for _ in range(4):
        for i in range(1, n):
            a, b = p[i - 1], p[i]
            d = [b[0] - a[0], b[1] - a[1], b[2] - a[2]]
            ln = math.sqrt(d[0] * d[0] + d[1] * d[1] + d[2] * d[2]) or 1
            for j in range(3):
                b[j] = a[j] + d[j] / ln * seg[i - 1]
            gy = ground(b[0], b[2]) + Lc["r"]
            if b[1] < gy + 1e-7:           # it drags on the ground (touching counts, so that every machine agrees)
                if b[1] < gy:
                    b[1] = gy
                q[i][0] += (b[0] - q[i][0]) * 0.5
                q[i][2] += (b[2] - q[i][2]) * 0.5
    return [list(x) for x in p]


def _limp_from(pts, r):
    seg = [math.sqrt(sum((pts[i][j] - pts[i - 1][j]) ** 2 for j in range(3))) for i in range(1, len(pts))]
    return {"p": [list(x) for x in pts], "q": [list(x) for x in pts], "seg": seg, "r": r}


def _rag_pose(S, ch):
    R = S.rag
    b, P, fq = R["base"], R["P"], R["frame"]
    tw = R["tw"] or 0

    def pt(n):
        q = P[n]
        return [q.p[0], q.p[1], q.z]

    def unit(a, c):
        x, y = c[0] - a[0], c[1] - a[1]
        ln = math.sqrt(x * x + y * y) or 1
        return [x / ln, y / ln, 0]

    def along(o, d, s, n=None, t=0):
        return [o[0] + d[0] * s + (n[0] * t if n else 0), o[1] + d[1] * s + (n[1] * t if n else 0), o[2]]

    def gnd(x, z):
        return R["terrain"](fq[1] + (x - fq[0]) * fq[3] - z * fq[4], fq[2] + (x - fq[0]) * fq[4] + z * fq[3])

    def limp(name, anchor, start, r):   # a limp chain kept with the ragdoll, started from where that part was
        Lc = R["limp"].get(name)
        if Lc is None:
            Lc = R["limp"][name] = _limp_from(start, r)
        return _limp_step(Lc, anchor, gnd, R["dt"])

    def legs_of(hip_of):
        out = []
        for k in range(len(b["legs"])):
            ld = ch["legs"][k]
            hip, knee, ankle, F = hip_of(k), pt("knee%d" % k), pt("ankle%d" % k), ld.get("foot")
            heel = toe = None
            ball = ankle
            if F:
                d = unit(ankle, pt("toe%d" % k))
                n = [-d[1], d[0], 0]
                heel, ball, toe = along(ankle, d, -F["hb"], n, -F["ah"]), along(ankle, d, F["fb"], n, -F["ah"]), along(ankle, d, F["fb"] + F["toe"], n, -F["ah"])
            else:
                ankle = along(knee, unit(knee, ankle), ld["lower"])       # (the ball stays where the particle is)
            out.append({"hip": hip, "knee": knee, "ankle": ankle, "heel": heel, "toe": toe, "ball": ball, "planted": False, "target": None, "side": ld["side"]})
        return out

    kind = ch["kind"]
    pose = {"kind": kind, "pitch": 0, "crouch": 0, "pack": 0, "lean": 0}
    if kind in ("biped", "mech"):
        r, c = pt("root"), pt("chest")
        u = unit(r, c)
        f = [u[1], -u[0], 0]
        ct, sw = math.cos(tw), math.sin(tw)
        f3 = [f[0] * ct, f[1] * ct, sw]                      # the turn it had is kept
        pose.update(root=r, chest=c, u=u, f=f3, side=[-f[0] * sw, -f[1] * sw, ct], lean=math.atan2(u[0], u[1]))
        pose["legs"] = legs_of(lambda k: [r[0], r[1], ch["legs"][k]["attach"][2]])
        if kind == "biped":
            pose["head"] = pt("head")
            pose["gaze"] = f3
            pose["arms"] = [{"shoulder": [c[0] - u[0] * 0.04, c[1] - u[1] * 0.04, ba["shoulder"][2]], "elbow": pt("elbow%d" % k), "hand": pt("hand%d" % k),
                             "side": ba["side"]} for k, ba in enumerate(b["arms"])]
            props = []
            for k, bp in enumerate(b.get("props") or []):
                if ("w%dS" % k) in P:
                    s0, m0 = pt("w%dS" % k), pt("w%dM" % k)
                    w = _b.prop_at(bp["kind"], s0, math.atan2(m0[1] - s0[1], m0[0] - s0[0]), s0[2])
                else:
                    pl = _b._stow_place(bp["kind"], k, r, u, f, c[2])
                    w = _b.prop_at(bp["kind"], pl["o"], pl["th"], pl["z"])
                    w["stow"] = 1
                props.append(w)
            pose["props"] = props
        else:
            a = R["aim"]
            dm = [f3[0] * math.cos(a) + u[0] * math.sin(a), f3[1] * math.cos(a) + u[1] * math.sin(a), f3[2] * math.cos(a)]
            pose["mounts"] = []
            for bm in b["mounts"]:
                j = [c[0] + 0.1 * f[0] - 0.3 * u[0], c[1] + 0.1 * f[1] - 0.3 * u[1], bm["joint"][2]]
                pose["mounts"].append({"joint": j, "base": along(j, dm, -0.35), "tip": along(j, dm, ch["pod"]["gunLen"]), "dir": dm, "flash": 0, "side": bm["side"]})
        return pose
    beast = ch.get("beast")
    mid = bool(beast and beast.get("mid"))
    bk, fr = pt("back"), pt("front")
    ax = unit(bk, fr)
    up = [-ax[1], ax[0], 0]
    md = pt("mid") if mid else [(bk[0] + fr[0]) / 2, (bk[1] + fr[1]) / 2, 0]
    pose.update(back=bk, front=fr, axis=ax, up=up, pitch=math.atan2(ax[1], ax[0]), root=md)

    def hip_at(k):
        at = ch["legs"][k]["attach"]
        if mid:
            o = pt("mid")
        elif kind == "quad":
            o = bk if at[0] < 0 else fr
        else:
            o = fr if at[0] > 0.3 else bk if at[0] < -0.3 else md
        return [o[0], o[1], at[2]]

    pose["legs"] = legs_of(hip_at)
    if kind == "quad":
        hd = pt("head")
        ga = math.atan2(hd[1] - fr[1], hd[0] - fr[0]) + R["gazeOff"]
        qc, qs = math.cos(tw), math.sin(tw)
        gz, sdq = [math.cos(ga) * qc, math.sin(ga), math.cos(ga) * qs], [-qs, 0, qc]
        gup = [sdq[1] * gz[2] - sdq[2] * gz[1], sdq[2] * gz[0] - sdq[0] * gz[2], sdq[0] * gz[1] - sdq[1] * gz[0]]
        gb = [hd[0] - 0.07 * gup[0], hd[1] - 0.07 * gup[1], hd[2] - 0.07 * gup[2]]
        pose.update(side=sdq, head=hd, gaze=gz, neck=fr, tail=along(bk, ax, -0.36, up, 0.10))
        pose["mounts"] = [{"joint": hd, "base": gb, "tip": along(gb, gz, 0.34), "dir": gz, "flash": 0, "side": 0}]
        if beast:
            hg = [hd[0] + 0.02 * gz[0] - 0.035 * gup[0], hd[1] + 0.02 * gz[1] - 0.035 * gup[1], hd[2] + 0.02 * gz[2] - 0.035 * gup[2]]
            pose["mounts"] = [{"joint": hd, "base": hg, "tip": along(hg, gz, beast["jaw"]), "dir": gz, "flash": 0, "side": 0}]
            pose.update(jaw=0, alert=0, flex=0, neck=along(fr, ax, 0.03, up, 0.10))
            tl = ch.get("tail")
            if tl:
                pose["tailPts"] = limp("tail", along(bk, ax, tl["at"][0] + (beast.get("back") or beast["half"]), up, tl["at"][1]), b["tailPts"], 0.03)
                pose["tail"] = pose["tailPts"][tl["n"]]
        return pose
    ta, tc, tj = R["aim"] * 0.5, math.cos(tw), along(md, ax, 0.05, up, 0.6)
    td = [(ax[0] * math.cos(ta) + up[0] * math.sin(ta)) * tc, ax[1] * math.cos(ta) + up[1] * math.sin(ta), math.cos(ta) * math.sin(tw)]
    pose["dome"] = along(md, ax, -0.05, up, 0.24)
    pose["eye"] = along(fr, ax, 0.5, up, -0.04)
    pose["mounts"] = [{"joint": tj, "base": tj, "tip": along(tj, td, 1.45), "dir": td, "flash": 0, "side": 0}]
    octo, az = ch.get("octo"), ch.get("arthro")
    if octo:
        pose["arms"] = [_b._arm_curve(l["hip"], l["knee"], l["ankle"], octo["arm"]["seg"]) for l in pose["legs"]]
        mc = along(md, ax, -0.10, up, 0.13)
        pose["mantle"] = {"c": mc, "tip": along(md, ax, -0.40, up, 0.16), "r": octo["mantle"]}
        pose["dome"] = mc
        pose["tail"] = pose["arms"][0][6]
        pose["eye"] = along(md, ax, 0.10, up, 0.12)
        pose["mounts"] = [{"joint": md, "base": md, "tip": pose["eye"], "dir": ax, "flash": 0, "side": 0}]
    if az:
        # claws and tail are limp chains now: they hang from the body, fall with it and lie where they land
        Cq, hf, TQ = az.get("claw"), az["half"], ch.get("tail")
        claws = []
        for ci, bc in enumerate(b["claws"]):
            sh = along(fr, ax, Cq["at"][0] - hf, up, Cq["at"][1])
            sh[2] = bc["side"] * Cq["at"][2]
            c4 = limp("claw%d" % ci, sh, [bc["shoulder"], bc["elbow"], bc["wrist"], bc["tip"]], 0.05)
            hv = [c4[3][j] - c4[2][j] for j in range(3)]
            fa = [c4[2][j] + hv[j] * 0.3 for j in range(3)]
            fb = [fa[j] + hv[j] * 0.7 for j in range(3)]
            fb[1] += 0.02
            fb[2] -= bc["side"] * 0.05
            claws.append({"shoulder": c4[0], "elbow": c4[1], "wrist": c4[2], "tip": c4[3], "fingerA": fa, "fingerB": fb, "side": bc["side"], "open": 0.3})
        pose["claws"] = claws
        if az.get("thorax"):
            tx = az["thorax"]
            pose["thorax"] = [along(md, ax, tx[0], up, tx[1]), along(md, ax, tx[2], up, tx[3])]
        if az.get("head"):
            pose["eye"] = along(md, ax, az["head"][0], up, az["head"][1])
        if TQ:
            tq2 = limp("tail", along(bk, ax, TQ["at"][0] + hf, up, TQ["at"][1]), b["tailPts"], 0.05)
            n = TQ["n"]
            tqd = [tq2[n][j] - tq2[n - 1][j] for j in range(3)]
            tl2 = math.sqrt(tqd[0] * tqd[0] + tqd[1] * tqd[1] + tqd[2] * tqd[2]) or 1
            pose["tailPts"] = tq2
            pose["tail"] = tq2[n]
            pose["mounts"] = [{"joint": tq2[n - 1], "base": tq2[n - 1], "tip": tq2[n], "dir": [tqd[0] * (1 / tl2), tqd[1] * (1 / tl2), tqd[2] * (1 / tl2)], "flash": 0, "side": 0}]
    return pose


def step_ragdoll(S, ch, terrain_w, dt):
    R = S.rag
    fr, P, L = R["frame"], R["list"], ch["L"]

    def terrain(q0):
        return terrain_w(fr[1] + (q0.p[0] - fr[0]) * fr[3] - q0.z * fr[4], fr[2] + (q0.p[0] - fr[0]) * fr[4] + q0.z * fr[3])

    S.t += dt
    R["t"] += dt
    R["dt"] = dt
    R["terrain"] = terrain_w
    S.flash[0] = S.flash[1] = 0
    if not R["asleep"]:
        g, fastest = G * dt * dt, 0.0
        vm = 14 * math.sqrt(L) * dt
        for q in P:
            vx, vy = (q.p[0] - q.q[0]) * 0.998, (q.p[1] - q.q[1]) * 0.998
            vl = math.sqrt(vx * vx + vy * vy)
            if vl > vm:
                vx *= vm / vl
                vy *= vm / vl
            q.q[0], q.q[1] = q.p[0], q.p[1]
            q.p[0] += vx
            q.p[1] += vy - g
            q.hit = False
        for _ in range(12):
            for A, B, rest, dz in R["bones"]:
                _pull(A, B, rest, _d2(A, B, dz))
            for A, B, rest, dz in R["mins"]:
                d = _d2(A, B, dz)
                if d < rest:
                    _pull(A, B, rest, d)
            for A, B, rest in R["maxs"]:
                d = _d2(A, B)
                if d > rest:
                    _pull(A, B, rest, d)
            for A, Bm, C, sg in R["signs"]:           # a knee or elbow never bends backwards: at worst it is straight
                cr = _cross_at(A, Bm, C)
                if cr * sg < 0:
                    # the joint has gone past straight: push all three points back, each by its share
                    gcx, gcy = -(Bm.p[1] - A.p[1]), Bm.p[0] - A.p[0]
                    gax, gay = -(C.p[1] - Bm.p[1]), C.p[0] - Bm.p[0]
                    gbx, gby = -gax - gcx, -gay - gcy
                    den = A.w * (gax * gax + gay * gay) + Bm.w * (gbx * gbx + gby * gby) + C.w * (gcx * gcx + gcy * gcy)
                    if den > 1e-12:
                        lam = -cr / den * 0.6
                        A.p[0] += lam * A.w * gax
                        A.p[1] += lam * A.w * gay
                        Bm.p[0] += lam * Bm.w * gbx
                        Bm.p[1] += lam * Bm.w * gby
                        C.p[0] += lam * C.w * gcx
                        C.p[1] += lam * C.w * gcy
            for q in P:
                gy = terrain(q) + q.r
                if q.p[1] < gy + 1e-7:                 # touching counts
                    if q.p[1] < gy:
                        q.p[1] = gy
                    q.hit = True
        for q in P:
            if q.hit:                                  # ground friction, no bounce
                q.q[0] = q.p[0] - (q.p[0] - q.q[0]) * 0.7
                if q.q[1] < q.p[1]:
                    q.q[1] = q.p[1]
            fastest = max(fastest, abs(q.p[0] - q.q[0]) + abs(q.p[1] - q.q[1]))
        R["still"] = R["still"] + dt if fastest < 0.06 * math.sqrt(L) * dt else 0
        if R["still"] > 0.5 or R["t"] > 6:
            R["asleep"] = True
    R["aim"] += (-0.45 - R["aim"]) * decay(2.5, dt)
    S.local = _rag_pose(S, ch)
    S.local["heading"] = R["h"]
    if ch.get("fly"):                                  # wings stay folded on a body that is down
        S.local["wings"] = _b.wing_pose(ch, S.local["root"], S.local["axis"], S.local["up"], 0, 0, 1)
    S.pose = pose_to_world(S.local, fr)
    cx = cy = 0.0
    for n in R["center"]:
        cx += R["P"][n].p[0]
        cy += R["P"][n].p[1]
    S.x = cx / len(R["center"])
    S.y = S.last_y = cy / len(R["center"])
    x = S.x - fr[0]
    S.px, S.pz = fr[1] + x * fr[3], fr[2] + x * fr[4]
    S.stats = {"Fr": 0, "stride": 0, "period": 1, "duty": 1, "run": 0, "phases": ch["gait"]["walk"]["phases"], "v": 0, "gait": "Down", "steps": 0, "air": 0,
               "idlePeriod": idle_period(L), "asleep": R["asleep"]}
    return S.pose
