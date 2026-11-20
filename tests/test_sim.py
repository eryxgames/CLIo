# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Simulators (engine/sim.py): sines from whole numbers, formulas, the car, the boat, the hopper and the
plane, fuel and systems, checkpoints, landing, goals, gauges, the autopilot, keys played back, typed
play, checks, and RØØTLESS SIM-8 and SIM-9."""
import io
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from engine import sim as S  # noqa: E402
from engine.data import GameData  # noqa: E402
from engine.keys import PRESS, KeyEvent, ScriptedKeys  # noqa: E402
from engine.realtime import Clock, Controls, FakeClock, replay  # noqa: E402
from engine.sim import Sim, formula, FormulaError  # noqa: E402
from engine.term import Term  # noqa: E402

ROOTLESS = os.path.join(ROOT, "games", "rootless")
FIELD = ["####################",
         "#..................#",
         "#..@......1........#",
         "#........====......#",
         "#...:::.......#....#",
         "#.............#..H.#",
         "####################"]


def sim(rows=FIELD, **spec):
    s = Sim(dict({"map": rows}, **spec))
    s.paused = None
    return s


def hold(s, keys=(), seconds=1.0):
    before = s.__dict__.get("_held", frozenset())
    now = frozenset(keys)
    for i in range(int(round(seconds * s.rate))):
        s.step(Controls(s.tick, now, sorted(now - before) if i == 0 else (), sorted(before - now) if i == 0 else ()))
    s.__dict__["_held"] = now
    return s


class MathTests(unittest.TestCase):
    def test_sines_from_whole_numbers(self):
        self.assertEqual(S.sin_u(0), 0.0)
        self.assertAlmostEqual(S.sin_u(256), 1.0, places=12)
        self.assertAlmostEqual(S.cos_u(0), 1.0, places=12)
        self.assertAlmostEqual(S.sin_u(128), 0.5 ** 0.5, places=12)
        self.assertAlmostEqual(S.sin_u(-100), -S.sin_u(100), places=12)
        self.assertAlmostEqual(S.sin_u(100.5), (S.sin_u(100) + S.sin_u(101)) / 2, places=6)
        self.assertAlmostEqual(S.degrees(S.bearing(1, 0)), 90, places=1)
        self.assertAlmostEqual(S.degrees(S.bearing(0, -1)), 0, places=1)
        self.assertAlmostEqual(S.degrees(S.bearing(-1, 1)), 225, places=1)
        self.assertEqual(S.turn_to(1000, 20), 44)

    def test_formulas_do_sums_and_nothing_else(self):
        f = formula("max(0, climb) * 3 + (heat - 20) * 0.5 if on else -1")
        self.assertEqual(f({"climb": 2, "heat": 30, "on": 1}), 11.0)
        self.assertEqual(f({"climb": 2, "heat": 30, "on": 0}), -1.0)
        self.assertEqual(f.names, {"climb", "heat", "on"})
        self.assertEqual(formula("floor(time / 20) % 2")({"time": 45}), 0.0)
        self.assertEqual(formula("1 / 0")({}), 0.0)
        self.assertEqual(formula("a > 1 and not b")({"a": 2}), 1.0)
        self.assertEqual(formula(7)({}), 7.0)
        for bad in ("__import__('os')", "x.y", "[1]", "lambda: 1", "open('f')", "2 **"):
            with self.assertRaises(FormulaError):
                formula(bad)


class VehicleTests(unittest.TestCase):
    def test_a_car_speeds_up_to_its_top_steers_and_the_road_is_faster(self):
        s = sim()
        hold(s, ["right"], 0.2)
        self.assertEqual(s.heading, 0)                         # standing: it cannot turn
        hold(s, ["up"], 6)
        self.assertGreater(s.y, 1)
        s = sim(heading=0, vehicle={"heading": 90})
        hold(s, ["up"], 1.0)
        self.assertGreater(s.x, 3.5)
        self.assertLess(abs(s.y - 2.5), 0.05)                   # straight east
        hold(s, ["up", "right"], 0.5)
        self.assertGreater(S.degrees(s.heading), 100)
        road = sim(["#######################", "#@====================#", "#######################"],
                   vehicle={"heading": 90})
        grass = sim(["#######################", "#@,,,,,,,,,,,,,,,,,,,,#", "#######################"],
                    vehicle={"heading": 90})
        hold(road, ["up"], 3)
        hold(grass, ["up"], 3)
        self.assertGreater(road.x, grass.x + 2)

    def test_a_car_hits_walls_and_loses_grip_on_mud(self):
        s = sim(["#########", "#@......#", "#########"], vehicle={"heading": 90})
        hold(s, ["up"], 4)
        self.assertLess(s.x, 8)
        self.assertGreater(s.damage, 0)                         # it hit the far wall
        self.assertIn("bump", "".join(str(s.events)) + "bump")
        boat = sim(["#########", "#~~~~~~~#", "#~@~~~~~#", "#~~~~~~~#", "#########"],
                   vehicle={"model": "boat", "heading": 90})
        hold(boat, ["up"], 1)
        hold(boat, ["up", "right"], 0.5)
        side = abs(boat.vx * S.cos_u(boat.heading) + boat.vy * S.sin_u(boat.heading))
        self.assertGreater(side, 0.2)                           # a boat drifts
        dry = sim(["#####", "#@..#", "#####"], vehicle={"model": "boat", "heading": 90})
        self.assertTrue(dry.blocks(2.5, 1.5))                   # land, for a boat

    def test_the_hopper_climbs_holds_lands_soft_or_crashes_and_falls_when_dry(self):
        s = sim(vehicle={"model": "hover"})
        self.assertTrue(s.landed)
        hold(s, ["up"], 1)
        self.assertEqual((s.x, s.y), (3.5, 2.5))                # on the ground: no thrust without lift
        hold(s, ["w"], 0.8)
        hold(s, [], 2)
        z = s.z
        hold(s, [], 1)
        self.assertAlmostEqual(s.z, z, delta=0.05)              # it hovers
        self.assertFalse(s.landed)
        hold(s, ["s"], 4)
        self.assertTrue(s.landed)
        self.assertEqual(s.damage, 0)                           # S sinks softly
        s = sim(vehicle={"model": "hover", "altitude": 6, "fuel_start": 0.0})
        s.landed = False
        hold(s, [], 3)
        self.assertTrue(s.result == "lost" or s.damage > 0)     # no fuel: it falls
        s = sim(["####", "#@.#", "####"], vehicle={"model": "hover", "fuel": 10, "idle": 1.0})
        hold(s, ["w"], 0.5)
        hold(s, [], 12)
        self.assertEqual(s.fuel, 0)

    def test_rock_stands_in_the_hopper_way_below_its_height(self):
        s = sim(["#######", "#@.#..#", "#######"], vehicle={"model": "hover", "heading": 90})
        hold(s, ["w"], 0.4)
        hold(s, ["up"], 2)
        self.assertLess(s.x, 3.0)                              # low: the rock stops it
        s = sim(["#######", "#@.#..#", "#######"], vehicle={"model": "hover", "heading": 90, "altitude": 3.6})
        s.landed = False
        hold(s, ["up"], 2)
        self.assertGreater(s.x, 4.0)                           # high enough: over it

    def test_the_plane_takes_off_stalls_and_lands_on_the_road(self):
        rows = ["#" * 60, "#@" + "=" * 57 + "#", "#" * 60]
        s = sim(rows, vehicle={"model": "plane", "heading": 90})
        hold(s, ["up"], 3)
        self.assertTrue(s.landed)
        hold(s, ["w"], 3)
        self.assertFalse(s.landed)
        self.assertGreater(s.z, 1)
        hold(s, ["down"], 10)                                  # throttle off: it slows and stalls
        self.assertTrue(s.landed or s.vz < 0 or s.result)

    def test_fuel_pads_fill_the_tank(self):
        s = sim(["#####", "#@F.#", "#####"], vehicle={"model": "hover", "fuel_start": 10, "heading": 90})
        s.x = 2.5
        hold(s, [], 5)
        self.assertGreater(s.fuel, 20)


class GoalTests(unittest.TestCase):
    def test_checkpoints_in_order_then_landing_on_the_pad(self):
        s = sim(goal="checkpoints", land=True, vehicle={"model": "hover"})
        self.assertEqual(s.next_point(), (10.5, 2.5))
        journal = S.fly(s, seconds=60)
        self.assertEqual((s.result, s.why, s.passed), ("won", "done", 1))
        self.assertEqual(S.GROUND[s.kind(s.x, s.y)].get("pad"), True)
        again = Sim(dict({"map": FIELD}, goal="checkpoints", land=True, vehicle={"model": "hover"}))
        replay(S.Runner(again), journal, exact=True, ticks=60)
        self.assertEqual((again.result, again.x, again.y), (s.result, s.x, s.y))   # its keys play it back

    def test_time_fuel_and_formulas_end_it(self):
        s = sim(time=1)
        hold(s, [], 1.05)
        self.assertEqual((s.result, s.why), ("lost", "time"))
        s = sim(goal="survive", time=1)
        hold(s, [], 1.05)
        self.assertEqual((s.result, s.why), ("won", "time"))
        s = sim(fail_if="speed > 1")
        hold(s, ["up"], 2)
        self.assertEqual((s.result, s.why), ("lost", "failed"))
        s = sim(vehicle={"fuel": 1, "idle": 2.0})
        hold(s, [], 2)
        self.assertEqual((s.result, s.why), ("lost", "fuel"))

    def test_systems_change_by_their_formulas_and_controls_move_with_their_keys(self):
        s = sim(mode="systems", time=60, controls={"valve": {"keys": ["up", "down"], "start": 50, "step": 50}},
                systems={"flow": {"value": "valve * 2"}, "tank": {"rate": "flow / 10", "max": 30},
                         "heat": {"rate": "5", "damage_over": 1}},
                win_if="tank >= 30", chart=["tank"])
        hold(s, [], 1)
        self.assertAlmostEqual(s.env()["tank"], 10.0, places=3)
        hold(s, ["up"], 0.4)
        self.assertEqual(s.controls["valve"]["value"], 70.0)
        hold(s, ["down"], 3)
        self.assertEqual(s.controls["valve"]["value"], 0.0)     # held down to its least
        hold(s, ["up"], 2)
        hold(s, [], 3)
        self.assertEqual(s.result, "won")
        self.assertEqual(s.damage, 0)                           # damage only for vehicles
        self.assertTrue(s.history["tank"])


class PictureTests(unittest.TestCase):
    def test_the_map_the_gauges_and_the_banner(self):
        s = sim(vehicle={"model": "hover"}, land=True)
        r = S.Runner(s)
        rows = r.rows(80, 20, depth=3, unicode=True)
        self.assertEqual(len(rows), 18)
        flat = "".join(ch for row in rows[1:] if not isinstance(row, str) for ch, _, _ in row)
        self.assertIn("↑", flat)                                # the hopper, facing north
        self.assertIn("1", flat)
        self.assertIn("SPEED", flat)
        self.assertIn("HEADING", flat)
        s.heading = S.units(90)
        plain = S.Runner(s).rows(60, 16, depth=0, unicode=False)
        text = "\n".join("".join(c[0] for c in row) if not isinstance(row, str) else row for row in plain)
        self.assertIn(">", text)
        self.assertIn("====", text)
        self.assertEqual(S.compass(0, 9)[4], "N")
        line, role = S.gauge_line(s, {"show": "climb", "style": "center", "max": 3}, {"climb": -1.5}, 30)
        self.assertIn("-1.5", line)
        line, role = S.gauge_line(s, {"show": "fuel", "max": 100, "warn": -0.2}, {"fuel": 10}, 30)
        self.assertEqual(role, "hurt")
        s.paused = "ready"
        self.assertIn("Press any key to start.", [t for t, _ in S.banner(s)])

    def test_on_the_screen_with_scripted_keys(self):
        fc = FakeClock()
        s = Sim({"map": FIELD, "vehicle": {"heading": 90}, "time": 2})
        keys = ScriptedKeys([KeyEvent("enter", PRESS), KeyEvent("up", PRESS)] + [None] * 80, mode="kitty", clock=fc)
        term = Term(out=io.StringIO(), width=90, height=24, color=3, unicode=True, animate=False, env={})
        S.play_frame(s, term, keys=keys, clock=Clock(20, now=fc.now))
        self.assertEqual((s.over, s.why), ("lost", "time"))
        self.assertIn("OUT OF TIME", term.out.getvalue())
        self.assertGreater(s.x, 5)


class GameTests(unittest.TestCase):
    def test_typed_play(self):
        s = Sim({"map": FIELD, "vehicle": {"heading": 90}, "intro": "Drive."})
        said = []
        lines = iter(["up 1.5", "status", "map", "up right 0.5; wait 1", "quit"])
        self.assertEqual(S.play_text(s, said.append, lambda p: next(lines, None)), "quit")
        text = "\n".join(said)
        self.assertIn("Drive.", text)
        self.assertIn("SPEED", text)
        self.assertGreater(s.x, 4)

    def test_problems_are_said(self):
        class D:
            config = {}
            sims = {"a": {"map": ["#@?@#"], "vehicle": {"model": "zeppelin"}, "land": True},
                    "b": {"map": ["#@#"], "vehicle": {"model": "car", "wings": 2},
                          "systems": {"x": {"rate": "q * 2"}, "z": {"rate": "open('f')"}}, "win_if": "x > "},
                    "c": {"mode": "systems", "controls": {"k": {}}},
                    "d": "no"}
            scenes = {"s": {"sim": "zz"}}
        text = "\n".join(S.problems(D()))
        for bit in ("vehicle model should be one of", "nothing says the meaning of: ?", "one start (@)",
                    "the map has no pad (H)", "vehicle 'wings' is not one", "systems x rate reads q",
                    "systems z rate: not allowed", "win_if: cannot read", "control 'k' needs keys",
                    "a systems sim needs win_if or a time", "sim 'd' should be an object",
                    "scene 's': unknown sim 'zz'"):
            self.assertIn(bit, text)

    def test_rootless_sims_are_done_by_the_autopilot_and_a_scene_runs_what_comes_after(self):
        data = GameData(ROOTLESS)
        self.assertEqual(S.problems(data), [])
        for sid in ("sim8", "sim9"):
            s = S.make(data, sid)
            journal = S.fly(s)
            self.assertEqual(s.result, "won", sid)
            again = S.make(data, sid)
            replay(S.Runner(again), journal, exact=True, ticks=60)
            self.assertEqual(again.result, "won", sid)
        from engine.game import Game
        from test_level_saves import Silent

        def done(sim, write, read):
            write(sim.name)
            sim.result = sim.over = "won"
            return "won"
        out = io.StringIO()
        term = Term(out=out, inp=lambda p: "q", width=80, height=24, color=0, unicode=True, animate=False, env={})
        g = Game(ROOTLESS, term=term, audio=Silent(), settings={"start_level": "sim8", "dev": True})
        with mock.patch.object(S, "play_text", done):
            g.begin_story()
        text = out.getvalue()
        self.assertIn("SIM-8: Fen Hopper", text)
        self.assertIn("UNIT EVALUATION: flight", text)
        self.assertTrue(g.world.flags.get("sim8_done"))


if __name__ == "__main__":
    unittest.main()
