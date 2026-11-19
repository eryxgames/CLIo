"""Models in the editor (a picture of one turning, broken, playing; a glTF file taken in), models that break into
their parts, and the eye of a machine that flies."""
import base64
import json
import math
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine import firstperson as fp  # noqa: E402
from engine import model  # noqa: E402
from engine.data import GameData  # noqa: E402
from engine.editor import EditorError  # noqa: E402
from engine.editor import levels as editor_levels  # noqa: E402
from engine.editor import service  # noqa: E402
from engine.level import Level, validate  # noqa: E402
from test_levels import ROOTLESS, room_with, with_level  # noqa: E402
from test_models import Builder, CUBE, CUBE_TRIS  # noqa: E402

PARTS = {"materials": {"a": {"color": "#808080"}},
         "parts": [{"shape": "box", "size": [0.4, 0.4, 0.4], "at": [-0.4, 0, 0.2], "material": "a"},
                   {"shape": "box", "size": [0.4, 0.4, 0.4], "at": [0.4, 0, 0.2], "material": "a", "group": "x"},
                   {"shape": "cylinder", "size": [0.2, 0.2, 0.6], "at": [0, 0, 0.3], "material": "a", "group": "x"}]}


class BreakTests(unittest.TestCase):
    def test_into_shards_parts_or_groups(self):
        m = model.Model("m", PARTS)
        self.assertEqual(m.breaks, "shards")
        self.assertEqual(len(m.pieces), len(m.faces))
        self.assertEqual(len(set(m.pieces)), 3)                        # a piece for each part

        def pieces(by):
            out = model.shards(m, m.verts, 0.5, 7, by=by)
            # the faces of a piece move together: the same offset for each corner of the piece
            moved = {}
            for tri, f in out:
                i = m.faces.index(f)
                key = m.pieces[i] if by == "parts" else f[5] if by == "groups" else i
                d = tuple(round(tri[0][k] - m.verts[f[0]][k], 6) for k in range(2))
                moved.setdefault(key, set()).add(d)
            return moved
        self.assertEqual(len(pieces("parts")), 3)
        self.assertEqual(len(pieces("groups")), 2)                     # "body" and "x"
        self.assertEqual(len(pieces("shards")), len(m.faces))
        self.assertEqual(model.shards(m, m.verts, 0.5, 7, by_group=True), model.shards(m, m.verts, 0.5, 7, by="groups"))

    def test_a_mesh_breaks_into_what_holds_together(self):
        two = [list(p) for p in CUBE] + [[p[0] + 3, p[1], p[2]] for p in CUBE]
        tris = [CUBE_TRIS[i:i + 3] for i in range(0, len(CUBE_TRIS), 3)]
        faces = [list(t) for t in tris] + [[a + 8, b + 8, c + 8] for a, b, c in tris]
        m = model.Model("m", {"materials": {"a": {}}, "mesh": {"v": two, "faces": {"a": faces}}, "break": "parts"})
        self.assertEqual(len(set(m.pieces)), 2)

    def test_the_check_knows_the_ways(self):
        self.assertTrue(any("break 'dust'" in p for p in model.problems({"m": dict(PARTS, **{"break": "dust"})})))
        self.assertEqual(model.problems({"m": dict(PARTS, **{"break": "parts"})}), [])


class EyeTests(unittest.TestCase):
    def test_a_flying_machine_sees_from_higher_up(self):
        lv = room_with(["#######",
                        "#.....#",
                        "#..H..#",
                        "#..@..#",
                        "#######"], {"H": {"monster": "hopper"}})
        v = fp.View(80, 20)
        tall = v.FS + v.CH
        standing = v.render(lv, fp.FX(), 0)
        self.assertIsNone(fp.View.eye_of(lv))
        hop = lv.monsters[0]
        lv.monsters.remove(hop)
        lv.player.vehicle, hop.fuel, hop.started = hop, 10, True
        self.assertAlmostEqual(fp.View.eye_of(lv), 0.74, delta=0.02)
        flying = v.render(lv, fp.FX(), 0)
        self.assertGreater(v.FS, tall * 0.7)
        self.assertAlmostEqual(v.FS + v.CH, tall)                     # walls as tall as before: the eye is higher
        self.assertNotEqual(standing, flying)
        v.render(lv, fp.FX(eye=0.52), 0)                               # an animation's frame says where the eye is
        self.assertAlmostEqual(v.FS / (v.FS + v.CH), 0.52)

    def test_lift_off_and_coming_down_animate_the_eye(self):
        lv = room_with(["#######",
                        "#.....#",
                        "#..H..#",
                        "#..@..#",
                        "#######"], {"H": {"monster": "hopper"}})
        eyes = []

        class Watch:
            def play(self, lv_, frames, dt):
                eyes.extend(fx.eye for fx in frames)

            def said(self, *a):
                pass
        lv.console = Watch()
        lv.run_line("k")                                               # board
        lv.player.vehicle.fuel = 2
        lv.run_line("k")                                               # it lifts
        up = [e for e in eyes if e is not None]
        self.assertTrue(up and up == sorted(up) and up[-1] > 0.7)
        eyes.clear()
        lv.run_line("w")
        lv.run_line("w")                                               # dry: it comes down, and the level ends
        down = [e for e in eyes if e is not None]
        self.assertTrue(down and down == sorted(down, reverse=True) and abs(down[-1] - 0.52) < 1e-6)
        self.assertEqual(lv.over, "exit")


class EditorModelTests(unittest.TestCase):
    def test_a_model_seen_turning_broken_and_playing(self):
        got = editor_levels.model_view(ROOTLESS, "hopper", turns=8)
        self.assertEqual(got["problems"], [])
        self.assertEqual((len(got["turn"]), len(got["broken"])), (8, 8))
        self.assertNotEqual(got["turn"][0], got["turn"][2])
        self.assertNotEqual(got["broken"][0], got["broken"][-1])
        self.assertEqual(got["parts"], len(GameData(ROOTLESS).models["hopper"]["parts"]))
        self.assertGreater(got["triangles"], 100)

    def test_its_frames_and_what_is_wrong(self):
        spec = dict(PARTS, frames={"idle": [[c for p in model.Model("m", PARTS).verts for c in p]] * 2})
        pending = {"models": {"m": spec, "bad": {"parts": [{"shape": "blob"}]}}}
        got = service.handle(ROOTLESS, "/api/modelview", {"name": "m", "pending": pending})
        self.assertIn("idle", got["clips"])
        bad = service.handle(ROOTLESS, "/api/modelview", {"name": "bad", "pending": pending})
        self.assertTrue(bad["problems"] and not bad["turn"])
        with self.assertRaises(EditorError):
            service.handle(ROOTLESS, "/api/modelview", {"name": "nothing"})

    def test_a_glb_from_the_page(self):
        b = Builder()
        pos = b.acc(CUBE, "VEC3")
        idx = b.acc(CUBE_TRIS, "SCALAR", 5123, "H")
        b.doc["materials"].append({"name": "Paint", "pbrMetallicRoughness": {"baseColorFactor": [0.2, 0.4, 0.1, 1]}})
        b.doc["meshes"].append({"primitives": [{"attributes": {"POSITION": pos}, "indices": idx, "material": 0}]})
        b.doc["nodes"].append({"mesh": 0})
        b.doc["scenes"][0]["nodes"].append(0)
        got = service.handle(ROOTLESS, "/api/modelimport", {"data": base64.b64encode(b.glb()).decode(), "name": "cube",
                                                            "scale": 0.5})
        self.assertEqual(list(got["spec"]["materials"]), ["paint"])
        self.assertEqual(model.problems({"cube": got["spec"]}), [])
        with self.assertRaises(EditorError):
            service.handle(ROOTLESS, "/api/modelimport", {"data": base64.b64encode(b"not a model").decode()})
        with self.assertRaises(EditorError):
            service.handle(ROOTLESS, "/api/modelimport", {"data": ""})

    def test_the_schema_gives_models_their_builder(self):
        from engine import schema
        kind = next(k for k in schema.KINDS if k["key"] == "models")
        self.assertEqual(kind["editor"], "model")
        self.assertIn("break", [f["key"] for f in kind["fields"]])


class LevelTextTests(unittest.TestCase):
    def test_an_intro_of_one_line_and_a_death_text_that_is_a_text(self):
        lv = room_with(["#E#", "#@#", "###"])
        lv.spec["intro"] = "One line."
        self.assertIn(("One line.", "dim"), lv.intro_lines())
        data = with_level({"map": ["#E#", "#@#", "###"], "death_text": "You died."})
        self.assertTrue(any("death_text 'You died.' is not a text" in p for p in validate(data)))

    def test_e1m3_is_whole(self):
        data = GameData(ROOTLESS)
        lv = Level(data, "e1m3", seed=1)
        self.assertEqual(lv.spec["death_text"], "outro_lose")
        self.assertTrue(isinstance(lv.spec["intro"], list))
        for name in ("drone_scout", "drone_hornet", "drone_warden", "hopper"):
            self.assertEqual(data.models[name].get("break"), "parts", name)
        new = ("drone_sight", "drone_zap", "drone_death", "hornet_sight", "hornet_sting", "warden_sight", "drone_bolt",
               "warden_death", "hopper_gun", "hopper_fly", "hopper_start", "hopper_stop", "refuel", "rumble", "thud",
               "clack", "switch")
        for name in new:
            self.assertIn(name, data.sound_sets["ballistic"], name)
        self.assertTrue(math.isfinite(len(json.dumps(data.sound_sets["ballistic"]))))


if __name__ == "__main__":
    unittest.main()
