# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Daniel Sandner
"""Erebus: Last Watch, the terminals demo: its data is sound, every console can be done, the wheel of
orders opens them one after another, and the last one ends the game."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from engine import model, viewer  # noqa: E402
from engine import panels as P  # noqa: E402
from engine import sim as S  # noqa: E402
from engine.data import GameData  # noqa: E402
from helpers import Session  # noqa: E402

EREBUS = os.path.join(ROOT, "games", "erebus")
ORDER = ("reactor", "scan", "bay", "approach", "descent")


class DataTests(unittest.TestCase):
    def test_nothing_is_wrong_with_it(self):
        self.assertEqual(GameData(EREBUS).validate(), [])

    def test_the_editor_sees_the_whole_game_when_it_checks(self):
        from engine import editor
        self.assertEqual(editor.load(EREBUS)["problems"], [])     # its planets too, though it has no page for them
        self.assertEqual(editor.check(os.path.join(ROOT, "templates", "station")), [])
        sims = dict(GameData(EREBUS).sims)
        sims["bay"] = dict(sims["bay"], win_if="nothing_there >= 1")
        self.assertEqual(len(editor.check(EREBUS, {"sims": sims})), 1)   # and what is on the page, not yet saved

    def test_every_console_can_be_done(self):
        data = GameData(EREBUS)
        self.assertEqual(tuple(sorted(data.sims)), tuple(sorted(ORDER)))
        for sid in ORDER:
            sim = S.make(data, sid)
            S.fly(sim)
            self.assertEqual(sim.result, "won", sid)

    def test_the_bay_has_to_be_done_in_order(self):
        sim = S.make(GameData(EREBUS), "bay")
        self.assertEqual([f.name for f in sim.functions], ["bleed", "clamps", "swing"])
        self.assertEqual((sim.function("clamps").can(), sim.function("swing").can()), (False, False))
        from engine.realtime import Controls
        sim.paused = None
        for tick in range(200):                                   # the doors run against the air: the motors burn out
            sim.step(Controls(tick, frozenset(["up"]), ("up",) if tick == 0 else (), ()))
            if sim.result:
                break
        self.assertEqual((sim.result, sim.env()["doors"]), ("lost", 0))

    def test_the_beacon_unfolds_and_the_bay_opens_as_values_say(self):
        data = GameData(EREBUS)
        models = model.load(data.models)
        self.assertEqual((models["beacon"].clips, models["bay"].clips), (["deploy"], ["open"]))
        beacon = models["beacon"]
        top = lambda t: max(p[2] for p in beacon.pose("deploy", t))
        wide = lambda t: max(abs(p[0]) for p in beacon.pose("deploy", t))
        self.assertLess(top(0.0), top(2.0) - 0.8)                # the mast comes up
        self.assertLess(wide(0.0), wide(2.0) - 0.4)              # the legs come down and out
        bay = viewer.Subject(models["bay"], look=viewer.looks(data)["bay"])
        shut, ajar, out = (viewer.draw(bay, None, 50, 18, at=a, clip="open") for a in (0.0, 0.5, 1.0))
        self.assertEqual(len({str(shut), str(ajar), str(out)}), 3)
        far = lambda t: max(p[1] for p in models["bay"].pose("open", t))
        self.assertGreater(far(2.0), far(1.2) + 1.0)             # the lander goes out past the open doors last
        sim = S.make(data, "bay")
        view = P.View(sim.panels, S.formula, models, data.planets)
        view.looks = viewer.looks(data)
        a = view.rows(112, 33, dict(sim.env(), stage=0.0), 0.0)
        b = view.rows(112, 33, dict(sim.env(), stage=0.6), 0.0)
        self.assertNotEqual(a, b)


    def test_the_haulers_have_the_parts_the_views_tell_apart(self):
        data = GameData(EREBUS)
        models = model.load(data.models)
        for name in ("hauler", "hauler_heavy", "hauler_light"):
            m = models[name]
            self.assertEqual(sorted(m.groups), ["body", "bridge", "decks", "engines", "hold", "reactor"], name)
            self.assertLess(len(m.faces), 800, name)             # low enough for a terminal
        heavy, light = models["hauler_heavy"], models["hauler_light"]
        wide = lambda m: max(p[0] for p in m.verts) - min(p[0] for p in m.verts)
        tall = lambda m: max(p[2] for p in m.verts)
        self.assertGreater(wide(heavy), 5.0)                     # pods out to either side of a low spine
        self.assertLess(tall(heavy), 1.4)
        self.assertGreater(tall(light), 3.0)                     # a tall body on a leg, antennas up
        used = str(data.sims)
        self.assertIn("hauler_heavy", used)
        self.assertIn("hauler_light", used)


class WatchTests(unittest.TestCase):
    def test_the_orders_open_one_after_another_and_the_last_ends_it(self):
        s = Session("erebus").start()
        game = s.game
        self.assertEqual((game.ui.menu_look, game.world.scene.get("id")), ("terminal", "berth"))
        text = s.do("go bridge", "orders", "2", "0")              # the scan before the core: locked, and why
        self.assertIn("The orders are short.", text)
        self.assertIn("no power yet", text)
        self.assertEqual(game.world.scene.get("id"), "bridge")
        for n, sid in enumerate(ORDER):
            if sid == "descent":
                break
            text = s.do("orders", str(n + 1), "quit")             # into its console, and out of it unfinished
            self.assertEqual(game.world.scene.get("id"), "bridge", sid)
            self.assertFalse(game.world.flags.get(sid + "_done"), sid)
            game.world.flags[sid + "_done"] = True                # as if it had been done
        text = s.do("orders", "1", "0")
        self.assertIn("The core holds at power.", text)           # what is done says so, and cannot be done again
        self.assertFalse(game.over)
        from engine import conditions
        scene = game.data.scenes["descent"]
        conditions.run(scene["on_sim_done"], game)
        self.assertEqual(game.over, "win")
        self.assertIn("Gordian Moon is under your boots.", s.text)


if __name__ == "__main__":
    unittest.main()
