"""Low-poly 3D models for first-person levels.

A game's ``models.json`` names its models. A model is made of **parts** - simple shapes (box, wedge,
cylinder, cone, sphere, ring) placed, sized and turned - or of a **mesh** brought in from Blender as
glTF (``clio.py GAME --import-model file.glb``, see engine/gltf.py), or both. Model space: x to the
right, y forward (the way the model faces), z up; one unit is a cell (and the room's height); the
origin is on the floor under the model's middle.

Materials are physically based in the glTF way: a colour, ``metal`` (0..1), ``rough`` (0..1) and
``glow`` (light of its own). Each triangle is lit as a whole (flat, the low-poly look) or, with
``"smooth": true``, at its corners and blended across. A part can belong to a ``group``; a group can
``spin`` about its own middle (rotors, turbines), and a model can ``bob`` and ``spin`` as a whole.
Imported animations are kept as frames of the mesh (``frames``: clip -> list of vertex lists).
When a model is destroyed, its triangles (or its groups) fly apart as shards: ``shards()``.

Everything here is drawing: nothing in a level's rules depends on it.
"""
from __future__ import annotations

import math
import random

SHAPES = ("box", "wedge", "cylinder", "cone", "sphere", "ring")
CLIPS = ("idle", "walk", "attack", "die")


# ---------------------------------------------------------------- shapes (unit size, centred) ----------
def _box():
    v = [(x, y, z) for z in (-0.5, 0.5) for y in (-0.5, 0.5) for x in (-0.5, 0.5)]
    f = [(0, 2, 3), (0, 3, 1), (4, 5, 7), (4, 7, 6), (0, 1, 5), (0, 5, 4), (2, 6, 7), (2, 7, 3),
         (0, 4, 6), (0, 6, 2), (1, 3, 7), (1, 7, 5)]
    return v, f


def _wedge():
    """A box whose top slopes down to the front edge (a nose, a ramp, a cockpit's glass)."""
    v = [(-0.5, -0.5, -0.5), (0.5, -0.5, -0.5), (-0.5, 0.5, -0.5), (0.5, 0.5, -0.5),
         (-0.5, -0.5, 0.5), (0.5, -0.5, 0.5)]
    f = [(0, 2, 3), (0, 3, 1), (0, 1, 5), (0, 5, 4), (2, 4, 5), (2, 5, 3), (0, 4, 2), (1, 3, 5)]
    return v, f


def _cylinder(n, tip=False):
    """Round, along z, from -0.5 to 0.5; ``tip``: a cone."""
    v, f = [], []
    for i in range(n):
        a = 2 * math.pi * i / n
        v.append((0.5 * math.cos(a), 0.5 * math.sin(a), -0.5))
        if not tip:
            v.append((0.5 * math.cos(a), 0.5 * math.sin(a), 0.5))
    bottom = len(v)
    v.append((0.0, 0.0, -0.5))
    top = len(v)
    v.append((0.0, 0.0, 0.5))
    for i in range(n):
        j = (i + 1) % n
        if tip:
            f += [(i, j, top), (bottom, j, i)]
        else:
            f += [(2 * i, 2 * j, 2 * j + 1), (2 * i, 2 * j + 1, 2 * i + 1), (bottom, 2 * j, 2 * i),
                  (top, 2 * i + 1, 2 * j + 1)]
    return v, f


def _sphere(detail):
    t = (1 + 5 ** 0.5) / 2
    v = [(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t),
         (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)]
    v = [_unit(p) for p in v]
    f = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6),
         (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11), (6, 2, 10),
         (8, 6, 7), (9, 8, 1)]
    for _ in range(max(0, min(3, detail))):
        mid, nf = {}, []

        def m(a, b):
            k = (min(a, b), max(a, b))
            if k not in mid:
                v.append(_unit([(v[a][i] + v[b][i]) / 2 for i in range(3)]))
                mid[k] = len(v) - 1
            return mid[k]
        for a, b, c in f:
            ab, bc, ca = m(a, b), m(b, c), m(c, a)
            nf += [(a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)]
        f = nf
    return [(x / 2, y / 2, z / 2) for x, y, z in v], f


def _ring(n, k, thick):
    """A torus round z: ``n`` steps round, ``k`` round the tube; the tube is ``thick`` of the ring's size."""
    r = 0.5 - thick / 2
    v, f = [], []
    for i in range(n):
        a = 2 * math.pi * i / n
        for j in range(k):
            b = 2 * math.pi * j / k
            d = r + thick / 2 * math.cos(b)
            v.append((d * math.cos(a), d * math.sin(a), thick / 2 * math.sin(b)))
    for i in range(n):
        for j in range(k):
            a, b = i * k + j, ((i + 1) % n) * k + j
            c, d = ((i + 1) % n) * k + (j + 1) % k, i * k + (j + 1) % k
            f += [(a, b, c), (a, c, d)]
    zs = [p[2] for p in v]
    span = (max(zs) - min(zs)) or 1.0                     # stretched to a height of 1, as every shape is
    return [(x, y, z / span) for x, y, z in v], f


def _unit(p):
    n = math.sqrt(sum(c * c for c in p)) or 1.0
    return tuple(c / n for c in p)


def shape(part):
    """A part's triangles in model space: ``(vertices, faces)``."""
    kind = part.get("shape", "box")
    sides = int(part.get("sides", 8))
    if kind == "wedge":
        v, f = _wedge()
    elif kind == "cylinder":
        v, f = _cylinder(max(3, sides))
    elif kind == "cone":
        v, f = _cylinder(max(3, sides), tip=True)
    elif kind == "sphere":
        v, f = _sphere(int(part.get("detail", 1)))
    elif kind == "ring":
        v, f = _ring(max(3, sides), max(3, int(part.get("tube", 6))), float(part.get("thick", 0.3)))
    else:
        v, f = _box()
    axis = part.get("axis", "z")                          # round things lie along this axis
    if kind in ("cylinder", "cone", "ring") and axis in ("x", "y"):
        v = [(z, x, y) if axis == "x" else (x, z, y) for x, y, z in v]
        if axis == "y":                                   # a swap of two axes turns them inside out (x is a turn)
            f = [(a, c, b) for a, b, c in f]
    sx, sy, sz = (list(part.get("size", [1, 1, 1])) + [1, 1, 1])[:3]
    v = [(x * sx, y * sy, z * sz) for x, y, z in v]
    yaw, pitch, roll = [math.radians(float(a)) for a in (list(part.get("turn", [0, 0, 0])) + [0, 0, 0])[:3]]
    if yaw or pitch or roll:
        v = [_turn(p, yaw, pitch, roll) for p in v]
    ax, ay, az = (list(part.get("at", [0, 0, 0])) + [0, 0, 0])[:3]
    return [(x + ax, y + ay, z + az) for x, y, z in v], f


def _turn(p, yaw, pitch, roll):
    x, y, z = p
    if roll:                                              # about y (forward)
        c, s = math.cos(roll), math.sin(roll)
        x, z = x * c - z * s, x * s + z * c
    if pitch:                                             # about x (right): the nose up
        c, s = math.cos(pitch), math.sin(pitch)
        y, z = y * c - z * s, y * s + z * c
    if yaw:                                               # about z (up): to the left
        c, s = math.cos(yaw), math.sin(yaw)
        x, y = x * c - y * s, x * s + y * c
    return x, y, z


def colour(text, default=(0.32, 0.32, 0.32)):
    """``"#rrggbb"`` or ``[r, g, b]`` (0..255), as picked on a screen (sRGB), to the linear 0..1 light is
    worked out in."""
    if isinstance(text, str) and text.startswith("#") and len(text) == 7:
        try:
            return tuple(_linear(int(text[i:i + 2], 16) / 255.0) for i in (1, 3, 5))
        except ValueError:
            return default
    if isinstance(text, (list, tuple)) and len(text) >= 3:
        return tuple(_linear(max(0.0, min(1.0, float(c) / 255.0))) for c in text[:3])
    return default


def _linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


# ---------------------------------------------------------------- the model ------------------------------
class Material:
    __slots__ = ("name", "rgb", "metal", "rough", "glow")

    def __init__(self, name, spec):
        spec = spec if isinstance(spec, dict) else {}
        self.name = name
        self.rgb = colour(spec.get("color", spec.get("colour")))
        self.metal = max(0.0, min(1.0, float(spec.get("metal", 0.0))))
        self.rough = max(0.04, min(1.0, float(spec.get("rough", 0.6))))
        self.glow = max(0.0, float(spec.get("glow", 0.0)))


class Model:
    def __init__(self, name, spec):
        self.name = name
        self.spec = spec
        mats = spec.get("materials") or {}
        self.materials = [Material(k, v) for k, v in mats.items()] or [Material("plain", {})]
        index = {m.name: i for i, m in enumerate(self.materials)}
        self.verts, self.faces = [], []                   # faces: (a, b, c, material, colour or None, group)
        self.groups = ["body"]
        self.group_spin = {}
        for part in spec.get("parts") or []:
            if not isinstance(part, dict):
                continue
            g = part.get("group", "body")
            if g not in self.groups:
                self.groups.append(g)
            v, f = shape(part)
            o = len(self.verts)
            self.verts += v
            mi = index.get(part.get("material"), 0)
            tint = colour(part["color"]) if part.get("color") else None
            self.faces += [(a + o, b + o, c + o, mi, tint, self.groups.index(g)) for a, b, c in f]
        mesh = spec.get("mesh") or {}
        if mesh.get("v"):
            o = len(self.verts)
            self.verts += [tuple(float(c) for c in p[:3]) for p in mesh["v"]]
            for mname, tris in (mesh.get("faces") or {}).items():
                mi = index.get(mname, 0)
                for t in tris:
                    self.faces.append((t[0] + o, t[1] + o, t[2] + o, mi, colour(t[3]) if len(t) > 3 else None, 0))
        for g, how in (spec.get("spin") or {}).items():   # groups that turn: {"fans": {"axis": "z", "speed": 360}}
            if g in self.groups and isinstance(how, dict):
                self.group_spin[self.groups.index(g)] = (how.get("axis", "z"), float(how.get("speed", 180)))
        self.scale = float(spec.get("scale", 1.0))
        self.smooth = bool(spec.get("smooth"))
        self.bob = spec.get("bob")                        # [height, beats a bob takes]
        self.turning = float(spec.get("turning", 0.0))     # degrees a beat, the whole model (a pickup)
        self.frames = {k: v for k, v in (spec.get("frames") or {}).items() if isinstance(v, list) and v}
        self.fps = float(spec.get("fps", 8.0))            # frames a beat
        self._pivots = self._centres()
        zs = [p[2] for p in self.verts] or [0.0]
        self.height = (max(zs) or 0.5) * self.scale
        self.radius = max([math.hypot(p[0], p[1]) for p in self.verts] or [0.5]) * self.scale

    def _centres(self):
        acc = {}
        for a, b, c, _m, _t, g in self.faces:
            for i in (a, b, c):
                s = acc.setdefault(g, [0.0, 0.0, 0.0, 0])
                p = self.verts[i]
                s[0] += p[0]
                s[1] += p[1]
                s[2] += p[2]
                s[3] += 1
        return {g: (s[0] / s[3], s[1] / s[3], s[2] / s[3]) for g, s in acc.items() if s[3]}

    def pose(self, clip="idle", t=0.0):
        """The vertices at time ``t`` (beats) playing ``clip``: frames if the model has them, turning groups,
        the whole bobbing and turning."""
        frames = self.frames.get(clip) or self.frames.get("idle")
        if frames:
            k = int(t * self.fps) % len(frames)
            flat = frames[k]
            verts = [(flat[i], flat[i + 1], flat[i + 2]) for i in range(0, len(flat) - 2, 3)]
            if len(verts) < len(self.verts):
                verts += self.verts[len(verts):]
        else:
            verts = self.verts
        if self.group_spin:
            verts = list(verts)
            moved = {}
            for a, b, c, _m, _t, g in self.faces:
                if g in self.group_spin:
                    for i in (a, b, c):
                        moved[i] = g
            for i, g in moved.items():
                axis, speed = self.group_spin[g]
                cx, cy, cz = self._pivots.get(g, (0, 0, 0))
                ang = math.radians(speed * t)
                x, y, z = verts[i][0] - cx, verts[i][1] - cy, verts[i][2] - cz
                c, s = math.cos(ang), math.sin(ang)
                if axis == "x":
                    y, z = y * c - z * s, y * s + z * c
                elif axis == "y":
                    x, z = x * c - z * s, x * s + z * c
                else:
                    x, y = x * c - y * s, x * s + y * c
                verts[i] = (x + cx, y + cy, z + cz)
        lift = 0.0
        if isinstance(self.bob, (list, tuple)) and len(self.bob) == 2 and self.bob[1]:
            lift = float(self.bob[0]) * math.sin(2 * math.pi * t / float(self.bob[1]))
        sc = self.scale
        if sc != 1.0 or lift:
            verts = [(x * sc, y * sc, z * sc + lift) for x, y, z in verts]
        return verts


def load(table):
    """``models.json``'s table: name -> Model (the ones that do not build are left out)."""
    out = {}
    for name, spec in (table or {}).items():
        if isinstance(spec, dict):
            try:
                out[name] = Model(name, spec)
            except (TypeError, ValueError, IndexError, KeyError):
                pass
    return out


def problems(table, where="models.json"):
    """What is wrong with a table of models, as sentences (for --check)."""
    out = []
    for name, spec in (table or {}).items():
        if not isinstance(spec, dict):
            out.append("%s: model '%s' should be an object" % (where, name))
            continue
        mats = spec.get("materials") or {}
        for i, part in enumerate(spec.get("parts") or []):
            if not isinstance(part, dict):
                out.append("%s: model '%s' part %d should be an object" % (where, name, i + 1))
                continue
            if part.get("shape", "box") not in SHAPES:
                out.append("%s: model '%s' part %d: shape '%s' is not one of %s"
                           % (where, name, i + 1, part.get("shape"), ", ".join(SHAPES)))
            if part.get("material") and part["material"] not in mats:
                out.append("%s: model '%s' part %d: no material '%s'" % (where, name, i + 1, part["material"]))
            for key in ("size", "at", "turn"):
                val = part.get(key)
                if val is not None and (not isinstance(val, list) or len(val) != 3
                                        or not all(isinstance(c, (int, float)) for c in val)):
                    out.append("%s: model '%s' part %d: %s should be three numbers" % (where, name, i + 1, key))
        mesh = spec.get("mesh") or {}
        n = len(mesh.get("v") or [])
        for mname, tris in (mesh.get("faces") or {}).items():
            if mname not in mats:
                out.append("%s: model '%s': mesh faces use material '%s', which it has not" % (where, name, mname))
            if any(not isinstance(t, list) or len(t) < 3 or any(not isinstance(i, int) or not 0 <= i < n for i in t[:3])
                   for t in tris or []):
                out.append("%s: model '%s': a face of '%s' names a corner the mesh has not" % (where, name, mname))
        if not spec.get("parts") and not n:
            out.append("%s: model '%s' has neither parts nor a mesh" % (where, name))
        try:
            Model(name, spec)
        except (TypeError, ValueError, IndexError, KeyError) as e:
            out.append("%s: model '%s' does not build: %s" % (where, name, e))
    return out


# ---------------------------------------------------------------- light ------------------------------
def pbr(mat, rgb, n, light, view):
    """A triangle's colour (0..255) under one light and a two-colour surround (Cook-Torrance: GGX,
    Smith-Schlick, Fresnel-Schlick; Reinhard)."""
    l, v = light, view
    h = (l[0] + v[0], l[1] + v[1], l[2] + v[2])
    hn = math.sqrt(h[0] * h[0] + h[1] * h[1] + h[2] * h[2]) or 1.0
    ndl = max(0.0, n[0] * l[0] + n[1] * l[1] + n[2] * l[2])
    ndv = max(1e-3, n[0] * v[0] + n[1] * v[1] + n[2] * v[2])
    ndh = max(0.0, (n[0] * h[0] + n[1] * h[1] + n[2] * h[2]) / hn)
    vdh = max(0.0, (v[0] * h[0] + v[1] * h[1] + v[2] * h[2]) / hn)
    rough, metal = mat.rough, mat.metal
    a2 = (rough * rough) ** 2
    d = a2 / (math.pi * (ndh * ndh * (a2 - 1) + 1) ** 2)
    k = (rough + 1) ** 2 / 8
    g = (ndl / (ndl * (1 - k) + k)) * (ndv / (ndv * (1 - k) + k))
    up = 0.5 + 0.5 * n[2]
    rx_, ry_, rz = 2 * ndv * n[0] - v[0], 2 * ndv * n[1] - v[1], 2 * ndv * n[2] - v[2]   # where a mirror looks
    lobe = max(0.0, rx_ * l[0] + ry_ * l[1] + rz * l[2])  # the light's side of the room is the bright one
    surround = 0.15 + 1.0 * lobe * lobe + 0.2 * max(0.0, rz)
    fres = (1 - ndv) ** 5
    out = []
    for i in range(3):
        alb = rgb[i]
        f0 = 0.04 * (1 - metal) + alb * metal
        fr = f0 + (1 - f0) * (1 - vdh) ** 5
        spec = d * g * fr / (4 * ndl * ndv + 1e-4)
        c = ((1 - fr) * (1 - metal) * alb / math.pi + spec) * ndl * 6.0
        c += alb * (0.08 + 0.16 * up) * (1 - 0.5 * metal)
        env = surround * (1.0, 0.97, 0.9)[i]
        c += env * (f0 + (1 - f0) * fres * 0.5) * (1 - 0.6 * rough)
        c = c / (1 + c)
        s = _srgb(c)
        if mat.glow:                                      # light of its own: towards its colour, not to white
            g = min(1.0, mat.glow / 2.5)
            s = s * (1 - g) + _srgb(alb) * g
        out.append(int(255 * s))
    return out


def _srgb(c):
    return 1.055 * c ** (1 / 2.4) - 0.055 if c > 0.0031308 else 12.92 * c


# ---------------------------------------------------------------- shards ------------------------------
def shards(model, verts, k, seed, by_group=False):
    """The model blown apart, ``k`` (0..1) of the way: its triangles (or its groups) thrown out from the
    middle and up, turning and falling to the floor. Returns ``[(triangle verts, face)]``."""
    rng = random.Random(seed)
    cx = sum(p[0] for p in verts) / max(1, len(verts))
    cy = sum(p[1] for p in verts) / max(1, len(verts))
    cz = sum(p[2] for p in verts) / max(1, len(verts))
    pieces = {}
    for f in model.faces:
        pieces.setdefault(f[5] if by_group else id(f), []).append(f)
    out = []
    t = k * 1.6
    for key in sorted(pieces, key=str):
        faces = pieces[key]
        pts = [verts[i] for f in faces for i in f[:3]]
        mx = sum(p[0] for p in pts) / len(pts)
        my = sum(p[1] for p in pts) / len(pts)
        mz = sum(p[2] for p in pts) / len(pts)
        dx, dy = mx - cx + rng.uniform(-0.2, 0.2), my - cy + rng.uniform(-0.2, 0.2)
        dn = math.hypot(dx, dy) or 1.0
        speed = rng.uniform(0.6, 1.4)
        vx, vy, vz = dx / dn * speed, dy / dn * speed, rng.uniform(0.6, 1.8) + (mz - cz)
        spin = rng.uniform(-6, 6)
        ox, oy = mx + vx * t, my + vy * t
        oz = max(0.02, mz + vz * t - 2.2 * t * t)
        c, s = math.cos(spin * t), math.sin(spin * t)
        shrink = max(0.0, 1.0 - max(0.0, k - 0.6) / 0.4)
        for f in faces:
            tri = []
            for i in f[:3]:
                x, y, z = verts[i][0] - mx, verts[i][1] - my, verts[i][2] - mz
                y, z = y * c - z * s, y * s + z * c
                tri.append((ox + x * shrink, oy + y * shrink, max(0.0, oz + z * shrink)))
            out.append((tri, f))
    return out


# ---------------------------------------------------------------- drawing ------------------------------
def raster(px, zbuf, W, H, pts, cols, depth_of=None):
    """Fill a triangle: ``pts`` three (x, y, depth) on the screen, ``cols`` one colour or three (blended).
    ``zbuf``: {pixel: depth} - nearer wins."""
    (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = pts
    smooth = isinstance(cols[0], (list, tuple))
    if smooth:
        order = sorted(range(3), key=lambda i: pts[i][1])
        (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = [pts[i] for i in order]
        c0, c1, c2 = [cols[i] for i in order]
    else:
        (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = sorted(pts, key=lambda p: p[1])
    if y2 - y0 < 1e-6:
        return
    ys, ye = max(0, int(math.ceil(y0 - 0.5))), min(H - 1, int(math.floor(y2 - 0.5)))
    for y in range(ys, ye + 1):
        yc = y + 0.5
        k2 = (yc - y0) / (y2 - y0)
        xa, za = x0 + (x2 - x0) * k2, z0 + (z2 - z0) * k2
        if yc < y1:
            if y1 - y0 < 1e-6:
                continue
            k1 = (yc - y0) / (y1 - y0)
            xb, zb = x0 + (x1 - x0) * k1, z0 + (z1 - z0) * k1
            if smooth:
                ca = [c0[i] + (c2[i] - c0[i]) * k2 for i in range(3)]
                cb = [c0[i] + (c1[i] - c0[i]) * k1 for i in range(3)]
        else:
            if y2 - y1 < 1e-6:
                continue
            k1 = (yc - y1) / (y2 - y1)
            xb, zb = x1 + (x2 - x1) * k1, z1 + (z2 - z1) * k1
            if smooth:
                ca = [c0[i] + (c2[i] - c0[i]) * k2 for i in range(3)]
                cb = [c1[i] + (c2[i] - c1[i]) * k1 for i in range(3)]
        if xa > xb:
            xa, xb, za, zb = xb, xa, zb, za
            if smooth:
                ca, cb = cb, ca
        xs, xe = max(0, int(math.ceil(xa - 0.5))), min(W - 1, int(math.floor(xb - 0.5)))
        if xe < xs:
            continue
        span = (xb - xa) or 1.0
        row = px[y]
        base = y * W
        flat = None if smooth else cols
        for x in range(xs, xe + 1):
            u = (x + 0.5 - xa) / span
            d = za + (zb - za) * u
            key = base + x
            if d < zbuf.get(key, 1e9):
                zbuf[key] = d
                if smooth:
                    row[x] = (int(ca[0] + (cb[0] - ca[0]) * u), int(ca[1] + (cb[1] - ca[1]) * u),
                              int(ca[2] + (cb[2] - ca[2]) * u))
                else:
                    row[x] = flat
