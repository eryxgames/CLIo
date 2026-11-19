"""3D models in levels: shapes, models from parts and meshes, poses, shards, the renderer, --check, and glTF
coming in from Blender (the files are made here)."""
import base64
import json
import math
import os
import shutil
import struct
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine import gltf, model  # noqa: E402
from engine.data import GameData  # noqa: E402
from engine.firstperson import FX, View  # noqa: E402
from engine.level import Level  # noqa: E402
from test_levels import ROOTLESS  # noqa: E402

DRONE = {
    "materials": {"hull": {"color": "#6b717c", "metal": 0.8, "rough": 0.35},
                  "eye": {"color": "#ff3020", "glow": 3}},
    "bob": [0.05, 2],
    "parts": [{"shape": "sphere", "size": [0.5, 0.5, 0.34], "at": [0, 0, 0.55], "material": "hull"},
              {"shape": "cylinder", "axis": "y", "size": [0.15, 0.4, 0.15], "at": [-0.36, 0, 0.52], "material": "hull",
               "group": "pods"},
              {"shape": "box", "size": [0.1, 0.07, 0.07], "at": [0, 0.25, 0.56], "material": "eye"}],
    "spin": {"pods": {"axis": "y", "speed": 90}},
}


def level_with(models, rows, legend, monsters=None):
    data = GameData(ROOTLESS)
    data.models = models
    if monsters:
        data.monsters = dict(data.monsters, **monsters)
    data.levels = dict(data.levels, t={"name": "T", "map": rows, "legend": legend, "facing": "n"})
    return Level(data, "t", seed=2)


class ShapeTests(unittest.TestCase):
    def test_every_shape_is_closed_and_sized(self):
        for kind in model.SHAPES:
            v, f = model.shape({"shape": kind, "size": [2, 1, 0.5], "at": [1, 0, 0.25]})
            xs, zs = [p[0] for p in v], [p[2] for p in v]
            self.assertAlmostEqual(max(xs) - min(xs), 2, delta=0.05, msg=kind)
            self.assertAlmostEqual(max(zs) - min(zs), 0.5, delta=0.05, msg=kind)
            self.assertAlmostEqual(min(zs), 0.0, delta=0.05, msg=kind)
            edges = {}
            for a, b, c in f:                            # closed: every edge is walked once each way
                for e in ((a, b), (b, c), (c, a)):
                    edges[e] = edges.get(e, 0) + 1
            self.assertTrue(all(edges.get((b, a)) == 1 for (a, b) in edges), kind)

    def test_faces_turn_outwards(self):
        for kind in model.SHAPES:
            for axis in ("x", "y", "z"):                 # a closed mesh turned outwards has a positive volume
                v, f = model.shape({"shape": kind, "axis": axis})
                vol = sum(sum(v[a][i] * _cross((0, 0, 0), v[b], v[c])[i] for i in range(3)) for a, b, c in f) / 6
                self.assertGreater(vol, 0.05, "%s along %s" % (kind, axis))

    def test_turn_and_place(self):
        v, _f = model.shape({"shape": "box", "size": [2, 0.2, 0.2], "turn": [90, 0, 0]})
        ys = [p[1] for p in v]
        self.assertAlmostEqual(max(ys) - min(ys), 2, delta=0.01)        # a quarter turn: x became y


def _cross(a, b, c):
    u = [b[i] - a[i] for i in range(3)]
    w = [c[i] - a[i] for i in range(3)]
    return (u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0])


class ModelTests(unittest.TestCase):
    def test_parts_materials_groups_and_poses(self):
        m = model.Model("drone", DRONE)
        self.assertEqual([x.name for x in m.materials], ["hull", "eye"])
        self.assertIn("pods", m.groups)
        a, b = m.pose("idle", 0.0), m.pose("idle", 0.5)
        self.assertNotEqual(a, b)                                       # bobbing, pods turning
        self.assertEqual(len(a), len(m.verts))
        self.assertGreater(m.height, 0.6)

    def test_frames_play_in_turn(self):
        spec = dict(DRONE, frames={"walk": [[0, 0, 0] * 3, [1, 1, 1] * 3]}, fps=2, bob=None)
        m = model.Model("d", spec)
        self.assertEqual(m.pose("walk", 0.0)[0], (0.0, 0.0, 0.0))
        self.assertEqual(m.pose("walk", 0.5)[0], (1.0, 1.0, 1.0))

    def test_shards_fly_out_and_fall(self):
        m = model.Model("drone", DRONE)
        v = m.pose()
        start = model.shards(m, v, 0.0, 7)
        later = model.shards(m, v, 0.8, 7)
        self.assertEqual(len(start), len(m.faces))
        spread0 = max(abs(p[0]) for tri, _f in start for p in tri)
        spread1 = max(abs(p[0]) for tri, _f in later for p in tri)
        self.assertGreater(spread1, spread0)
        self.assertTrue(all(p[2] >= 0.0 for tri, _f in later for p in tri))
        self.assertEqual(start, model.shards(m, v, 0.0, 7))             # the same each time it is drawn

    def test_check_finds_what_is_wrong(self):
        bad = {"a": {"parts": [{"shape": "blob"}, {"material": "none"}, {"size": [1, 2]}]},
               "b": {"materials": {"m": {}}, "mesh": {"v": [[0, 0, 0]], "faces": {"m": [[0, 1, 2]], "x": []}}},
               "c": {}}
        text = " ".join(model.problems(bad))
        for want in ("shape 'blob'", "no material 'none'", "size should be three numbers", "corner the mesh has not",
                     "material 'x'", "neither parts nor a mesh"):
            self.assertIn(want, text)
        self.assertEqual(model.problems({"drone": DRONE}), [])


class DrawTests(unittest.TestCase):
    def monster(self):
        drone = dict(GameData(ROOTLESS).monsters["kworker"], model="drone", float=0.4, tag="d")
        return level_with({"drone": DRONE}, ["#######", "#.....#", "#..d..#", "#.....#", "#..@..#", "#######"],
                          {"d": {"monster": "drone"}}, {"drone": drone})

    def test_a_monster_with_a_model_is_drawn_lit_and_labelled(self):
        lv = self.monster()
        m = lv.monsters[0]
        self.assertIn("drone", lv.models)
        v = View(80, 20, "pixel")
        with_it = v.render(lv, FX(), 0)
        m.gone = True
        without = v.render(lv, FX(), 0)
        m.gone = False
        self.assertNotEqual(with_it, without)
        self.assertIn("d1", "".join(c[0] or "" for row in with_it for c in row))
        red = [c for row in with_it for c in row for col in (c[1], c[2]) if col and col[0] > 180 and col[1] < 90]
        self.assertTrue(red)                                            # its glowing eye, turned to the player

    def test_it_faces_the_way_it_moved(self):
        lv = self.monster()
        m = lv.monsters[0]
        m.heading = 0.0
        v = View(80, 20, "pixel")
        side = v.render(lv, FX(), 0)
        m.heading = math.pi / 2
        toward = v.render(lv, FX(), 0)
        self.assertNotEqual(side, toward)

    def test_destroyed_it_breaks_into_shards(self):
        lv = self.monster()
        m = lv.monsters[0]
        frames = []

        class Keep:
            def play(self, lv_, fx, dt):
                frames.extend(fx)

            def said(self, *a):
                pass
        lv.console = Keep()
        lv.damage([(m, 999)])
        dissolve = [fx.dissolve.get(m.id) for fx in frames if m.id in fx.dissolve]
        self.assertEqual(len(dissolve), 8)
        self.assertFalse(any(m.id in fx.tint for fx in frames))       # no blood
        self.assertFalse(lv.decals)                                     # and no gore left
        v = View(80, 20, "pixel")
        a = v.render(lv, FX(dissolve={m.id: 0.3}), 0)
        b = v.render(lv, FX(), 0)
        self.assertNotEqual(a, b)


# ---------------------------------------------------------------- glTF made here ------------------------------
def _pack(fmt, values):
    return b"".join(struct.pack("<" + fmt, *v) if isinstance(v, (tuple, list)) else struct.pack("<" + fmt, v)
                    for v in values)


class Builder:
    """A small glTF document with its binary data."""

    def __init__(self):
        self.doc = {"asset": {"version": "2.0"}, "buffers": [], "bufferViews": [], "accessors": [],
                    "meshes": [], "nodes": [], "scenes": [{"nodes": []}], "scene": 0, "materials": []}
        self.bin = b""

    def acc(self, values, kind, ctype=5126, fmt="f"):
        width = gltf.WIDTH[kind]
        data = _pack(fmt * width if width > 1 else fmt, values)
        while len(self.bin) % 4:
            self.bin += b"\0"
        self.doc["bufferViews"].append({"buffer": 0, "byteOffset": len(self.bin), "byteLength": len(data)})
        self.bin += data
        a = {"bufferView": len(self.doc["bufferViews"]) - 1, "componentType": ctype, "count": len(values), "type": kind}
        if kind in ("VEC3",) and ctype == 5126:
            a["min"] = [min(v[i] for v in values) for i in range(3)]
            a["max"] = [max(v[i] for v in values) for i in range(3)]
        self.doc["accessors"].append(a)
        return len(self.doc["accessors"]) - 1

    def glb(self):
        doc = dict(self.doc, buffers=[{"byteLength": len(self.bin)}])
        js = json.dumps(doc).encode()
        js += b" " * (-len(js) % 4)
        binary = self.bin + b"\0" * (-len(self.bin) % 4)
        body = struct.pack("<II", len(js), 0x4E4F534A) + js + struct.pack("<II", len(binary), 0x004E4942) + binary
        return struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body

    def gltf(self):
        uri = "data:application/octet-stream;base64," + base64.b64encode(self.bin).decode()
        return json.dumps(dict(self.doc, buffers=[{"byteLength": len(self.bin), "uri": uri}])).encode()


CUBE = [(-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1), (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)]
CUBE_TRIS = [0, 2, 1, 0, 3, 2, 4, 5, 6, 4, 6, 7, 0, 1, 5, 0, 5, 4, 2, 3, 7, 2, 7, 6, 1, 2, 6, 1, 6, 5, 0, 4, 7, 0, 7, 3]


class GltfTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)

    def write(self, name, data):
        p = os.path.join(self.dir, name)
        with open(p, "wb") as f:
            f.write(data)
        return p

    def cube(self):
        b = Builder()
        pos = b.acc(CUBE, "VEC3")
        idx = b.acc(CUBE_TRIS, "SCALAR", 5123, "H")
        b.doc["materials"].append({"name": "Hull Paint", "pbrMetallicRoughness": {
            "baseColorFactor": [0.5, 0.05, 0.02, 1], "metallicFactor": 0.2, "roughnessFactor": 0.7},
            "emissiveFactor": [0, 0, 0]})
        b.doc["meshes"].append({"primitives": [{"attributes": {"POSITION": pos}, "indices": idx, "material": 0}]})
        b.doc["nodes"].append({"mesh": 0, "translation": [0, 1, 0]})
        b.doc["scenes"][0]["nodes"].append(0)
        return b

    def test_a_cube_with_a_material_comes_in_on_clios_axes(self):
        b = self.cube()
        spec, notes = gltf.to_model(self.write("cube.glb", b.glb()), scale=0.5)
        self.assertEqual(notes, [])
        self.assertEqual(list(spec["materials"]), ["hull_paint"])
        mat = spec["materials"]["hull_paint"]
        self.assertEqual((mat["metal"], mat["rough"]), (0.2, 0.7))
        self.assertTrue(mat["color"].startswith("#b"))                  # linear 0.5 -> sRGB about 0.74
        zs = [p[2] for p in spec["mesh"]["v"]]
        self.assertEqual((min(zs), max(zs)), (0.0, 1.0))                # glTF +Y up -> z up, scaled
        self.assertEqual(len(spec["mesh"]["v"]), 8)
        self.assertEqual(sum(len(t) for t in spec["mesh"]["faces"].values()), 12)
        self.assertEqual(model.problems({"cube": spec}), [])
        m = model.Model("cube", spec)                                   # and it turns outwards still
        out = 0
        for a, bb, c, *_ in m.faces:
            n = model._unit(_cross(m.verts[a], m.verts[bb], m.verts[c]))
            mid = [(m.verts[a][i] + m.verts[bb][i] + m.verts[c][i]) / 3 - (0, 0, 0.5)[i] for i in range(3)]
            out += sum(n[i] * mid[i] for i in range(3)) > 0
        self.assertEqual(out, 12)

    def test_an_animation_becomes_frames(self):
        b = self.cube()
        times = b.acc([0.0, 1.0], "SCALAR")
        s = math.sqrt(0.5)
        rots = b.acc([(0, 0, 0, 1), (0, s, 0, s)], "VEC4")             # a quarter turn about up
        b.doc["animations"] = [{"name": "Idle", "samplers": [{"input": times, "output": rots}],
                                "channels": [{"sampler": 0, "target": {"node": 0, "path": "rotation"}}]}]
        spec, _ = gltf.to_model(self.write("spin.gltf", b.gltf()), scale=1.0, fps=4)
        frames = spec["frames"]["idle"]
        self.assertEqual(len(frames), 8)                                # 1 s = 2 beats, 4 frames a beat
        first, mid = frames[0], frames[4]
        self.assertNotEqual(first, mid)
        self.assertEqual(len(first), 3 * len(spec["mesh"]["v"]))
        m = model.Model("spin", spec)
        self.assertNotEqual(m.pose("idle", 0.0), m.pose("idle", 1.0))

    def test_a_texture_gives_each_triangle_its_colour(self):
        from engine.sheets import png
        b = Builder()
        quad = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]
        pos = b.acc(quad, "VEC3")
        uv = b.acc([(0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9)], "VEC2")
        idx = b.acc([0, 1, 2, 0, 2, 3], "SCALAR", 5123, "H")
        picture = png([[(255, 0, 0, 255), (0, 0, 255, 255)], [(255, 0, 0, 255), (0, 0, 255, 255)]])
        b.doc["images"] = [{"uri": "data:image/png;base64," + base64.b64encode(picture).decode()}]
        b.doc["textures"] = [{"source": 0}]
        b.doc["materials"].append({"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}, "metallicFactor": 0}})
        b.doc["meshes"].append({"primitives": [{"attributes": {"POSITION": pos, "TEXCOORD_0": uv}, "indices": idx,
                                                "material": 0}]})
        b.doc["nodes"].append({"mesh": 0})
        b.doc["scenes"][0]["nodes"].append(0)
        spec, notes = gltf.to_model(self.write("tex.gltf", b.gltf()))
        tris = list(spec["mesh"]["faces"].values())[0]
        self.assertEqual(sorted(t[3] for t in tris), ["#0000ff", "#ff0000"])

    def test_a_skin_bends_with_its_bones(self):
        b = Builder()
        bar = [(x, y, 0) for x in (0, 1, 2) for y in (0, 0.2)]
        pos = b.acc(bar, "VEC3")
        idx = b.acc([0, 2, 3, 0, 3, 1, 2, 4, 5, 2, 5, 3], "SCALAR", 5123, "H")
        joints = b.acc([(0, 0, 0, 0)] * 2 + [(0, 1, 0, 0)] * 2 + [(1, 0, 0, 0)] * 2, "VEC4", 5121, "B")
        weights = b.acc([(1, 0, 0, 0)] * 2 + [(0.5, 0.5, 0, 0)] * 2 + [(1, 0, 0, 0)] * 2, "VEC4")
        ibm = b.acc([(1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1),
                     (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, -1, 0, 0, 1)], "MAT4")
        b.doc["meshes"].append({"primitives": [{"attributes": {"POSITION": pos, "JOINTS_0": joints, "WEIGHTS_0": weights},
                                                "indices": idx}]})
        b.doc["nodes"] = [{"mesh": 0, "skin": 0}, {"children": [2]}, {"translation": [1, 0, 0]}]
        b.doc["skins"] = [{"joints": [1, 2], "inverseBindMatrices": ibm}]
        b.doc["scenes"][0]["nodes"] = [0, 1]
        times = b.acc([0.0, 0.5], "SCALAR")
        lift = b.acc([(1, 0, 0), (1, 1, 0)], "VEC3")                    # the second bone goes up a metre
        b.doc["animations"] = [{"name": "walk", "samplers": [{"input": times, "output": lift}],
                                "channels": [{"sampler": 0, "target": {"node": 2, "path": "translation"}}]}]
        spec, _ = gltf.to_model(self.write("skin.glb", b.glb()), fps=4)
        rest = spec["frames"]["walk"][0]
        last = spec["frames"]["walk"][-1]
        pts = lambda f: [(f[i], f[i + 1], f[i + 2]) for i in range(0, len(f), 3)]
        far = lambda f: max(p[2] for p in pts(f) if p[0] <= -1.5)      # glTF +x 2 is CLIo x -2
        near = lambda f: max(p[2] for p in pts(f) if p[0] >= -0.01)
        self.assertGreater(far(last), far(rest) + 0.5)                  # the far end rose with its bone
        self.assertAlmostEqual(near(last), near(rest), places=3)       # the near end stayed

    def test_import_model_writes_models_json_and_keeps_hand_made_keys(self):
        import importlib.util
        spec_ = importlib.util.spec_from_file_location("clio_main", os.path.join(ROOT, "clio.py"))
        clio = importlib.util.module_from_spec(spec_)
        spec_.loader.exec_module(clio)
        game = os.path.join(self.dir, "g")
        os.makedirs(game)
        with open(os.path.join(game, "models.json"), "w") as f:
            json.dump({"cube": {"turning": 30, "materials": {"x": {}}, "parts": [{"shape": "box", "material": "x"}]},
                       "other": DRONE}, f)
        path = self.write("Cube.glb", self.cube().glb())
        import io as io_mod
        from contextlib import redirect_stdout
        out = io_mod.StringIO()
        with redirect_stdout(out):
            self.assertEqual(clio.import_model(game, path), 0)
        self.assertIn("12 triangles", out.getvalue())
        with open(os.path.join(game, "models.json")) as f:
            text = f.read()
        table = json.loads(text)
        self.assertEqual(list(table), ["cube", "other"])
        self.assertEqual(table["cube"]["turning"], 30)                  # kept
        self.assertIn("mesh", table["cube"])
        self.assertIn("[0.4,", text.replace(" ", ""))                  # a vertex a line, not a number a line
        self.assertLess(text.count("\n"), 120)

    def test_not_gltf_says_so(self):
        with self.assertRaises(gltf.GltfError):
            gltf.to_model(self.write("x.gltf", b"not json"))


if __name__ == "__main__":
    unittest.main()
