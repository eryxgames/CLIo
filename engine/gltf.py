"""glTF 2.0 (``.glb`` or ``.gltf``, as Blender exports it) into a CLIo model: ``clio.py GAME --import-model FILE``.

What comes in: the meshes of the default scene with their nodes' placing; materials in glTF's own PBR
(base colour, metallic, roughness, emission) - a base colour texture (PNG) or vertex colours become a
colour per triangle; and the animations, one clip each, named as in Blender (``idle``, ``walk``,
``attack``, ``die`` are the ones a level plays): nodes that stay stiff as tracks (a few keys for each
node, which becomes a named part of the mesh), a skin on bones as frames of the mesh, packed. Not
taken: morph targets, sparse accessors, JPEG textures (say so, and are left out).

glTF's axes (+Y up, +Z forward, -X right) become CLIo's (x right, y forward, z up); ``scale`` turns its
metres into cells (a cell is the room's height: 0.4 makes a 2.5 m room one cell).
"""
from __future__ import annotations

import base64
import json
import math
import os
import struct

COMPONENTS = {5120: ("b", 1), 5121: ("B", 1), 5122: ("h", 2), 5123: ("H", 2), 5125: ("I", 4), 5126: ("f", 4)}
WIDTH = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
BEAT = 0.5                    # seconds of an animation that make a beat


class GltfError(ValueError):
    pass


# ---------------------------------------------------------------- reading ------------------------------
def read(path):
    """``(document, buffers, folder)``."""
    with open(path, "rb") as f:
        data = f.read()
    folder = os.path.dirname(os.path.abspath(path))
    if data[:4] == b"glTF":
        _magic, version, _length = struct.unpack_from("<4sII", data, 0)
        if version != 2:
            raise GltfError("glTF version %d: only 2 is read" % version)
        at, doc, binary = 12, None, None
        while at + 8 <= len(data):
            n, kind = struct.unpack_from("<II", data, at)
            chunk = data[at + 8:at + 8 + n]
            if kind == 0x4E4F534A:
                doc = json.loads(chunk.decode("utf-8"))
            elif kind == 0x004E4942:
                binary = chunk
            at += 8 + n
        if doc is None:
            raise GltfError("no JSON in the .glb")
    else:
        try:
            doc = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as e:
            raise GltfError("not a glTF file: %s" % e)
        binary = None
    if not str((doc.get("asset") or {}).get("version", "2")).startswith("2"):
        raise GltfError("glTF version %s: only 2.0 is read" % (doc.get("asset") or {}).get("version"))
    buffers = []
    for i, b in enumerate(doc.get("buffers") or []):
        uri = b.get("uri")
        if uri is None:
            if binary is None:
                raise GltfError("buffer %d has no data" % i)
            buffers.append(binary)
        elif uri.startswith("data:"):
            buffers.append(base64.b64decode(uri.split(",", 1)[1]))
        else:
            with open(os.path.join(folder, uri), "rb") as f:
                buffers.append(f.read())
    return doc, buffers, folder


def accessor(doc, buffers, i):
    """An accessor's values: a list of numbers (SCALAR) or of tuples."""
    acc = doc["accessors"][i]
    if acc.get("sparse"):
        raise GltfError("sparse accessors are not read (accessor %d)" % i)
    fmt, size = COMPONENTS[acc["componentType"]]
    width = WIDTH[acc["type"]]
    count = acc["count"]
    if "bufferView" not in acc:
        return [0.0] * count if width == 1 else [(0.0,) * width] * count
    view = doc["bufferViews"][acc["bufferView"]]
    data = buffers[view["buffer"]]
    start = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    stride = view.get("byteStride") or size * width
    out = []
    one = struct.Struct("<" + fmt * width)
    for k in range(count):
        vals = one.unpack_from(data, start + k * stride)
        if acc.get("normalized"):
            top = {"b": 127.0, "B": 255.0, "h": 32767.0, "H": 65535.0, "I": 4294967295.0}.get(fmt)
            if top:
                vals = tuple(max(-1.0, v / top) for v in vals)
        out.append(vals[0] if width == 1 else vals)
    return out


# ---------------------------------------------------------------- matrices (column-major, as glTF) -----------
def ident():
    return [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0]


def mul(a, b):
    out = [0.0] * 16
    for c in range(4):
        for r in range(4):
            out[c * 4 + r] = sum(a[k * 4 + r] * b[c * 4 + k] for k in range(4))
    return out


def trs(t=(0, 0, 0), r=(0, 0, 0, 1), s=(1, 1, 1)):
    x, y, z, w = r
    m = [1 - 2 * (y * y + z * z), 2 * (x * y + z * w), 2 * (x * z - y * w), 0,
         2 * (x * y - z * w), 1 - 2 * (x * x + z * z), 2 * (y * z + x * w), 0,
         2 * (x * z + y * w), 2 * (y * z - x * w), 1 - 2 * (x * x + y * y), 0,
         t[0], t[1], t[2], 1]
    for c in range(3):
        for r_ in range(3):
            m[c * 4 + r_] *= s[c]
    return m


def apply(m, p):
    x, y, z = p
    return (m[0] * x + m[4] * y + m[8] * z + m[12], m[1] * x + m[5] * y + m[9] * z + m[13],
            m[2] * x + m[6] * y + m[10] * z + m[14])


def slerp(a, b, k):
    d = sum(x * y for x, y in zip(a, b))
    if d < 0:
        b, d = [-x for x in b], -d
    if d > 0.9995:
        q = [x + (y - x) * k for x, y in zip(a, b)]
    else:
        th = math.acos(d)
        s = math.sin(th)
        q = [(math.sin((1 - k) * th) * x + math.sin(k * th) * y) / s for x, y in zip(a, b)]
    n = math.sqrt(sum(x * x for x in q)) or 1.0
    return [x / n for x in q]


# ---------------------------------------------------------------- the scene ------------------------------
class Scene:
    def __init__(self, doc, buffers, folder):
        self.doc, self.buffers, self.folder = doc, buffers, folder
        self.nodes = doc.get("nodes") or []
        self.parent = {}
        for i, n in enumerate(self.nodes):
            for c in n.get("children") or []:
                self.parent[c] = i
        scenes = doc.get("scenes") or [{"nodes": [i for i in range(len(self.nodes)) if i not in self.parent]}]
        self.roots = scenes[doc.get("scene", 0)].get("nodes") or []
        self.notes = []

    def local(self, i, pose=None):
        n = self.nodes[i]
        if pose and i in pose:
            t, r, s = pose[i]
            return trs(t, r, s)
        if "matrix" in n:
            return [float(x) for x in n["matrix"]]
        return trs(n.get("translation", (0, 0, 0)), n.get("rotation", (0, 0, 0, 1)), n.get("scale", (1, 1, 1)))

    def worlds(self, pose=None):
        out = {}

        def walk(i, m):
            w = mul(m, self.local(i, pose))
            out[i] = w
            for c in self.nodes[i].get("children") or []:
                walk(c, w)
        for r in self.roots:
            walk(r, ident())
        return out

    def base_pose(self, i):
        n = self.nodes[i]
        return [list(n.get("translation", (0, 0, 0))), list(n.get("rotation", (0, 0, 0, 1))),
                list(n.get("scale", (1, 1, 1)))]

    def sample(self, anim, time):
        """Each animated node's (translation, rotation, scale) at ``time`` seconds."""
        pose = {}
        for ch in anim.get("channels") or []:
            tgt = ch.get("target") or {}
            i, path = tgt.get("node"), tgt.get("path")
            if i is None or path not in ("translation", "rotation", "scale"):
                if path == "weights":
                    self.notes.append("morph targets are not taken (animation '%s')" % anim.get("name", "?"))
                continue
            smp = anim["samplers"][ch["sampler"]]
            times = accessor(self.doc, self.buffers, smp["input"])
            vals = accessor(self.doc, self.buffers, smp["output"])
            cubic = smp.get("interpolation") == "CUBICSPLINE"
            if cubic:                                    # in-tangent, value, out-tangent: the values are the middle ones
                vals = vals[1::3]
            if i not in pose:
                pose[i] = self.base_pose(i)
            k = 0
            while k + 1 < len(times) and times[k + 1] <= time:
                k += 1
            if time <= times[0] or k + 1 >= len(times) or smp.get("interpolation") == "STEP":
                v = vals[0] if time <= times[0] else vals[k]
            else:
                u = (time - times[k]) / ((times[k + 1] - times[k]) or 1.0)
                v = (slerp(vals[k], vals[k + 1], u) if path == "rotation"
                     else [a + (b - a) * u for a, b in zip(vals[k], vals[k + 1])])
            pose[i][{"translation": 0, "rotation": 1, "scale": 2}[path]] = list(v)
        return pose


def _clio(p, scale):
    """glTF (+Y up, +Z forward, -X right) -> CLIo (x right, y forward, z up)."""
    return (-p[0] * scale, p[2] * scale, p[1] * scale)


def _hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(c * 255)))) for c in rgb)


def _srgb(c):
    return 1.055 * c ** (1 / 2.4) - 0.055 if c > 0.0031308 else 12.92 * c


def _name(text, taken):
    base = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in (text or "material").lower()) or "material"
    name, n = base, 2
    while name in taken:
        name, n = "%s_%d" % (base, n), n + 1
    taken.add(name)
    return name


def inverse(m):
    """The inverse of a matrix that places, turns and sizes (no perspective); None if it flattens."""
    a, b, c, d, e, f, g, h, i = m[0], m[4], m[8], m[1], m[5], m[9], m[2], m[6], m[10]
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    if abs(det) < 1e-12:
        return None
    r = [(e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det,
         (f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det,
         (d * h - e * g) / det, (b * g - a * h) / det, (a * e - b * d) / det]
    tx, ty, tz = m[12], m[13], m[14]
    return [r[0], r[3], r[6], 0, r[1], r[4], r[7], 0, r[2], r[5], r[8], 0,
            -(r[0] * tx + r[1] * ty + r[2] * tz), -(r[3] * tx + r[4] * ty + r[5] * tz),
            -(r[6] * tx + r[7] * ty + r[8] * tz), 1]


def _key(m, scale):
    """A matrix (glTF's axes) as a key of a track on CLIo's: ``(move, turn as x y z w, size)``; None if it
    shears (a size that is not along the part's own axes cannot be said in those three)."""
    # CLIo's axes: x = -X, y = Z, z = Y. The matrix there is C m C^-1; C is its own kind of turn.
    def el(r, c):                                         # row r, column c of the 3x3, on CLIo's axes
        sign = (-1.0, 1.0, 1.0)
        src = (0, 2, 1)
        return sign[r] * sign[c] * m[src[c] * 4 + src[r]]
    cols = [[el(r, c) for r in range(3)] for c in range(3)]
    size = [math.sqrt(sum(v * v for v in col)) for col in cols]
    if min(size) < 1e-9:
        return None
    u = [[v / size[c] for v in cols[c]] for c in range(3)]
    for a, b in ((0, 1), (0, 2), (1, 2)):
        if abs(sum(x * y for x, y in zip(u[a], u[b]))) > 1e-3:
            return None
    det = (u[0][0] * (u[1][1] * u[2][2] - u[1][2] * u[2][1]) - u[1][0] * (u[0][1] * u[2][2] - u[0][2] * u[2][1])
           + u[2][0] * (u[0][1] * u[1][2] - u[0][2] * u[1][1]))
    if det < 0:                                           # a mirror: one size is the other way
        size[0], u[0] = -size[0], [-v for v in u[0]]
    m00, m11, m22 = u[0][0], u[1][1], u[2][2]             # u[c][r]: column c, row r
    tr = m00 + m11 + m22
    if tr > 0:
        k = math.sqrt(tr + 1.0) * 2
        q = [(u[1][2] - u[2][1]) / k, (u[2][0] - u[0][2]) / k, (u[0][1] - u[1][0]) / k, 0.25 * k]
    elif m00 > m11 and m00 > m22:
        k = math.sqrt(1.0 + m00 - m11 - m22) * 2
        q = [0.25 * k, (u[1][0] + u[0][1]) / k, (u[2][0] + u[0][2]) / k, (u[1][2] - u[2][1]) / k]
    elif m11 > m22:
        k = math.sqrt(1.0 + m11 - m00 - m22) * 2
        q = [(u[1][0] + u[0][1]) / k, 0.25 * k, (u[2][1] + u[1][2]) / k, (u[2][0] - u[0][2]) / k]
    else:
        k = math.sqrt(1.0 + m22 - m00 - m11) * 2
        q = [(u[2][0] + u[0][2]) / k, (u[2][1] + u[1][2]) / k, 0.25 * k, (u[0][1] - u[1][0]) / k]
    move = _clio((m[12], m[13], m[14]), scale)
    return list(move), q, size


def _thin(times, rows, close):
    """Keys left out where going evenly between their neighbours says the same (within ``close``)."""
    keep = [0]
    while keep[-1] < len(times) - 1:
        a = keep[-1]
        b = a + 1
        while b + 1 < len(times):
            ok = True
            for i in range(a + 1, b + 1):
                k = (times[i] - times[a]) / ((times[b + 1] - times[a]) or 1.0)
                if not close(rows[a], rows[b + 1], k, rows[i]):
                    ok = False
                    break
            if not ok:
                break
            b += 1
        keep.append(b)
    return keep


def _tracks(sc, anim, length, nodes, rest, scale, per_beat=8, most=96):
    """An animation of parts that stay stiff as tracks: ``{"length", "parts": {name: {"t", "move", "turn",
    "size", "about"}}}`` - for each mesh node what it is moved, turned and sized by since it was at rest.
    None when a part shears on its way (then only frames can say it)."""
    count = max(2, min(most, int(round(length / BEAT * per_beat)) + 1))
    times = [length * f / (count - 1) for f in range(count)]
    keys = {name: [] for name in nodes}
    for time in times:
        worlds = sc.worlds(sc.sample(anim, time))
        for name, ni in nodes.items():
            back = inverse(rest[ni])
            key = _key(mul(worlds[ni], back), scale) if back else None
            if key is None:
                return None
            keys[name].append(key)
    beats = [round(t / BEAT, 4) for t in times]
    parts = {}
    for name, rows in keys.items():
        for a, b in zip(rows, rows[1:]):                  # the same turn can be said two ways: the nearer one each time
            if sum(x * y for x, y in zip(a[1], b[1])) < 0:
                b[1][:] = [-x for x in b[1]]
        still = all(max(abs(c) for c in r[0]) < 1e-5 and abs(abs(r[1][3]) - 1.0) < 1e-7
                    and max(abs(c - 1.0) for c in r[2]) < 1e-5 for r in rows)
        if still:
            continue

        def close(a, b, k, c):
            move = max(abs(a[0][i] + (b[0][i] - a[0][i]) * k - c[0][i]) for i in range(3)) < 2e-3
            size = max(abs(a[2][i] + (b[2][i] - a[2][i]) * k - c[2][i]) for i in range(3)) < 2e-3
            q = slerp(a[1], b[1], k)
            return move and size and abs(sum(x * y for x, y in zip(q, c[1]))) > 1.0 - 2e-6
        kept = _thin(beats, rows, close)
        part = {"t": [beats[i] for i in kept], "about": [0, 0, 0]}
        if any(max(abs(c) for c in r[0]) >= 1e-5 for r in rows):
            part["move"] = [[round(c, 4) for c in rows[i][0]] for i in kept]
        if any(abs(abs(r[1][3]) - 1.0) >= 1e-7 for r in rows):
            part["turn"] = [[round(c, 5) for c in rows[i][1]] for i in kept]
        if any(max(abs(c - 1.0) for c in r[2]) >= 1e-5 for r in rows):
            part["size"] = [[round(c, 4) for c in rows[i][2]] for i in kept]
        parts[name] = part
    return {"length": round(length / BEAT, 4), "parts": parts}


def to_model(path, scale=1.0, fps=4, max_frames=48, tracks=True, packed=True):
    """A model for models.json, and notes on what was left out: ``(spec, notes)``.

    An animation of parts that stay stiff (nodes moved, turned, sized) is kept as ``tracks`` - a few keys
    for each part, played at any moment; one that bends a skin, or shears a part, as ``frames`` of the
    mesh (``fps`` a beat, ``max_frames`` at most), ``packed`` unless asked otherwise. ``tracks=False``:
    frames for all of them."""
    doc, buffers, folder = read(path)
    sc = Scene(doc, buffers, folder)
    notes = sc.notes
    # materials
    taken, mats, mat_names, textures = set(), {}, [], {}
    for i, m in enumerate(doc.get("materials") or []):
        pbr = m.get("pbrMetallicRoughness") or {}
        base = list(pbr.get("baseColorFactor", (1, 1, 1, 1)))[:3]
        name = _name(m.get("name") or "material_%d" % i, taken)
        emit = max(list(m.get("emissiveFactor", (0, 0, 0))) or [0])
        strength = ((m.get("extensions") or {}).get("KHR_materials_emissive_strength") or {}).get("emissiveStrength", 1.0)
        spec = {"color": _hex([_srgb(c) for c in base]), "metal": round(float(pbr.get("metallicFactor", 1.0)), 3),
                "rough": round(float(pbr.get("roughnessFactor", 1.0)), 3)}
        if emit * strength > 0.01:
            spec["glow"] = round(min(4.0, 2.5 * emit * strength), 2)
        mats[name] = spec
        mat_names.append(name)
        tex = (pbr.get("baseColorTexture") or {}).get("index")
        if tex is not None:
            picture = _texture(doc, buffers, folder, tex, notes)
            if picture:
                textures[i] = (picture, base)
    plain = None
    # the meshes in their nodes, at rest
    worlds = sc.worlds()
    pieces = []                                          # (node, mesh primitive, skin)
    for ni, w in worlds.items():
        node = sc.nodes[ni]
        if "mesh" not in node:
            continue
        for prim in doc["meshes"][node["mesh"]].get("primitives") or []:
            if prim.get("mode", 4) != 4:
                notes.append("a primitive that is not triangles (mode %s) was left out" % prim.get("mode"))
                continue
            if prim.get("targets"):
                notes.append("morph targets are not taken")
            pieces.append((ni, prim, node.get("skin")))
    verts, keys, faces = [], {}, {}
    sources = []                                         # for frames: each kept vertex -> (node, prim no, index)
    spans, part_names = {}, {}                           # a mesh node that is no skin: its corners, and its name as a part
    for pi, (ni, prim, skin) in enumerate(pieces):
        at = prim["attributes"]
        if skin is None and ni not in spans:
            spans[ni] = [len(verts), 0]
            part_names[ni] = _name(sc.nodes[ni].get("name") or "part_%d" % (len(spans)), set(part_names.values()) | {"body"})
        pos = accessor(doc, buffers, at["POSITION"])
        idx = accessor(doc, buffers, prim["indices"]) if "indices" in prim else list(range(len(pos)))
        cols = accessor(doc, buffers, at["COLOR_0"]) if "COLOR_0" in at else None
        uvs = accessor(doc, buffers, at["TEXCOORD_0"]) if "TEXCOORD_0" in at else None
        mi = prim.get("material")
        if mi is None:
            if plain is None:
                plain = _name("plain", taken)
                mats[plain] = {"color": "#b0b0b0", "metal": 0.0, "rough": 0.6}
            mname = plain
        else:
            mname = mat_names[mi]
        local = []
        w = worlds[ni] if skin is None else _skin_matrices(sc, skin, worlds, None)
        for k, p in enumerate(pos):
            q = apply(w, p) if skin is None else _skinned(sc, at, k, p, w)
            c = _clio(q, scale)
            key = (round(c[0], 4), round(c[1], 4), round(c[2], 4), pi if skin is not None else ni)
            if key not in keys:
                keys[key] = len(verts)
                verts.append(c)
                sources.append((pi, k))
            local.append(keys[key])
        tex = textures.get(mi)
        for t in range(0, len(idx) - 2, 3):
            a, b, c = idx[t], idx[t + 1], idx[t + 2]
            tri = [local[a], local[b], local[c]]
            if len({tri[0], tri[1], tri[2]}) < 3:
                continue
            rgb = None
            if tex and uvs:
                u = sum(uvs[i][0] for i in (a, b, c)) / 3
                v = sum(uvs[i][1] for i in (a, b, c)) / 3
                rgb = _sample(tex[0], u, v, tex[1])
            if cols:
                vc = [sum((cols[i][j] if j < len(cols[i]) else 1.0) for i in (a, b, c)) / 3 for j in range(3)]
                base = rgb or [_lin(int(mats[mname]["color"][1 + 2 * j:3 + 2 * j], 16) / 255.0) for j in range(3)]
                rgb = [base[j] * vc[j] for j in range(3)]
            if rgb is not None:
                tri.append(_hex([_srgb(min(1.0, max(0.0, x))) for x in rgb]))
            faces.setdefault(mname, []).append(tri)
        if skin is None:
            spans[ni][1] = len(verts) - spans[ni][0]
    if not verts:
        raise GltfError("no triangles in %s" % os.path.basename(path))
    spec = {"source": os.path.basename(path), "materials": mats,
            "mesh": {"v": [[round(c, 4) for c in p] for p in verts], "faces": faces}}
    stiff = bool(spans) and all(skin is None for _ni, _prim, skin in pieces)
    if len(spans) > 1 or (stiff and tracks and doc.get("animations")):      # its nodes are its named parts
        spec["mesh"]["parts"] = {part_names[ni]: list(span) for ni, span in spans.items() if span[1]}
    # animations: parts that stay stiff as tracks, what bends as frames of the mesh
    clips, moving = {}, {}
    for ai, anim in enumerate(doc.get("animations") or []):
        name = _name(anim.get("name") or "clip_%d" % ai, set(clips) | set(moving))
        times = []
        for smp in anim.get("samplers") or []:
            times += accessor(doc, buffers, smp["input"])
        if not times:
            continue
        length = max(times)
        if stiff and tracks and length > 0:
            made = _tracks(sc, anim, length, {part_names[ni]: ni for ni, span in spans.items() if span[1]}, worlds, scale)
            if made is not None:
                moving[name] = made
                continue
            notes.append("animation '%s' shears a part: kept as frames" % name)
        count = max(1, min(max_frames, int(round(length / BEAT * fps))))
        frames = []
        for f in range(count):
            pose = sc.sample(anim, length * f / count)
            worlds_f = sc.worlds(pose)
            flat = []
            for (pi, k) in sources:
                ni, prim, skin = pieces[pi]
                p = accessor_cache(doc, buffers, prim["attributes"]["POSITION"])[k]
                if skin is None:
                    q = apply(worlds_f[ni], p)
                else:
                    q = _skinned(sc, prim["attributes"], k, p, _skin_matrices(sc, skin, worlds_f, pose))
                flat += [round(c, 3) for c in _clio(q, scale)]
            frames.append(flat)
        clips[name] = model_pack(frames) if packed else frames
    if clips:
        spec["frames"] = clips
        spec["fps"] = fps
    if moving:
        spec["tracks"] = moving
    spec["notes"] = sorted(set(notes))
    return spec, sorted(set(notes))


def model_pack(frames):
    from .model import pack_frames
    return pack_frames(frames)


_cache = {}


def accessor_cache(doc, buffers, i):
    key = (id(doc), i)
    if key not in _cache:
        _cache[key] = accessor(doc, buffers, i)
    return _cache[key]


def _skin_matrices(sc, si, worlds, pose):
    skin = sc.doc["skins"][si]
    inv = accessor_cache(sc.doc, sc.buffers, skin["inverseBindMatrices"]) if "inverseBindMatrices" in skin else None
    return [mul(worlds[j], list(inv[k]) if inv else ident()) for k, j in enumerate(skin["joints"])]


def _skinned(sc, attrs, k, p, joints):
    js = accessor_cache(sc.doc, sc.buffers, attrs["JOINTS_0"])[k] if "JOINTS_0" in attrs else (0, 0, 0, 0)
    ws = accessor_cache(sc.doc, sc.buffers, attrs["WEIGHTS_0"])[k] if "WEIGHTS_0" in attrs else (1, 0, 0, 0)
    total = sum(ws) or 1.0
    x = y = z = 0.0
    for j, wgt in zip(js, ws):
        if wgt:
            q = apply(joints[int(j)], p)
            x, y, z = x + q[0] * wgt / total, y + q[1] * wgt / total, z + q[2] * wgt / total
    return x, y, z


def _lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _texture(doc, buffers, folder, ti, notes):
    from .sheets import read_png, PictureError
    tex = (doc.get("textures") or [])[ti]
    img = (doc.get("images") or [])[tex.get("source", 0)]
    try:
        if "bufferView" in img:
            view = doc["bufferViews"][img["bufferView"]]
            data = buffers[view["buffer"]][view.get("byteOffset", 0):view.get("byteOffset", 0) + view["byteLength"]]
        elif str(img.get("uri", "")).startswith("data:"):
            data = base64.b64decode(img["uri"].split(",", 1)[1])
        else:
            with open(os.path.join(folder, img["uri"]), "rb") as f:
                data = f.read()
        w, h, rows = read_png(data)
        return w, h, rows
    except (PictureError, OSError, KeyError, ValueError, IndexError) as e:
        notes.append("texture %d left out (%s): only PNG textures are read - its triangles keep the material's colour"
                     % (ti, img.get("mimeType") or e))
        return None


def _sample(picture, u, v, base):
    w, h, rows = picture
    x = int((u % 1.0) * w) % w
    y = int((v % 1.0) * h) % h
    r, g, b = rows[y][x][:3]
    return [_lin(r / 255.0) * base[0], _lin(g / 255.0) * base[1], _lin(b / 255.0) * base[2]]
