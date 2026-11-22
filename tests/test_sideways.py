# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Walls walked as floors: a building's face, a lift shaft. The map says which way the world's up is
(``"world_up"``); the sky is drawn round it, things fall the world's way down, and the boots stay on."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from engine import levelbot  # noqa: E402
from engine.firstperson import FX, View  # noqa: E402
from engine.level import Level, validate  # noqa: E402
from test_levels import Quiet, put, with_level  # noqa: E402

F = {"world_up": "n", "sky": True}
FACE = ["vvvvvvvvv",
        "v...w...v",
        "v.......v",
        "v.......v",
        "v.......v",
        "v...@...v",
        "vvvvvvvvv"]
LEGEND = {"v": dict(F, pit=True, height=-40), ".": dict(F), "@": dict(F, start=True),
          "w": dict(F, sheds={"monster": "shard", "every": 3, "near": 20}), "#": {"wall": True}}
SHARD = {"name": "shard", "tag": "g", "sprite": "shells", "hp": 1, "float": True, "attack": {"kind": "none"},
         "falls": {"speed": 2, "damage": [7, 7]}, "remains": "none"}
WEIGHT = dict(SHARD, name="counterweight", tag="W", falls={"speed": 3, "damage": [30, 30], "fills": True})


def data_with(rows=FACE, legend=LEGEND, **more):
    spec = {"map": rows, "legend": legend, "render": "mesh", "sky": "night"}
    spec.update(more)
    data = with_level(spec)
    data.monsters = dict(data.monsters, shard=SHARD, weight=WEIGHT)
    return data


def level(**more):
    lv = Level(data_with(**more), "t", seed=1)
    lv.console = Quiet()
    lv.player.magboots = lv.player.mag_on = True
    return lv


class FrameTests(unittest.TestCase):
    def test_down_is_where_the_map_says(self):
        lv = level()
        self.assertEqual(lv.down_at(4, 5), 2)                  # world up north: down is south
        flat = level(rows=["#####", "#.@.#", "#####"], legend={".": {}, "@": {"start": True}})
        self.assertIsNone(flat.down_at(2, 1))

    def test_the_boots_stay_on_and_no_jetpack(self):
        lv = level()
        self.assertFalse(lv.magswitch("off"))
        self.assertTrue(lv.player.mag_on)
        self.assertIn("long way down", lv.log[-1][0])
        lv.player.jet = 10
        self.assertFalse(lv.jetpack("on"))
        self.assertFalse(lv.player.jet_on)

    def test_the_sky_is_all_round(self):
        lv = level()
        v = View(60, 20, "pixel", "high")
        sky = v.sky_rows(lv, 4.0, 5.0, 0, 1)
        self.assertEqual(len(sky), v.PH)                       # the whole picture, not only over the horizon
        up = sum(sum(c) for c in sky[0])
        east = v.sky_rows(lv, 4.0, 5.0, 1, 1)                  # along the wall: the world's up to the left
        self.assertNotEqual(east, sky)
        left = sum(sum(c) for row in east for c in row[:20])
        right = sum(sum(c) for row in east for c in row[-20:])
        self.assertNotEqual(left, right)
        self.assertGreater(up, 0)

    def test_past_the_edge_the_sky_shows(self):
        lv = level()
        put(lv, 4, 5, 1)                                       # along the wall, to its edge
        v = View(60, 20, "pixel", "high")
        cells = v.render(lv, FX(hands=False), 1)
        from engine.firstperson import HAZE
        self.assertFalse(any(fg == HAZE or bg == HAZE for row in cells for _ch, fg, bg in row))


class FallingTests(unittest.TestCase):
    def test_a_window_sheds_glass_that_falls_and_hits(self):
        lv = level()
        p = lv.player
        hp = p.hp
        shards = []
        for _ in range(9):
            lv.run_line("w")
            shards += [m for m in lv.monsters if m.kind == "shard" and m not in shards]
        self.assertGreaterEqual(len(shards), 2)                # every 3 beats
        self.assertEqual((hp - p.hp) % 7, 0)
        self.assertLess(p.hp, hp)                              # it fell down his column: hit
        self.assertTrue(all(m.dead and m.gone for m in shards[:-1]))
        self.assertEqual(lv.stats["kills"], 0)                 # not counted

    def test_a_falling_thing_breaks_on_what_stops_it(self):
        rows = list(FACE)
        rows[3] = "v...#...v"
        lv = level(rows=rows)
        put(lv, 2, 5, 0)                                       # out of its way
        m = lv.add_monster("shard", 4, 1)
        m.awake = True
        lv.run_line("w")
        self.assertEqual((m.x, m.y), (4, 2))                   # one cell: the wall is next
        lv.run_line("w")
        self.assertTrue(m.dead and m.gone)

    def test_on_the_ceiling_only_what_fills_the_way_hits(self):
        lv = level(legend=dict(LEGEND, **{".": dict(F, ceiling_mag=True, ceiling_height=2.0),
                                          "@": dict(F, start=True, ceiling_mag=True, ceiling_height=2.0)}))
        p = lv.player
        p.ceiling = True
        hp = p.hp
        shard = lv.add_monster("shard", 4, 3)
        shard.awake = True
        lv.run_line("w")
        self.assertEqual(p.hp, hp)                             # glass falls past, under him
        weight = lv.add_monster("weight", 4, 2)
        weight.awake = True
        lv.run_line("w")
        self.assertEqual(hp - p.hp, 30)

    def test_the_bot_waits_for_it(self):
        lv = level()
        bot = levelbot.Bot(lv, [])
        put(lv, 3, 3, 1)                                       # facing east, the shard's column next
        m = lv.add_monster("shard", 4, 1)
        m.awake = True
        self.assertEqual(bot.wary(lv, "k"), "w")
        self.assertEqual(bot.wary(lv, "j"), "j")


class CheckTests(unittest.TestCase):
    def test_what_is_wrong_is_named(self):
        legend = dict(LEGEND, a=dict(F, world_up="up"), b=dict(F, sheds={"monster": "nobody"}),
                      c=dict(F, sheds={"monster": "zombie"}), d=dict(F, sheds={"monster": "shard", "every": 0}))
        data = data_with(rows=["vvvvvv", "v@abcd", "vvvvvv"], legend=legend)
        got = " | ".join(q for q in validate(data) if "level 't'" in q)
        for want in ("'a' world_up", "'b' sheds should name", "'c' sheds 'zombie', which does not fall",
                     "'d' sheds every"):
            self.assertIn(want, got)


if __name__ == "__main__":
    unittest.main()
