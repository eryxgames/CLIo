# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Magboots on the ceiling: plating up to it, walking it over what is on the floor, switches and hatches only
reached from up there, letting go, the plating's power cut - and the world drawn upside down."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from engine import levelbot, picture  # noqa: E402
from engine.firstperson import FX, View  # noqa: E402
from engine.level import Level, validate  # noqa: E402
from test_levels import Quiet, put, with_level  # noqa: E402

C = {"ceiling_mag": True, "ceiling_height": 2.0}
LEGEND = {".": dict(C), "~": dict(C, toxic=True), "@": dict(C, start=True), "b": {"ceiling_height": 2.0},
          "!": {"switch": "lights", "high": True}, "s": {"switch": "low"}, "D": {"door": True, "opens_on": "lights"},
          "^": {"mag_ceiling": True}, "u": dict(C, monster="bugrat"), "x": dict(C, mag_off_on="lights"),
          "y": dict(C, mag_off_on="lights", mag_delay=2), "E": {"exit": True},
          "H": {"hatch": "up", "deck": 1}, "h": dict(C, hatch="up"), "l": {"ceiling_height": 1.0, "ceiling_mag": True},
          "L": {"ceiling_height": 1.0, "ceiling_mag": True, "start": True}, "g": dict(C, item="magboots")}
ROOM = ["##########",
        "#....b...!",
        "#.~~~~~..#",
        "#.~~~~~..D",
        "#@...u.xy#",
        "####^#s###"]


def room(rows=ROOM, **more):
    spec = {"map": rows, "legend": LEGEND}
    spec.update(more)
    lv = Level(with_level(spec), "t", seed=1)
    lv.console = Quiet()
    lv.player.magboots = lv.player.mag_on = True
    return lv


def upside_down(cells):
    """A pixel-style picture turned half round: rows and columns reversed, each cell's two pixels swapped."""
    return [[(ch, bg, fg) if ch is None else (ch, fg, bg) for ch, fg, bg in reversed(row)] for row in reversed(cells)]


class CeilingTests(unittest.TestCase):
    def test_up_the_plating_and_over_the_acid(self):
        lv = room()
        p = lv.player
        put(lv, 4, 4, 2)                                       # facing the plating, south
        p.mag_on = False
        lv.run_line("k")
        self.assertFalse(p.ceiling)                            # boots off: it is only a wall
        p.mag_on = True
        lv.run_line("k")
        self.assertTrue(p.ceiling)
        self.assertEqual(((p.x, p.y), p.facing), ((4, 4), 0))  # on the ceiling over where he stood, facing back
        hp = p.hp
        for _ in range(3):
            lv.run_line("k")
        self.assertEqual((p.x, p.y), (4, 1))                   # over the acid
        self.assertEqual(p.hp, hp)                             # which does not reach him

    def test_right_and_left_are_the_screens(self):
        lv = room()
        p = lv.player
        put(lv, 4, 1, 0)
        p.ceiling = True
        lv.run_line("turn right")                              # upside down: the screen's right is the world's west
        self.assertEqual(p.facing, 3)
        lv.run_line("turn left")
        lv.run_line("l")                                       # a step right: west
        self.assertEqual((p.x, p.y), (3, 1))

    def test_what_stops_him_on_the_ceiling(self):
        lv = room()
        p = lv.player
        put(lv, 4, 1, 1)
        p.ceiling = True
        lv.run_line("k")                                       # east: the ceiling there is bare
        self.assertEqual((p.x, p.y), (4, 1))
        self.assertIn("bare", lv.log[-1][0])

    def test_switches_are_reached_from_where_they_are(self):
        lv = room()
        p = lv.player
        put(lv, 8, 1, 1)
        lv.run_line("use")                                     # a high switch, from the floor of a tall room
        self.assertFalse(lv.cell(9, 1).pressed)
        self.assertIn("Out of reach", lv.log[-1][0])
        p.ceiling = True
        lv.run_line("use")
        self.assertTrue(lv.cell(9, 1).pressed)
        self.assertEqual(lv.cell(9, 3).open, 1.0)              # its door
        put(lv, 6, 4, 2)
        p.ceiling = True
        lv.run_line("use")                                     # a switch down by the floor, from the ceiling
        self.assertFalse(lv.cell(6, 5).pressed)
        low = room(["#####", "#Lls#", "##^##"])                # in a room no higher than 1.3 both are in reach
        put(low, 2, 1, 1)
        low.player.ceiling = True
        low.run_line("use")
        self.assertTrue(low.cell(3, 1).pressed)

    def test_a_bite_does_not_reach_the_ceiling_of_a_tall_room(self):
        lv = room()
        put(lv, 4, 4, 0)
        lv.player.ceiling = True
        rat = lv.monsters[0]
        self.assertFalse(lv.reaches_up(rat))
        hp = lv.player.hp
        rat.awake = True
        for _ in range(4):
            lv.run_line("w")
        self.assertEqual(lv.player.hp, hp)
        low = room(["#####", "#Llu#", "#####"])
        low.player.ceiling = True
        self.assertTrue(low.reaches_up(low.monsters[0]))

    def test_letting_go_drops_him_on_to_what_is_below(self):
        lv = room()
        p = lv.player
        put(lv, 5, 4, 0)                                       # over the bugrat
        p.ceiling = True
        hp = p.hp
        lv.run_line("mag off")
        self.assertFalse(p.ceiling)
        self.assertTrue(lv.monsters[0].dead)                   # landed on
        self.assertEqual(hp - p.hp, 18)                        # a fall of 2: (2 - 1.25) x 25
        flat = room(["#####", "#Lll#", "##^##"])
        flat.player.ceiling = True
        hp = flat.player.hp
        flat.run_line("mag off")
        self.assertEqual(flat.player.hp, hp)                   # from a ceiling of 1: on his feet

    def test_the_platings_power_is_cut(self):
        lv = room()
        p = lv.player
        put(lv, 7, 4, 0)                                       # x: cut at once by "lights"; y: two beats later
        p.ceiling = True
        lv.event("lights")
        self.assertFalse(p.ceiling)
        self.assertFalse(lv.cell(7, 4).ceiling_mag)
        self.assertTrue(lv.cell(8, 4).ceiling_mag)
        lv.run_line("w")
        lv.run_line("w")
        self.assertFalse(lv.cell(8, 4).ceiling_mag)

    def test_hatches_lead_up_from_the_ceiling_and_down_from_the_floor(self):
        rows = ["#######",
                "#..H..#",
                "#######",
                "#@.h..#",
                "###^###"]
        lv = room(rows)
        p = lv.player
        put(lv, 3, 3, 0)
        lv.run_line("use")
        self.assertEqual((p.x, p.y), (3, 3))                   # out of reach from the floor
        p.ceiling = True
        lv.run_line("use")
        self.assertEqual(((p.x, p.y), p.ceiling), ((3, 1), False))    # up through it, on the deck above
        lv.run_line("use")
        self.assertEqual(((p.x, p.y), p.ceiling), ((3, 3), True))     # down again: the boots catch the ceiling
        lv.run_line("mag off")
        lv.run_line("mag on")
        put(lv, 3, 1, 0)
        p.mag_on = False
        lv.run_line("use")
        self.assertEqual(((p.x, p.y), p.ceiling), ((3, 3), False))    # boots off: a drop to the floor

    def test_the_world_is_drawn_upside_down(self):
        for render in ("mesh", "classic"):
            lv = room(render=render)
            put(lv, 4, 4, 0)
            lv.player.ceiling = True
            top = 2.0 if render == "mesh" else 1.0
            for frame in (False, True):
                if frame and picture.load() is None:
                    continue
                v = View(60, 20, "pixel", "high")
                v.use_frame = frame
                hanging = v.render(lv, FX(hands=False), 1)
                from_eye = v.render(lv, FX(hands=False, flip=False, eye=top - v.EYE0 if render == "mesh"
                                           else 1 - v.EYE0), 1)
                self.assertEqual(hanging, upside_down(from_eye), (render, frame))
            hands = View(60, 20, "pixel", "high").render(lv, FX(), 1)
            self.assertNotEqual(hands, hanging)               # the hands are not turned over: still at the bottom

    def test_saved_on_the_ceiling(self):
        import json
        from engine import snapshot
        lv = room()
        put(lv, 4, 1, 0)
        lv.player.ceiling = True
        lv.event("lights")                                     # x cut now, y in two beats
        snap = json.loads(json.dumps(snapshot.capture(lv)))
        back = snapshot.restore(room(), snap)
        self.assertTrue(back.player.ceiling)
        self.assertFalse(back.cell(7, 4).ceiling_mag)
        self.assertEqual([list(c) for c in back.cuts], [list(c) for c in lv.cuts])

    def test_the_check_names_what_is_wrong(self):
        legend = dict(LEGEND, h={"hatch": "lone"}, q={"high": True}, r={"mag_off_on": "lights"},
                      t=dict(C, mag_delay="soon"))
        data = with_level({"map": ["#######", "#@hqrt#", "#######"], "legend": legend})
        problems = [q for q in validate(data) if "level 't'" in q]
        self.assertTrue(any("hatch 'lone' should have two ends" in q for q in problems), problems)
        self.assertTrue(any("'q' is \"high\"" in q for q in problems))
        self.assertTrue(any("'r' cuts the power" in q for q in problems))
        self.assertTrue(any("'t' mag_delay" in q for q in problems))

    def test_the_bot_goes_by_the_ceiling(self):
        rows = ["###^#########",
                "#@g...~~~...!",
                "#.....~~~...#",
                "#.....~~~...#",
                "##########D##",
                "##########.##",
                "##########E##"]
        spec = {"map": rows, "legend": LEGEND, "bot": ["magboots", "^", "!", "drop", "E"]}
        data = with_level(spec)
        self.assertEqual([q for q in validate(data) if "level 't'" in q], [])
        out, lv = levelbot.play(data, "t", seed=1)
        self.assertEqual(out, "exit", lv.log[-6:])


if __name__ == "__main__":
    unittest.main()
