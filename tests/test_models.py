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

from engine import viewer  # noqa: E402
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

    def test_frames_packed_are_a_seventh_the_size_and_the_same(self):
        frames = [[round(math.sin(i * 0.1 + f * 0.3) * 2.5 + ((i * 7 + f) % 11) * 0.0004, 3) for i in range(300)]
                  for f in range(48)]
        packed = model.pack_frames(frames)
        self.assertEqual((packed["count"], packed["size"]), (48, 300))
        self.assertLess(len(json.dumps(packed)), len(json.dumps(frames)) // 6)
        back = model.unpack_frames(packed)
        self.assertLess(max(abs(a - b) for f, g in zip(frames, back) for a, b in zip(f, g)), 0.0001)
        self.assertEqual(model.unpack_frames(json.loads(json.dumps(packed))), back)      # through a file the same
        spec = dict(DRONE, frames={"walk": [[0, 0, 0] * 3, [1, 1, 1] * 3]}, fps=2, bob=None)
        plain, small = model.Model("d", spec), model.Model("d", model.pack(spec))
        self.assertEqual(sorted(model.pack(spec)["frames"]["walk"]), ["count", "packed", "size", "step"])
        self.assertEqual(model.pack(model.pack(spec)), model.pack(spec))                 # packed already: left
        for t in (0.0, 0.5, 0.9):
            for p, q in zip(plain.pose("walk", t), small.pose("walk", t)):
                self.assertAlmostEqual(p[0], q[0], places=4)
        for wrong in ({"packed": "!!", "count": 2, "size": 9, "step": 0.1}, {"count": 2},
                      dict(packed, count=47), dict(packed, packed=packed["packed"][:40])):
            with self.assertRaises(ValueError):
                model.unpack_frames(wrong)
        bad = model.problems({"d": dict(DRONE, frames={"walk": dict(packed, count=47)})})
        self.assertEqual(len(bad), 1)
        self.assertIn("packed frames are not as long as they say", bad[0])
        with self.assertRaises(ValueError):
            model.pack_frames([[1, 2, 3], [1, 2]])

    def door(self, **more):
        return {"materials": {"m": {"color": "#888888"}},
                "parts": [{"shape": "box", "size": [0.1, 0.1, 2], "at": [0, 0, 1]},
                          {"shape": "box", "size": [1, 0.1, 2], "at": [0.5, 0, 1], "group": "door"}],
                "tracks": {"open": dict({"length": 2, "parts": {"door": {"t": [0, 2], "turn": [[0, 0, 0], [90, 0, 0]],
                                                                         "about": [0, 0, 0]}}}, **more)}}

    def test_tracks_move_a_named_part_at_any_moment(self):
        m = model.Model("door", self.door(loop=False))
        self.assertEqual((m.clips, m.beats("open"), m.moves), (["open"], 2.0, True))
        post, leaf = m.pose("open", 0.0)[:8], m.pose("open", 0.0)[8:]
        self.assertEqual(m.pose("open", 2.0)[:8], post)                 # the post has no track: it stays
        far = max(leaf, key=lambda p: p[0])
        self.assertAlmostEqual(far[0], 1.0)
        swung = max(m.pose("open", 2.0)[8:], key=lambda p: p[1])
        self.assertAlmostEqual(swung[1], 1.0, places=5)                  # a quarter turn to the left about its hinge
        self.assertAlmostEqual(swung[0], 0.05, places=5)
        half = max(m.pose("open", 1.0)[8:], key=lambda p: p[1])
        self.assertAlmostEqual(math.degrees(math.atan2(half[1], half[0])), 45.0, delta=3.5)
        self.assertEqual(m.pose("open", 9.0), m.pose("open", 2.0))      # it does not go round: it stays open
        self.assertNotEqual(m.pose("open", 0.37), m.pose("open", 0.38)) # no frames: every moment is its own
        round_ = model.Model("door", self.door())
        self.assertEqual(round_.pose("open", 2.5), round_.pose("open", 0.5))
        for yaw, pitch, roll in ((30, 0, 0), (0, 40, 0), (0, 0, 50), (20, -35, 70)):     # a turn in degrees is a part's turn
            t = model.Track({"t": [0], "turn": [[yaw, pitch, roll]]}, [0], (0, 0, 0))
            verts = [(0.3, -0.7, 0.4)]
            t.apply(verts, 0.0)
            want = model._turn((0.3, -0.7, 0.4), math.radians(yaw), math.radians(pitch), math.radians(roll))
            for a, b in zip(verts[0], want):
                self.assertAlmostEqual(a, b, places=6)
        moved = model.Track({"t": [0, 1], "move": [[0, 0, 0], [0, 0, 2]], "size": [[1, 1, 1], [2, 2, 2]]}, [0], (1, 0, 0))
        verts = [(2.0, 0.0, 0.0)]
        moved.apply(verts, 0.5)
        self.assertEqual(verts[0], (2.5, 0.0, 1.0))                     # half as big again about its middle, a cell up

    def test_tracks_that_are_wrong_are_said(self):
        for change, said in (({"parts": {"lid": {"t": [0]}}}, "a part 'lid' that it has not"),
                             ({"parts": {"door": {"t": [0, 1], "turn": [[0, 0, 0]]}}}, "a key for each of its 2 times"),
                             ({"parts": {"door": {"t": [1, 0]}}}, "times should go up"),
                             ({"parts": None}, "should have \"parts\"")):
            spec = self.door(**change)
            wrong = model.problems({"door": spec})
            self.assertEqual(len(wrong), 1, wrong)
            self.assertIn(said, wrong[0])
        mesh = {"materials": {"m": {}}, "mesh": {"v": [[0, 0, 0], [1, 0, 0], [0, 1, 0]], "faces": {"m": [[0, 1, 2]]},
                                                  "parts": {"wing": [1, 9]}}}
        self.assertIn("should be [first corner, how many] within the mesh", model.problems({"x": mesh})[0])

    def test_a_models_lines_move_with_it(self):
        m = model.Model("door", self.door(loop=False))
        v = viewer.Subject(m)
        self.assertTrue(v.moving)
        shut, in_parts = v.posed("open", 0.0)
        wide, _ = v.posed("open", 2.0)
        self.assertEqual((shut.edges, len(shut.verts)), (wide.edges, len(wide.verts)))   # the same lines, moved
        self.assertNotEqual(shut.verts, wide.verts)
        self.assertEqual([n for n, _ in in_parts], ["body", "door"])
        self.assertIs(v.posed("open", 2.0)[0], wide)                                     # the same moment: not made twice
        rows = lambda at: viewer.draw(v, "solid", 40, 16, at=at, clip="open")
        self.assertNotEqual(rows(0.0), rows(1.0))
        self.assertEqual(rows(0.5), viewer.draw(v, "solid", 40, 16, t=1.0, clip="open"))  # half way is a beat in
        self.assertNotEqual(viewer.draw(v, "shaded", 40, 16, at=0.0, clip="open"),
                            viewer.draw(v, "shaded", 40, 16, at=1.0, clip="open"))
        still = viewer.Subject(model.Model("d", DRONE))
        self.assertFalse(still.moving)
        self.assertIs(still.posed("idle", 3.0)[0], still.wire)

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
        spec, _ = gltf.to_model(self.write("spin.gltf", b.gltf()), scale=1.0, fps=4, tracks=False, packed=False)
        frames = spec["frames"]["idle"]
        self.assertEqual(len(frames), 8)                                # 1 s = 2 beats, 4 frames a beat
        first, mid = frames[0], frames[4]
        self.assertNotEqual(first, mid)
        self.assertEqual(len(first), 3 * len(spec["mesh"]["v"]))
        m = model.Model("spin", spec)
        self.assertNotEqual(m.pose("idle", 0.0), m.pose("idle", 1.0))

    def spinning(self):
        b = self.cube()
        times = b.acc([0.0, 0.5, 1.0], "SCALAR")
        s, e = math.sqrt(0.5), math.sin(math.radians(22.5))
        rots = b.acc([(0, 0, 0, 1), (0, e, 0, math.cos(math.radians(22.5))), (0, s, 0, s)], "VEC4")   # a quarter turn about up
        b.doc["nodes"][0]["name"] = "Hatch"
        b.doc["animations"] = [{"name": "Idle", "samplers": [{"input": times, "output": rots}],
                                "channels": [{"sampler": 0, "target": {"node": 0, "path": "rotation"}}]}]
        return b

    def test_parts_that_stay_stiff_come_in_as_tracks(self):
        path = self.write("spin.gltf", self.spinning().gltf())
        spec, notes = gltf.to_model(path, scale=1.0)
        self.assertEqual(notes, [])
        self.assertNotIn("frames", spec)
        self.assertEqual(spec["mesh"]["parts"], {"hatch": [0, 8]})      # the node is a named part of the mesh
        track = spec["tracks"]["idle"]
        self.assertEqual((track["length"], list(track["parts"])), (2.0, ["hatch"]))   # 1 s is 2 beats
        hatch = track["parts"]["hatch"]
        self.assertEqual((hatch["t"], hatch["about"]), ([0.0, 2.0], [0, 0, 0]))       # an even turn: two keys say it
        self.assertEqual(sorted(hatch), ["about", "t", "turn"])         # it is not moved and keeps its size
        self.assertEqual(model.problems({"spin": spec}), [])
        m = model.Model("spin", spec)
        self.assertEqual((m.groups, m.clips, m.beats("idle")), (["body", "hatch"], ["idle"], 2.0))
        baked, _ = gltf.to_model(path, scale=1.0, fps=8, tracks=False, packed=False)  # the same, frame by frame
        for k, frame in enumerate(baked["frames"]["idle"]):
            pose = m.pose("idle", k / 8.0)
            for i, p in enumerate(pose):
                for c in range(3):
                    self.assertAlmostEqual(p[c], frame[i * 3 + c], places=3)
        between = m.pose("idle", 0.3141)                                 # and at any moment between two frames
        self.assertNotIn(between, (m.pose("idle", 0.25), m.pose("idle", 0.375)))
        self.assertLess(len(json.dumps(spec["tracks"])), len(json.dumps(baked["frames"])) // 8)

    def test_a_part_on_a_part_goes_where_both_take_it(self):
        b = self.cube()
        pos, idx = 0, 1
        b.doc["meshes"].append({"primitives": [{"attributes": {"POSITION": pos}, "indices": idx, "material": 0}]})
        b.doc["nodes"] = [{"mesh": 0, "name": "Arm", "translation": [0, 1, 0], "children": [1]},
                          {"mesh": 1, "name": "Hand", "translation": [2, 0, 0], "scale": [0.5, 0.5, 0.5]}]
        times = b.acc([0.0, 1.0, 2.0], "SCALAR")
        s = math.sqrt(0.5)
        rots = b.acc([(0, 0, 0, 1), (0, 0, s, s), (0, 0, 1, 0)], "VEC4")
        lift = b.acc([(2, 0, 0), (2, 0.5, 0), (3, 0, 0)], "VEC3")
        b.doc["animations"] = [{"name": "wave", "samplers": [{"input": times, "output": rots}, {"input": times, "output": lift}],
                                "channels": [{"sampler": 0, "target": {"node": 0, "path": "rotation"}},
                                             {"sampler": 1, "target": {"node": 1, "path": "translation"}}]}]
        path = self.write("arm.glb", b.glb())
        spec, notes = gltf.to_model(path, scale=0.5)
        self.assertEqual(notes, [])
        self.assertEqual(list(spec["mesh"]["parts"]), ["arm", "hand"])
        self.assertEqual(sorted(spec["tracks"]["wave"]["parts"]["hand"]), ["about", "move", "t", "turn"])
        m = model.Model("arm", spec)
        baked, _ = gltf.to_model(path, scale=0.5, fps=8, tracks=False, packed=False)
        frames = baked["frames"]["wave"]
        worst = 0.0
        for k, frame in enumerate(frames):
            pose = m.pose("wave", k / 8.0)
            worst = max(worst, max(abs(p[c] - frame[i * 3 + c]) for i, p in enumerate(pose) for c in range(3)))
        self.assertLess(worst, 0.006)                                    # as the frames have it, to a hundredth of a cell
        v = viewer.Subject(m)                                            # and its parts are apart in the viewer
        self.assertEqual([n for n, _ in v.parts], ["arm", "hand"])

    def test_a_part_that_shears_is_kept_as_frames(self):
        b = self.cube()
        b.doc["meshes"].append({"primitives": [{"attributes": {"POSITION": 0}, "indices": 1, "material": 0}]})
        b.doc["nodes"] = [{"mesh": 0, "name": "Base", "scale": [1, 3, 1], "children": [1]},
                          {"mesh": 1, "name": "Vane", "translation": [2, 0, 0]}]
        times = b.acc([0.0, 1.0], "SCALAR")
        s = math.sqrt(0.5)
        rots = b.acc([(0, 0, 0, 1), (0, 0, math.sin(0.4), math.cos(0.4))], "VEC4")   # turned inside a squashed parent
        b.doc["animations"] = [{"name": "idle", "samplers": [{"input": times, "output": rots}],
                                "channels": [{"sampler": 0, "target": {"node": 1, "path": "rotation"}}]}]
        spec, notes = gltf.to_model(self.write("shear.glb", b.glb()), fps=4)
        self.assertEqual(notes, ["animation 'idle' shears a part: kept as frames"])
        self.assertNotIn("tracks", spec)
        self.assertEqual(spec["frames"]["idle"]["count"], 8)
        self.assertEqual(model.problems({"shear": spec}), [])
        self.assertNotEqual(model.Model("shear", spec).pose("idle", 0.0), model.Model("shear", spec).pose("idle", 1.0))

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
        self.assertNotIn("tracks", spec)                                # a skin bends: only frames can say it
        self.assertEqual(sorted(spec["frames"]["walk"]), ["count", "packed", "size", "step"])
        walk = model.unpack_frames(spec["frames"]["walk"])
        rest, last = walk[0], walk[-1]
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
