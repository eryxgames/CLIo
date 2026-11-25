# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Daniel Sandner
"""CLIo Motion in Python, stage 1: the numeric kernel everything else is built on.

A port of js/core.js with nothing but the standard library, checked against spec/kernel_vectors.txt, which the
JavaScript version writes.  Units: metres, seconds, radians.  Vectors are lists of three floats: x forward,
y up, z to the right.
"""
from __future__ import annotations

import math

G = 9.81
TAU = 6.283185307179586


def clamp(x, a, b):
    return a if x < a else b if x > b else x


def lerp(a, b, t):
    return a + (b - a) * t


def frac(x):
    return x - math.floor(x)


def smooth(a, b, x):
    t = clamp((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def decay(rate, dt):
    return 1 - math.exp(-rate * dt)


def ease(s, snap):
    sm = s * s * s * (s * (6 * s - 15) + 10)
    return lerp(s, sm, 0.4 + 0.6 * snap)


def wrap_pi(a):
    a = math.fmod(a + math.pi, TAU)
    if a < 0:
        a += TAU
    return a - math.pi


def idle_noise(t, period, k):
    """Idle motion is built from three harmonics of one period, so an idle clip loops exactly."""
    a = TAU * t / period
    return (math.sin(a + k) + 0.6 * math.sin(2 * a + 2.3 * k) + 0.4 * math.sin(3 * a + 4.1 * k)) / 2


def idle_period(L):
    return 2.1 * TAU * math.sqrt(L / G)


class Spring:
    """A damped spring: the one piece of real-time physics used everywhere."""
    __slots__ = ("x", "v")

    def __init__(self, x=0.0, v=0.0):
        self.x = x
        self.v = v

    def step(self, target, omega, zeta, dt):
        a = -2 * zeta * omega * self.v - omega * omega * (self.x - target)
        self.v += a * dt
        self.x += self.v * dt


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _len(a):
    return math.sqrt(_dot(a, a))


def ik2(root, target, l1, l2, pole):
    """Two-bone inverse kinematics: (mid, end).  The joint bends in the plane that holds root, target and the
    pole direction."""
    d = [target[0] - root[0], target[1] - root[1], target[2] - root[2]]
    dist = _len(d)
    max_r = (l1 + l2) * 0.999
    min_r = abs(l1 - l2) + 1e-4
    reach = clamp(dist, min_r, max_r)
    if dist > 1e-6:
        inv = 1 / dist
        dr = [d[0] * inv, d[1] * inv, d[2] * inv]
    else:
        dr = [0.0, -1.0, 0.0]
    cos_a = clamp((l1 * l1 + reach * reach - l2 * l2) / (2 * l1 * reach), -1.0, 1.0)
    sin_a = math.sqrt(1 - cos_a * cos_a)
    pd = _dot(pole, dr)
    perp = [pole[0] - dr[0] * pd, pole[1] - dr[1] * pd, pole[2] - dr[2] * pd]
    pl = _len(perp)
    if pl > 1e-6:
        inv = 1 / pl
        perp = [perp[0] * inv, perp[1] * inv, perp[2] * inv]
    else:
        perp = [1.0, 0.0, 0.0]
    a, b = l1 * cos_a, l1 * sin_a
    mid = [root[i] + (dr[i] * a + perp[i] * b) for i in range(3)]
    end = [root[i] + dr[i] * reach for i in range(3)]
    return mid, end


def lob(p, t, vmax=15.0):
    """Launch velocity that lobs something from p to t, no faster than vmax."""
    dx, dz, dy = t[0] - p[0], t[2] - p[2], t[1] - p[1]
    d = math.sqrt(dx * dx + dz * dz)
    if d < 0.3:
        dd = d or 1.0
        dx = dx / dd * 0.3 or 0.3
        dz = dz / dd * 0.3
        d = 0.3
    th = 0.95 if d < 3 else 0.72
    den = d * math.tan(th) - dy
    if den < 0.15 * d:
        th = min(math.atan2(dy, d) + 0.5, 1.35)
        den = max(d * math.tan(th) - dy, 0.05 * d)
    c = math.cos(th)
    v = min(math.sqrt(G * d * d / (2 * c * c * den)), vmax or 15.0)
    return [v * c * dx / d, v * math.sin(th), v * c * dz / d]


def reach_chain(pts, a, b, seg, most=0.985):
    """Links of fixed length from a to a point b that the last one must reach if it can.  pts is a first guess
    (n + 1 points) and is changed in place; most is the share of its full length the chain may stretch to."""
    n = len(pts) - 1
    tot = n * seg * (most or 0.985)
    ab = [b[0] - a[0], b[1] - a[1], b[2] - a[2]]
    al = _len(ab)
    if al > tot:
        s = tot / al
        b = [a[0] + ab[0] * s, a[1] + ab[1] * s, a[2] + ab[2] * s]
    for _ in range(5):
        pts[n] = list(b)
        for k in range(n - 1, 0, -1):
            q = pts[k + 1]
            d = [pts[k][0] - q[0], pts[k][1] - q[1], pts[k][2] - q[2]]
            s = seg / (_len(d) or 1.0)
            pts[k] = [q[0] + d[0] * s, q[1] + d[1] * s, q[2] + d[2] * s]
        pts[0] = list(a)
        for k in range(1, n + 1):
            q = pts[k - 1]
            d = [pts[k][0] - q[0], pts[k][1] - q[1], pts[k][2] - q[2]]
            s = seg / (_len(d) or 1.0)
            pts[k] = [q[0] + d[0] * s, q[1] + d[1] * s, q[2] + d[2] * s]
    return pts


class GaitState:
    """What carries over from step to step: the blends between gaits, and which side of each switch the body
    is on."""
    __slots__ = ("run", "gal", "run_want", "gal_want")

    def __init__(self):
        self.run = 0.0
        self.gal = 0.0
        self.run_want = False
        self.gal_want = False


def _round_half_up(d):
    return math.floor(d + 0.5)          # what JavaScript's Math.round does


def gait_params(ch, s, v, crouch=0.0, style_stride=1.0, dt=1 / 60):
    """The gait rules for a character (a dict as in spec/characters.json) at speed v.

    Dynamic similarity: animals of different sizes move alike at the same Froude number v^2 / (g L).  That is
    what makes a big machine stride slowly and a soldier quickly without tuning either by hand."""
    g = ch["gait"]
    gw, gr, gg = g["walk"], g.get("run"), g.get("gallop")
    leff = ch["L"] * (1 - 0.5 * ch["crouchDrop"] * crouch)
    tn = TAU * math.sqrt(leff / G)                      # natural swing period of the leg
    fr = v * v / (G * leff)
    if gr:
        s.run_want = fr > g["frRun"] * (0.8 if s.run_want else 1)      # hysteresis around the walk-run switch
        s.run += ((1 if s.run_want else 0) - s.run) * decay(1 / (0.11 * tn), dt)
    else:
        s.run = 0.0
    run = s.run
    # stride length: Alexander's relation, stride / leg length = 2.3 Fr^0.3
    stride = leff * 2.3 * math.pow(max(fr, 1e-6), 0.3) * style_stride * lerp(1, ch["runStride"], run) * (1 - 0.45 * crouch)
    period = stride / max(v, 1e-4)
    if period > tn:                                     # legs never swing slower than a pendulum
        period = tn
        stride = v * tn
    wd = lerp(gw["duty"][0], gw["duty"][1], clamp(fr / g["frRun"], 0, 1))
    rd = lerp(gr["duty"][0], gr["duty"][1], clamp((fr - g["frRun"]) / (g["frMax"] - g["frRun"]), 0, 1)) if gr else wd
    duty = lerp(wd, rd, run)
    phases = []
    for i, p in enumerate(gw["phases"]):
        if gr:
            d = gr["phases"][i] - p
            d -= _round_half_up(d)                      # shortest way round the cycle
            p = frac(p + d * run + 1)
        phases.append(p)
    gal = 0.0
    if gg:
        s.gal_want = fr > gg["fr"] * (0.8 if s.gal_want else 1)
        s.gal = s.gal + ((1 if s.gal_want else 0) - s.gal) * decay(1 / (0.16 * tn), dt)
        gal = s.gal
        duty = lerp(duty, lerp(gg["duty"][0], gg["duty"][1], clamp((fr - gg["fr"]) / (gg["frMax"] - gg["fr"]), 0, 1)), gal)
        for i, p in enumerate(phases):
            d = gg["phases"][i] - p
            d -= _round_half_up(d)
            phases[i] = frac(p + d * gal + 1)
    moving = smooth(0.02, 0.25, v / math.sqrt(G * leff))
    # walk: the hip vaults over the planted foot like an inverted pendulum (highest mid-step)
    q4 = min(stride / 4, 0.8 * leff)
    aw = 0.3 * (leff - math.sqrt(leff * leff - q4 * q4))
    # run: the leg is a spring (lowest mid-step); bounce size follows from step time and gravity
    ts = period / 2
    ar = min(G * ts * ts / (TAU * TAU) * (1 + 2 * max(0, 0.5 - duty)), 0.09 * leff)
    return {"Leff": leff, "Tn": tn, "Fr": fr, "run": run, "stride": stride, "period": period, "duty": duty,
            "phases": phases, "moving": moving, "Aw": aw, "Ar": ar, "gal": gal}
