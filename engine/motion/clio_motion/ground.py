# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Daniel Sandner
"""CLIo Motion in Python, stage 2: the ground step.

Where the feet go and what the hips do: speed and turning, travel in any direction, the gait, foot planning with
feet planted in the world, jumps and pounces, body height and pitch over uneven ground, and the legs' inverse
kinematics.  A port of ``stepGround`` in js/core.js, kept statement for statement so that it gives the same
numbers; checked against the replays in spec/ground/.

    S = create_state(ch, terrain)
    pose = step_ground(S, ch, {"speed": 1.4, "steer": 0.3}, STYLE, terrain, 1 / 60)

``terrain(x, z)`` is the ground height at a point of the world.  ``pose`` holds ``root``, ``pitch``, ``heading`` and
``legs`` (hip, knee, ankle, ball, heel, toe, planted, target, side), with points in world coordinates.  The upper
body (spine, arms, head, tail, weapons) is stage 3.
"""
from __future__ import annotations

import math

from .kernel import G, TAU, Spring, clamp, decay, ease, frac, gait_params, idle_noise, idle_period, ik2, lerp, smooth, wrap_pi

STYLE = {"bounce": 1.0, "stride": 1.0, "arm": 1.0, "lean": 1.0, "step": 1.0, "snap": 0.3, "still": 0.0}


class Swing:
    """A foot in the air on its way to its next place."""
    __slots__ = ("air", "s", "manual", "rate", "start", "alpha0", "tx", "ty", "tz", "psi0", "early", "start_w")

    def __init__(self, start, alpha0, manual=False, rate=0.0, psi0=0.0, air=False, early=False, tx=None, ty=None, tz=None):
        self.air = air
        self.s = 0.0
        self.manual = manual
        self.rate = rate
        self.start = start
        self.alpha0 = alpha0
        self.tx = tx
        self.ty = ty
        self.tz = tz
        self.psi0 = psi0
        self.early = early
        self.start_w = None


class Leg:
    __slots__ = ("ball", "swing", "alpha", "strike", "slope", "fwd", "drop", "ref_y", "w", "hd", "psi", "over", "behind")

    def __init__(self, ball, ref_y):
        self.ball = ball
        self.swing = None
        self.alpha = 0.0
        self.strike = 0.0
        self.slope = 0.0
        self.fwd = 0.0
        self.drop = 0.0
        self.ref_y = ref_y
        self.w = None
        self.hd = 0.0
        self.psi = 0.0
        self.over = 0.0
        self.behind = 0.0


class Jump:
    __slots__ = ("stage", "t", "vy", "y", "v0", "phi", "landed", "pounce", "vx", "struck", "acc")

    def __init__(self, v0, pounce=False, vx=0.0):
        self.stage = "prep"
        self.t = 0.0
        self.vy = 0.0
        self.y = 0.0
        self.v0 = v0
        self.phi = 0.0
        self.landed = False
        self.pounce = pounce
        self.vx = vx
        self.struck = False
        self.acc = 0.0


class State:
    """Everything a character carries from one step to the next."""

    def __init__(self, ch, terrain):
        g0 = terrain(0.0, 0.0)
        self.t = 0.0
        self.x = 0.0
        self.y = g0 + ch["rootHeight"]
        self.v = 0.0
        self.a = 0.0
        self.phase = 0.0
        self.run = 0.0
        self.run_want = False
        self.gal = 0.0
        self.gal_want = False
        self.standing = True
        self.crouch = 0.0
        self.g_ref = Spring(g0)
        self.pitch = Spring()
        self.reach_drop = 0.0
        self.pack = Spring()
        self.pack_vy = 0.0
        self.last_y = g0 + ch["rootHeight"]
        self.mode = "ground"
        self.events = []
        self.stats = None
        self.pose = None
        self.jump = None
        self.hop = Spring()
        self.air_b = 0.0
        self.idle_t = 0.0
        self.px = 0.0
        self.pz = 0.0
        self.h = 0.0
        self.om = 0.0
        self.kv = [0.0, 0.0]
        self.bank = Spring()
        self.side = Spring()
        self.lean = Spring()
        self.rise = Spring()
        self.flinch = Spring()
        self.flinch_dir = -1
        self.vl = None
        self.tv = [1.0, 0.0]
        self.mv = [0.0, 0.0]
        self.lag = 0.0
        # set by the upper body's actions (stage 3); at rest here
        self.guard = Spring()
        self.stance = Spring()
        self.carry = None
        self.act = None
        self.act_crouch = 0.0
        self.act_back = 0.0
        # the upper body: aim, weapons, actions (stage 3)
        mount = ch.get("mount") or {}
        self.aim = Spring()
        self.twist = Spring()
        self.armed = Spring(1.0)
        self.kick = [Spring(), Spring()]
        self.flash = [0.0, 0.0]
        self.cool = 0.0
        self.gun = 0
        self.kit = mount.get("kit")
        self.ammo = None
        self.block = Spring()
        self.ac_tw = 0.0
        self.ho_rel = [None, None]
        self.jaw = Spring()
        self.chains = {}
        self.ink_t = 0.0
        # off the ground (stage 4)
        self.swim = None
        self.fly = None
        self.lad = None
        self.ladder = None
        self.lad_frame = None
        self.ledge = None
        self.rag = None
        self.ride = None
        self.local = None
        self.legs = [Leg([l["rest"][0], terrain(l["rest"][0], 0.0), l["rest"][1]], g0) for l in ch["legs"]]


def create_state(ch, terrain):
    return State(ch, terrain)


DIR_KEYS = frozenset(("gaze", "u", "f", "dir", "axis", "up", "side", "t1", "t2"))


def pose_to_world(o, fr, key=None):
    """A pose worked out in the body's frame, in the world: points are moved and turned, directions only turned.
    fr: (the body's local x, its place px, pz, cos and sin of its heading)."""
    if isinstance(o, list):
        if len(o) == 3 and isinstance(o[0], (int, float)) and not isinstance(o[0], bool):
            if key in DIR_KEYS:
                return [o[0] * fr[3] - o[2] * fr[4], o[1], o[0] * fr[4] + o[2] * fr[3]]
            x, z = o[0] - fr[0], o[2]
            return [fr[1] + x * fr[3] - z * fr[4], o[1], fr[2] + x * fr[4] + z * fr[3]]
        return [pose_to_world(v, fr, key) for v in o]
    if isinstance(o, dict):
        return {k: pose_to_world(v, fr, k) for k, v in o.items()}
    return o


def _slope_at(terrain, x, w):
    return clamp(math.atan2(terrain(x + w) - terrain(x - w), 2 * w), -0.45, 0.45)


def step_ground(S, ch, inp, st, terrain_w, dt, upper=None):
    """One step of the legs and hips.  ``upper`` is the upper-body function of stage 3 (see body.py); without it
    the pose holds the root and the legs only."""
    L = ch["L"]
    cl = ch["legs"]
    S.t += dt
    Tn0 = TAU * math.sqrt(L / G)
    # steering: a turn rate, limited by sideways grip at speed and by how fast the feet can shuffle on the spot
    heading = inp.get("heading")
    he = wrap_pi(heading - S.h) if heading is not None else 0.0
    om_spot = 5 / Tn0 * clamp(1.8 - (S.lag or 0) / 0.2, 0.2, 1) * clamp(1 - S.v / (0.5 * math.sqrt(G * L)), 0, 1)
    om_max = max(om_spot, min(0.35 * G / S.v, S.v / (1.1 * L)) if S.v > 0.01 else 0) * clamp(1 - S.reach_drop / (0.05 * L), 0.1, 1)
    om_t = clamp(he * 6, -om_max, om_max) if heading is not None else clamp(inp.get("steer") or 0, -1, 1) * om_max
    if S.jump and S.jump.stage == "air":
        om_t = S.om
    S.om += (om_t - S.om) * decay(16 / Tn0, dt)
    S.h = wrap_pi(S.h + S.om * dt)
    hc, hs = math.cos(S.h), math.sin(S.h)

    def to_w(p):
        x, z = p[0] - S.x, p[2]
        return [S.px + x * hc - z * hs, p[1], S.pz + x * hs + z * hc]

    def to_l(p):
        x, z = p[0] - S.px, p[2] - S.pz
        return [S.x + x * hc + z * hs, p[1], -x * hs + z * hc]

    def terrain(lx, lz=0.0):        # ground height under a point given in the body's frame
        return terrain_w(S.px + (lx - S.x) * hc - lz * hs, S.pz + (lx - S.x) * hs + lz * hc)

    # a blow that does not floor the body: it slides, the torso snaps away, the knees give
    hit = inp.get("hit")
    if hit:
        hi = hit["impulse"]
        hz = hi[2] if len(hi) > 2 else 0.0
        kq = math.sqrt(L / 0.92)
        hf = hi[0] * hc + hz * hs
        hlat = -hi[0] * hs + hz * hc
        hm = math.sqrt(hf * hf + hlat * hlat)
        S.kv[0] += 0.6 * kq * hi[0]
        S.kv[1] += 0.6 * kq * hz
        S.lean.v += 7 * hf / kq
        S.hop.v -= 1.1 * hm * kq
        S.side.v += 1.2 * hlat * kq
        S.rise.v += 8 * hm
        S.flinch.v += 16 * hm
        S.flinch_dir = -1 if hf < 0 else 1
        S.events.append({"type": "hit"})
    S.crouch += (max(clamp(inp.get("crouch") or 0, 0, 1), S.act_crouch or 0) - S.crouch) * decay(14 / Tn0, dt)
    vT = clamp(inp.get("speed") or 0, 0, ch["vmax"] * (1 - 0.65 * min(S.crouch, 1)))
    if S.carry:
        vT = 0 if S.act else min(vT, 0.62 * math.sqrt(G * L))
    from .body import held_kit                         # (the body module is built on this one)
    kit_now = held_kit(S, ch)
    if kit_now and kit_now.get("pace") and S.armed.x > 0.5:    # nor is a case on wheels run with
        vT = min(vT, kit_now["pace"] * math.sqrt(G * L))
    if heading is not None:
        vT *= clamp(1.5 - abs(he) / 0.8, 0, 1)             # brake for a sharp turn, pivot, then go
    a_max = (0.4 if vT > S.v else 0.65) * G
    if S.jump and S.jump.pounce and S.jump.stage == "land":
        a_max = 1.3 * G                                     # dig in after a pounce
    dv = clamp(vT - S.v, -a_max * dt, a_max * dt)
    dx, dz = 1.0, 0.0
    if S.jump and S.jump.stage == "air":
        dv = 0.0                                            # no steering in the air
    d_in = inp.get("dir") or 0
    if d_in or S.vl:
        # travel in any direction while facing another: the velocity is steered as a vector
        cA, sA = math.cos(d_in), math.sin(d_in)
        vK = 1 - 0.62 * sA * sA - (0.5 * cA * cA if cA < 0 else 0)
        if not S.vl:
            S.vl = [S.v, 0.0]
        tvx = vT * vK * cA - S.vl[0]
        tvz = vT * vK * sA - S.vl[1]
        tl = math.sqrt(tvx * tvx + tvz * tvz)
        am = 0.55 * G * dt
        if not (S.jump and S.jump.stage == "air"):
            if tl > am:
                tvx *= am / tl
                tvz *= am / tl
            S.vl[0] += tvx
            S.vl[1] += tvz
        nv = math.sqrt(S.vl[0] * S.vl[0] + S.vl[1] * S.vl[1])
        dv = nv - S.v
        if nv > 1e-3:
            S.tv = [S.vl[0] / nv, S.vl[1] / nv]
        dx, dz = S.tv[0], S.tv[1]
        if not d_in and abs(S.vl[1]) < 1e-4 and S.vl[0] >= 0 and tl < 1e-6:
            S.vl = None                                     # going straight ahead again
            dx, dz = 1.0, 0.0
    S.a += (dv / dt - S.a) * decay(30 / Tn0, dt)
    S.v += dv
    gp = gait_params(ch, S, S.v, S.crouch, st["stride"], dt)
    duty, period, phases = gp["duty"], gp["period"], gp["phases"]
    # jump: crouch (prep), leave the ground on a ballistic arc (air), absorb the landing with a spring (land)
    J = S.jump
    n = len(S.legs)
    if inp.get("jump") and not J and ch.get("jumpH") and not S.carry and not (S.act and S.act.get("name") != "reload"):
        J = S.jump = Jump(math.sqrt(2 * G * ch["jumpH"] * L))
    pounce = inp.get("pounce")
    if pounce is not None and pounce is not False and not J and ch.get("beast") and not S.act:
        # a leap onto something: a flat arc along the heading, far enough to bring the jaws down on the target
        tgt = pounce.get("target") if isinstance(pounce, dict) else None
        pt0 = to_l([tgt[0], tgt[1], tgt[2] if len(tgt) > 2 else 0.0]) if tgt else [S.x + 3.4 * L, 0.0, 0.0]
        pdist = clamp(pt0[0] - S.x - 1.3 * L - S.v * (0.11 * Tn0 + 0.12), 1.2 * L, 5.5 * L)
        pv0 = math.sqrt(0.3 * G * pdist)
        J = S.jump = Jump(pv0, True, pdist * G / (2 * pv0))
    if J:
        J.t += dt
        if J.stage == "prep" and J.t > 0.11 * Tn0:
            # push off: constant thrust over the crouch depth, so take-off speed is reached at standing height
            J.stage = "push"
            J.t = 0.0
            J.acc = J.v0 * J.v0 / (2 * max(-S.hop.x, 0.05 * L))
            S.hop.v = 0.0
        if J.stage == "push" and S.hop.x >= 0:
            J.stage = "air"
            J.t = 0.0
            J.vy = min(S.hop.v, 1.1 * J.v0)
            J.y = S.y
            S.reach_drop = 0.0
            if J.pounce:
                S.v = max(S.v, J.vx)
                S.a = 0.0
            J.phi = frac(0.02 - phases[0] + 1)             # the stride phase to land in
            for lg in S.legs:
                lg.swing = Swing(list(lg.ball), lg.alpha, manual=True, air=True, tx=lg.ball[0], ty=lg.ball[1])
            S.events.append({"type": "jump"})
    air = bool(J) and J.stage == "air"
    if air:
        J.vy -= G * dt
        J.y += J.vy * dt
        gl = 0.0
        for i in range(n):
            gl += terrain(S.x + cl[i]["rest"][0])
        gl /= n
        if J.vy < 0 and J.y <= gl + ch["rootHeight"] * (1 - ch["crouchDrop"] * S.crouch):
            J.stage = "land"
            J.t = 0.0
            J.landed = True
            air = False
            S.g_ref.x = gl
            S.g_ref.v = 0.0
            S.phase = J.phi
            for i in range(n):
                lg = S.legs[i]
                lx = lg.ball[0]
                ly = terrain(lx)
                lg.ball = [lx, ly, lg.ball[2]]
                lg.swing = None
                lg.w = None
                lg.hd = S.h
                lg.strike = 0.0
                lg.alpha = 0.0
                lg.ref_y = ly
                lg.drop = 0.0
                foot = cl[i].get("foot")
                lg.slope = _slope_at(terrain, lx, 0.5 * foot["fb"]) if foot else 0.0
                wj = to_w(lg.ball)
                S.events.append({"type": "land", "leg": i, "x": wj[0], "y": ly, "z": wj[2], "hd": S.h, "side": cl[i]["side"]})
    S.air_b += ((1 if air else 0) - S.air_b) * decay(24 / Tn0, dt)
    standing = vT <= 1e-4 and S.v < 0.05 * math.sqrt(G * L)
    if standing and not S.standing:
        # stopping: let any foot in the air finish its step on its own clock
        for lg in S.legs:
            sw0 = lg.swing
            if sw0 and not sw0.manual:
                tr = clamp((1 - sw0.s) * (1 - duty) * period, 0.06 * gp["Tn"], 0.2 * gp["Tn"])
                sw0.manual = True
                sw0.rate = max(1 - sw0.s, 0.05) / tr
    if not standing and S.standing:
        if not any(lg.swing for lg in S.legs):
            S.phase = frac(duty - phases[0] + 1)           # first leg is about to lift
    S.standing = standing
    if not standing and not air:
        S.phase = frac(S.phase + dt / period)
    S.x += S.v * dx * dt
    kd = math.exp(-dt / (0.12 * Tn0))
    # drift: slow movement in any direction without turning to face it; the feet shuffle to keep up
    mv_in = inp.get("move") if standing else None
    mvx = (mv_in[0] or 0) if mv_in else 0
    mvz = (mv_in[1] or 0) if mv_in else 0
    mv_max = 0.33 * math.sqrt(G * L)
    mvm = math.sqrt(mvx * mvx + mvz * mvz)
    kmv = decay(20 / Tn0, dt)
    if mvm > mv_max:
        mvx *= mv_max / mvm
        mvz *= mv_max / mvm
    S.mv[0] += (mvx - S.mv[0]) * kmv
    S.mv[1] += (mvz - S.mv[1]) * kmv
    mvl = [S.mv[0] * hc + S.mv[1] * hs, -S.mv[0] * hs + S.mv[1] * hc]
    mvs = math.sqrt(mvl[0] * mvl[0] + mvl[1] * mvl[1])
    S.px += (hc * S.v * dx - hs * S.v * dz + S.kv[0] + S.mv[0]) * dt
    S.pz += (hs * S.v * dx + hc * S.v * dz + S.kv[1] + S.mv[1]) * dt
    S.kv[0] *= kd
    S.kv[1] *= kd
    # fighting stance: the feet stand staggered while on guard
    fight = ch.get("fight")
    S.stance.step(1 if standing and fight and S.guard.x > 0.5 else 0, 14, 1, dt)
    stK = clamp(S.stance.x, 0, 1) if fight else 0

    def rest_of(k):
        r0 = cl[k]["rest"]
        if stK > 0:
            so = fight["stance"][k]
            return [r0[0] + stK * so[0], r0[1] + stK * so[1]]
        return r0

    # feet are remembered in the world: find where each one is in the body's frame this step
    for lg in S.legs:
        swp = lg.swing
        if swp and not swp.air:
            if swp.start_w is None:
                swp.start_w = list(lg.w) if lg.w else to_w(swp.start)
            swp.start = to_l(swp.start_w)
        elif not swp and lg.w:
            lg.ball = to_l(lg.w)
    S.idle_t = S.idle_t + dt if standing and not J and abs(S.om) < 0.2 else 0.0

    stance_travel = duty * gp["stride"]
    for i in range(n):
        lg = S.legs[i]
        ld = cl[i]
        foot = ld.get("foot")
        if air:
            # feet trail the body: legs stretch at take-off, tuck at the top, reach down to land
            psi_l = frac(J.phi + phases[i])
            offx = stance_travel * (0.5 - psi_l / duty) if psi_l < duty else -0.3 * stance_travel
            h_stand = ch["rootHeight"] + ld["attach"][1]
            lat = ld["rest"][1] - ld["attach"][2]
            lmx = 0.96 * (ld["upper"] + ld["lower"])
            ext = clamp((math.sqrt(max(lmx * lmx - lat * lat, 0)) + (foot["ah"] if foot else 0)) / h_stand, 1, 1.1)
            tuck = max(0, 0.3 * (1 - math.pow(J.vy / J.v0, 2)))
            if J.pounce:                                    # forelegs reach for the landing, hind legs trail
                if ch["beast"].get("mid") and J.vy < 0:
                    offx += 0.22 * L
                elif ld["attach"][0] > 0:
                    offx += (0.50 if J.vy < 0 else 0.30) * L
                else:
                    offx += -0.30 * L * max(0, J.vy / J.v0)
            txa = S.x + ld["rest"][0] + offx * dx
            tya = max(J.y + ld["attach"][1] - h_stand * ext * (1 - tuck), terrain(txa) + 0.01 * L)
            kA = decay(34 / Tn0, dt)
            lg.ball = [lerp(lg.ball[0] + S.v * dt, txa, kA), lerp(lg.ball[1], tya, kA), ld["rest"][1]]
            lg.alpha = 0.12 + 0.6 * max(0, J.vy / J.v0) if foot else 0.0
            t_land = (J.vy + math.sqrt(J.vy * J.vy + 2 * G * max(0, J.y - (S.g_ref.x + ch["rootHeight"])))) / G
            lg.swing.tx = txa + S.v * t_land
            lg.swing.ty = terrain(lg.swing.tx)
            lg.ref_y = terrain(S.x + ld["rest"][0])
            lg.psi = psi_l
            lg.drop = 0.0
            continue
        psi = frac(S.phase + phases[i])
        lg.psi = psi
        lg.drop *= math.exp(-dt / 0.03)
        if not lg.swing and not standing and psi >= duty:
            lg.swing = Swing(list(lg.ball), lg.alpha, psi0=min(psi, 0.97), ty=lg.ball[1])
        sw = lg.swing
        if sw:
            done = False
            if sw.manual:
                sw.s += sw.rate * dt
                if sw.s >= 1:
                    sw.s = 1.0
                    done = True
            elif psi < duty and not sw.early:
                sw.s = 1.0
                done = True
            else:
                sw.s = max(sw.s, (psi - sw.psi0) / (1 - sw.psi0))
                if psi >= duty:
                    sw.early = False
            t_rem = 0.0 if done else (1 - sw.s) / sw.rate if sw.manual else (1 - psi) * period
            # land ahead of the hip so that mid-stance ends up under it; allow for speeding up or slowing down
            vL = clamp(S.v + S.a * t_rem, 0, ch["vmax"])
            lead = 0.5 * duty * gp["stride"] * math.pow(clamp(vL / max(S.v, 0.05 * math.sqrt(G * L)), 0.4, 1.8), 0.6)
            if sw.manual:
                pl = frac(psi + t_rem / period)
                lead = 0 if standing or pl >= duty else S.v * period * (duty - pl - duty / 2)
            # where the foot's place under the body will be when it lands: the body will have moved on and turned
            fwd = S.v * t_rem + 0.5 * S.a * t_rem * t_rem * (0 if standing else 1)
            ang = S.om * t_rem
            ca, sa = math.cos(ang), math.sin(ang)
            rr = rest_of(i)
            rx = rr[0] + lead * dx
            rz = rr[1] + lead * dz
            ch2, sh2 = math.cos(ang / 2), math.sin(ang / 2)
            if dz:                                          # going sideways, a foot closes up to the other but does not cross it
                rz = max(rz, 0.02 * L) if ld["side"] > 0 else min(rz, -0.02 * L)
            tx = S.x + fwd * (dx * ch2 - dz * sh2) + rx * ca - rz * sa
            tz = fwd * (dx * sh2 + dz * ch2) + rx * sa + rz * ca
            if standing and mvs > 1e-4:                     # drifting: step to where the body is going
                ahead = t_rem + 0.09 * gp["Tn"]
                tx += mvl[0] * ahead
                tz += mvl[1] * ahead
            ty = terrain(tx, tz)
            sw.tx, sw.ty, sw.tz = tx, ty, tz
            e = ease(sw.s, st["snap"])
            bx = lerp(sw.start[0], tx, e)
            bz = lerp(sw.start[2], tz, e)
            dist = math.sqrt(math.pow(tx - sw.start[0], 2) + math.pow(tz - sw.start[2], 2))
            lift = L * lerp(ch["liftWalk"], ch["liftRun"], S.run) * st["step"] * clamp(dist / (0.3 * L), 0.2, 1) * (0.7 if sw.manual else 1)
            up = ty > sw.start[1]
            ey = 1 - math.pow(1 - sw.s, 3) if up else math.pow(sw.s, 3)   # rise early onto a ledge, drop late off one
            eY = lerp(e, ey, clamp(abs(ty - sw.start[1]) / (0.1 * L), 0, 1))
            by = lerp(sw.start[1], ty, eY) + lift * math.sin(math.pi * sw.s)
            by = max(by, terrain(bx, bz) + 0.004 * L)
            if foot:
                land_a = -foot["strike"] * (1 - 0.8 * S.run) * clamp(dist / (0.3 * L), 0, 1) * (0.3 if sw.manual else 1)
                lg.alpha = sw.alpha0 * (1 - smooth(0, 0.55, sw.s)) + land_a * smooth(0.5, 0.95, sw.s)
            if done:
                gy = terrain(bx, bz)
                lg.drop = by - gy
                lg.ball = [bx, gy, bz]
                lg.swing = None
                lg.w = None
                lg.hd = S.h
                lg.strike = lg.alpha
                lg.slope = _slope_at(terrain, bx, 0.5 * foot["fb"]) if foot else 0.0
                lg.ref_y = gy
                wl = to_w(lg.ball)
                S.events.append({"type": "land", "leg": i, "x": wl[0], "y": gy, "z": wl[2], "hd": S.h, "side": ld["side"]})
            else:
                lg.ball = [bx, by, bz]
                lg.ref_y = ty
        else:
            lg.ref_y = lg.ball[1]
    if not standing:
        S.lag = 0.0
    if standing and not any(lg.swing for lg in S.legs):
        # standing still (or turning on the spot): bring the worst-placed foot back under the body (of feet equally
        # badly placed, as mirrored ones are, the first: a later one has to be worse by more than a billionth of a leg)
        worst, worst_d, offs = -1, 0.09 * L, []
        for i in range(n):
            bl = S.legs[i].ball
            rs = rest_of(i)
            off = math.sqrt(math.pow(bl[0] - (S.x + rs[0]), 2) + math.pow(bl[2] - rs[1], 2)) + 0.2 * L * abs(wrap_pi(S.h - S.legs[i].hd))
            offs.append(off)
            if off > worst_d + (0 if worst < 0 else 1e-9 * L):
                worst_d = off
                worst = i
        S.lag = max(offs) / L
        if worst >= 0:
            grp = (ch["gait"].get("run") or ch["gait"]["walk"])["phases"]
            for i in range(n):
                # legs that move together in the gait step together here too (the spider's tripods)
                if i != worst and (offs[i] < 0.045 * L or abs(wrap_pi(TAU * (grp[i] - grp[worst]))) > 0.1):
                    continue
                lg = S.legs[i]
                lg.swing = Swing(list(lg.ball), lg.alpha, manual=True, rate=1 / ((0.17 - 0.05 * clamp(mvs / (0.5 * mv_max), 0, 1)) * gp["Tn"]),
                                 tx=lg.ball[0], ty=lg.ball[1], tz=lg.ball[2])

    # body height follows the feet, softened by a spring
    mean_y = mx = 0.0
    for i in range(n):
        mean_y += S.legs[i].ref_y
        mx += cl[i]["rest"][0]
    mean_y /= n
    mx /= n
    S.g_ref.step(mean_y, 27 / Tn0, 1, dt)
    sxx = sxy = 0.0
    for i in range(n):
        rx = cl[i]["rest"][0] - mx
        sxx += rx * rx
        sxy += rx * (S.legs[i].ref_y - mean_y)
    pitch_t = clamp(math.atan(sxy / sxx), -0.4, 0.4) if sxx > 1e-6 else 0.0
    if air and J.pounce:
        pitch_t = clamp(0.8 * math.atan2(J.vy, max(S.v, 0.5)), -0.45, 0.45)      # nose follows the arc
    S.pitch.step(pitch_t, 20 / Tn0, 1, dt)
    pitch, flex = S.pitch.x, 0.0
    beast = ch.get("beast")
    if beast and gp["gal"] > 1e-3:
        # gallop: the back stretches out as the hind legs drive and bunches up in the air
        flex = -beast["flex"] * gp["gal"] * math.cos(TAU * (S.phase - 0.42))
        pitch += beast["rock"] * gp["gal"] * math.cos(TAU * (S.phase - 0.10))
    cp, sn = math.cos(pitch), math.sin(pitch)

    h = ch["rootHeight"] * (1 - ch["crouchDrop"] * S.crouch) * (1 - ch["runDrop"] * gp["run"])
    phi_mid = duty / 2 - phases[0]
    c = math.cos(2 * TAU * (S.phase - phi_mid))
    c = (-1 if c < 0 else 1) * math.pow(abs(c), 1 - 0.6 * st["snap"])
    bob = st["bounce"] * ch["bob"] * gp["moving"] * ((1 - gp["run"]) * gp["Aw"] - gp["run"] * gp["Ar"]) * c
    if gp["gal"] > 1e-3:                                   # one rise and fall a stride, highest in flight
        bob = lerp(bob, st["bounce"] * ch["bob"] * 0.075 * L * math.cos(TAU * (S.phase - 0.95)), gp["gal"])
    sway = 0.02 * L * ch["sway"] * (1 - gp["run"]) * gp["moving"] * math.cos(TAU * (S.phase - phi_mid)) * cl[0]["side"]
    # idle: slow weight shifts; the planted feet stay put, so the knees and hips do the work
    idle = (1 - gp["moving"]) * (0 if J else 1) * (1 - (st.get("still") or 0))      # still: no life in a standing body
    P = idle_period(L)
    ix = 0.012 * L * idle * idle_noise(S.t, P, 1.0) - (S.act_back or 0)
    iy = -0.008 * L * idle * (1 + idle_noise(S.t, P, 3.0))
    sway += 0.03 * L * idle * idle_noise(S.t, P, 2.0)
    # lean into a turn, from the feet up, by the angle that balances the sideways pull
    S.bank.step(clamp(math.atan(S.v * S.om / G) * st["lean"], -0.4, 0.4), 30 / Tn0, 1, dt)
    S.side.step(0, 26 / Tn0, 0.7, dt)
    bank_t = math.tan(S.bank.x)
    sway0 = sway + S.side.x
    sway = sway0 + bank_t * h
    if J and J.stage == "prep":
        S.hop.step(-0.22 * h, 30 / Tn0, 1, dt)
    elif J and J.stage == "push":
        S.hop.v += J.acc * dt
        S.hop.x += S.hop.v * dt
    elif not air:
        if J and J.landed:
            J.landed = False
            S.hop.x = J.y - (S.g_ref.x + h + bob)
            S.hop.v = J.vy
        S.hop.step(0, 21 / Tn0, 0.75, dt)
        if J and J.stage == "land" and J.t > 0.3 * Tn0 and abs(S.hop.x) < 0.01 * L:
            S.jump = None
    else:
        S.hop.x = 0.0
        S.hop.v = 0.0
    S.hop.x = max(S.hop.x, -0.45 * h)
    y0 = J.y if air else S.g_ref.x + h + bob + iy + S.hop.x

    hips, ankles, need = [], [], 0.0
    for i in range(n):
        lg = S.legs[i]
        ld = cl[i]
        at = ld["attach"]
        cpl, snl = cp, sn
        if flex:                                            # each end of a bending spine carries its own legs
            fa = pitch + (flex if at[0] < 0 else -flex)
            cpl, snl = math.cos(fa), math.sin(fa)
        hip = [S.x + ix + at[0] * cpl - at[1] * snl, y0 + at[0] * snl + at[1] * cpl, at[2] + sway]
        ball = [lg.ball[0], lg.ball[1] + lg.drop, lg.ball[2]]
        ankle, heel, toe = ball, None, None
        F = ld.get("foot")
        if F:
            if not lg.swing:
                lg.strike *= math.exp(-dt / (0.035 * gp["Tn"]))
                behind = (hip[0] - ball[0]) / L
                lg.alpha = lg.strike + F["heelLift"] * smooth(0.2, 0.62, behind) * (0.4 + 0.6 * gp["moving"])
            al = lg.alpha
            rot = al - (0 if lg.swing else lg.slope)
            ca, sa = math.cos(rot), math.sin(rot)
            b2 = [ball[0], ball[1] + max(0, (F["fb"] + F["hb"]) * math.sin(-al)), ball[2]]   # toes up: pivot on the heel
            ankle = [b2[0] - F["fb"] * ca + F["ah"] * sa, b2[1] + F["fb"] * sa + F["ah"] * ca, b2[2]]
            heel = [b2[0] - (F["fb"] + F["hb"]) * ca, b2[1] + (F["fb"] + F["hb"]) * sa, b2[2]]
            toe = [b2[0] + F["toe"], b2[1], b2[2]] if rot > 0 else [b2[0] + F["toe"] * ca, b2[1] - F["toe"] * sa, b2[2]]
            ball = b2
        hips.append(hip)
        ankles.append((ankle, heel, toe, ball))
        if not lg.swing:
            l_max = 0.985 * (ld["upper"] + ld["lower"])
            dh2 = math.pow(ankle[0] - hip[0], 2) + math.pow(ankle[2] - hip[2], 2)
            top = ankle[1] + math.sqrt(max(l_max * l_max - dh2, 0))
            lg.over = hip[1] - top
            lg.behind = hip[0] - ankle[0]
            need = max(need, lg.over)
        else:
            lg.over = 0.0
        raw = clamp((lg.ball[0] - hip[0]) / (0.5 * stance_travel + 0.08 * L), -1, 1)
        lg.fwd += (raw - lg.fwd) * decay(40 / Tn0, dt)
    # a trailing foot that has run out of reach steps early, as long as enough other feet are down
    if not standing:
        down = sum(1 for lg in S.legs if not lg.swing)
        for lg in S.legs:
            if not lg.swing and lg.over > 0.03 * L and lg.behind > 0 and down - 1 >= max(1, (n >> 1) - 1) and lg.psi < duty - 0.02:
                if lg.psi > duty - 0.2:
                    # close to its normal lift-off: simply start the real step a little early
                    lg.swing = Swing(list(lg.ball), lg.alpha, psi0=lg.psi, early=True, tx=lg.ball[0], ty=lg.ball[1], tz=lg.ball[2])
                else:
                    # far out of step (a gait change): one quick corrective step
                    lg.swing = Swing(list(lg.ball), lg.alpha, manual=True, rate=1 / max(0.7 * (1 - duty) * period, 0.08 * gp["Tn"]),
                                     tx=lg.ball[0], ty=lg.ball[1], tz=lg.ball[2])
                down -= 1
    # if a planted leg still cannot reach, the body sinks instead of the foot sliding
    need = min(need, 0.4 * h)
    S.reach_drop += (need - S.reach_drop) * (decay(50, dt) if need > S.reach_drop else decay(1 / (0.08 * gp["Tn"]), dt))
    S.y = y0 - S.reach_drop

    def world(p):                                           # a point of the body's frame, in the world
        x, z = p[0] - S.x, p[2]
        return [S.px + x * hc - z * hs, p[1], S.pz + x * hs + z * hc]

    legs = []
    for i in range(n):
        lg = S.legs[i]
        ld = cl[i]
        hips[i][1] -= S.reach_drop
        ankle, heel, toe, ball = ankles[i]
        knee, end = ik2(hips[i], ankle, ld["upper"], ld["lower"], ld["pole"])
        sw = lg.swing
        target = [sw.tx, sw.ty, ld["rest"][1] if sw.tz is None else sw.tz] if sw else None
        legs.append({"hip": hips[i], "knee": knee, "ankle": end, "heel": heel, "toe": toe, "ball": ball, "planted": not sw, "target": target,
                     "side": ld["side"]})

    # backpack / tail: a loose spring dragged along by the body's vertical motion
    vy = (S.y - S.last_y) / dt
    S.last_y = S.y
    S.pack.v -= (vy - (S.pack_vy or 0)) * 0.6
    S.pack_vy = vy
    S.pack.step(0, 60 / Tn0, 0.35, dt)

    if air:
        gait = "Jump"
    elif standing or S.v < 0.02:
        gait = "Standing"
    elif gp["gal"] > 0.5:
        gait = "Gallop"
    elif gp["run"] > 0.5:
        gait = "Trot" if ch["kind"] == "quad" and n > 2 else "Run"
    else:
        gait = "Walk"
    S.stats = {"Fr": gp["Fr"], "stride": gp["stride"], "period": period, "duty": duty, "run": gp["run"], "phases": phases, "v": S.v,
               "gait": gait, "idlePeriod": P, "steps": 60 * n / period if S.v > 0.02 else 0, "air": max(0, 1 - 2 * duty) if ch["gait"].get("run") else 0,
               "heading": S.h, "turn": S.om}
    if upper is not None:
        aim = inp.get("aim")
        acc_lean = math.atan(S.a / G) * 0.55 * st["lean"]
        B = {"root": [S.x + ix, S.y, sway], "pitch": pitch, "gp": gp, "Tn": Tn0, "idle": idle, "P": P, "bank": bank_t, "sway0": sway0,
             "aim": to_l([aim[0], aim[1], aim[2] if len(aim) > 2 else S.pz]) if aim and not S.carry else None,
             "to_l": to_l, "to_w": to_w, "terrain": terrain, "flex": flex,
             "drift": [mvl[0] + S.kv[0] * hc + S.kv[1] * hs, mvl[1] - S.kv[0] * hs + S.kv[1] * hc],
             "prep": clamp(-S.hop.x / (0.22 * h), 0, 1) if J and J.stage in ("prep", "push") else 0,
             "leanBase": ((0.03 + 0.05 * min(gp["Fr"], 2) + 0.09 * gp["run"]) * st["lean"] * dx + acc_lean * dx + 0.42 * S.crouch) - 0.8 * S.hop.x / h - 0.06 * S.air_b}
        S.local = upper(S, ch, inp, st, dt, legs, B)
        S.local["heading"] = S.h
    for lg in S.legs:
        if not lg.swing and not lg.w:
            lg.w = to_w(lg.ball)
    if upper is not None:
        S.stats["ammo"] = list(S.ammo) if S.ammo else None
        S.stats["kit"] = S.kit
        S.stats["action"] = S.act["name"] if S.act else None
        S.pose = pose_to_world(S.local, (S.x, S.px, S.pz, hc, hs))
        return S.pose
    for l in legs:
        for key in ("hip", "knee", "ankle", "heel", "toe", "ball", "target"):
            if l[key] is not None:
                l[key] = world(l[key])
    # The one thing the action layer (stage 3) feeds back into the ground step when nothing is being done:
    # a mantis rocks like a leaf in the wind while it stands.
    arthro = ch.get("arthro")
    if arthro:
        S.act_back = arthro["rock"] * math.sin(TAU * S.t / 1.4) if arthro.get("rock") and standing else 0.0
    S.pose = {"kind": ch["kind"], "heading": S.h, "root": world([S.x + ix, S.y, sway]), "pitch": pitch, "legs": legs, "crouch": S.crouch}
    return S.pose
