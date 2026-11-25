# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Daniel Sandner
"""CLIo Motion in Python, stage 5a: the skeleton, live.  What a game needs to move a model, or to draw a character's
parts, from a pose while it runs.

    sk = skeleton(ch, pose, sk)          # where every joint is for this pose; pass back what the last call gave
    sk["frames"][j]                      # {"o": place, "x": side, "y": along the bone, "z": the third axis}
    parts(sk)                            # the parts those joints carry (capsules a..b of radius r, with colour)
    order(parts(sk), sk["heading"], yaw) # the same list back to front for a view, each with its shade level
    joint_move(sk, j)                    # 4 x 4, glTF axes: takes anything bound to joint j from the template pose
                                         # to where it is now (world = move * rest)

Places and directions are in the pose's own axes: x forward, y up, z to the right.  The rigs (joint names, parents,
the template pose, the parts) are data, in rigs.json, the same data the JavaScript and C versions use.

A port of the joints that js/rig.js declares and of liveSkeleton, liveParts and jointMove in js/bake.js; checked
against the numbers in spec/skeleton/.
"""
from __future__ import annotations

import json
import math
import os

_rigs = None


def rigs():
    """The rigs by name: one for each character, and one for each of the soldier's kits (soldier, soldier_pistols,
    soldier_sword)."""
    global _rigs
    if _rigs is None:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "rigs.json"), encoding="utf-8") as f:
            _rigs = json.load(f)
    return _rigs


def rig_for(ch, pose):
    """The rig a pose belongs to: the character's, or for a soldier the one of the kit in the pose."""
    name = ch["id"]
    if ch["mount"]["type"] == "held" and pose.get("props"):
        kinds = [w["kind"] for w in pose["props"]]
        kit = "sword" if "sword" in kinds else "pistols" if "pistol" in kinds else "rifle"
        if kit != ch["mount"]["kit"]:
            name += "_" + kit
    return rigs()[name]


def _add(a, b):
    return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]


def _sub(a, b):
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def _mul(a, s):
    return [a[0] * s, a[1] * s, a[2] * s]


def _unit(a):
    ln = math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2]) or 1
    return [a[0] / ln, a[1] / ln, a[2] / ln]


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _mix(a, b, t):
    return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t]


def joints(ch, pose, rig=None):
    """Every joint of the pose: (name, parent's name or None, where it is, the point its bone aims at, its own side
    direction or None), in the order the rig lists them."""
    p, c, J = pose, ch, []
    rig = rig or rig_for(ch, pose)
    hd0 = p.get("heading") or 0
    rt = [-math.sin(hd0), 0.0, math.cos(hd0)]
    rt_u = p.get("side") or rt

    def perp(d):
        return _cross(rt, d)

    def perp_u(d):
        return _cross(rt_u, d)

    def add(name, parent, o, aim, side=None):
        J.append((name, parent, o, aim, side))

    def side_name(base, k):
        return base + ("_R" if k == 0 else "_L")

    def wings(parent):
        for k, w in enumerate(p.get("wings") or ()):
            nm = "R" if k == 0 else "L"
            add("Wing_" + nm, parent, w["root"], w["mid"], w["t1"])
            add("WingTip_" + nm, "Wing_" + nm, w["mid"], w["tip"], w["t2"])

    kind = p.get("kind") or c["kind"]
    legs = p["legs"]
    if kind == "biped":
        for i, l in enumerate(legs):
            add(side_name("UpperLeg", i), "Hips", l["hip"], l["knee"])
            add(side_name("LowerLeg", i), side_name("UpperLeg", i), l["knee"], l["ankle"])
            add(side_name("Foot", i), side_name("LowerLeg", i), l["ankle"], _add(l["ankle"], _unit(_sub(l["ball"], l["heel"]))))
            add(side_name("Toe", i), side_name("Foot", i), l["ball"], _add(l["ball"], _unit(_sub(l["toe"], l["ball"]))))
        mid, u, f, pack = _mix(p["root"], p["chest"], 0.5), p["u"], p["f"], p.get("pack") or 0
        pk_a = _add(p["chest"], _add(_mul(f, -0.21), _mul(u, -0.04)))
        pk_b = _add(mid, _mul(f, -0.20))
        add("Hips", None, p["root"], p["chest"])
        add("Pack", "Hips", [pk_a[0], pk_a[1] + pack, pk_a[2]], [pk_b[0], pk_b[1] + pack, pk_b[2]])
        add("Spine", "Hips", mid, p["chest"], rt_u)
        add("Head", "Spine", p["head"], _add(p["head"], perp_u(p["gaze"])), rt_u)
        for k, w in enumerate(p.get("props") or ()):
            pistol = w["kind"] == "pistol"
            nm = side_name("Weapon", k) if pistol else "Shield" if w["kind"] == "shield" else "Weapon"
            sv = _cross(w["dir"], w["up"])
            add(nm, "Hips", w["o"], w["muzzle"], sv)
            if w["kind"] in ("sword", "shield"):
                continue
            add(side_name("Magazine", k) if pistol else "Magazine", nm, w["magA"], w["magB"], sv)
        gr = p.get("grenade")
        gp = gr["p"] if gr else _add(_add(p["root"], _add(_mul(u, 0.09), _mul(f, 0.07))), _mul(rt, 0.185))
        add("Grenade", "Hips", gp, _add(gp, u))
        cr = p.get("carry")
        if cr:
            add("Carry", "Hips", cr["c"], _add(cr["c"], cr["u"]), cr["side"])
        else:
            cc = _add(p["root"], _add(_mul(f, 0.34), _mul(u, 0.22)))
            add("Carry", "Hips", cc, _add(cc, u), rt_u)
        for i, s in enumerate(p["arms"]):
            add(side_name("UpperArm", i), "Spine", s["shoulder"], s["elbow"])
            add(side_name("LowerArm", i), side_name("UpperArm", i), s["elbow"], s["hand"])
            add(side_name("Hand", i), side_name("LowerArm", i), s["hand"], _add(s["hand"], _sub(s["hand"], s["elbow"])))
    elif kind == "mech":
        for i, l in enumerate(legs):
            add(side_name("UpperLeg", i), "Hips", l["hip"], l["knee"])
            add(side_name("LowerLeg", i), side_name("UpperLeg", i), l["knee"], l["ankle"])
            add(side_name("Foot", i), side_name("LowerLeg", i), l["ankle"], _add(l["ankle"], _unit(_sub(l["ball"], l["heel"]))))
            add(side_name("Toe", i), side_name("Foot", i), l["ball"], _add(l["ball"], _unit(_sub(l["toe"], l["ball"]))))
        pc = p["chest"]
        add("Hips", None, p["root"], pc)
        add("Hull", "Hips", pc, _add(pc, p["u"]), rt_u)
        for i in range(2):
            m = p["mounts"][i]
            add(side_name("Gun", i), "Hull", m["base"], _add(m["base"], m["dir"]))
    elif kind == "quad" and c.get("beast"):
        tp = p.get("tailPts") or [p["back"], p["tail"]]
        for i in range(len(tp) - 1):
            add("Tail%d" % (i + 1), "Tail%d" % i if i else "Hips", tp[i], tp[i + 1])
        add("Hips", None, p["root"], p["back"])
        add("Chest", "Hips", p["root"], p["front"])
        nd = _unit(_sub(p["head"], p["neck"]))
        add("Neck", "Chest", p["neck"], p["head"])
        add("NeckTop", "Neck", p["head"], _add(p["head"], nd))
        add("Head", "Neck", p["head"], _add(p["head"], p["gaze"]), rt_u)
        es = rig.get("ears") or 0
        if es:                                               # ears: they go back when the animal is roused
            hup = perp_u(p["gaze"])
            ear = _add(p["head"], _add(_mul(hup, 0.085 * es), _mul(p["gaze"], (-0.03 - 0.05 * (p.get("alert") or 0)) * es)))
            add("Ears", "Head", ear, _add(ear, p["gaze"]), rt_u)
        jw = p["mounts"][0]
        add("Jaw", "Head", jw["base"], jw["tip"], rt_u)
        for i, l in enumerate(legs):
            nm = c["legs"][i]["name"]
            add("UpperLeg_" + nm, "Chest" if c["legs"][i]["attach"][0] > 0 else "Hips", l["hip"], l["knee"])
            add("LowerLeg_" + nm, "UpperLeg_" + nm, l["knee"], l["ankle"])
            if l.get("heel"):                                # walks on its toes
                add("Foot_" + nm, "LowerLeg_" + nm, l["ankle"], _add(l["ankle"], _unit(_sub(l["ball"], l["heel"]))))
                add("Toe_" + nm, "Foot_" + nm, l["ball"], _add(l["ball"], _unit(_sub(l["toe"], l["ball"]))))
        wings("Chest")
    elif c.get("octo"):
        om = p["mantle"]
        add("Body", None, p["root"], _add(p["root"], p["axis"]))
        add("Mantle", "Body", om["c"], om["tip"])
        add("Eyes", "Body", p["eye"], _add(p["eye"], p["axis"]))
        for k, arm in enumerate(p["arms"]):
            for i in range(len(arm) - 1):
                add("Arm%d_%d" % (k, i + 1), "Arm%d_%d" % (k, i) if i else "Body", arm[i], arm[i + 1])
    elif c.get("arthro"):
        look = c["arthro"].get("look") or "scorpion"
        sax = _unit(_sub(p["front"], p["back"]))
        add("Body", None, p["back"], p["front"])
        st = p.get("tailPts") or []
        for i in range(len(st) - 1):
            add("Tail%d" % (i + 1), "Tail%d" % i if i else "Body", st[i], st[i + 1])
        if look == "mantis":
            add("Thorax", "Body", p["thorax"][0], p["thorax"][1])
            add("Head", "Thorax", p["eye"], _add(p["eye"], sax))
        elif look != "scorpion":
            add("Head", "Body", p["eye"], _add(p["eye"], sax))
        for k, cl in enumerate(p.get("claws") or ()):
            nm = "R" if k == 0 else "L"
            add("ClawUpper_" + nm, "Thorax" if look == "mantis" else "Body", cl["shoulder"], cl["elbow"])
            add("ClawLower_" + nm, "ClawUpper_" + nm, cl["elbow"], cl["wrist"])
            add("ClawHand_" + nm, "ClawLower_" + nm, cl["wrist"], cl["tip"])
            add("ClawFinger_" + nm, "ClawHand_" + nm, cl["fingerA"], cl["fingerB"])
        for i, l in enumerate(legs):
            nm = c["legs"][i]["name"]
            add("UpperLeg_" + nm, "Body", l["hip"], l["knee"])
            add("LowerLeg_" + nm, "UpperLeg_" + nm, l["knee"], l["ankle"])
        wings("Body")
    elif kind == "quad":
        add("Body", None, p["back"], p["front"])
        add("Tail", "Body", p["back"], p["tail"])
        add("Neck", "Body", _add(p["front"], _mul(p["up"], 0.03)), p["head"])
        add("Head", "Neck", p["head"], _add(p["head"], p["gaze"]), rt_u)
        for i, l in enumerate(legs):
            nm = c["legs"][i]["name"]
            add("UpperLeg_" + nm, "Body", l["hip"], l["knee"])
            add("LowerLeg_" + nm, "UpperLeg_" + nm, l["knee"], l["ankle"])
    else:
        t = p["mounts"][0]
        add("Body", None, p["back"], p["front"])
        add("Turret", "Body", t["base"], _add(t["base"], t["dir"]))
        for i, l in enumerate(legs):
            nm = c["legs"][i]["name"]
            add("UpperLeg_" + nm, "Body", l["hip"], l["knee"])
            add("LowerLeg_" + nm, "UpperLeg_" + nm, l["knee"], l["ankle"])
    return J


def _held_layers(pose):
    """Things in the hands change their place in the draw order with what the hands are doing.  By group: (layer, shade)."""
    o = {}
    for k, w in enumerate(pose.get("props") or ()):
        st = w["stow"] > 0.5
        if w["kind"] == "pistol":
            o["prop%d" % k] = ((2.1 if st else 3.1) if k == 0 else (-2.1 if st else -2.9), 3 if k == 0 else 1)
        elif w["kind"] == "sword":
            o["prop%d" % k] = (-2.3 if st else 3.1, 3)
        elif w["kind"] == "shield":
            o["prop%d" % k] = (-0.6 if st else -2.6, 1)
        else:
            o["prop%d" % k] = (-0.5 if st else 0.5, 2)
    if (pose.get("kind") or "") == "biped":
        gr = pose.get("grenade")
        o["grenade"] = (3.05 if gr and gr.get("held") else 2.2, 3)
    return o


def skeleton(ch, pose, prev=None):
    """Where every joint is for this pose.  prev: what the last call returned for this character (a bone seen end on
    keeps the turn it had; with nothing before it, the turn it has in the template pose).
    Returns {"rig", "frames": [{"o", "x", "y", "z"}], "heading", "held"}."""
    rig = rig_for(ch, pose)
    J = joints(ch, pose, rig)
    if len(J) != len(rig["joints"]):
        raise ValueError("The pose has %d joints; the rig %s has %d." % (len(J), rig["name"], len(rig["joints"])))
    hd = pose.get("heading") or 0
    lat, fwd = [math.sin(hd), 0.0, -math.cos(hd)], [math.cos(hd), 0.0, math.sin(hd)]
    before = prev["frames"] if prev and prev["rig"] is rig else rig["joints"]
    frames = []
    for k, (name, parent, o, aim, side) in enumerate(J):
        d = _sub(aim, o)
        ln = math.sqrt(d[0] * d[0] + d[1] * d[1] + d[2] * d[2])
        y = [d[0] / ln, d[1] / ln, d[2] / ln] if ln > 1e-6 else [0.0, 1.0, 0.0]
        ref = side if side else fwd if rig["joints"][k]["ref"] else lat
        t = ref[0] * y[0] + ref[1] * y[1] + ref[2] * y[2]
        x = [ref[0] - y[0] * t, ref[1] - y[1] * t, ref[2] - y[2] * t]
        xl = math.sqrt(x[0] * x[0] + x[1] * x[1] + x[2] * x[2])
        if xl < 1e-4:                                        # the bone points along its side reference
            b = before[k]
            frames.append({"o": list(o), "x": list(b["x"]), "y": list(b["y"]), "z": list(b["z"])})
            continue
        x = [x[0] / xl, x[1] / xl, x[2] / xl]
        frames.append({"o": list(o), "x": x, "y": y, "z": _cross(x, y)})
    pk = dict(pose)
    pk.setdefault("kind", ch["kind"])
    return {"rig": rig, "frames": frames, "heading": hd, "held": _held_layers(pk)}


def parts(sk):
    """The parts the joints carry, as the rig lists them: dicts with a, b (None for a ball), r, color, group, layer,
    shade, joint, and end, on, part, of, raw, sq where the part has them."""
    F, rig, out = sk["frames"], sk["rig"], []
    for q in rig["parts"]:
        f = F[q["joint"]]

        def at(l):
            return [f["o"][i] + f["x"][i] * l[0] + f["y"][i] * l[1] + f["z"][i] * l[2] for i in range(3)] if l else None

        hl = sk["held"].get(q["group"])
        o = {"a": at(q["a"]), "b": at(q["b"]), "r": q["r"], "color": q["color"], "group": q["group"], "layer": hl[0] if hl else q["layer"],
             "shade": hl[1] if hl else q["shade"], "joint": rig["joints"][q["joint"]]["name"], "raw": q["raw"], "sq": q["sq"], "part": q["part"], "of": q["of"]}
        if q["end"]:
            o["end"] = at(q["end"])
        if q["on"]:
            o["on"] = at(q["on"])
        out.append(o)
    return out


def order(plist, heading, yaw=0.0):
    """Back to front for a view turned by yaw (0: from the body's right side when its heading is 0).  Sets on each
    part "key" (its place in the order) and "level" (its shade, 0 dark to 4 light, -1 for a part that glows), and
    returns the list sorted.  The body seen from its other side has its near and far parts change places."""
    flip = math.cos(heading - yaw) < -1e-9
    sy, cy = math.sin(yaw), math.cos(yaw)
    for q in plist:
        ly = q["layer"]
        side = abs(ly) >= 1
        k = -ly if flip and side else ly
        on = q.get("on")
        # something on the surface of a rounder part (an eye on a head): on the side turned away it goes behind that part
        if on and (-q["a"][0] * sy + q["a"][2] * cy) < (-on[0] * sy + on[2] * cy) - 0.004:
            k -= 0.005
        q["key"] = k
        q["level"] = -1 if q["raw"] else 4 - q["shade"] if flip and side else q["shade"]
    return [q for i, q in sorted(enumerate(plist), key=lambda iq: (iq[1]["key"], iq[0]))]


def joint_move(sk, j):
    """The 4 x 4 matrix, in glTF axes (+Y up, +Z forward) and written column after column, that takes anything bound to
    joint j from the template pose to where it is now.  For a model built on templates/3d: world = move * rest."""
    def g(v):
        return [-v[2], v[1], v[0]]

    f, t = sk["frames"][j], sk["rig"]["joints"][j]
    A, B = [g(f["x"]), g(f["y"]), g(f["z"])], [g(t["x"]), g(t["y"]), g(t["z"])]
    o0, o1 = g(t["o"]), g(f["o"])
    R = [A[0][r] * B[0][c] + A[1][r] * B[1][c] + A[2][r] * B[2][c] for c in range(3) for r in range(3)]
    return [R[0], R[1], R[2], 0.0, R[3], R[4], R[5], 0.0, R[6], R[7], R[8], 0.0,
            o1[0] - (R[0] * o0[0] + R[3] * o0[1] + R[6] * o0[2]), o1[1] - (R[1] * o0[0] + R[4] * o0[1] + R[7] * o0[2]), o1[2] - (R[2] * o0[0] + R[5] * o0[1] + R[8] * o0[2]), 1.0]


def part_place(im, a, b, rs, ppm, flip=False):
    """Where a part's picture goes on the screen.  im: {"axis": "ball" | "up" | "down" | "right", "w", "h"} and, for a
    picture cut from a drawing, "box" [x0, y0, x1, y1] (metres, in the bone's frame), "len" and "r" (the bone's length
    and radius as drawn).  a, b: the bone's ends on the screen (b None for a part with no length); rs: the part's
    radius there; ppm: pixels to a metre; flip: the body is seen from its other side.
    Returns {"x", "y", "rot", "fx", "fy", "dx", "dy", "dw", "dh"}: move to (x, y), turn by rot (radians, clockwise on a
    screen whose y runs down), scale by (fx, fy), then draw the picture into the box (dx, dy, dw, dh)."""
    o = {"x": a[0], "y": a[1], "rot": 0.0, "fx": 1, "fy": 1}
    bx = im.get("box")
    if im["axis"] == "ball" or b is None:
        if flip:
            o["fx"] = -1
        if bx:
            o.update(dx=bx[0] * ppm, dy=bx[1] * ppm, dw=(bx[2] - bx[0]) * ppm, dh=(bx[3] - bx[1]) * ppm)
        else:
            dh = 2.3 * rs
            dw = dh * im["w"] / im["h"]
            o.update(dx=-dw / 2, dy=-dh / 2, dw=dw, dh=dh)
        return o
    if im["axis"] == "up":
        a, b = b, a
        o["x"], o["y"] = a[0], a[1]
    ex, ey = b[0] - a[0], b[1] - a[1]
    dist = math.sqrt(ex * ex + ey * ey)
    ln, ang = dist + 2 * rs, math.atan2(ey, ex)
    # a bone seen end on has no length on the screen: the picture is then no shorter than the part is thick
    k = max(dist / (im["len"] * ppm), 2 * rs / ((im["len"] + 2 * im["r"]) * ppm)) if bx else 1
    if im["axis"] == "right":
        o["rot"] = ang
        if flip:
            o["fy"] = -1
        if bx:
            o.update(dx=bx[0] * ppm * k, dy=bx[1] * ppm, dw=(bx[2] - bx[0]) * ppm * k, dh=(bx[3] - bx[1]) * ppm)
        else:
            dh = ln * im["h"] / im["w"]
            o.update(dx=-rs, dy=-dh / 2, dw=ln, dh=dh)
    else:
        o["rot"] = ang - math.pi / 2
        if flip:
            o["fx"] = -1
        if bx:
            o.update(dx=bx[0] * ppm, dy=bx[1] * ppm * k, dw=(bx[2] - bx[0]) * ppm, dh=(bx[3] - bx[1]) * ppm * k)
        else:
            dw = ln * im["w"] / im["h"]
            o.update(dx=-dw / 2, dy=-rs, dw=dw, dh=ln)
    return o
