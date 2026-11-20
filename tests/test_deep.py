# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Getting about: magboots, stairs and magnetic plating, the jetpack, swimming and diving, a submarine -
and SIM-11 Deep Works, the level that has them all."""
import io
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from engine import levelbot  # noqa: E402
from engine.data import GameData  # noqa: E402
from engine.firstperson import FX, UNDERWATER, View, tilt  # noqa: E402
from engine.level import Level, validate  # noqa: E402
from test_levels import Quiet, ROOTLESS  # noqa: E402

LEGEND = {">": {"conveyor": "e"}, ";": {"slick": True}, "~": {"toxic": True},
          "U": {"stairs": "deck", "deck": 0}, "D": {"stairs": "deck", "deck": 1, "facing": "w"},
          "M": {"mag": "shaft", "deck": 0}, "N": {"mag": "shaft", "deck": 1},
          "o": {"pit": True, "floor": "pit"}, "w": {"deep": True, "floor": "water"}, "|": {"bulkhead": True},
          "g": "magboots", "j": "jetpack", "B": {"monster": "minisub", "deep": True, "floor": "water"}}


def room(rows, **more):
    data = GameData(ROOTLESS)
    data.levels = dict(data.levels, t=dict({"name": "Test", "map": rows, "legend": LEGEND, "facing": "n"}, **more))
    lv = Level(data, "t", seed=1)
    lv.console = Quiet()
    return lv


def at(lv, x, y, facing=0):
    lv.player.x, lv.player.y, lv.player.facing = x, y, facing
    lv.update_seen()


class Magboots(unittest.TestCase):
    MAP = ["#########",
           "#.......#",
           "#;;;;;;.#",
           "#>>>>>..#",
           "#g.....@#",
           "#########"]

    def test_they_stop_a_slide_and_hold_on_a_belt(self):
        lv = room(self.MAP)
        at(lv, 6, 1, 3)                                    # facing west, the slick row below
        lv.run_line("turn left")                           # facing south
        lv.run_line("k")                                   # onto the slick floor: no slide (it runs east-west)
        at(lv, 7, 2, 3)
        lv.run_line("k")                                   # west on to the slick: slides to the wall
        self.assertEqual((lv.player.x, lv.player.y), (1, 2))
        lv.player.magboots = lv.player.mag_on = True
        at(lv, 7, 2, 3)
        lv.run_line("k")
        self.assertEqual((lv.player.x, lv.player.y), (6, 2))
        self.assertIn("clamp", lv.log[-1][0])
        at(lv, 3, 3, 0)
        lv.run_line("w")
        self.assertEqual((lv.player.x, lv.player.y), (3, 3))   # the belt does not carry him
        lv.run_line("mag off")
        lv.run_line("w")
        self.assertEqual((lv.player.x, lv.player.y), (4, 3))   # now it does

    def test_picked_up_and_switched(self):
        lv = room(self.MAP)
        at(lv, 2, 4, 3)
        lv.run_line("k")                                   # on to the magboots
        self.assertTrue(lv.player.magboots and lv.player.mag_on)
        beat = lv.beat
        lv.run_line("mag")
        self.assertFalse(lv.player.mag_on)
        self.assertEqual(lv.beat, beat)                    # a free action
        self.assertEqual(lv.player.keep()["magboots"], True)  # on to the next level


class Rides(unittest.TestCase):
    MAP = ["#########",
           "#...#...#",
           "#...D...#",
           "#...#...#",
           "#...U...#",
           "#.@.#...#",
           "#####N###",
           "#####M###",
           "#.......#",
           "#######E#"]

    def test_stairs_lead_to_the_other_end(self):
        lv = room(self.MAP)
        self.assertEqual(validate(lv.data), [])
        at(lv, 3, 4, 1)                                    # facing the stairs U (east)
        lv.run_line("k")
        p = lv.player
        self.assertEqual((p.x, p.y), (3, 2))               # stepped off D: its first open side
        self.assertEqual(lv.beat, 1)
        self.assertIn("climb the stairs up", lv.log[-1][0])
        lv.run_line("turn around")                         # and back down
        at(lv, 3, 2, 1)
        lv.run_line("use")
        self.assertIn("down", lv.log[-1][0])

    def test_plating_needs_magboots(self):
        lv = room(self.MAP)
        at(lv, 5, 8, 0)                                    # under M, facing north
        lv.run_line("k")
        self.assertEqual((lv.player.x, lv.player.y), (5, 8))
        self.assertIn("Magnetic plating", lv.log[-1][0])
        lv.player.magboots = lv.player.mag_on = True
        lv.run_line("k")
        self.assertEqual((lv.player.x, lv.player.y), (5, 5))   # up the shaft, off N's open side
        self.assertEqual(lv.player.facing, 0)
        self.assertIn("tips on its side", lv.log[-1][0])

    def test_two_ends_or_a_problem(self):
        data = GameData(ROOTLESS)
        data.levels = dict(data.levels, t={"name": "T", "map": ["#####", "#@.E#", "#U###", "#####"], "legend": LEGEND})
        self.assertTrue(any("stairs 'deck' should have two ends, it has 1" in p for p in validate(data)))

    def test_the_world_tips(self):
        a, b, c = (200, 0, 0), (0, 200, 0), (0, 0, 200)
        px = [[a] * 3 + [b] * 3 for _ in range(3)] + [[c] * 6 for _ in range(3)]   # 6 x 6 pixels: square
        cells = [[(None, t, u) for t, u in zip(px[2 * r], px[2 * r + 1])] for r in range(3)]
        self.assertEqual(tilt(cells, 0), cells)
        turned = tilt(cells, 90)                            # a quarter turn, clockwise
        self.assertEqual((len(turned), len(turned[0])), (3, 6))
        self.assertEqual(turned[0][0][1], c)                # the bottom comes round to the left
        self.assertEqual(turned[0][5][1], a)                # the top-left to the top-right
        self.assertEqual(turned[2][5][2], b)                # the top-right to the bottom-right


class Jetpack(unittest.TestCase):
    MAP = ["##########",
           "#..oooo..#",
           "#j.oooo..#",
           "#..~~~~..#",
           "#.@......#",
           "##########"]

    def test_up_over_a_drop_and_down(self):
        lv = room(self.MAP)
        p = lv.player
        at(lv, 2, 1, 1)
        lv.run_line("k")                                   # a drop: no
        self.assertEqual((p.x, p.y), (2, 1))
        self.assertIn("sheer drop", lv.log[-1][0])
        at(lv, 1, 3, 0)
        lv.run_line("k")                                   # the jetpack
        self.assertEqual(p.jet, 40)
        lv.run_line("jet")
        self.assertTrue(p.jet_on)
        self.assertGreater(View.eye_of(lv), 0.8)           # the eye goes up
        at(lv, 2, 1, 1)
        for _ in range(4):
            lv.run_line("k")
        self.assertEqual((p.x, p.y), (6, 1))               # over the drop
        self.assertLess(p.jet, 40 - 4)                     # a beat of fuel a beat
        lv.run_line("jet off")
        self.assertTrue(p.jet_on)
        self.assertIn("nothing to land on", lv.log[-1][0])
        hp = p.hp
        at(lv, 5, 3, 1)                                    # over the acid: it does not burn
        lv.run_line("w")
        self.assertEqual(p.hp, hp)
        lv.run_line("k")
        lv.run_line("k")
        lv.run_line("jet")
        self.assertFalse(p.jet_on)
        self.assertEqual((p.x, p.y), (7, 3))

    def test_dry_over_a_drop(self):
        lv = room(self.MAP)
        p = lv.player
        p.jet, p.jet_on = 1, True
        at(lv, 3, 1, 1)                                    # at the edge of the drop
        lv.run_line("w")
        self.assertFalse(p.jet_on)
        self.assertEqual((p.x, p.y), (2, 1))               # glided to the edge
        p.jet, p.jet_on = 1, True
        for row in lv.grid:                                # all a drop now
            for c in row:
                c.pit = c.pit or not c.solid
        at(lv, 5, 2, 1)
        lv.run_line("w")
        self.assertEqual(lv.over, "dead")                  # nowhere near: a fall


class Water(unittest.TestCase):
    MAP = ["##########",
           "#.wwww|w.#",
           "#.wwww|w.#",
           "#.wwBw|w.#",
           "#@......E#",
           "##########"]

    def test_swimming_needs_the_level(self):
        lv = room(self.MAP)
        at(lv, 1, 1, 1)
        lv.run_line("k")
        self.assertEqual(lv.player.x, 1)
        self.assertIn("Too deep", lv.log[-1][0])
        lv = room(self.MAP, swim=True)
        at(lv, 1, 1, 1)
        lv.run_line("k")
        self.assertEqual(lv.player.x, 2)
        self.assertTrue(lv.swimming())
        self.assertLess(View.eye_of(lv), 0.4)              # head just over the water

    def test_diving_breath_and_the_bulkhead(self):
        lv = room(self.MAP, swim=True)
        p = lv.player
        at(lv, 5, 1, 1)
        lv.run_line("k")                                   # a bulkhead in the way at the top
        self.assertEqual(p.x, 5)
        lv.run_line("dive")
        self.assertTrue(p.diving)
        air = p.air
        lv.run_line("k")                                   # under it: two cells
        self.assertEqual((p.x, p.y), (7, 1))
        self.assertLess(p.air, air)
        lv.run_line("k")
        self.assertEqual(p.x, 7)                           # no climbing out under water
        self.assertIn("surface first", lv.log[-1][0])
        p.air = 1
        hp = p.hp
        lv.run_line("w")
        lv.run_line("w")
        self.assertLess(p.hp, hp)                          # drowning
        lv.run_line("surface")
        self.assertEqual(p.air, lv.breath())

    def test_under_water_it_looks_it(self):
        lv = room(self.MAP, swim=True)
        at(lv, 3, 2, 0)
        lv.run_line("dive")
        under = View(60, 20, "pixel").render(lv, FX(), 0)
        lv.player.diving = False
        over = View(60, 20, "pixel").render(lv, FX(), 0)
        self.assertNotEqual(under, over)

        def tint(rows):
            px = [c for r in rows for ch, fg, bg in r for c in (fg, bg) if c]
            return sum(abs(c[0] - UNDERWATER[0]) + abs(c[1] - UNDERWATER[1]) + abs(c[2] - UNDERWATER[2]) for c in px) / len(px)
        self.assertLess(tint(under), tint(over))           # all of it through the water's green

    def test_the_submarine(self):
        lv = room(self.MAP, swim=True)
        p = lv.player
        at(lv, 4, 4, 0)                                    # on the dock, the sub north of him
        lv.run_line("k")
        self.assertIsNotNone(p.vehicle)
        self.assertEqual((p.x, p.y), (4, 3))
        lv.run_line("j")                                   # back on to the dock: no
        self.assertEqual((p.x, p.y), (4, 3))
        self.assertIn("stays in the water", lv.log[-1][0])
        lv.run_line("turn right")
        lv.run_line("k")                                   # east to (5, 3); the bulkhead next
        lv.run_line("k")
        self.assertEqual(p.x, 5)
        lv.run_line("dive")
        self.assertTrue(p.diving and p.vehicle.dived)
        air = p.air
        lv.run_line("k")
        self.assertEqual(p.x, 7)                           # under the bulkhead
        self.assertEqual(p.air, air)                       # the sub has its own air
        lv.run_line("out")
        self.assertIsNotNone(p.vehicle)                    # not under water
        lv.run_line("surface")
        lv.run_line("out")
        self.assertIsNone(p.vehicle)
        self.assertFalse(lv.cell(p.x, p.y).deep)


class DeepWorks(unittest.TestCase):
    def test_the_level_is_right(self):
        data = GameData(ROOTLESS)
        self.assertEqual([q for q in validate(data) if "sim11" in q], [])
        lv = Level(data, "sim11", seed=1)
        self.assertEqual(len(lv.rides), 6)

    def test_the_bot_gets_through(self):
        data = GameData(ROOTLESS)
        for seed in (0, 3):
            out, lv = levelbot.play(data, "sim11", seed=seed)
            self.assertEqual(out, "exit", seed)
            self.assertIsNone(lv.player.vehicle)

    def test_a_save_holds_it_all(self):
        data = GameData(ROOTLESS)
        _o, played = levelbot.play(data, "sim11", seed=2)
        lines = [l for _b, l in played.journal]
        lv = Level(data, "sim11", seed=2)
        lv.console = Quiet()
        lv.host, lv._assume_duels = None, "won"
        for line in lines:                                 # to the middle of the dive, then a save
            lv.run_line(line)
            if lv.player.diving and lv.player.vehicle is None:
                break
        block = lv.save_block()
        again = Level(data, "sim11", seed=2)
        again.console = Quiet()
        from engine.level import resume
        back, _note = resume(data, block)
        self.assertEqual(back.state_hash(), lv.state_hash())
        self.assertTrue(back.player.diving)


if __name__ == "__main__":
    unittest.main()
