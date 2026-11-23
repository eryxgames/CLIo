# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Panels (engine/panels.py): the layout, each widget, colours that warn, lamps and conditions, plots
over time, scopes (a scene, a model that comes into sight), a host's map, pulsing with a cue, what
is wrong in a layout - and a simulator with a screen of its own, and the station starter."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from engine import panels as P  # noqa: E402
from engine import sim as S  # noqa: E402
from engine.data import GameData  # noqa: E402
from engine.realtime import Controls  # noqa: E402
from engine.term import strip_ansi  # noqa: E402

STATION = os.path.join(ROOT, "templates", "station")
ENV = {"heat": 900.0, "flow": 15.0, "rods": 40.0, "drift": -5.0, "power": 62.5, "top": 1200.0, "bearing": 90.0}
CORE = {"title": "CORE", "widgets": [
    {"gauge": "heat", "max": "top", "warn": 0.7, "hot": 0.9, "unit": "K"},
    {"gauge": "flow", "max": 100, "warn": -0.2},
    {"control": "rods", "max": 100, "keys": ["up", "down"]},
    {"center": "drift", "max": 10},
    {"rule": True},
    {"number": "power", "unit": "%"},
    {"space": 1},
    {"lamps": [{"label": "COOLANT", "if": "flow > 20"}, {"label": "GRID", "if": "power > 50", "tone": "good"},
               {"label": "SCRAM", "if": "rods > 95", "tone": "hot"}]},
    {"text": "CORE {heat:.0f} K, {missing} more", "tone": "warn"},
    {"text": "only when hot", "when": "heat > 1000"}]}


def view(spec, **kw):
    return P.View(spec, S.formula, **kw)


def cell(rows, text, y):
    """The colour of the first cell of ``text`` in row ``y``."""
    line = "".join(c[0] or "▀" for c in rows[y])
    return rows[y][line.index(text)][1]


class LayoutTests(unittest.TestCase):
    def test_room_is_shared_by_size_and_weight(self):
        self.assertEqual(P.split([{"size": 10}, {}, {}], 30), [10, 10, 10])
        self.assertEqual(P.split([{}, {"weight": 3}], 40), [10, 30])
        self.assertEqual(P.split([{"size": 20}, {"size": 20}, {}], 30), [20, 10, 0])  # too much: the last give way
        self.assertEqual(sum(P.split([{}, {}, {}], 31)), 31)
        self.assertEqual(P.split([], 10), [])

    def test_panels_side_by_side_and_one_over_another(self):
        spec = {"rows": [{"size": 3, "title": "TOP", "widgets": [{"text": "hello"}]},
                         {"cols": [{"title": "A", "size": 12}, {"title": "B", "border": "double", "colour": "amber"}]}]}
        text = view(spec).plain(30, 8, {})
        self.assertEqual(text, ["┌─ TOP ──────────────────────┐", "│ hello                      │",
                                "└────────────────────────────┘", "┌─ A ──────┐╔═ B ════════════╗",
                                "│          │║                ║", "│          │║                ║",
                                "│          │║                ║", "└──────────┘╚════════════════╝"])
        rows = view(spec).rows(30, 8, {})
        self.assertEqual((rows[0][0][1], rows[3][12][1]), (P.shade((70, 255, 140), 0.55), P.shade((255, 176, 40), 0.55)))
        self.assertEqual(rows[0][3][1], P.bright((70, 255, 140)))            # a title is brighter than its frame
        self.assertEqual(view({"title": "X"}).plain(3, 1, {}), [""])         # no room: nothing, and no trouble


class WidgetTests(unittest.TestCase):
    def test_each_widget_in_a_panel(self):
        text = view(CORE).plain(40, 14, ENV)
        self.assertEqual(text, [
            "┌─ CORE ───────────────────────────────┐",
            "│ HEAT  ████████████████░░░░░░    900K │",
            "│ FLOW  ███░░░░░░░░░░░░░░░░░░░      15 │",
            "│ RODS  ↑/↓ ███████░░░░░░░░░░░      40 │",
            "│ DRIFT ░░░░░██████│░░░░░░░░░░    -5.0 │",
            "│ ──────────────────────────────────── │",
            "│ POWER                         62.5 % │",
            "│                                      │",
            "│ ○ COOLANT  ● GRID  ○ SCRAM           │",
            "│ CORE 900 K, 0.0 more                 │",
            "│                                      │",
            "│                                      │",
            "│                                      │",
            "└──────────────────────────────────────┘"])
        hot = dict(ENV, heat=1150.0, flow=50.0, rods=100.0)
        text = view(CORE).plain(40, 14, hot)
        self.assertIn("● COOLANT  ● GRID  ● SCRAM", text[8])
        self.assertIn("only when hot", text[10])

    def test_colours_that_warn(self):
        rows = view(CORE).rows(40, 14, ENV)
        ink = (70, 255, 140)
        self.assertEqual(cell(rows, "█", 1), P.TONES["warn"])                 # heat at 75% of the way
        self.assertEqual(cell(rows, "█", 2), P.TONES["warn"])                 # flow under a fifth
        self.assertEqual(cell(rows, "█", 3), ink)
        self.assertEqual(cell(rows, "HEAT", 1), P.shade(ink, 0.45))
        self.assertEqual((cell(rows, "○ COOLANT", 8), cell(rows, "● GRID", 8)), (P.shade(ink, 0.45), P.TONES["good"]))
        self.assertEqual(cell(rows, "CORE 900", 9), P.TONES["warn"])
        rows = view(CORE).rows(40, 14, dict(ENV, heat=1150.0, rods=100.0))
        self.assertEqual((cell(rows, "█", 1), cell(rows, "● SCRAM", 8)), (P.TONES["hot"], P.TONES["hot"]))

    def test_a_number_in_letters_of_lines_and_a_compass(self):
        spec = {"widgets": [{"number": "power", "big": True, "unit": "%", "label": "output"}, {"compass": "bearing"}]}
        text = view(spec).plain(30, 6, ENV)
        self.assertEqual(text[1:5], ["│ OUTPUT        ┏━╸╺━┓ ┏━╸   │", "│               ┣━┓┏━┛ ┗━┓   │",
                                     "│               ┗━┛┗━╸╹╺━┛ % │", "│  N  ·  ·  E  ·  ·  S   90° │"])
        plain = view(spec).plain(30, 6, ENV, unicode=False)
        self.assertEqual(plain[1], "| OUTPUT              62.5 % |")
        self.assertTrue(all(ch.isascii() for line in plain for ch in line))
        self.assertTrue(all(ch.isascii() for line in view(CORE).plain(40, 14, ENV, unicode=False) for ch in line))

    def test_lamps_wrap_and_long_text_wraps(self):
        spec = {"widgets": [{"lamps": [{"label": "ALPHA"}, {"label": "BRAVO"}, {"label": "CHARLIE"}]},
                            {"text": "one two three four five six", "align": "center"}]}
        text = view(spec).plain(22, 7, {})
        self.assertEqual(text[1:5], ["│ ● ALPHA  ● BRAVO   │", "│ ● CHARLIE          │", "│ one two three four │",
                                     "│      five six      │"])

    def test_plots_over_time(self):
        spec = {"widgets": [{"plot": ["heat", "flow"], "rows": 3, "min": 0, "max": 100}]}
        v = view(spec)
        self.assertEqual(v.plotted, ["flow", "heat"])
        for i in range(40):
            rows = v.rows(24, 5, {"heat": i * 2.5, "flow": 50.0})
        self.assertEqual(len(v.history["heat"]), 40)
        text = ["".join(c[0] for c in r) for r in rows]
        self.assertIn("HEAT 97.5  FLOW 50", text[1])
        dots = [c for r in rows[1:4] for c in r if 0x2800 < ord(c[0]) < 0x2900]
        self.assertGreater(len(dots), 15)
        self.assertEqual({c[1] for c in dots}, {(70, 255, 140), P.TONES["warn"]})   # a colour a line
        for _ in range(P.KEEP + 50):
            v.rows(24, 5, {"heat": 1.0, "flow": 2.0})
        self.assertEqual(len(v.history["heat"]), P.KEEP)
        plain = v.plain(24, 5, {"heat": 1.0, "flow": 2.0}, unicode=False)
        self.assertEqual(plain[1][2], "_")
        self.assertTrue(all(ch.isascii() for line in plain for ch in line))

    def test_a_scope_with_a_scene_and_with_a_model_that_comes_into_sight(self):
        from engine import model
        models = model.load(GameData(STATION).models)
        spec = {"colour": "cyan", "widgets": [{"scope": {"model": "mast", "reveal": "scan", "whole": 100}}]}
        v = view(spec, models=models)

        def lit(rows):
            return sum(1 for r in rows for c in r if c[0] and 0x2800 < ord(c[0]) < 0x2900)
        none, half, whole = (lit(v.rows(60, 24, {"scan": k}, 3.0)) for k in (0.0, 50.0, 100.0))
        self.assertLess(none, half)
        self.assertLess(half, whole)
        self.assertGreater(whole, 100)
        self.assertNotEqual(v.rows(60, 24, {"scan": 100.0}, 3.0), v.rows(60, 24, {"scan": 100.0}, 9.0))   # it turns
        wire = v._wire("mast")
        cut = P.below(wire, wire.mid)
        self.assertTrue(all(cut.verts[i][2] <= wire.mid + 1e-9 for e in cut.edges for i in e))
        self.assertLess(len(cut.edges), len(wire.edges))
        self.assertGreater(lit(view({"widgets": [{"scope": {"model": "no such"}}]}).rows(40, 16, {})), 10)   # a box
        big = "\n".join(view({"widgets": [{"scope": "orbit"}]}).plain(80, 24, {}, 2.0))
        small = "\n".join(view({"widgets": [{"scope": "orbit"}]}).plain(40, 14, {}, 2.0))
        self.assertIn("PERIAPSIS", big)
        self.assertNotIn("PERIAPSIS", small)                                 # too small for a scene's words
        self.assertTrue(all(ch.isascii() for line in view({"widgets": [{"scope": "scan"}]}).plain(60, 20, {}, 2.0, unicode=False)
                            for ch in line))

    def test_what_the_host_draws_and_a_frame_that_moves_with_the_sound(self):
        spec = {"pulse": "bar", "widgets": [{"map": True}]}
        tile = [[("#", (1, 2, 3), (4, 5, 6))] * 4] * 2
        rows = view(spec).rows(12, 6, {}, parts={"map": lambda w, h: tile})
        self.assertEqual(rows[1][2], ("#", (1, 2, 3), (4, 5, 6)))
        self.assertIn("NO MAP", view(spec).plain(12, 6, {})[1])
        quiet = view(spec).rows(12, 6, {}, level=lambda action: 0.0)[0][0][1]
        loud = view(spec).rows(12, 6, {}, level=lambda action: 1.0 if action == "bar" else 0.0)[0][0][1]
        self.assertGreater(sum(loud), sum(quiet))
        self.assertEqual(view(spec).rows(12, 6, {}, level=lambda action: 1 / 0)[0][0][1], quiet)


class CheckTests(unittest.TestCase):
    def test_what_is_wrong_in_a_layout_is_said(self):
        bad = {"colour": "pink", "border": "wavy", "rows": [
            {"cols": [], "widgets": []},
            {"widgets": [{"gauge": "nope", "max": "also_nope"}, {"dial": 1}, {"plot": ["heat", "gone"]},
                         {"lamps": [{"if": "heat >"}, {"label": "A", "if": "heat > (", "tone": "blue"}]},
                         {"scope": "wormhole"}, {"scope": {}}, {"scope": {"model": "ghost", "reveal": "gone"}},
                         {"text": "x", "when": "1 +"}, {"lamps": 3}]},
            7]}
        text = "\n".join(P.problems(bad, {"heat"}, "sim 'x': panels", S.formula, {"mast": {}}))
        for part in ("sim 'x': panels: unknown colour 'pink' (green, amber,", "sim 'x': panels: unknown border 'wavy'",
                     "panels row 1: one of \"rows\", \"cols\" or \"widgets\"", "panels row 1: \"cols\" should be a list of panels",
                     "row 2 widget 1: there is no value called 'nope'", "row 2 widget 1: there is no value called 'also_nope'",
                     "row 2 widget 2: it should be one of gauge, center, number,", "row 2 widget 3: there is no value called 'gone'",
                     "row 2 widget 4: a lamp needs a \"label\"", "row 2 widget 4 lamp 'A': unknown tone 'blue'",
                     "row 2 widget 5: unknown scene 'wormhole' (hauler, approach, orbit, scan, signals)",
                     "row 2 widget 6: a scope needs a \"scene\" or a \"model\"", "row 2 widget 7: there is no model called 'ghost'",
                     "row 2 widget 7: there is no value called 'gone'", "row 2 widget 9: \"lamps\" should be a list",
                     "panels row 3: it should be a map"):
            self.assertIn(part, text)
        self.assertIn("row 2 widget 4 lamp 'A':", text)
        self.assertIn("row 2 widget 8:", text)
        self.assertEqual(P.problems(P.SAMPLE), [])
        self.assertEqual(P.problems([], None), ["panels: it should be a map"])


class SimTests(unittest.TestCase):
    def test_a_sim_with_a_screen_of_its_own(self):
        data = GameData(STATION)
        self.assertEqual(data.validate(), [])
        sim = S.make(data, "reactor")
        runner = S.Runner(sim)
        sim.paused = None
        for i in range(60):
            sim.step(Controls(i, held=("up",)))
        before = sim.state_hash()
        rows = runner.rows(100, 33, 3, True)
        text = "\n".join("".join(c[0] or "▀" for c in r) if isinstance(r, list) else strip_ansi(r) for r in rows)
        for part in ("REACTOR  bring the core to power", "─ CORE ─", "─ SHIP  heat ─", "RODS OUT ↑/↓", "HOLDING", "○ AT POWER",
                     "HEAT ", "POWER "):
            self.assertIn(part, text)
        self.assertEqual(sim.state_hash(), before)                           # a screen changes nothing under it
        small = "\n".join(strip_ansi(r) if isinstance(r, str) else "".join(c[0] or " " for c in r) for r in runner.rows(50, 16, 3, True))
        self.assertNotIn("─ CORE ─", small)                                  # no room: the instruments as ever
        self.assertIn("HEAT", small)
        helm = S.Runner(S.make(data, "helm"))
        text = "\n".join("".join(c[0] or "▀" for c in r) if isinstance(r, list) else strip_ansi(r) for r in helm.rows(100, 33, 3, True))
        for part in ("─ SURFACE ─", "─ FLIGHT ─", "─ APPROACH ─", "TO THE MARK", "FUEL"):
            self.assertIn(part, text)
        self.assertIn("│", text.splitlines()[16][:2])                       # the word in the middle lies over the panels

        class Sounding:                                                      # a track that plays: the frames move to it
            def cues(self):
                from engine import cues
                return cues.Sheet({"format": "playhead-cues", "source": {"duration": 4.0},
                                   "cues": [{"t": 0.0, "length": 4.0, "action": "bar", "shape": "hold"}]})

            def clock(self):
                return 1.0
        quiet = S.Runner(S.make(data, "reactor")).rows(100, 33, 3, True)[5][0][1]
        loud = S.Runner(S.make(data, "reactor"), audio=Sounding()).rows(100, 33, 3, True)[5][0][1]
        self.assertGreater(sum(loud), sum(quiet))

    def test_the_station_starter_can_be_won_and_its_panels_are_checked(self):
        data = GameData(STATION)
        for sid in ("helm", "reactor", "scan"):
            sim = S.make(data, sid)
            S.fly(sim)
            self.assertEqual(sim.result, "won", sid)
        data.sims["scan"]["panels"]["cols"][0]["rows"][0]["widgets"][0]["gauge"] = "mst"
        self.assertEqual([p for p in data.validate() if "panels" in p],
                         ["sim 'scan': panels col 1 row 1 widget 1: there is no value called 'mst'"])

    def test_the_station_starter_at_a_prompt(self):
        from helpers import Session
        s = Session("templates/station").start()
        text = s.do("go scan", "status", "quit")
        self.assertIn("BEAM", text)
        self.assertEqual(s.game.world.scene.get("id"), "bridge")
        self.assertEqual((s.game.ui.menu_look, s.game.ui.menus), ("terminal", "bar"))


if __name__ == "__main__":
    unittest.main()
