# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""What is ahead (engine/ahead.py): the things it draws with; the view forward over a simulator's map -
the net, rock, buildings, the marks and which way the next one is; the same map as space; the field of
rocks; the panel widget and its checks; and the station starter's helm."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from engine import ahead as A  # noqa: E402
from engine import panels as P  # noqa: E402
from engine import sim as S  # noqa: E402
from engine import vector as V  # noqa: E402
from engine.data import GameData  # noqa: E402
from engine.sim import Sim  # noqa: E402

STATION = os.path.join(ROOT, "templates", "station")
FIELD = ["##############",
         "#............#",
         "#.@....1..B..#",
         "#.........T..#",
         "#....#.....H.#",
         "#....~~..2...#",
         "##############"]


def sim(heading=90, **more):
    s = Sim(dict({"map": FIELD, "vehicle": {"model": "hover", "heading": heading}}, **more))
    s.paused = None
    return s


def lit(rows):
    return sum(1 for row in rows for ch, _fg, _bg in row if ch not in (" ", None))


def text(rows):
    return ["".join(ch or " " for ch, _fg, _bg in row) for row in rows]


class ShapeTests(unittest.TestCase):
    def test_chance_is_the_same_every_time(self):
        self.assertEqual(A.chance(3, 4), A.chance(3, 4))
        self.assertNotEqual(A.chance(3, 4), A.chance(4, 3))
        got = [A.chance(1, i) for i in range(400)]
        self.assertTrue(all(0.0 <= v < 1.0 for v in got))
        self.assertTrue(0.4 < sum(got) / len(got) < 0.6)

    def test_a_rock_adrift(self):
        a = A.lump(3)
        self.assertIs(a, A.lump(3))                                          # made once
        self.assertEqual((len(a.verts), len(a.edges), len(a.faces), a.wound), (12, 30, 20, True))
        self.assertNotEqual(a.verts, A.lump(4).verts)
        self.assertTrue(all(max(abs(c) for c in v) <= 0.65 for v in a.verts))
        centre = [sum(v[k] for v in a.verts) / 12 for k in range(3)]
        for f in a.faces:                                                    # every side looks out
            p, q, r = (a.verts[i] for i in f)
            n = V._cross(V._sub(q, p), V._sub(r, p))
            self.assertGreater(V._dot(n, V._sub(p, centre)), 0)

    def test_rock_beside_rock_is_one_ridge(self):
        s = sim()
        alone = A.ridge(s, 5, 4)                                             # ground all round it: a peak
        self.assertEqual((len(alone.verts), len(alone.faces)), (5, 4))
        self.assertEqual([v[2] for v in alone.verts[:4]], [0.0] * 4)
        self.assertGreater(alone.verts[4][2], 2.0)
        rim = A.ridge(s, 3, 0)                                               # the map's edge: up from the ground, outwards
        self.assertEqual(len(rim.verts), 4)
        self.assertEqual([v[2] > 1.5 for v in rim.verts], [False, False, True, True])
        self.assertEqual(A.ridge(s, 4, 0).verts[3], rim.verts[2])            # its neighbour shares the corner
        self.assertEqual(len(A.block(2.0).faces), 5)
        self.assertEqual(A.tree(1, 1.0).verts[4][2], 1.0)


class ViewTests(unittest.TestCase):
    def test_the_eye_is_the_vehicles(self):
        s = sim(heading=90)                                                  # east: +x; the map's rows go south, here -y
        cam, (fx, fy) = A.eye_of(s)
        self.assertEqual((cam.eye[0], cam.eye[1], round(cam.eye[2], 2)), (2.5, -2.5, round(s.z + A.EYE, 2)))
        self.assertEqual((round(fx, 6), round(fy, 6)), (1.0, 0.0))
        self.assertGreater(cam.see((7.5, -2.5, 0.5))[2], 4.9)                # the first mark is straight ahead
        self.assertAlmostEqual(cam.see((7.5, -2.5, 0.5))[0], 0.0, places=6)
        north, (fx, fy) = A.eye_of(sim(heading=0))
        self.assertEqual((round(fx, 6), round(fy, 6)), (0.0, 1.0))

    def test_over_its_own_map(self):
        s = sim()
        rows = A.rows(s, 72, 20, None, "amber")
        self.assertEqual((len(rows), len(rows[0])), (20, 72))
        t = text(rows)
        self.assertEqual(sum(line.count("1") for line in t), 1)              # the mark ahead, by its number
        mark = next(y for y, line in enumerate(t) if "1" in line)
        self.assertTrue(30 <= t[mark].index("1") <= 42)
        self.assertEqual(sum(line.count("2") for line in t), 1)              # and the one after, to its right
        self.assertGreater(t[next(y for y, line in enumerate(t) if "2" in line)].index("2"), t[mark].index("1"))
        horizon = max(range(20), key=lambda y: sum(1 for ch in t[y] if ch != " "))
        self.assertTrue(4 <= horizon <= 10)
        self.assertGreater(sum(1 for ch in t[horizon] if ch != " "), 60)     # where the ground ends: a line across
        self.assertGreater(lit(rows[horizon + 1:]), 80)                      # the net on the ground
        self.assertTrue(0 < lit(rows[:horizon]) < 200)                       # stars, and what stands above the horizon
        self.assertEqual(rows, A.rows(s, 72, 20, None, "amber"))             # the same from the same place
        self.assertNotEqual(rows, A.rows(sim(heading=0), 72, 20, None, "amber"))
        near = A.rows(s, 72, 20, {"far": 4}, "amber")
        self.assertLess(lit(near), lit(rows))
        through = A.rows(s, 72, 20, {"solid": False}, "amber")               # nothing hides anything
        self.assertGreaterEqual(lit(through), lit(rows))
        plain = A.rows(s, 72, 20, None, "amber", unicode=False)
        self.assertTrue(all(ord(ch or " ") < 128 for row in plain for ch, _f, _b in row))
        self.assertGreater(lit(plain), 100)

    def test_which_way_the_next_mark_is(self):
        s = sim(heading=270)                                                 # away from it
        t = text(A.rows(s, 72, 20, None, "amber"))
        self.assertTrue(t[10].startswith("< 1") or t[10].rstrip().endswith("1 >"))
        s = sim(heading=0)                                                   # it is to the right
        self.assertTrue(text(A.rows(s, 72, 20, None, "amber"))[10].rstrip().endswith("1 >"))
        s = sim(heading=180)
        self.assertTrue(text(A.rows(s, 72, 20, None, "amber"))[10].startswith("< 1"))
        s = sim()
        s.passed = 1                                                         # the first passed: the second is next
        self.assertIn("2", "".join(text(A.rows(s, 72, 20, None, "amber"))))
        s.passed = 2
        t = "".join(text(A.rows(s, 72, 20, None, "amber")))
        self.assertNotIn(">", t)
        self.assertNotIn("<", t)

    def test_the_same_map_as_space(self):
        s = sim()
        ground = A.rows(s, 72, 20, None, "cyan")
        space = A.rows(s, 72, 20, {"look": "space"}, "cyan")
        self.assertNotEqual(space, ground)
        t = text(space)
        self.assertIn("1", "".join(t))
        self.assertGreater(min(line.count(" ") for line in t), 6)            # no horizon: no line right across
        later = A.rows(s, 72, 20, {"look": "space"}, "cyan", t=3.0)          # the rocks tumble
        self.assertNotEqual(later, space)
        self.assertGreater(lit(space), 40)
        self.assertEqual(A.rows(s, 72, 20, {"look": "space", "stars": False}, "cyan", t=3.0) == later, False)

    def test_a_field_of_rocks(self):
        scope = V.Scope(60, 18, colour="green")
        scope.clear()
        self.assertEqual(A.field(scope, 2.0), "A field of rocks, flown through")
        a = scope.rows()
        self.assertGreater(lit(a), 60)
        self.assertIn("ASTEROIDS", text(a)[0])
        scope.clear()
        A.field(scope, 2.0)
        self.assertEqual(scope.rows(), a)
        scope.clear()
        A.field(scope, 2.5)
        self.assertNotEqual(scope.rows(), a)
        scope.clear()
        A.field(scope, 2.0 + 34.0 / 2.6 * 3)                                 # three laps on: rocks still come
        self.assertGreater(lit(scope.rows()), 60)
        self.assertIn("asteroids", V.SCENES)
        scope.clear()
        self.assertEqual(V.scene("asteroids", 1.0, scope), "A field of rocks, flown through")


class PanelTests(unittest.TestCase):
    LAYOUT = {"colour": "amber", "cols": [{"title": "AHEAD", "widgets": [{"ahead": {"far": 9}}]},
                                          {"title": "MAP", "size": 20, "widgets": [{"map": True}]}]}

    def test_in_a_simulators_panels(self):
        s = sim(panels=self.LAYOUT)
        runner = S.Runner(s)
        rows = runner.panel_rows(100, 24, 3, True, None)
        t = text(rows)
        self.assertIn("AHEAD", t[0])
        self.assertGreater(sum(1 for line in t[1:23] for ch in line[1:78] if 0x2800 < ord(ch) < 0x2900), 150)
        self.assertEqual(len(runner._ahead), 1)                              # one display, kept
        runner.panel_rows(100, 24, 3, True, None)
        self.assertEqual(len(runner._ahead), 1)
        s.heading = S.units(0)
        self.assertNotEqual(runner.panel_rows(100, 24, 3, True, None), rows)
        view = P.View(self.LAYOUT)                                           # nobody to draw it
        self.assertIn("NO VIEW AHEAD", "\n".join(view.plain(100, 24, {})))
        whole = S.Runner(sim(panels=self.LAYOUT)).rows(100, 30, 3, True)
        self.assertGreater(len(whole), 24)

    def test_problems_are_said(self):
        bad = {"widgets": [{"ahead": True}, {"ahead": {"look": "sea", "far": 99, "fov": "wide", "tilt": True}}, {"ahead": 3}]}
        self.assertEqual(P.problems(bad, set(), "p", ahead=True),
                         ["p widget 2: unknown look 'sea' (terrain, space)",
                          "p widget 2: \"far\" should be a number from 3 to 40",
                          "p widget 2: \"fov\" should be a number from 30 to 120",
                          "p widget 2: \"tilt\" should be a number from -45 to 45",
                          "p widget 3: it should be true, or a map (look, far, fov, tilt, solid, stars)"])
        self.assertEqual(P.problems({"widgets": [{"ahead": True}]}, set(), "p", ahead=False),
                         ["p widget 1: there is no vehicle here to look ahead of (a simulator with a map has one)"])

        class D:
            config = {}
            scenes = {}
            sims = {"core": {"mode": "systems", "time": 30, "controls": {"a": {"keys": ["up", "down"]}},
                             "systems": {"b": {"rate": "a"}}, "panels": {"widgets": [{"ahead": True}]}},
                    "fly": {"map": FIELD, "panels": {"widgets": [{"ahead": {"look": "space"}}]}}}
        self.assertEqual(S.problems(D()), ["sim 'core': panels widget 1: there is no vehicle here to look ahead of "
                                           "(a simulator with a map has one)"])

    def test_the_station_starters_helm(self):
        data = GameData(STATION)
        self.assertEqual(data.validate(), [])
        helm = S.make(data, "helm")
        self.assertEqual((helm.W, helm.H), (34, 12))
        runner = S.Runner(helm)
        t = text(runner.rows(110, 34, 3, True)[1:])
        self.assertIn("AHEAD", t[0])
        self.assertIn("SURFACE", "\n".join(t))
        S.fly(helm)
        self.assertEqual(helm.result, "won")
        self.assertGreater(helm.fuel, 5)
        after = runner.panel_rows(110, 32, 3, True, None)                    # drawn where it ended, too
        self.assertEqual(len(after), 32)


if __name__ == "__main__":
    unittest.main()
