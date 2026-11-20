# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Arcade stages (engine/arcade.py, engine/stagebot.py): a platformer's runs, jumps, platforms and ladders;
enemies that walk, fly, hunt and shoot; pickups, doors, hazards, lives and goals; the pictures; the bot that
finds a way through a stage, and runs played back from their keys."""
import io
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from engine import arcade, stagebot  # noqa: E402
from engine.arcade import FP, Runner, Stage, parse_moves, play_frame, play_text  # noqa: E402
from engine.data import GameData  # noqa: E402
from engine.keys import PRESS, RELEASE, KeyEvent, ScriptedKeys  # noqa: E402
from engine.realtime import Controls, FakeClock, replay  # noqa: E402
from engine.term import Term  # noqa: E402

ROOTLESS = os.path.join(ROOT, "games", "rootless")


def stage(rows, **spec):
    st = Stage(dict({"map": rows}, **spec))
    st.paused = None
    return st


def hold(st, keys=(), n=1):
    """Hold ``keys`` for ``n`` ticks: pressed on the first, the keys held before and not now let go."""
    before = st.__dict__.get("_held", frozenset())
    now = frozenset(keys)
    for i in range(n):
        st.step(Controls(st.tick, now, sorted(now - before) if i == 0 else (), sorted(before - now) if i == 0 else ()))
    st.__dict__["_held"] = now
    return st


def tile(b):
    return b.cx // FP, (b.y + b.h - 1) // FP


ROOM = ["##########",
        "#........#",
        "#........#",
        "#........#",
        "#........#",
        "#@.......#",
        "##########"]


class PhysicsTests(unittest.TestCase):
    def test_running_reaches_its_speed_and_stops_when_let_go(self):
        st = stage(ROOM)
        hold(st, ["right"], 10)
        self.assertEqual(st.player.vx, st.ph["speed"])
        hold(st, [], 6)
        self.assertEqual(st.player.vx, 0)
        hold(st, ["right"], 60)
        self.assertEqual(st.player.x + st.player.w, 9 * FP)     # the wall stops it
        self.assertEqual(st.player.vx, 0)

    def test_a_jump_held_rises_about_as_high_as_said_and_a_tap_less(self):
        st = stage(ROOM)
        y0, low = st.player.y, st.player.y
        for _ in range(30):
            hold(st, ["space"])
            low = min(low, st.player.y)
        self.assertTrue(3 * FP < y0 - low <= int(3.5 * FP), y0 - low)
        self.assertEqual((st.player.y, st.player.vy), (y0, 0))  # back on the floor
        hold(st, [], 2)
        hold(st, ["space"])
        low = st.player.y
        for _ in range(30):
            hold(st, [])
            low = min(low, st.player.y)
        self.assertLess(y0 - low, 2 * FP)                       # let go at once: a hop
        moon = stage(ROOM, physics={"jump": 2})
        y0, low = moon.player.y, moon.player.y
        for _ in range(30):
            hold(moon, ["space"])
            low = min(low, moon.player.y)
        self.assertTrue(int(1.75 * FP) < y0 - low <= 2 * FP)

    def test_a_ceiling_stops_a_jump(self):
        st = stage(["#####", "#...#", "##..#", "#@..#", "#####"])
        low = st.player.y
        for _ in range(4):
            hold(st, ["space"])
            low = min(low, st.player.y)
        self.assertEqual(low, 3 * FP)                           # up to the block, not into it
        hold(st, ["space"], 20)
        self.assertEqual(tile(st.player), (1, 3))

    def test_a_platform_is_jumped_through_from_below_stood_on_and_dropped_through(self):
        st = stage(["#####", "#...#", "#...#", "#===#", "#...#", "#@..#", "#####"])
        hold(st, ["space"], 30)
        self.assertEqual(st.player.y + st.player.h, 3 * FP)      # on top of it
        hold(st, [], 5)
        self.assertEqual(st.player.y + st.player.h, 3 * FP)
        hold(st, ["down"])
        hold(st, ["down", "space"], 2)
        hold(st, [], 30)
        self.assertEqual(st.player.y + st.player.h, 6 * FP)      # down through it to the floor
        self.assertEqual(st.events, [])

    def test_a_ladder_is_climbed_up_stood_on_and_climbed_down(self):
        st = stage(["#######", "#.....#", "#.....#", "#.H...#", "#.H...#", "#@H...#", "#######"])
        hold(st, ["right"], 4)
        hold(st, [], 6)
        hold(st, ["up"], 40)
        self.assertFalse(st.player.climbing)
        self.assertEqual(st.player.y + st.player.h, 3 * FP)      # on the ladder's top
        hold(st, [], 10)
        self.assertEqual(st.player.y + st.player.h, 3 * FP)
        hold(st, ["down"], 3)
        self.assertTrue(st.player.climbing)
        hold(st, ["down"], 40)
        self.assertEqual(st.player.y + st.player.h, 6 * FP)
        hold(st, ["up"], 3)
        hold(st, ["up", "space"])                                # a jump off the ladder
        self.assertFalse(st.player.climbing)
        self.assertLess(st.player.vy, 0)

    def test_a_jump_just_after_the_edge_still_jumps(self):
        st = stage(["########", "#......#", "#......#", "#@.....#", "####...#", "#......#", "########"])
        for _ in range(40):
            if not st._on_ground(st.player):
                break
            hold(st, ["right"])
        hold(st, ["right", "space"])                            # a tick late: it still jumps
        self.assertLess(st.player.vy, 0)

    def test_top_down_walks_every_way_and_diagonals_are_no_faster(self):
        st = stage(["#########", "#.......#", "#.......#", "#...@...#", "#.......#", "#.......#", "#########"],
                   mode="topdown")
        hold(st, ["up"], 10)
        self.assertEqual((st.player.vx, st.player.vy), (0, -st.ph["speed"]))
        hold(st, ["down", "right"], 8)
        self.assertEqual(st.player.vx, st.player.vy)
        self.assertLess(st.player.vx, st.ph["speed"])
        x, y = st.player.x, st.player.y
        hold(st, [], 20)
        self.assertEqual((st.player.vx, st.player.vy), (0, 0))
        self.assertNotEqual((st.player.x, st.player.y), (x, y))   # it slowed, it did not stop dead


class EnemyTests(unittest.TestCase):
    def test_a_walker_turns_at_walls_and_at_edges(self):
        st = stage(["##########", "#........#", "#..w.....#", "#..####..#", "#........#", "#@.......#", "##########"])
        e = st.enemies[0]
        xs = set()
        for _ in range(200):
            hold(st, [])
            xs.add(e.x)
        self.assertGreaterEqual(min(xs), 3 * FP)
        self.assertLessEqual(max(xs) + e.w, 7 * FP)             # it kept to its ledge
        self.assertTrue(e.alive)
        st = stage(["######", "#....#", "#@..w#", "######"], enemies={"walker": {"edges": "fall"}})
        hold(st, [], 10)
        self.assertEqual(st.enemies[0].dir, -1)                   # a wall turned it

    def test_jumping_on_a_walker_kills_it_and_walking_into_one_hurts(self):
        st = stage(["##########", "#........#", "#........#", "#@.....w.#", "##########"],
                   enemies={"walker": {"speed": 0}})
        hold(st, ["right"], 12)
        hold(st, ["right", "space"], 14)
        hold(st, [], 20)
        self.assertFalse(st.enemies[0].alive)
        self.assertEqual((st.kills, st.score, st.health), (1, 50, 3))
        st = stage(["##########", "#........#", "#@.....w.#", "##########"], enemies={"walker": {"speed": 0}})
        hold(st, ["right"], 40)
        self.assertEqual(st.health, 2)
        self.assertTrue(st.enemies[0].alive)
        self.assertGreater(st.player.invuln, 0)
        hold(st, ["right"], 5)
        self.assertEqual(st.health, 2)                           # a moment safe after a hit

    def test_a_turret_shoots_along_its_row_and_its_shot_hurts(self):
        st = stage(["############", "#..........#", "#..........#", "#@.......t.#", "############"])
        for _ in range(60):
            hold(st, [])
        self.assertLess(st.health, 3)
        st = stage(["############", "#.........t#", "#.........##", "#.........##", "#@........##",
                    "############"])
        hold(st, [], 80)
        self.assertEqual(st.health, 3)                           # not level with it: it holds its fire

    def test_a_flyer_comes_for_the_player_it_sees_and_not_through_walls(self):
        st = stage(["##########", "#........#", "#.....f..#", "#........#", "#@.......#", "##########"])
        e = st.enemies[0]
        d0 = abs(e.cx - st.player.cx)
        hold(st, [], 10)
        self.assertLess(abs(e.cx - st.player.cx), d0)
        st = stage(["##########", "#....#...#", "#....#.f.#", "#....#...#", "#@...#...#", "##########"])
        e = st.enemies[0]
        hold(st, [], 40)
        self.assertGreaterEqual(e.x, 6 * FP)                     # the wall between: it does not see

    def test_top_down_hunters_hunt_and_shots_kill_them(self):
        rows = ["##########", "#........#", "#@......c#", "#........#", "##########"]
        st = stage(rows, mode="topdown", gun=True, goal="clear")
        e = st.enemies[0]
        x0 = e.x
        hold(st, [], 5)
        self.assertLess(e.x, x0)
        hold(st, ["right"])
        hold(st, ["x"], 30)
        self.assertFalse(e.alive)
        self.assertEqual(st.result, "won")
        self.assertEqual((st.kills, st.score), (1, 50))


class PlayTests(unittest.TestCase):
    def test_chips_keys_and_hearts_are_taken_and_a_key_opens_a_door(self):
        st = stage(["##########", "#........#", "#@*+k.D..#", "##########"], health=2)
        hold(st, ["right"], 60)
        self.assertEqual((st.chips, st.score, st.health, st.keys), (1, 10, 0 + 2, 0))
        self.assertEqual(st.items, {(3, 2): "heart"})            # a heart is left while health is full
        self.assertGreater(st.player.x, 6 * FP)                   # through the door
        self.assertEqual(st.opened, [(6, 2)])

    def test_a_door_holds_without_a_key(self):
        st = stage(["#######", "#.....#", "#@..D.#", "#######"])
        hold(st, ["right"], 40)
        self.assertEqual(st.player.x + st.player.w, 4 * FP)
        self.assertIn("Locked", st.note[0])

    def test_spikes_hurt_a_pit_takes_a_life_and_the_checkpoint_is_where_you_come_back(self):
        st = stage(["############", "#..........#", "#@.!..^....#", "########~~##"], lives=2)
        hold(st, ["right"], 12)
        self.assertEqual(st.check, (3, 2))
        hold(st, ["right"], 12)
        self.assertEqual(st.health, 2)                           # the spikes
        hold(st, [], 40)
        hold(st, ["left"], 4)
        for _ in range(80):
            hold(st, ["right"])
            if st.deaths:
                break
        self.assertEqual((st.lives, st.deaths), (1, 1))          # into the pit
        hold(st, [], st.rate + 1)
        self.assertEqual(tile(st.player), (3, 2))                # back at the checkpoint
        self.assertEqual(st.health, st.max_health)
        hold(st, ["right"], 80)
        self.assertEqual((st.result, st.why), ("lost", "lives"))

    def test_the_exit_wants_its_chips_and_then_the_stage_is_won(self):
        st = stage(["##########", "#........#", "#@...E.*.#", "##########"], need=1)
        hold(st, ["right"], 18)
        self.assertIsNone(st.result)
        self.assertIn("Need 1 more chip", st.note[0])
        hold(st, ["right"], 20)
        hold(st, ["left"], 20)
        self.assertEqual(st.result, "won")
        self.assertIsNone(st.over)
        hold(st, [], st.rate * 2)
        self.assertEqual(st.over, "won")                         # after a moment to see it

    def test_goals_chips_clear_survive_and_a_time_limit(self):
        st = stage(["#######", "#@.*.*#", "#######"], goal="chips")
        hold(st, ["right"], 40)
        self.assertEqual(st.result, "won")
        st = stage(["#######", "#@....#", "#######"], goal="survive", time=1)
        hold(st, [], 19)
        self.assertIsNone(st.result)
        hold(st, [])
        self.assertEqual(st.result, "won")
        st = stage(["#######", "#@...E#", "#######"], time=1)
        hold(st, [], 20)
        self.assertEqual((st.result, st.why), ("lost", "time"))

    def test_ready_pause_and_quit(self):
        st = Stage({"map": ROOM})
        self.assertEqual(st.paused, "ready")
        hold(st, ["right"])
        self.assertEqual((st.ticks, st.paused), (0, None))       # the first key only starts it
        hold(st, ["right"], 3)
        self.assertEqual(st.ticks, 3)
        hold(st, ["p"])
        hold(st, [], 10)
        self.assertEqual((st.paused, st.ticks), ("paused", 3))
        hold(st, ["x"])
        self.assertEqual(st.paused, "paused")                    # only its keys go on
        hold(st, ["p"])
        self.assertIsNone(st.paused)
        hold(st, ["esc"])
        hold(st, ["q"])
        self.assertEqual(st.over, "quit")
        st = stage(ROOM)
        hold(st, ["ctrl-d"])
        self.assertEqual(st.over, "quit")

    def test_the_same_keys_play_the_same_and_a_copy_is_its_own(self):
        rows = ["##############", "#............#", "#...f....=====#", "#.....t......#", "#@...w...^...E#",
                "##############"]

        def keys():
            out = [[0, [["enter", PRESS]]], [1, [["enter", RELEASE]]]]
            names = ["right", "space", "left", "down"]
            for i in range(40):
                out.append([3 + i * 5, [[names[(i * 7) % 4], PRESS]]])
                out.append([5 + i * 5, [[names[(i * 7) % 4], RELEASE]]])
            return out
        a, b = Stage({"map": rows}), Stage({"map": rows})
        replay(Runner(a), keys(), exact=True)
        replay(Runner(b), keys(), exact=True)
        self.assertEqual(a.state_hash(), b.state_hash())
        self.assertGreater(a.ticks, 100)
        c = a.clone()
        hold(c, ["right"], 30)
        self.assertNotEqual(c.state_hash(), a.state_hash())
        self.assertEqual(a.state_hash(), b.state_hash())         # the copy played on alone


class PictureTests(unittest.TestCase):
    ROWS = ["##############", "#............#", "#..*..f..===.#", "#....H.......#", "#@...H.w..^.E#", "##############"]

    def test_pixels_glyphs_and_the_line_above(self):
        st = Stage({"map": self.ROWS, "name": "Test"})
        run = Runner(st)
        rows = run.rows(40, 12, depth=3, unicode=True)
        self.assertEqual(len(rows), 10)                          # the line above and the picture
        self.assertTrue(all(c[0] is None for c in rows[1]))       # half-block pixels
        self.assertIn("Press any key", "".join(r for r in rows if isinstance(r, str)))
        hold(st, ["right"])
        hold(st, [])
        rows = run.rows(40, 12, depth=0, unicode=False)
        pic = ["".join(c[0] for c in r) for r in rows[1:]]
        self.assertTrue(any("@" in r for r in pic))
        self.assertTrue(any("####" in r for r in pic))
        self.assertTrue(any("w" in r and "E" in r for r in pic))
        self.assertIn("HP 3/3  LIVES 3", rows[0])
        self.assertIn("♥♥♥", "".join(t for t, _ in run.view.hud(unicode=True)))
        st.player.x = 12 * FP
        run.rows(8, 12, depth=0, unicode=False)
        cx, cy = run.view.cam
        self.assertGreater(cx, 0)                                # the camera follows

    def test_a_stage_on_the_screen_with_keys_as_a_kitty_terminal_sends_them(self):
        fc = FakeClock()
        st = Stage({"map": ["#######", "#@...E#", "#######"], "name": "Short"})
        script = [KeyEvent("enter", PRESS), KeyEvent("enter", RELEASE), KeyEvent("right", PRESS)] + [None] * 80
        keys = ScriptedKeys(script, mode="kitty", clock=fc)
        term = Term(out=io.StringIO(), width=80, height=24, color=3, unicode=True, animate=False, env={})
        rec = play_frame(st, term, keys=keys, clock=arcade_clock(fc))
        self.assertEqual(st.over, "won")
        out = term.out.getvalue()
        self.assertIn("STAGE CLEAR", out)
        self.assertIn("\x1b[?1049l", out)                        # the screen given back
        again = Stage({"map": ["#######", "#@...E#", "#######"]})
        replay(Runner(again), rec.journal, exact=True, ticks=60)
        self.assertEqual(again.ticks, st.ticks)

    def test_typed_lines_play_a_stage(self):
        st = Stage({"map": ["#########", "#@..*..E#", "#########"], "intro": "Run."})
        said = []
        lines = iter(["sideways", "right 8", "help", "r 30"])
        self.assertEqual(play_text(st, said.append, lambda p: next(lines, None)), "won")
        text = "\n".join(said)
        self.assertIn("Run.", text)
        self.assertIn("Not a move: sideways", text)
        self.assertIn("STAGE CLEAR. Score 10.", text)
        self.assertEqual(parse_moves("jump right 10, wait, f 2"), [(("space", "right"), 10), ((), 6), (("x",), 2)])
        self.assertIsNone(parse_moves("quit"))
        self.assertEqual(parse_moves(""), [((), 10)])


def arcade_clock(fc):
    from engine.realtime import Clock
    return Clock(20, now=fc.now)


class BotTests(unittest.TestCase):
    def test_the_bot_clears_a_stage_and_its_keys_play_the_run_back(self):
        spec = {"map": ["#####################", "#..................E#", "#..............=====#",
                        "#.....*....===......#", "#@....H..........w..#", "###...H..^^...#######",
                        "#####################"], "need": 1}
        moves, journal = stagebot.solve(Stage(spec))
        self.assertIsNotNone(moves)
        st = Stage(spec)
        replay(Runner(st), journal, exact=True, ticks=60)
        self.assertEqual((st.result, st.over, st.deaths), ("won", "won", 0))

    def test_rootless_arcade_sims_can_be_cleared(self):
        data = GameData(ROOTLESS)
        self.assertEqual(arcade.problems(data), [])
        for sid in ("sim5", "sim6"):
            moves, journal = stagebot.solve(arcade.make(data, sid), budget=8000)
            self.assertIsNotNone(moves, sid)
            st = arcade.make(data, sid)
            replay(Runner(st), journal, exact=True, ticks=60)
            self.assertEqual(st.result, "won", sid)


class DataTests(unittest.TestCase):
    def test_what_is_wrong_with_a_stage_is_said(self):
        class D:
            config = {"arcade": {"enemies": {"blob": {"move": "ooze"}}}}
            stages = {"a": {"map": ["#@@#", "#?k#"], "mode": "sideways", "need": 3},
                      "b": {"map": ["#@D#"], "goal": "survive"},
                      "c": "no", "d": {"map": [], "legend": {"z": "lava"}}}
            scenes = {"s": {"stage": "zz"}}
        text = "\n".join(arcade.problems(D()))
        for bit in ("arcade enemy 'blob': move", "stage 'a': mode", "stage 'a': the map has characters nothing says "
                    "the meaning of: ?", "should have one start (@), not 2",
                    "the goal is the exit, and the map has none",
                    "need is 3 chips, and the map has 0", "stage 'b': 1 doors and only 0 keys",
                    "a survive goal needs a time", "stage 'c' should be an object", "stage 'd': map should be a list",
                    "scene 's': unknown stage 'zz'"):
            self.assertIn(bit, text)

    def test_a_scene_plays_its_stage_and_runs_what_it_says_after(self):
        from engine.game import Game
        data = GameData(ROOTLESS)
        moves, _ = stagebot.solve(arcade.make(data, "sim5"))
        words = {"space": "jump", "x": "fire"}
        line = ", ".join(" ".join([words.get(k, k) for k in mv] or ["wait"]) + " 4" for mv in moves)
        out = io.StringIO()
        feed = iter([line])
        term = Term(out=out, inp=lambda p: next(feed, "q"), width=80, height=24, color=0, unicode=True,
                    animate=False, env={})
        from test_level_saves import Silent
        g = Game(ROOTLESS, term=term, audio=Silent(), settings={"start_level": "sim5", "dev": True})
        g.begin_story()
        text = out.getvalue()
        self.assertIn("SIM-5: Bus Run", text)
        self.assertIn("STAGE CLEAR", text)
        self.assertIn("UNIT EVALUATION: movement", text)
        self.assertTrue(g.world.flags.get("sim5_cleared"))
        self.assertEqual(g.world.vars["stages"]["sim5"]["result"], "won")


if __name__ == "__main__":
    unittest.main()
