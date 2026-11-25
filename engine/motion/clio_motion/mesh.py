# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Daniel Sandner
"""CLIo Motion in Python: a stand-in model in triangles, for a renderer that draws triangles.

Every part of a rig (a capsule or a ball) becomes a small closed shape of flat faces, each corner bound to the
part's joint, so the whole model follows a skeleton with no skinning:

    m = build(rig.rigs()["hyena"], sides=6)     # once
    pts = place(m, sk)                          # every frame: the corners for rig.skeleton's answer, in the pose's axes
    for (a, b, c), part in zip(m["faces"], m["face_part"]):
        m["parts"][part]["color"]               # "#rrggbb"; also "group", "glow", and the rig's own part under "def"

Faces are wound anticlockwise seen from outside (x forward, y up, z to the right).  ``rest(m)`` gives the corners
in the template pose.  ``lines(rig)`` is the same body for a display that draws lines: outlines of the thick
parts, one line for each thin one.  The shapes are low on purpose: a capsule is a prism with a blunt point at each end, a thin
one has fewer sides, a ball is a double pyramid unless it is one of the big ones (a head, a hull).
"""
from __future__ import annotations

import math


def _unit(v):
    n = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    return [v[0] / n, v[1] / n, v[2] / n]


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _shape(a, b, r, n, flat, rings):
    """Corners (in the joint's frame) and faces of one part.  a, b: its ends (b None: a ball); n sides; flat: its ends
    are cut square; rings: a ball has two rings of corners (else one: a double pyramid)."""
    if b is not None and math.dist(a, b) < 1e-9:
        b = None
    if b is None:
        d, half = [0.0, 1.0, 0.0], (0.5 * r if rings else 0.0)
        rr = math.sqrt(r * r - half * half)
        a, b = [a[0], a[1] - half, a[2]], [a[0], a[1] + half, a[2]]
        tip = r - half
    else:
        d = _unit([b[0] - a[0], b[1] - a[1], b[2] - a[2]])
        rr, tip = r, (0.0 if flat else 0.7 * r)
    u = [1.0, 0.0, 0.0] if abs(d[0]) < 0.9 else [0.0, 0.0, 1.0]
    t = u[0] * d[0] + u[1] * d[1] + u[2] * d[2]
    u = _unit([u[0] - d[0] * t, u[1] - d[1] * t, u[2] - d[2] * t])
    v = _cross(d, u)
    pts, faces = [], []
    one = b is not None and math.dist(a, b) < 1e-9          # a ball as a double pyramid: one ring only
    for end in ((a,) if one else (a, b)):
        for k in range(n):
            c, s = math.cos(2 * math.pi * k / n) * rr, math.sin(2 * math.pi * k / n) * rr
            pts.append([end[0] + u[0] * c + v[0] * s, end[1] + u[1] * c + v[1] * s, end[2] + u[2] * c + v[2] * s])
    top = len(pts)
    pts.append([a[0] - d[0] * tip, a[1] - d[1] * tip, a[2] - d[2] * tip])
    pts.append([b[0] + d[0] * tip, b[1] + d[1] * tip, b[2] + d[2] * tip])
    hi = 0 if one else n                                    # where the far ring starts
    for k in range(n):
        j = (k + 1) % n
        if not one:
            faces += [(k, j, n + j), (k, n + j, n + k)]
        faces += [(j, k, top), (hi + k, hi + j, top + 1)]
    return pts, faces


def build(rig, sides=6, thin=4):
    """The stand-in model of a rig (one of ``rig.rigs()``).  sides: how many sides a part has round its length;
    thin: how many for a part less than 0.6 of the rig's middling radius (legs of insects, barrels, whiskers).
    Returns ``{"rig", "joint", "local", "faces", "face_part", "parts", "by_joint"}``: for each corner its joint
    and its place in that joint's frame; for each face its three corners and its part."""
    radii = sorted(q["r"] for q in rig["parts"])
    mid = radii[len(radii) // 2] if radii else 0.0
    joint, local, faces, face_part, parts = [], [], [], [], []
    for i, q in enumerate(rig["parts"]):
        small = q["r"] < 0.6 * mid
        n = max(3, thin if small else sides)
        pts, fs = _shape(q["a"], q["b"], q["r"], n, bool(q.get("sq")), q["r"] >= 1.5 * mid)
        first = len(local)
        local += pts
        joint += [q["joint"]] * len(pts)
        faces += [(a + first, b + first, c + first) for a, b, c in fs]
        face_part += [i] * len(fs)
        parts.append({"color": q["color"], "group": q["group"], "glow": bool(q.get("raw")), "first": first, "count": len(pts), "def": q})
    by_joint = {}
    for k, j in enumerate(joint):
        by_joint.setdefault(j, []).append((k, local[k][0], local[k][1], local[k][2]))
    return {"rig": rig, "joint": joint, "local": local, "faces": faces, "face_part": face_part, "parts": parts, "by_joint": sorted(by_joint.items())}


def lines(rig, sides=4, thick=0.5):
    """The stand-in model for a display that draws lines (a vector display, a plotter): a part at least ``thick``
    times as thick as the rig's thickest is the outline of a prism of ``sides`` sides (a ball: of a double
    pyramid), a thinner one a single line along its length, a small ball nothing.  Returns what ``build`` returns
    (so ``place`` and ``rest`` take it), with ``"edges"``: pairs of corners.  Its faces are the thick parts' only:
    they are there to hide the lines behind them."""
    most = max([q["r"] for q in rig["parts"]] or [0.0])
    joint, local, faces, face_part, edges, parts = [], [], [], [], [], []
    for i, q in enumerate(rig["parts"]):
        first = len(local)
        ball = q["b"] is None or math.dist(q["a"], q["b"]) < 1e-9
        if q["r"] >= thick * most:
            n = max(3, sides)
            pts, fs = _shape(q["a"], q["b"], q["r"], n, bool(q.get("sq")), False)
            local += pts
            faces += [(a + first, b + first, c + first) for a, b, c in fs]
            face_part += [i] * len(fs)
            if ball:                                        # one ring and two points
                for k in range(n):
                    edges += [(first + k, first + (k + 1) % n), (first + k, first + n), (first + k, first + n + 1)]
            else:                                           # two rings and what joins them
                for k in range(n):
                    edges += [(first + k, first + (k + 1) % n), (first + n + k, first + n + (k + 1) % n), (first + k, first + n + k)]
        elif not ball:
            local += [list(q["a"]), list(q["b"])]
            edges.append((first, first + 1))
        joint += [q["joint"]] * (len(local) - first)
        parts.append({"color": q["color"], "group": q["group"], "glow": bool(q.get("raw")), "first": first, "count": len(local) - first, "def": q})
    by_joint = {}
    for k, j in enumerate(joint):
        by_joint.setdefault(j, []).append((k, local[k][0], local[k][1], local[k][2]))
    return {"rig": rig, "joint": joint, "local": local, "faces": faces, "face_part": face_part, "edges": edges, "parts": parts,
            "by_joint": sorted(by_joint.items())}


def place(m, sk):
    """The corners of a model for a skeleton (``rig.skeleton``'s answer), in the pose's axes."""
    return _place(m, sk["frames"])


def rest(m):
    """The corners in the template pose."""
    return _place(m, m["rig"]["joints"])


def _place(m, frames):
    out = [None] * len(m["local"])
    for j, pts in m["by_joint"]:
        f = frames[j]
        (ox, oy, oz), (xx, xy, xz), (yx, yy, yz), (zx, zy, zz) = f["o"], f["x"], f["y"], f["z"]
        for k, lx, ly, lz in pts:
            out[k] = (ox + xx * lx + yx * ly + zx * lz, oy + xy * lx + yy * ly + zy * lz, oz + xz * lx + yz * ly + zz * lz)
    return out
