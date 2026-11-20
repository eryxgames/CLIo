"""Open land (engine/land.py): ground made from numbers, as far as one likes; the true-perspective
picture of it; its rules (deep water, cliffs, hills that hide); what is put about it; and E1M4,
Xantrium Fens, the level made of it."""
import io
import math
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine import firstperson as fp  # noqa: E402
from engine import land as land_mod  # noqa: E402
from engine import levelbot  # noqa: E402
from engine.data import GameData  # noqa: E402
from engine.level import Level, validate  # noqa: E402
from test_levels import ROOTLESS, Quiet, put, told, with_level  # noqa: E402

LAND = {"size": [48, 48], "seed": 77, "scale": 14, "height": 7, "sea": 0.38, "ridges": 0.4, "start": [24, 24]}


def land_level(land=None, rows=None, legend=None, seed=1):
    spec = {"land": dict(LAND, **(land or {}))}
    if rows is not None:
        spec["map"] = rows
    if legend:
        spec["legend"] = legend
    lv = Level(with_level(spec), "t", seed=seed)
    lv.console = Quiet()
    return lv


def cells(lv, test):
    return [(x, y) for y in range(lv.h) for x in range(lv.w) if test(lv.cell(x, y))]


class GroundTests(unittest.TestCase):
    def test_the_same_numbers_make_the_same_land(self):
        a, b = land_mod.Land(LAND), land_mod.Land(LAND)
        c = land_mod.Land(dict(LAND, seed=78))
        spots = [(x, y) for x in range(0, 48, 7) for y in range(0, 48, 5)]
        self.assertEqual([a.height(x, y) for x, y in spots], [b.height(x, y) for x, y in spots])
        self.assertNotEqual([a.height(x, y) for x, y in spots], [c.height(x, y) for x, y in spots])

    def test_the_land_goes_on_past_the_level(self):
        """The ground is a sum of the coordinates, nothing stored: any cell has one, as far off as it is."""
        a, b = land_mod.Land(dict(LAND, edge="open")), land_mod.Land(dict(LAND, edge="open"))
        far = [(5000, -3000), (-12345, 777), (10 ** 6, 10 ** 6)]
        heights = [a.height(x, y) for x, y in far]
        self.assertEqual(heights, [b.height(x, y) for x, y in far])
        self.assertTrue(all(0.0 <= h <= LAND["height"] + 0.01 for h in heights))
        self.assertGreater(len(set(round(h, 3) for h in heights)), 1)

    def test_the_rim_rises_but_not_for_ever(self):
        rim = land_mod.Land(LAND)
        top = LAND["height"]
        self.assertLess(max(rim.height(-x, 24) for x in range(1, 60)), top + 1.5 + top * 0.5 + 0.01)

    def test_a_pad_is_flat_and_the_map_stands_on_it(self):
        lv = land_level(rows=["#####", "#...#", "#.@.#", "#...#", "##.##"], land={"at": [20, 20], "start": None})
        self.assertEqual((lv.player.x, lv.player.y), (22, 22))
        self.assertEqual(lv.cell(20, 20).kind, "wall")
        self.assertEqual({lv.ground(x, y) for x in range(21, 24) for y in range(21, 24)}, {0.0})
        self.assertIn((22, 22), lv.land.stamp)
        self.assertNotIn((10, 10), lv.land.stamp)
        self.assertTrue(lv.cell(10, 10).sky)

    def test_ground_between_cells_is_smooth(self):
        lv = land_level()
        a, b = lv.ground(10, 10), lv.ground(11, 10)
        mid = lv.ground(10.5, 10)
        self.assertGreaterEqual(mid, min(a, b) - 1e-6)
        self.assertLessEqual(mid, max(a, b) + 1e-6)


class RuleTests(unittest.TestCase):
    def setUp(self):
        self.lv = land_level()

    def test_deep_water_and_cliffs_stop_a_walker(self):
        lv = self.lv
        for kind in ("deep", "steep"):
            spots = cells(lv, lambda c, k=kind: getattr(c, k))
            self.assertTrue(spots, "the test land has %s cells" % kind)
            for x, y in spots:                                # stand by one, facing it
                for f, (dx, dy) in enumerate(fp.DIRS):
                    c = lv.cell(x - dx, y - dy)
                    if not (c.solid or c.deep or c.steep or c.toxic):
                        put(lv, x - dx, y - dy, f)
                        lv.run_line("k")
                        self.assertEqual((lv.player.x, lv.player.y), (x - dx, y - dy))
                        self.assertIn("Too deep to wade." if kind == "deep" else "Too steep to climb.", told(lv))
                        self.assertFalse(lv.passable(x, y))
                        self.assertTrue(lv.passable(x, y, floats=True))   # a drone floats over
                        break
                else:
                    continue
                break

    def test_a_hill_between_hides(self):
        lv = self.lv
        found = None
        for y in range(4, 44):
            for x in range(4, 36):
                ends = max(lv.ground(x, y), lv.ground(x + 10, y))
                if max(lv.ground(x + i, y) for i in range(1, 10)) > ends + 2.5 \
                        and not lv.cell(x, y).solid and not lv.cell(x + 10, y).solid:
                    found = (x, y)
                    break
            if found:
                break
        self.assertIsNotNone(found, "the test land has a ridge")
        x, y = found
        self.assertFalse(lv.line_of_sight(x, y, x + 10, y))
        flat = [(x, y) for (x, y) in cells(lv, lambda c: not c.solid)
                if all(abs(lv.ground(x + i, y) - lv.ground(x, y)) < 0.2 for i in range(6))]
        self.assertTrue(flat)
        fx_, fy_ = flat[0]
        self.assertTrue(lv.line_of_sight(fx_, fy_, fx_ + 5, fy_))

    def test_things_and_scatter_are_put_where_they_are_asked(self):
        spec = {"things": [{"at": [20, 20], "item": "medkit"}, {"at": [30, 22], "monster": "scout"},
                           {"at": [25, 25], "item": "armor", "secret": True}],
                "scatter": [{"monster": "hornet", "count": 5, "on": ["water", "deep water"], "away": 4},
                            {"item": "stimpack", "count": 6, "away": 9}]}
        a, b = land_level(spec), land_level(spec)
        place = lambda lv: sorted((m.kind, m.x, m.y) for m in lv.monsters) + sorted((i.iid, i.x, i.y) for i in lv.items)  # noqa: E731
        self.assertEqual(place(a), place(b))                  # the same every time
        self.assertTrue(any((i.iid, i.x, i.y) == ("medkit", 20, 20) for i in a.items))
        self.assertTrue(any((m.kind, m.x, m.y) == ("scout", 30, 22) for m in a.monsters))
        hornets = [m for m in a.monsters if m.kind == "hornet"]
        self.assertEqual(len(hornets), 5)
        self.assertTrue(all(a.land.biome_of(m.x, m.y) in ("water", "deep water") for m in hornets))
        stims = [i for i in a.items if i.iid == "stimpack"]
        self.assertEqual(len(stims), 6)
        self.assertTrue(all(math.hypot(i.x - 24, i.y - 24) >= 9 for i in stims))
        self.assertTrue(all(not (a.cell(i.x, i.y).deep or a.cell(i.x, i.y).steep) for i in stims))
        self.assertEqual(a.total_secrets, 1)

    def test_a_flyer_running_dry_glides_to_firm_ground(self):
        lv = self.lv
        deep = cells(lv, lambda c: c.deep)
        x, y = deep[len(deep) // 2]
        hop = lv.add_monster("hopper_fens", x, y)
        lv.board(hop)
        hop.started, hop.fuel = True, 1
        lv.fuel_beat()
        here = lv.cell(lv.player.x, lv.player.y)
        self.assertFalse(here.deep or here.steep or here.toxic)
        self.assertIn("glides down", told(lv))
        self.assertTrue(lv.leave())                           # and one can climb out there


class PictureTests(unittest.TestCase):
    def test_nearer_paint_wins(self):
        v = fp.View(40, 10, "pixel")
        row = land_mod.DepthRow([(0, 0, 0)] * 4)
        row.depth, row.view = [10.0, 10.0, 3.0, 3.0], v
        v.cur_z = 5.0
        for i in range(4):
            row[i] = (255, 0, 0)
        self.assertEqual(row, [(255, 0, 0), (255, 0, 0), (0, 0, 0), (0, 0, 0)])

    def test_a_land_view_has_sky_above_and_ground_below(self):
        lv = Level(GameData(ROOTLESS), "e1m4", seed=1)
        v = fp.View(120, 26, "pixel")
        put(lv, 16, 80, 1)
        rows = v.render(lv, fp.FX(), 0)
        self.assertEqual((len(rows[0]), len(rows)), (120, 26))
        sky, ground = rows[1][60], rows[-3][30]
        self.assertNotEqual(sky, ground)
        self.assertIsNotNone(v.air)                           # far things go into the haze
        haze, vis = v.air
        tone = v.toner(vis * 5, 1.0)
        far = tone((255, 0, 0), 0, 0)
        self.assertLess(sum(abs(a - b) for a, b in zip(far, haze)), 40)
        v2 = fp.View(120, 26, "pixel")
        v2.render(Level(GameData(ROOTLESS), "e1m1", seed=1), fp.FX(), 0)
        self.assertIsNone(v2.air)                             # indoors: as before, darker with the distance

    def test_the_land_brings_its_props_and_landmarks(self):
        lv = Level(GameData(ROOTLESS), "e1m4", seed=1)
        pics, mdls = lv.land.uses()
        self.assertIn("prop_reeds", pics)
        self.assertIn("relay_mast", mdls)
        self.assertTrue(all(p in lv.sprites for p in pics))
        self.assertTrue(all(m in lv.models for m in mdls))

    def test_the_mast_is_on_the_map_from_the_start(self):
        from engine.level import KEYMAP, FrameConsole
        from engine.term import Term
        lv = Level(GameData(ROOTLESS), "e1m4", seed=1)
        put(lv, 95, 21, 0)
        term = Term(out=io.StringIO(), inp=lambda p: "", width=120, height=40, color=3, unicode=True, animate=False, env={})
        con = FrameConsole(term, "pixel", keys=False, keymap=KEYMAP, animate=False)
        text = "".join(con.automap(lv, 120, 40))
        self.assertNotIn((95, 8), lv.seen_cells)
        self.assertIn("230;90;70", text)                      # seen from afar: on the map before one gets there
        self.assertTrue(lv.cell(95, 8).steep)                 # and solid: a walker goes round it


class CheckTests(unittest.TestCase):
    def check(self, spec):
        data = with_level(spec)
        return [p for p in validate(data) if "'t'" in p]

    def test_a_land_level_needs_no_map(self):
        self.assertEqual(self.check({"land": dict(LAND, things=[{"at": [5, 5], "item": "medkit"}]),
                                     "legend": {"E": {"exit": True}}, "map": ["E"]}), [])
        self.assertEqual(self.check({"land": dict(LAND, things=[{"at": [3, 3], "monster": "hopper"}])}), [])

    def test_what_is_wrong_with_a_land(self):
        bad = self.check({"land": dict(LAND, edge="cliff", start=None, size=[3, 3],
                                       things=[{"at": [1, 1], "monster": "dragon"}],
                                       landmarks=[{"at": [1, 1], "model": "nothing"}])})
        text = " | ".join(bad)
        self.assertIn("edge should be", text)
        self.assertIn("size should be", text)
        self.assertIn("unknown monster 'dragon'", text)
        self.assertIn("no model 'nothing'", text)
        self.assertIn("give the land a \"start\"", text)
        both = self.check({"land": LAND, "map": ["@E"]})
        self.assertIn("not both", " | ".join(both))


class FensTests(unittest.TestCase):
    def test_e1m4_checks_out(self):
        data = GameData(ROOTLESS)
        self.assertEqual([p for p in validate(data) if "e1m4" in p], [])
        lv = Level(data, "e1m4", seed=0)
        self.assertEqual((lv.w, lv.h), (112, 112))
        self.assertEqual((lv.player.x, lv.player.y), (16, 80))
        self.assertEqual(lv.total_secrets, 1)
        self.assertGreater(len(lv.monsters), 30)

    def test_the_bot_crosses_the_fens(self):
        data = GameData(ROOTLESS)
        for seed in (0, 1):                                   # tests/levelbot.py 10 rootless e1m4 for more
            outcome, lv = levelbot.play(data, "e1m4", seed)
            self.assertEqual(outcome, "exit", "seed %d" % seed)
            self.assertEqual((lv.player.x, lv.player.y), (95, 12))
            self.assertIsNone(lv.player.vehicle)

    def test_the_bot_way_is_quick(self):
        """The bot's way over open land is worked out once from the goal, not each beat."""
        lv = Level(GameData(ROOTLESS), "e1m4", seed=0)
        bot = levelbot.Bot(lv, ["E"])
        first = bot.go(lv, 95, 12)
        self.assertIn(first, ("k", "turn left", "turn right", "turn around"))
        self.assertEqual(len(bot.fields), 1)
        bot.go(lv, 95, 12)
        self.assertEqual(len(bot.fields), 1)


if __name__ == "__main__":
    unittest.main()
