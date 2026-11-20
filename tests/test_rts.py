# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Skirmishes (engine/rts.py): maps and sides, flow-field paths, gathering, building and training, fights,
towers, fog, who is out, the computer player, orders played back, the controls (keys and mouse), the
picture, typed commands, and RØØTLESS SIM-7."""
import io
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from engine import rts  # noqa: E402
from engine.data import GameData  # noqa: E402
from engine.keys import PRESS, RELEASE, KeyEvent, ScriptedKeys, decode  # noqa: E402
from engine.realtime import Clock, Controls, FakeClock, Recorder  # noqa: E402
from engine.rts import FP, UI, Runner, World  # noqa: E402
from engine.term import Term  # noqa: E402

ROOTLESS = os.path.join(ROOT, "games", "rootless")
MAP = ["##############################",
       "#............................#",
       "#.$$$...........#............#",
       "#.$$$...........#.........2..#",
       "#...............#............#",
       "#.....1.........#............#",
       "#............................#",
       "#~~~~~~~.....................#",
       "##############################"]


def world(rows=MAP, **spec):
    sides = spec.pop("sides", [{"name": "Blue", "control": "player"}, {"name": "Red", "control": "none"}])
    return World(dict({"name": "Test", "map": rows, "sides": sides}, **spec))


def run(w, seconds):
    for _ in range(int(seconds * w.rate)):
        w.step()
    return w


def tile(t):
    return t.x // FP, t.y // FP


class WorldTests(unittest.TestCase):
    def test_a_map_gives_each_side_its_base_workers_and_crystal(self):
        w = world()
        hq = w.buildings_of(0, "hq")[0]
        self.assertEqual((hq.tx, hq.ty, hq.w, hq.h), (5, 4, 3, 3))
        self.assertEqual(len(w.units_of(0, "worker")), 4)
        self.assertEqual(len(w.buildings_of(1)), 1)
        self.assertEqual(len(w.crystal), 6)
        self.assertEqual(w.sides[0].credits, 200)
        self.assertTrue(w.explored[0][5 * w.W + 6])
        self.assertFalse(w.explored[0][3 * w.W + 26])          # the far side, not seen yet
        self.assertFalse(w.seen(w.buildings_of(1)[0]))

    def test_units_walk_round_rock_and_water_and_give_up_where_they_cannot_go(self):
        w = world()
        u = w.units_of(0, "worker")[0]
        w.order(0, {"do": "move", "units": [u.id], "to": [20, 2]})
        run(w, 12)
        self.assertEqual(tile(u), (20, 2))                     # round the end of the wall
        self.assertEqual(u.order["do"], "idle")
        f = w.field(("at", 20, 2))
        self.assertEqual(f[2 * w.W + 20], 0)
        self.assertGreaterEqual(f[2 * w.W + 15], 10 * 5)
        w.order(0, {"do": "move", "units": [u.id], "to": [3, 8]})  # rock: next to it at best
        run(w, 15)
        self.assertEqual(u.order["do"], "idle")
        many = w.units_of(0, "worker")
        w.order(0, {"do": "move", "units": [t.id for t in many], "to": [12, 5]})
        run(w, 10)
        self.assertTrue(all(abs(t.x // FP - 12) <= 3 and abs(t.y // FP - 5) <= 3 for t in many))
        self.assertTrue(all(t.order["do"] == "idle" for t in many))  # a group stops round the place
        self.assertEqual(len({(t.x, t.y) for t in many}), 4)        # not on top of one another

    def test_workers_bring_crystal_home_and_a_tile_mined_out_is_ground(self):
        w = world(crystal=10)
        ws = w.units_of(0, "worker")
        w.order(0, {"do": "gather", "units": [t.id for t in ws], "at": [3, 3]})
        run(w, 20)
        self.assertGreater(w.sides[0].credits, 200)
        self.assertTrue(all(t.order["do"] == "gather" for t in ws))
        run(w, 40)
        self.assertEqual(w.sides[0].credits, 200 + 60)        # all six tiles, ten each
        self.assertEqual(w.crystal, {})
        self.assertEqual(w.terrain[3 * w.W + 3], "ground")
        self.assertTrue(all(t.order["do"] == "idle" for t in ws))  # none left: they stop

    def test_a_worker_builds_a_building_that_trains_and_a_queue_is_paid_back(self):
        w = world()
        w.sides[0].credits = 1000
        u = w.units_of(0, "worker")[0]
        w.order(0, {"do": "build", "units": [u.id], "kind": "factory", "at": [10, 3]})
        run(w, 1)
        self.assertEqual(w.sides[0].credits, 1000)              # a factory needs barracks first
        self.assertIn("needs a barracks", w.messages[-1][1])
        w.order(0, {"do": "build", "units": [u.id], "kind": "barracks", "at": [3, 7]})
        run(w, 1)
        self.assertIn("cannot stand there", w.messages[-1][1])  # on the water
        w.order(0, {"do": "build", "units": [u.id], "kind": "barracks", "at": [10, 3]})
        run(w, 1)
        self.assertEqual(w.sides[0].credits, 850)
        run(w, 30)
        b = w.buildings_of(0, "barracks")[0]
        self.assertTrue(b.done)
        self.assertEqual(b.hp, b.max)
        self.assertEqual(u.order["do"], "idle")
        w.order(0, {"do": "train", "building": b.id, "kind": "ranger"})
        w.order(0, {"do": "train", "building": b.id, "kind": "soldier"})
        run(w, 1)
        self.assertEqual((b.queue, w.sides[0].credits), (["ranger", "soldier"], 850 - 135))
        w.order(0, {"do": "cancel", "building": b.id})
        w.order(0, {"do": "rally", "units": [b.id], "to": [14, 6]})
        run(w, 16)
        self.assertEqual(w.sides[0].credits, 850 - 75)
        rangers = [t for t in w.units_of(0) if t.kind == "ranger"]
        self.assertEqual(len(rangers), 1)
        self.assertLessEqual(abs(rangers[0].x // FP - 14) + abs(rangers[0].y // FP - 6), 3)  # to the rally point

    def test_units_fight_what_comes_near_hold_where_told_and_tanks_hit_round_about(self):
        w = world(sides=[{"control": "player"}, {"control": "ai", "workers": 0, "ai": {"every": 9999}}])
        a = w.add("soldier", 0, 12 * FP + 128, 5 * FP + 128)
        b = w.add("soldier", 1, 15 * FP + 128, 5 * FP + 128)
        run(w, 20)
        self.assertEqual(len([t for t in (a, b) if t.id in w.things]), 1)  # they met; one stands
        h = w.add("ranger", 0, 12 * FP + 128, 2 * FP + 128)
        w.order(0, {"do": "hold", "units": [h.id]})
        e = w.add("soldier", 1, 19 * FP + 128, 2 * FP + 128)
        run(w, 3)
        self.assertEqual(tile(h), (12, 2))                    # holds: no chase to something out of range
        self.assertEqual(e.hp, e.max)
        t = w.add("tank", 0, 22 * FP + 128, 6 * FP + 128)
        x1 = w.add("worker", 1, 25 * FP + 128, 6 * FP + 128)
        x2 = w.add("worker", 1, 26 * FP + 128, 6 * FP + 128)
        w.order(0, {"do": "attack", "units": [t.id], "target": x1.id})
        run(w, 1)
        self.assertLess(x2.hp, x2.max)                        # the blast reaches the next one

    def test_a_tower_shoots_and_a_side_with_no_buildings_is_out(self):
        w = world()
        tw = w.add("tower", 0, 12, 5)
        e = w.add("soldier", 1, 15 * FP + 128, 5 * FP + 128)
        w.order(1, {"do": "hold", "units": [e.id]})
        run(w, 15)
        self.assertNotIn(e.id, w.things)
        self.assertIsNotNone(tw.shot)
        red = w.buildings_of(1)[0]
        w.sides[1].control = "ai"
        w.remove(red)
        run(w, 1)
        self.assertEqual((w.result, w.why), ("won", "destroyed"))
        self.assertIsNone(w.over)
        run(w, 3)
        self.assertEqual(w.over, "won")
        w = world(goal="survive", time=5)
        run(w, 5)
        self.assertEqual((w.result, w.why), ("won", "time"))

    def test_the_computer_builds_trains_and_attacks(self):
        rows = list(MAP)
        rows[6] = "#......................$$$...#"
        w = world(rows, sides=[{"control": "player"}, {"control": "ai", "ai": {"first": 60, "wave": 3}}])
        run(w, 100)
        red = w.sides[1]
        roles = {b.spec["role"] for b in w.buildings_of(1)}
        self.assertIn("barracks", roles)
        self.assertGreaterEqual(len(w.units_of(1, "worker")), 5)
        self.assertGreaterEqual(red.attacks, 1)
        self.assertTrue(any(m[1] == "Red attacks." for m in w.messages) or red.name != "Red")
        mine = w.buildings_of(0)
        self.assertTrue(all(b.hp < b.max for b in mine) or w.result == "lost" or not mine)

    def test_the_same_orders_play_the_same(self):
        def play():
            w = world(sides=[{"control": "player"}, {"control": "ai", "ai": {"first": 40, "wave": 2}}])
            ws = w.units_of(0, "worker")
            w.order(0, {"do": "gather", "units": [t.id for t in ws[:3]], "at": [3, 3]})
            w.order(0, {"do": "build", "units": [ws[3].id], "kind": "barracks", "at": [10, 2]})
            run(w, 60)
            b = w.buildings_of(0, "barracks")[0]
            w.order(0, {"do": "train", "building": b.id, "kind": "soldier"})
            run(w, 60)
            return w
        a = play()
        b = World(a.spec, "Test")
        rts.replay(b, a.journal, until=a.tick)
        self.assertEqual(a.state_hash(), b.state_hash())
        self.assertEqual([o["do"] for _, _, o in a.journal], ["gather", "build", "train"])  # the player's alone

    def test_the_computer_plays_rootless_sim7_and_wins_and_a_player_who_does_nothing_loses(self):
        data = GameData(ROOTLESS)
        self.assertEqual(rts.problems(data), [])
        w = rts.make(data, "sim7")
        self.assertEqual(rts.autoplay(w, minutes=15), ("won", "destroyed"))
        w = rts.make(data, "sim7")
        run(w, 8 * 60)
        self.assertEqual(w.result, "lost")


class UITests(unittest.TestCase):
    def setUp(self):
        self.w = world()
        self.ui = UI(self.w)

    def keys(self, *names):
        for k in names:
            self.ui.key(k)
        run(self.w, 0.1)

    def test_the_cursor_chooses_and_enter_sends(self):
        ui, w = self.ui, self.w
        u = w.units_of(0, "worker")[0]
        ui.cursor = list(tile(u))
        self.keys("space")
        self.assertEqual(ui.selected, [u.id])
        ui.cursor = [3, 3]
        self.keys("enter")
        self.assertEqual(u.order["do"], "gather")              # Enter on crystal: gather it
        ui.cursor = [12, 6]
        self.keys("enter")
        self.assertEqual(u.order["do"], "move")
        ui.cursor = [1, 1]
        self.keys("v")
        ui.cursor = [12, 7]
        self.keys("v")
        self.assertEqual(len(ui.selected), 4)                  # a box round them all
        self.keys("e")
        self.assertEqual(len(ui.selected), 4)
        self.keys("s")
        self.assertTrue(all(t.order["do"] == "idle" for t in ui.chosen()))
        self.keys("tab")
        self.assertEqual(len(ui.selected), 1)
        self.assertEqual(ui.cursor, list(tile(ui.chosen()[0])))
        ui.move_cursor(-100, -100)
        self.assertEqual(ui.cursor, [0, 0])

    def test_the_build_menu_places_and_a_building_trains_with_digits(self):
        ui, w = self.ui, self.w
        w.sides[0].credits = 500
        ui.selected = [w.units_of(0, "worker")[0].id]
        self.keys("b")
        self.assertEqual(ui.mode, "menu")
        names = [s["name"] for k, s in ui.buildable()]
        self.assertEqual(names[:2], ["Headquarters", "Barracks"])
        self.keys("2")
        self.assertEqual(ui.mode, ("place", "barracks"))
        ui.cursor = [10, 2]
        self.keys("enter")
        self.assertIsNone(ui.mode)
        self.assertEqual(w.sides[0].credits, 350)
        hq = w.buildings_of(0, "hq")[0]
        ui.selected = [hq.id]
        self.keys("1")
        self.assertEqual(hq.queue, ["worker"])
        self.keys("c")
        self.assertEqual(hq.queue, [])
        ui.cursor = [12, 6]
        self.keys("r")
        self.assertEqual(hq.rally, (12, 6))

    def test_pause_and_leaving(self):
        w = self.w
        r = Runner(w)
        r.step(Controls(0, pressed=["p"]))
        t = w.tick
        for i in range(6):
            r.step(Controls(i + 1))
        self.assertEqual(w.tick, t)                            # paused: no time passes
        self.assertIn("PAUSED", "".join(t for t, _ in r.banner()))
        r.step(Controls(7, pressed=["enter"]))
        for i in range(4):
            r.step(Controls(8 + i))
        self.assertGreater(w.tick, t)
        r.step(Controls(20, pressed=["esc"]))
        r.step(Controls(21, pressed=["q"]))
        self.assertEqual(w.over, "quit")

    def test_the_mouse_chooses_drags_a_box_and_gives_orders(self):
        w = self.w
        r = Runner(w)
        ui = r.ui
        r.rows(80, 24, depth=3, unicode=True)                  # the camera, where clicks land
        cx, cy = ui.cam
        u = w.units_of(0, "worker")[0]
        x, y = tile(u)
        sx, sy = x - cx, y - cy + 1
        r.step(Controls(0, events=[("mouse:0:%d:%d" % (sx, sy), PRESS), ("mouseup:0:%d:%d" % (sx, sy), PRESS)]))
        self.assertEqual(ui.selected, [u.id])
        r.step(Controls(1, events=[("mouse:2:%d:%d" % (12 - cx, 6 - cy + 1), PRESS)]))
        r.step(Controls(2))
        self.assertEqual((u.order["do"], u.order.get("to")), ("move", (12, 6)))
        r.step(Controls(3, events=[("mouse:0:%d:%d" % (1 - cx, 1 - cy + 1), PRESS),
                                   ("mouse:32:%d:%d" % (14 - cx, 7 - cy + 1), PRESS),
                                   ("mouseup:0:%d:%d" % (14 - cx, 7 - cy + 1), PRESS)]))
        self.assertEqual(len(ui.selected), 4)
        self.assertEqual(decode("[<0;5;3M"), "mouse:0:4:2")
        rec = Recorder()
        c = rec.next([KeyEvent("mouse:0:4:2", PRESS)])
        self.assertEqual(c.events, (("mouse:0:4:2", PRESS),))

    def test_the_picture_fog_glyphs_panel_and_minimap(self):
        w, ui = self.w, self.ui
        r = Runner(w)
        rows = r.rows(90, 24, depth=3, unicode=True)
        self.assertEqual(len(rows), 22)
        self.assertEqual(len(rows[1]), 90)
        self.assertIn("CRYSTAL 200", rows[0])
        text = "".join(ch for row in rows[1:] for ch, _, _ in row if ch)
        self.assertIn("Headquarters", "".join(t for line in ui.panel(30) for t, _ in line) + "Headquarters")
        self.assertIn("◆", text)
        self.assertTrue(any(c[0] is None for c in rows[6]))     # the minimap's half-block pixels
        plain = Runner(w).rows(40, 16, depth=0, unicode=False)
        flat = ["".join(c[0] for c in row) for row in plain[1:]]
        self.assertTrue(any("$$$" in line for line in flat))
        self.assertTrue(any("H==" in line for line in flat))  # your headquarters
        self.assertTrue(any("w" in line for line in flat))
        self.assertFalse(any("2" in line or "R" in line for line in flat))
        w.sides[1].control = "ai"
        ui.cursor = [26, 3]
        self.assertIn("not seen yet", ui.describe(26, 3))

    def test_a_skirmish_on_the_screen_with_scripted_keys(self):
        fc = FakeClock()
        w = world()
        keys = ScriptedKeys([KeyEvent("space", PRESS), KeyEvent("space", RELEASE), None, None,
                             KeyEvent("p", PRESS), KeyEvent("q", PRESS)] + [None] * 5, mode="kitty", clock=fc)
        term = Term(out=io.StringIO(), width=90, height=26, color=3, unicode=True, animate=False, env={})
        rts.play_frame(w, term, keys=keys, clock=Clock(20, now=fc.now))
        self.assertEqual(w.over, "quit")
        out = term.out.getvalue()
        self.assertIn("\x1b[?1002h\x1b[?1006h", out)           # the mouse asked for, and given back
        self.assertIn("\x1b[?1002l", out)
        self.assertIn("CRYSTAL", out)


class TextTests(unittest.TestCase):
    def test_typed_commands_play_a_skirmish(self):
        w = world()
        said = []
        lines = iter(["select workers; gather 3,3", "wait 20", "select 6,8", "status",
                      "select workers; build barracks 10,2; wait 30", "train ranger 2; wait 30", "look 12,4",
                      "bogus", "quit"])
        self.assertEqual(rts.play_text(w, said.append, lambda p: next(lines, None)), "quit")
        text = "\n".join(said)
        self.assertIn("4 chosen.", text)
        self.assertIn("Yours: 1 Barracks", text)
        self.assertIn("Not a command: bogus", text)
        self.assertEqual(sum(1 for t in w.units_of(0) if t.kind == "ranger"), 2)
        self.assertIn("    0         1         2", text)       # the columns' numbers above a map

    def test_problems_are_said(self):
        class D:
            config = {"rts": {"kinds": {"blob": {"role": "oozer", "char": "bb", "produces": ["nothing"]}}}}
            skirmishes = {"a": {"map": ["#1?#"], "sides": [{"control": "player"}, {"control": "player"}]},
                          "b": {"map": ["#1#"], "sides": [{"faction": "elves"}], "goal": "survive"},
                          "c": {"map": []}}
            scenes = {"s": {"skirmish": "zz"}}
        text = "\n".join(rts.problems(D()))
        for bit in ("rts kind 'blob': role should be", "rts kind 'blob' makes 'nothing'", "char should be one",
                    "skirmish 'a': the map has characters nothing says the meaning of: ?",
                    "skirmish 'a': side 2 has no start (2)", "one side at most is the player's",
                    "side 1 (faction elves) has no hq kind", "a survive goal needs a time",
                    "skirmish 'c': map should be a list", "scene 's': unknown skirmish 'zz'"):
            self.assertIn(bit, text)

    def test_a_scene_plays_its_skirmish_and_what_comes_after(self):
        from engine.game import Game
        from test_level_saves import Silent

        def won(world, write, read):
            write(world.name)
            world.result = world.over = "won"
            return "won"
        out = io.StringIO()
        term = Term(out=out, inp=lambda p: "q", width=80, height=24, color=0, unicode=True, animate=False, env={})
        g = Game(ROOTLESS, term=term, audio=Silent(), settings={"start_level": "sim7", "dev": True})
        with mock.patch.object(rts, "play_text", won):
            g.begin_story()
        text = out.getvalue()
        self.assertIn("SIM-7: Xantrium Rush", text)
        self.assertIn("UNIT EVALUATION: command", text)
        self.assertTrue(g.world.flags.get("sim7_won"))
        self.assertEqual(g.world.vars["skirmishes"]["sim7"]["result"], "won")


if __name__ == "__main__":
    unittest.main()
