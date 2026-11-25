# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Daniel Sandner
"""--add: working pieces pasted into a game; and the gallery of every widget with the JSON that makes it."""
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from engine import panels, recipes  # noqa: E402
from engine import sim as S  # noqa: E402
from engine.data import GameData  # noqa: E402


class RecipeTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="clio-recipe-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.game = os.path.join(self.dir, "mine")
        shutil.copytree(os.path.join(ROOT, "templates", "starter"), self.game)

    def read(self, name):
        with open(os.path.join(self.game, name + ".json"), encoding="utf-8") as f:
            return json.load(f)

    def test_a_console_comes_with_its_scene_and_what_it_shows(self):
        before = self.read("scenes")
        said = recipes.add(self.game, "console", "bay")
        self.assertEqual(said[-1], "The game checks clean.")
        self.assertIn('the simulator "bay"', said[0])
        data = GameData(self.game)
        self.assertEqual(data.validate(), [])
        self.assertEqual((sorted(data.sims), sorted(data.models), sorted(data.planets)),
                         (["bay"], ["bay", "hauler_light"], ["moon"]))
        scenes = self.read("scenes")
        self.assertEqual(len(scenes), len(before) + 1)
        new = scenes[-1]
        self.assertEqual((new["id"], new["sim"], new["on_sim_done"][1]), ("bay", "bay", {"set": "bay_done"}))
        first = self.read("game")["initial_scene"]
        home = next(s for s in scenes if s["id"] == first)
        self.assertEqual(home["exits"][-1], {"door_name": "Bay 2", "scene_id": "bay"})
        self.assertEqual(new["on_sim_done"][-1], {"goto": first})
        sim = S.make(data, "bay")
        S.fly(sim)
        self.assertEqual(sim.result, "won")                      # and it can be done where it now is

    def test_nothing_of_the_games_own_is_replaced(self):
        recipes.add(self.game, "console", "reactor")
        models = self.read("models")
        models["hauler"]["mine"] = True
        with open(os.path.join(self.game, "models.json"), "w", encoding="utf-8") as f:
            json.dump(models, f)
        said = recipes.add(self.game, "console", "reactor", "core")           # the same again, under another name
        self.assertTrue(self.read("models")["hauler"]["mine"])
        self.assertIn("the game's own hauler is shown", "\n".join(said))
        self.assertEqual(sorted(self.read("sims")), ["core", "reactor"])
        self.assertEqual(recipes.add(self.game, "console", "scan")[0][:31], 'sims.json: the simulator "scan"')
        with self.assertRaises(recipes.RecipeError) as taken:
            recipes.add(self.game, "console", "bay", "core")
        self.assertIn("called 'core' already", str(taken.exception))
        again = recipes.add(self.game, "console", "reactor")                  # no name asked for: the next free one
        self.assertIn('"reactor2"', again[0])

    def test_a_menu_and_a_model(self):
        said = recipes.add(self.game, "menu", "wheel", "orders") + recipes.add(self.game, "model", "door")
        self.assertIn('{"menu": "orders"}', said[0])
        self.assertIn('"clip": "open"', said[2])
        data = GameData(self.game)
        self.assertEqual(data.validate(), [])
        self.assertEqual((data.menus["orders"]["look"], list(data.models["door"]["tracks"])), ("wheel", ["open"]))
        recipes.add(self.game, "model", "beacon")
        self.assertEqual(list(self.read("models")["beacon"]["tracks"]), ["deploy"])
        for kind, name in (("menu", "ring"), ("menu", "bar"), ("model", "hauler")):
            self.assertEqual(recipes.add(self.game, kind, name)[-1], "The game checks clean.")

    def test_what_there_is_and_what_there_is_not(self):
        lines = recipes.listing()
        self.assertEqual(len(lines), len(recipes.CONSOLES) + len(recipes.MENUS) + len(recipes.MODELS))
        self.assertTrue(lines[0].startswith("console reactor: "))
        self.assertEqual(len(recipes.listing("menu")), 3)
        for kind, name in (("console", "warp"), ("gadget", "x")):
            with self.assertRaises(recipes.RecipeError) as none:
                recipes.add(self.game, kind, name)
            self.assertIn("There is no", str(none.exception))
        with self.assertRaises(recipes.RecipeError):
            recipes.add(self.dir, "menu", "wheel")               # not a game's folder
        for name, (source, sim_id, _what) in recipes.CONSOLES.items():        # every recipe is where it says
            self.assertIn(sim_id, GameData(source).sims, name)


class GalleryTests(unittest.TestCase):
    def test_every_widget_once_with_its_json(self):
        got = panels.gallery(64)
        self.assertEqual(sorted({k for k, _w, _s, _c in got}), sorted(w for w in panels.WIDGETS if w != "space"))
        for kind, what, spec, cells in got:
            self.assertIn(kind, json.loads(spec), kind)
            self.assertEqual(len(cells[0]), 64, kind)
            text = "".join(c[0] or "#" for row in cells for c in row)
            self.assertIn(kind.upper(), text)
            self.assertNotIn("NO MODEL", text)
        text = {k: "".join(c[0] or "#" for row in cells for c in row) for k, _w, _s, cells in got}
        self.assertIn("●", text["lamps"])                       # its condition holds: lit
        self.assertIn("[X] SCRAM", text["functions"])
        self.assertIn("NO MAP", text["map"])                     # what only a simulator gives is said to be missing
        plain = panels.gallery(64, unicode=False)
        self.assertTrue(all(("".join(c[0] or "#" for row in cells for c in row)).isascii() for _k, _w, _s, cells in plain))


if __name__ == "__main__":
    unittest.main()
