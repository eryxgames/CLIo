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


class ScanTests(unittest.TestCase):
    HILL = [[0, 0, 0, 0, 0, 0], [0, 1, 2, 2, 1, 0], [0, 2, 5, 5, 2, 0], [0, 1, 2, 2, 1, 0], [0, 0, 0, 0, 0, 0]]

    def scan(self, heights, t=0.0, cols=80, lines=24, **more):
        scope = V.Scope(cols, lines, colour="green")
        scope.clear()
        got = A.scan(scope, heights, t, **more)
        return scope.rows(), got

    def test_real_ground_as_profiles(self):
        rows, (row, relief) = self.scan(self.HILL, 0.0, title="Scan  the hill", unit="KM")
        t = text(rows)
        self.assertEqual((t[0].strip(), t[-1].strip()), ("SCAN  THE HILL", "PROFILE 01/10  RELIEF +0.00 KM"))
        self.assertGreater(lit(rows), 300)
        flat, _ = self.scan([[0] * 6] * 5)
        self.assertNotEqual(rows, flat)
        later, (row, relief) = self.scan(self.HILL, 0.9, unit="KM")          # the sweep has gone on, to the hill
        self.assertEqual((row, relief), (5, 5))
        self.assertNotEqual(later, rows)
        white = lambda rr: sum(1 for r in rr for c in r if c[1] and min(c[1]) > 200 and c[0] != " ")   # noqa: E731
        self.assertGreater(white(self.scan(self.HILL, 0.0, at=(2, 2))[0]), white(rows) + 5)     # where we are, marked
        loud, _ = self.scan(self.HILL, 0.0, beat=1.0)                        # the music hits: the relief swells
        self.assertNotEqual(loud, rows)
        small, _ = self.scan(self.HILL, 0.0, cols=24, lines=10, unit="KM")   # a small display: fewer profiles, short words
        self.assertEqual(text(small)[-1].strip(), "01/08  +0.00 KM")

    def test_a_simulators_map_and_a_planet(self):
        s = sim()
        grid = A.heights_of(s)
        self.assertEqual((len(grid), len(grid[0])), (7, 14))
        self.assertEqual((grid[0][0], grid[1][1], grid[2][10], grid[3][10], grid[5][5]), (3.0, 0.0, 2.0, 1.0, -0.5))
        from engine.viewer import Planet
        moon = Planet(GameData(STATION).planets["moon"], "moon")
        high = A.planet_heights(moon, 0.0)
        self.assertEqual((len(high), len(high[0])), (20, 40))
        self.assertGreater(max(max(max(r) for r in A.planet_heights(moon, turn)) for turn in (0, 90, 180, 270)), 2.0)
        self.assertNotEqual(A.planet_heights(moon, 90.0), high)              # turned: other ground
        self.assertIsNone(A.planet_heights(Planet({"legend": {".": {"colour": "#888"}}, "field": ["."]}, "bare")))

    def test_in_panels(self):
        layout = {"cols": [{"title": "RELIEF", "widgets": [{"scan": True}]},
                           {"title": "MOON", "widgets": [{"scan": {"planet": "moon", "unit": "KM", "pulse": "hit.low"}}]}]}
        data = GameData(STATION)
        s = sim(panels=layout)
        s.data = data
        runner = S.Runner(s)
        rows = runner.panel_rows(100, 20, 3, True, None)
        t = text(rows)
        self.assertIn("PROFILE 01/", t[18])
        self.assertIn("KM", t[18][50:])
        self.assertGreater(sum(1 for line in t[2:17] for ch in line[1:49] if 0x2800 < ord(ch) < 0x2900), 100)
        self.assertGreater(sum(1 for line in t[2:17] for ch in line[51:99] if 0x2800 < ord(ch) < 0x2900), 100)
        self.assertIn("NOTHING TO SCAN", "\n".join(P.View({"widgets": [{"scan": True}]}).plain(60, 12, {})))
        bad = {"widgets": [{"scan": 3}, {"scan": {"planet": "mars"}}, {"scan": {"planet": "bare"}}, {"scan": True}]}
        self.assertEqual(P.problems(bad, set(), "p", planets={"bare": {"legend": {".": {"colour": "#888"}}}}, ahead=False),
                         ["p widget 1: \"scan\" should be true (the map here), or a map (planet, title, unit, pulse)",
                          "p widget 2: there is no planet called 'mars'",
                          "p widget 3: planet 'bare' has no heights to scan (give its legend's grounds a \"height\")",
                          "p widget 4: there is no map here to scan (a simulator with a map has one; or name a planet)"])

    def test_the_rocks_flare_with_the_music(self):
        quiet, loud = V.Scope(60, 18), V.Scope(60, 18)
        quiet.clear()
        loud.clear()
        A.field(quiet, 2.0)
        A.field(loud, 2.0, beat=1.0)
        self.assertGreater(lit(loud.rows()), lit(quiet.rows()))

        class Sheet:
            def level(self, action, t):
                return 1.0 if action == "hit.low" else 0.0
        with_music = V.Scope(60, 18)
        with_music.clear()
        V.scene("asteroids", 2.0, with_music, Sheet())
        self.assertEqual(with_music.rows(), loud.rows())


class LevelTests(unittest.TestCase):
    ROOM = ["#########",
            "#...#...#",
            "#.z.+...#",
            "#...#..E#",
            "#.@.#####",
            "#########"]

    def level(self, **more):
        from engine.level import Level
        from test_levels import with_level
        spec = dict({"map": self.ROOM, "facing": "n",
                     "legend": {"z": {"monster": "zombie"}, "E": {"exit": True}}}, **more)
        return Level(with_level(spec), "t", seed=1)

    def test_a_level_is_a_place(self):
        lv = self.level()
        place = A.LevelPlace(lv)
        self.assertEqual((place.x, place.y, place.degrees, place.W, place.H), (2.5, 4.5, 0.0, 9, 6))
        self.assertEqual([place.kind(x, y) for x, y in ((0, 0), (1, 1), (4, 2), (7, 3), (-1, 0), (4, 1))],
                         ["wall", "ground", "door", "exit", "void", "wall"])
        lv.cell(4, 2).open = 1.0                                             # an open door is a way through
        self.assertEqual(place.kind(4, 2), "ground")
        lv.cell(4, 2).open = 0.0
        who = [t for t in place.things() if t.get("label")]
        self.assertEqual([(t["x"], t["y"], t["label"]) for t in who], [(2.5, 2.5, "Z")])
        sides = A.walls(place, 4, 1, place.floor)                            # a wall between rooms: two sides face floors
        self.assertEqual(len(sides.faces), 2)
        self.assertIsNone(A.walls(place, 0, 0, place.floor))                 # the corner faces none
        grid = A.heights_of(place)
        self.assertEqual((grid[0][0], grid[1][1]), (A.WALL, 0.0))

    def test_what_is_ahead_in_lines(self):
        lv = self.level()
        view = A.LevelView(80, 24, "lines")
        rows = view.render(lv, None, 0)
        self.assertEqual((len(rows), len(rows[0])), (24, 80))
        t = text(rows)
        self.assertEqual(sum(line.count("Z") for line in t), 1)              # who is ahead, by a letter
        self.assertGreater(lit(rows), 200)
        self.assertFalse(view.meshed(lv))
        self.assertIsNone(view.rolled(lv, 30))
        lv.player.facing = 2                                                 # the other way: a wall close by, nobody
        back = view.render(lv, None, 0)
        self.assertNotEqual(back, rows)
        self.assertNotIn("Z", "".join(text(back)))
        lv.player.facing = 1                                                 # east: a wall between: not seen through it
        lv.player.x, lv.player.y = 2, 3
        self.assertNotIn("EXIT", "".join(text(view.render(lv, None, 0))))
        lv.player.x, lv.player.y, lv.player.facing = 5, 3, 1                 # in the other room: the way out, named
        self.assertIn("EXIT", "".join(text(view.render(lv, None, 0))))
        from engine.firstperson import FX
        turning = view.render(lv, FX(yaw=0.8), 0)                            # between facings, as a turn is drawn
        self.assertNotEqual(turning, view.render(lv, None, 0))

    def test_the_level_as_a_scan_and_in_its_console(self):
        from engine.level import FrameConsole, LINE_VIEWS
        from engine.term import Term
        import io
        lv = self.level()
        rows = A.LevelView(80, 24, "scan").render(lv, None, 0)
        t = text(rows)
        self.assertTrue(t[0].strip().startswith("SCAN"))
        self.assertIn("PROFILE 01/12  RELIEF +1.00", t[-1])
        self.assertEqual(LINE_VIEWS, A.LEVEL_VIEWS)
        term = Term(out=io.StringIO(), inp=lambda p: "", width=100, height=34, color=3, unicode=True, animate=False, env={})
        for style in ("lines", "scan"):
            console = FrameConsole(term, style, keys=False)
            console.layout()
            view = console.view_for(lv)
            self.assertEqual((view.__class__.__name__, view.style), ("LevelView", style))
            self.assertIs(console.view_for(lv), view)                        # kept
            self.assertEqual(len(console.snapshot(lv)), console.size[1])
            self.assertIsNone(console.rolled(lv, [10, 20]))
            self.assertEqual(console.view_for(lv, "dots").__class__.__name__, "View")   # another, for a moment
        plain = FrameConsole(term, "pixel", keys=False)
        plain.layout()
        self.assertEqual(plain.view_for(lv).__class__.__name__, "View")
        one = self.level(view="scan")                                        # one level's own view
        self.assertEqual(plain.view_for(one).style, "scan")
        goggles = self.level(goggles="lines")
        self.assertEqual(plain.view_for(goggles).__class__.__name__, "View")


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
