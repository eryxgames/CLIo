# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Views (engine/viewer.py): the colour of a heat, a wire cut by a plane, a model ready to be seen and its
six views, a planet and its three, what is wrong in planets.json, the viewer's keys, the command line -
and views in a panel's scope."""
import contextlib
import io
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from engine import model, vector  # noqa: E402
from engine import viewer as V  # noqa: E402
from engine.data import GameData  # noqa: E402
from engine.keys import ScriptedKeys  # noqa: E402
from engine.term import Term, strip_ansi  # noqa: E402

STATION = os.path.join(ROOT, "templates", "station")
DATA = GameData(STATION)
MODELS = model.load(DATA.models)
HAULER = V.Subject(MODELS["hauler"])
MOON = V.Planet(DATA.planets["moon"], "moon")


def dots(rows):
    return sum(bin(ord(c[0]) - 0x2800).count("1") for r in rows for c in r if c[0] and 0x2800 < ord(c[0]) < 0x2900)


def pixels(rows):
    return [c for r in rows for c in r if c[0] is None]


class PieceTests(unittest.TestCase):
    def test_the_colour_of_a_heat(self):
        self.assertEqual((V.thermal(0), V.thermal(1), V.thermal(-3), V.thermal(9)), ((8, 8, 40), (255, 250, 220)) * 2)
        self.assertEqual(V.thermal(0.5), (190, 45, 95))
        heats = [sum(V.thermal(k / 10.0)) for k in range(11)]
        self.assertEqual(heats, sorted(heats))                               # hotter is brighter, all the way

    def test_a_wire_cut_by_a_plane(self):
        box = vector.box((2.0, 2.0, 2.0))
        low = V.cut(box, 2, 0.0)
        self.assertEqual(len(low.edges), 4 + 4)                              # the bottom, and half of each upright
        self.assertTrue(all(low.verts[i][2] <= 1e-9 for e in low.edges for i in e))
        high = V.cut(box, 2, 0.0, 1)
        self.assertTrue(all(high.verts[i][2] >= -1e-9 for e in high.edges for i in e))
        self.assertEqual(len(V.cut(box, 0, 5.0).edges), 12)                  # all of it is under
        self.assertEqual(V.cut(box, 0, -5.0).edges, [])

    def test_a_model_made_ready(self):
        self.assertEqual(HAULER.groups, ["body", "decks", "hold", "reactor", "bridge", "engines"])
        self.assertEqual([name for name, _w in HAULER.parts], HAULER.groups)
        self.assertEqual([round(c, 2) for c in HAULER.half], [1.2, 4.01, 0.9])
        cam = HAULER.camera(0, 0, 1.0, 120, 80)
        scope = vector.Scope(60, 20)
        ends = [scope.project(cam, p) for p in (HAULER.low, HAULER.high)]
        self.assertTrue(all(0 <= x <= scope.W and 0 <= y <= scope.H for x, y, _d in ends))       # all of it in sight


class ModelViewTests(unittest.TestCase):
    def test_lines_all_of_them_and_only_those_in_front(self):
        wire, solid = dots(V.draw(HAULER, "wire", 60, 20)), dots(V.draw(HAULER, "solid", 60, 20))
        self.assertGreater(wire, 600)
        self.assertLess(solid, wire * 0.75)                                  # what is inside is hidden
        self.assertEqual(V.draw(HAULER, "no such", 30, 10), V.draw(HAULER, "shaded", 30, 10))
        plain = V.draw(HAULER, "solid", 60, 20, unicode=False)
        self.assertTrue(all(c[0].isascii() for r in plain for c in r))

    def test_what_is_inside_in_colours_and_cut_open(self):
        rows = V.draw(HAULER, "structure", 60, 20)
        colours = {c[1] for r in rows for c in r if c[0] != " "}
        self.assertGreater(len(colours), 6)                                  # a colour a group (and their shades)
        whole, half = dots(rows), dots(V.draw(HAULER, "structure", 60, 20, cut_at=0.5, axis=0))
        self.assertLess(half, whole)
        self.assertGreater(half, 100)
        self.assertNotEqual(V.draw(HAULER, "structure", 60, 20, cut_at=0.5, axis=0), V.draw(HAULER, "structure", 60, 20, cut_at=0.5, axis=2))
        self.assertLess(dots(V.draw(HAULER, "structure", 60, 20, cut_at=1.0)), 80)   # all cut away: the plane alone

    def test_a_plan_floor_by_floor(self):
        whole = V.draw(HAULER, "plan", 60, 20, yaw=0.0)
        lower, upper = (V.draw(HAULER, "plan", 60, 20, yaw=0.0, levels=2, level=n) for n in (0, 1))
        self.assertNotEqual(lower, upper)
        self.assertGreater(dots(whole), dots(lower))
        text = V.plain(whole)
        used = [len(line) for line in text if line.strip()]
        self.assertGreater(max(used), 2 * len(used))                         # it lies along the screen
        tall = V.plain(V.draw(HAULER, "plan", 20, 30, yaw=0.0))
        self.assertGreater(len([l for l in tall if l.strip()]), 16)          # and stands up in a tall one
        self.assertEqual(V.draw(HAULER, "plan", 60, 20, yaw=0.0, levels=2, level=9), upper)
        self.assertNotEqual(V.draw(HAULER, "plan", 60, 20, yaw=90.0), whole)

    def test_shaded_and_by_heat(self):
        shaded = V.draw(HAULER, "shaded", 60, 20)
        self.assertGreater(len(pixels(shaded)), 200)
        self.assertGreater(len({c[1] for c in pixels(shaded)}), 5)           # lit: several shades
        cold = V.draw(HAULER, "heat", 60, 20, values={})
        hot = V.draw(HAULER, "heat", 60, 20, values={"reactor": 1.0, "engines": 0.7})
        self.assertLess(max(sum(c[1]) for c in pixels(cold)), 200)
        self.assertGreater(max(sum(c[1]) for c in pixels(hot)), 500)         # the core shows through the hull
        self.assertNotEqual(V.draw(HAULER, "heat", 60, 20), cold)            # no values: by its groups, for a look
        mast = V.Subject(MODELS["mast"])                                     # one group: the hull is all there is
        self.assertGreater(len(pixels(V.draw(mast, "heat", 40, 20, values={"body": 0.5}))), 20)
        plain = V.draw(HAULER, "shaded", 60, 20, unicode=False)
        self.assertEqual(pixels(plain), [])
        self.assertTrue(any(c[0] not in " " for r in plain for c in r))
        hopper = V.Subject(MODELS["hopper"])                                 # its fans turn: it moves with the time
        self.assertNotEqual(V.draw(hopper, "shaded", 40, 16, t=0.0), V.draw(hopper, "shaded", 40, 16, t=0.4))


class PlanetTests(unittest.TestCase):
    def test_the_ground_at_a_place(self):
        self.assertEqual(MOON.at(89, 0)[0], "methane ice")
        self.assertEqual(MOON.at(-89, 200)[0], "methane ice")
        self.assertEqual(MOON.at(0, 30)[0], "hot ground")
        self.assertEqual(MOON.at(0, 30 + 360)[0], "hot ground")
        self.assertEqual(V.Planet({}).at(0, 0), (".", (120, 120, 120), 0.5))
        self.assertEqual((MOON.name, len(MOON.sites)), ("Gordian Moon", 2))

    def test_lit_by_its_sun_by_its_heat_and_as_a_grid(self):
        surface = V.draw_planet(MOON, "surface", 40, 20, turn=0.0)
        px = pixels(surface)
        self.assertGreater(len(px), 350)
        left = [sum(c[1]) for r in surface for c in r[:14] if c[0] is None]
        right = [sum(c[1]) for r in surface for c in r[26:] if c[0] is None]
        self.assertGreater(sum(right) / len(right), 3 * sum(left) / len(left))   # the sun is to the right: night to the left
        heat = V.draw_planet(MOON, "heat", 40, 20, turn=0.0)
        self.assertIn(V.thermal(0.05)[2] > 0, (True,))
        top, mid = heat[1], heat[10]
        self.assertLess(max(sum(c[1]) for c in top if c[0] is None), max(sum(c[1]) for c in mid if c[0] is None))   # cold poles
        self.assertNotEqual(V.draw_planet(MOON, "surface", 40, 20, turn=0.0), V.draw_planet(MOON, "surface", 40, 20, turn=90.0))
        self.assertNotEqual(V.draw_planet(MOON, "surface", 40, 20, t=0.0), V.draw_planet(MOON, "surface", 40, 20, t=5.0))
        grid = V.draw_planet(MOON, "grid", 40, 20, turn=0.0)
        self.assertGreater(dots(grid), 300)
        self.assertEqual(V.draw_planet(MOON, "no such", 40, 20, turn=0.0), surface)
        plain = V.draw_planet(MOON, "surface", 40, 20, turn=0.0, unicode=False)
        self.assertTrue(all(c[0].isascii() for r in plain for c in r))

    def test_places_on_the_near_side_are_named(self):
        text = "\n".join(V.plain(V.draw_planet(MOON, "grid", 44, 20, turn=0.0)))
        self.assertIn("┼ EREBUS", text)
        self.assertNotIn("FER", text)                                        # on the far side
        self.assertIn("┼ FER", "\n".join(V.plain(V.draw_planet(MOON, "heat", 44, 20, turn=-150.0))))
        self.assertIn("+ EREBUS", "\n".join(V.plain(V.draw_planet(MOON, "surface", 44, 20, turn=0.0, unicode=False))))

    def test_what_is_wrong_in_planets_json_is_said(self):
        self.assertEqual(DATA.validate(), [])

        class Data:
            planets = {"a": {"field": ["ab", "cd"], "legend": {"a": "#ffffff", "b": {"heat": 3}}, "colour": "pink",
                             "sites": [{"name": "X"}, {"name": "Y", "lat": 1, "lon": 2}]},
                       "b": {"field": []}, "c": 7}
        text = "\n".join(V.planet_problems(Data()))
        for part in ("planet 'a': the field has characters the legend does not explain: c d",
                     "planet 'a': the heat of 'b' should be from 0 to 1", "planet 'a': unknown colour 'pink'",
                     "planet 'a': a site needs a \"name\", a \"lat\" and a \"lon\"", "planet 'b': it needs a \"field\"",
                     "planet 'c': it should be a map"):
            self.assertIn(part, text)
        self.assertEqual(text.count("a site needs"), 1)
        Data.planets = []
        self.assertEqual(V.planet_problems(Data()), [])
        Data.planets = [1]
        self.assertEqual(V.planet_problems(Data()), ["planets.json should be a map of planets by name"])


class LookTests(unittest.TestCase):
    def test_the_keys_of_the_viewer(self):
        look = V.Look(V.things_of(DATA))
        self.assertEqual([th.name for th in look.things], ["mast", "hopper", "hauler", "Gordian Moon"])
        for k in ("tab", "tab"):
            look.key(k)
        self.assertEqual((look.thing.name, look.views()), ("hauler", V.VIEWS))
        look.key("right")
        self.assertEqual((look.yaw, look.turning), (40.0, False))
        look.key("up")
        look.key("+")
        self.assertEqual((look.pitch, round(look.zoom, 2)), (30.0, 1.2))
        look.key("4")
        self.assertIn("structure (4/6)  C cuts it", look.status())
        for k in ("c", "]", "x"):
            look.key(k)
        self.assertEqual((round(look.cut, 1), look.axis), (0.6, 2))
        self.assertIn("cut z at 60%", look.status())
        look.key("v")
        look.key("l")
        look.key(".")
        look.key(".")
        self.assertEqual((look.views()[look.view], look.levels, look.level), ("plan", 2, 1))
        self.assertIn("level 2 of 2", look.status())
        rows = look.rows(60, 20, 0.0)
        self.assertGreater(dots(rows), 100)
        look.key("v")
        self.assertIn("by group: body decks", look.status())
        look.key("n")
        self.assertEqual((look.thing.name, look.views()[look.view]), ("Gordian Moon", "grid"))    # its last view
        self.assertGreater(dots(look.rows(40, 20, 1.0)), 200)
        look.key("space")
        look.key("q")
        self.assertEqual((look.turning, look.over), (True, True))

    def test_on_a_terminal(self):
        out = io.StringIO()
        term = Term(out=out, width=80, height=24, color=3, unicode=True, animate=False, env={})
        clock = iter(range(100))
        look = V.run(term, V.things_of(DATA), "hauler", "solid", ScriptedKeys(["v", None, "tab", None, "q"]), lambda: next(clock))
        self.assertTrue(look.over)
        text = strip_ansi(out.getvalue())
        for part in ("HAULER  solid (3/6)", "HAULER  structure (4/6)", "GORDIAN MOON  grid (3/3)", "V view  Tab next"):
            self.assertIn(part, text)
        self.assertTrue(out.getvalue().endswith("\x1b[?1049l"))
        look = V.run(term, V.things_of(DATA), frames=1, keys=ScriptedKeys([]))
        self.assertFalse(look.over)

    def test_from_the_command_line(self):
        def said(*argv):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = V.main(list(argv))
            return code, out.getvalue()
        code, text = said(STATION, "hauler", "--print", "plan")
        self.assertEqual(code, 0)
        self.assertGreater(len([l for l in text.splitlines() if l.strip()]), 5)
        code, text = said(STATION, "Gordian Moon", "--print", "grid")
        self.assertIn("EREBUS", text)
        self.assertEqual(said(STATION, "ghost")[1].strip(), "Nothing called 'ghost'. There is: mast, hopper, hauler, Gordian Moon")
        self.assertEqual(said(os.path.join(ROOT, "templates", "starter"))[1].strip(), "Nothing to look at there: no models, no planets.")
        self.assertEqual(said()[0], 2)
        self.assertIn("Looking at things needs a terminal.", said(STATION)[1])


class PanelTests(unittest.TestCase):
    def test_views_in_a_panels_scope(self):
        from engine import panels as P
        from engine import sim as S
        spec = {"cols": [
            {"widgets": [{"scope": {"model": "hauler", "view": "heat", "max": 100, "values": {"engines": "core", "hold": 50}}}]},
            {"widgets": [{"scope": {"model": "hauler", "view": "plan", "levels": 2, "level": "deck"}}]},
            {"widgets": [{"scope": {"model": "hauler", "view": "structure", "cut": "open", "whole": 100, "axis": "x"}}]},
            {"widgets": [{"planet": "moon", "view": "heat"}]},
            {"widgets": [{"scope": {"model": "ghost", "view": "wire"}}]}]}
        v = P.View(spec, S.formula, MODELS, DATA.planets)
        cold = v.rows(150, 20, {"core": 0.0, "deck": 0, "open": 0})
        hot = v.rows(150, 20, {"core": 100.0, "deck": 1, "open": 60})
        self.assertNotEqual([r[:30] for r in cold], [r[:30] for r in hot])       # the core's heat
        self.assertNotEqual([r[30:60] for r in cold], [r[30:60] for r in hot])   # the other deck
        self.assertGreater(dots([r[60:90] for r in cold]), dots([r[60:90] for r in hot]))   # cut open
        self.assertGreater(len(pixels([r[90:120] for r in cold])), 100)          # the moon
        self.assertIn("NO MODEL", "".join(c[0] or "" for c in cold[1]))
        text = "\n".join(P.problems({"widgets": [{"scope": {"model": "hauler", "view": "inside", "cut": "gone", "values": {"a": "lost"}}},
                                                 {"planet": "mars", "view": "night"}, {"planet": "moon"}]},
                                    {"core"}, "panels", S.formula, MODELS, DATA.planets))
        for part in ("widget 1: unknown view 'inside' (shaded, wire, solid, structure, plan, heat)", "widget 1: there is no value called 'gone'",
                     "widget 1: there is no value called 'lost'", "widget 2: there is no planet called 'mars'",
                     "widget 2: unknown view 'night' (surface, heat, grid)"):
            self.assertIn(part, text)
        self.assertNotIn("widget 3", text)

    def test_the_station_starter_uses_them(self):
        from engine import sim as S
        for sid, part in (("reactor", "─ SHIP  heat ─"), ("scan", "─ BELOW  surface ─")):
            runner = S.Runner(S.make(DATA, sid))
            runner.sim.paused = None                                         # no word in the middle
            rows = runner.rows(110, 34, 3, True)
            text = "\n".join("".join(c[0] or "▀" for c in r) if isinstance(r, list) else strip_ansi(r) for r in rows)
            self.assertIn(part, text)
            self.assertGreater(len([c for r in rows if isinstance(r, list) for c in r if c[0] is None]), 60)


if __name__ == "__main__":
    unittest.main()
