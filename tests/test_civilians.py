# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""What a level of people to keep alive needs: civilians, an event when the level is clean, a fall the story
goes on from, a level's own player, criticals, what a scan marks, a picture in one colour."""
import io
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from engine import ahead, firstperson, levelbot  # noqa: E402
from engine.level import KEYMAP, FrameConsole, Level, resume, validate  # noqa: E402
from engine.term import Term  # noqa: E402
from test_levels import Quiet, put, told, with_level  # noqa: E402

OURS = {
    "clerk": {"name": "clerk", "tag": "c", "hp": 20, "civilian": True, "death": "%s is killed."},
    "grunt": {"name": "grunt", "tag": "g", "hp": 40, "sight": 9, "attack": {"kind": "melee", "damage": [5, 5], "speed": 1}},
    "gun": {"name": "gun", "tag": "u", "hp": 40, "sight": 9,
            "attack": {"kind": "hitscan", "damage": [4, 4], "range": 8, "eager": 1.0, "keep": [1, 8], "accuracy": [1.0] * 9}},
    "giant": {"name": "giant", "tag": "G", "hp": 500, "sight": 9, "spares_civilians": True,
              "attack": {"kind": "melee", "damage": [30, 30], "speed": 1}},
}
PISTOL = {"1": {"name": "fist", "kind": "melee", "damage": [5, 5], "accuracy": 1.0},
          "2": {"name": "pistol", "ammo": "bullets", "damage": [10, 10]}}
LEGEND = {"c": "clerk", "g": {"monster": "grunt", "awake": True}, "s": "grunt", "u": {"monster": "gun", "awake": True},
          "G": {"monster": "giant", "awake": True}}


def made(rows, legend=None, weapons=None, **spec):
    data = with_level(dict({"map": rows, "legend": dict(LEGEND, **(legend or {}))}, **spec), weapons=weapons)
    data.monsters = dict(data.monsters, **OURS)
    lv = Level(data, "t", seed=1)
    lv.console = Quiet()
    return lv


def one(lv, tag):
    return next(m for m in lv.monsters if m.tag == tag)


class Civilians(unittest.TestCase):
    def test_they_are_not_to_be_killed_and_not_aimed_at(self):
        lv = made(["########",
                   "#@.c..s#",
                   "########"], weapons=PISTOL)
        put(lv, 1, 1, 1)
        c, g = one(lv, "c1"), one(lv, "g1")
        self.assertEqual((lv.total_kills, lv.total_civil), (1, 1))
        self.assertTrue(c.awake and c.civil and not g.civil)
        self.assertEqual(lv.cone(), [g])                        # the gun finds the grunt behind him, not him
        self.assertTrue(lv.set_target())
        self.assertIs(lv.target, g)
        lv.target = None
        lv.rng.random = lambda: 0.0                             # every shot lands
        lv.run_line("f")
        self.assertEqual((c.hp, g.hp), (20, 30))
        lv.run_line("f c1")                                     # by name: it is the player's to do
        self.assertEqual(c.hp, 10)
        self.assertEqual(c.label()[1], "good")

    def test_nobody_else_in_sight_nobody_to_aim_at(self):
        lv = made(["#####",
                   "#@.c#",
                   "#####"])
        put(lv, 1, 1, 1)
        self.assertFalse(lv.set_target())
        self.assertIn("Nobody to aim at", told(lv))

    def test_one_gives_way_and_a_blow_is_held(self):
        lv = made(["#####",
                   "#@c.#",
                   "#####"], weapons=PISTOL)
        put(lv, 1, 1, 1)
        c = one(lv, "c1")
        lv.run_line("1")
        lv.run_line("f")
        self.assertEqual(c.hp, 20)
        self.assertIn("You hold the blow", told(lv))
        lv.run_line("k")                                        # into him: they change places
        self.assertEqual(((lv.player.x, lv.player.y), (c.x, c.y)), ((2, 1), (1, 1)))
        self.assertIn("c1 lets you by", told(lv))
        self.assertEqual(c.post, (2, 1))                        # (where he goes back to is where he was put)

    def test_they_go_for_the_nearest_of_ours_unless_he_is_nearer(self):
        lv = made(["##########",
                   "#@.....c.g",
                   "##########"])
        put(lv, 1, 1, 1)
        c, g = one(lv, "c1"), one(lv, "g1")
        lv.marks_civilian(g)
        self.assertIs(g.grudge, c)
        self.assertIn("g1 goes for c1", told(lv))
        self.assertEqual(lv.open_to(g), None)                   # (no criticals in this level)
        lv.player.x = 7                                         # ...he steps between: nearer, and in its sight
        c.x = 4
        lv.marks_civilian(g)
        self.assertIsNone(g.grudge)

    def test_shot_by_him_it_leaves_ours_alone_a_while(self):
        lv = made(["##########",
                   "#@.....c.g",
                   "##########"])
        c, g = one(lv, "c1"), one(lv, "g1")
        lv.marks_civilian(g)
        lv.damage([(g, 1)], lead="BANG.")
        self.assertIsNone(g.grudge)
        self.assertEqual(g.spared, lv.beat + 6)
        lv.marks_civilian(g)
        self.assertIsNone(g.grudge)                             # not at once
        lv.beat += 6
        lv.marks_civilian(g)
        self.assertIs(g.grudge, c)
        lv.damage([(g, 1)], lead="The blast:")                  # not his shot: it stays on its civilian
        self.assertIs(g.grudge, c)

    def test_one_that_is_after_him_alone(self):
        lv = made(["##########",
                   "#@.....c.G",
                   "##########"])
        G = one(lv, "G1")
        for _ in range(3):
            lv.end_beat()
        self.assertIsNone(G.grudge)
        self.assertEqual(one(lv, "c1").hp, 20)

    def test_ours_run_and_cornered_stay(self):
        lv = made(["##########",
                   "#@..c..g.#",
                   "#........#",
                   "##########"])
        c, g = one(lv, "c1"), one(lv, "g1")
        lv.moved, lv.queue = [], []                             # (as a beat has them)
        g.awake = False                                         # asleep: nothing to run from
        lv.civil_act(c)
        self.assertEqual((c.x, c.y), (4, 1))
        g.awake = True
        lv.civil_act(c)
        self.assertGreater(max(abs(c.x - g.x), abs(c.y - g.y)), 3)
        self.assertEqual(c.fled, lv.beat)
        c.x, c.y = 6, 1                                         # at arm's length: no outrunning it
        lv.civil_act(c)
        self.assertEqual((c.x, c.y), (6, 1))
        g.dead = True                                           # gone: back to his post, every other beat, after a while
        lv.beat += 5
        was = (c.x, c.y)
        lv.beat += (lv.beat + c.id) % 2
        lv.civil_act(c)
        self.assertEqual(abs(c.x - 4), abs(was[0] - 4) - 1)

    def test_one_of_ours_dies_and_is_counted(self):
        lv = made(["######",
                   "#@.cg#",
                   "######"])
        c, g = one(lv, "c1"), one(lv, "g1")
        for _ in range(6):
            lv.end_beat()
        self.assertTrue(c.dead)
        self.assertEqual((lv.stats["lost"], lv.stats["kills"]), (1, 0))
        self.assertIn("c1 is killed.  (0 of 1 alive)", told(lv))
        self.assertNotIn("turns on", told(lv))                  # ours bear no grudge
        self.assertIsNone(lv.over)
        self.assertIsNone(g.grudge)
        text = " ".join(t for t, _role in lv.end_lines())
        self.assertIn("civilians  0%   (0 of 1 alive)", text)

    def test_too_few_left_and_the_level_is_lost(self):
        for need in (1, {"need": 1, "text": "Nobody is left."}):
            lv = made(["######",
                       "#@.c.#",
                       "######"], protect=need, death_after=True)
            lv.kill(one(lv, "c1"))
            self.assertEqual(lv.run(lv.console), "dead")        # lost - and not a fall the story goes on from
            said = "Nobody is left." if isinstance(need, dict) else "Too many of them are dead."
            self.assertEqual(lv.failed, said)
            self.assertEqual(lv.end_lines()[0], (said, "hurt"))

    def test_a_save_keeps_them(self):
        rows = ["##########",
                "#@.....c.g",
                "#........#",
                "##########"]
        lv = made(rows)
        for _ in range(3):
            lv.run_line("w")
        block = lv.save_block()
        again, note = resume(lv.data, block)
        self.assertIsNone(note)
        self.assertEqual(again.state_hash(), lv.state_hash())
        c, g = one(again, "c1"), one(again, "g1")
        self.assertTrue(c.civil)
        self.assertEqual((again.total_civil, g.grudge is c or c.dead), (1, True))


class CleanAndFallen(unittest.TestCase):
    ROWS = ["########",
            "#@.s.s.#",
            "####X###",
            "#..G.c.#",
            "########"]

    def level(self, **spec):
        spec.setdefault("on_clear", "quiet")
        return made(self.ROWS, {"X": {"wall": "steel", "opens_on": "quiet"},
                                "G": {"monster": "giant", "wake_on": "quiet"}}, **spec)

    def test_the_level_is_clean_when_nobody_that_counts_is_left(self):
        lv = self.level(events={"quiet": "It is quiet."})
        g1, g2, G = one(lv, "g1"), one(lv, "g2"), one(lv, "G1")
        self.assertEqual(lv.total_kills, 3)
        lv.kill(g1)
        self.assertNotIn("quiet", lv.events)
        lv.kill(g2)                                             # the giant wakes on it: it does not count; nor does the clerk
        self.assertIn("quiet", lv.events)
        self.assertTrue(G.awake)
        self.assertEqual(lv.cell(4, 2).kind, "floor")
        self.assertIn("It is quiet.", told(lv))

    def test_a_fall_after_the_event_is_not_the_end(self):
        lv = self.level(death_after="quiet", fall_lines=["DOWN", "It stands over him."])
        lv.over = "dead"
        self.assertEqual(lv.run(lv.console), "dead")            # before it: dead as ever
        self.assertEqual(lv.end_lines()[0][1], "hurt")
        lv = self.level(death_after="quiet", fall_lines=["DOWN", "It stands over him."])
        lv.event("quiet")
        lv.over = "dead"
        self.assertEqual(lv.run(lv.console), "fallen")
        self.assertEqual(lv.end_lines()[:2], [("DOWN", "hurt"), ("It stands over him.", "dim")])
        lv = self.level(death_after=True)
        lv.over = "dead"
        self.assertEqual(lv.run(lv.console), "fallen")
        self.assertEqual(lv.end_lines()[0], ("T  LOST", "hurt"))

    def test_the_games_own_words_for_a_death(self):
        lv = self.level()
        lv.over = "dead"
        self.assertEqual(lv.end_lines()[0][0], "Process terminated.")
        lv.cfg = dict(lv.cfg, death_lines=["He is down.", "Nothing more."])
        self.assertEqual(lv.end_lines()[:2], [("He is down.", "hurt"), ("Nothing more.", "dim")])

    def test_a_level_begins_with_its_own_player(self):
        spec = {"map": ["###", "#@#", "###"], "player": {"health": 150, "max_health": 150, "weapons": ["1"], "weapon": "1"}}
        lv = Level(with_level(spec), "t", seed=1, player={"health": 30, "armor": 80, "weapons": ["1", "2", "3"], "weapon": "3"})
        p = lv.player
        self.assertEqual((p.hp, p.max_hp, p.armor, p.weapons, p.weapon), (150, 150, 80, ["1"], "1"))
        again = Level(with_level(spec), "t", seed=1, player=lv.player.keep())     # (a save's start: the same again)
        self.assertEqual((again.player.hp, again.player.weapons), (150, ["1"]))


class Criticals(unittest.TestCase):
    def level(self, **spec):
        lv = made(["#########",
                   "#@..g...#",
                   "#...c...#",
                   "#########"], weapons=PISTOL, **spec)
        put(lv, 1, 1, 1)
        return lv, one(lv, "g1")

    def test_where_one_is_open(self):
        lv, g = self.level(criticals=2)
        self.assertEqual(lv.criticals, 2.0)
        g.heading = 3.14159                                     # facing west: at him
        self.assertIsNone(lv.open_to(g))
        g.intent = "aim"
        self.assertEqual(lv.open_to(g), "as it aims")
        g.intent, g.stun = None, 2
        self.assertEqual(lv.open_to(g), "as it reels")
        g.stun, g.heading = 0, 0.0                              # facing east: its back to him
        self.assertEqual(lv.open_to(g), "from behind")
        g.heading, g.grudge = 3.14159, one(lv, "c1")
        self.assertEqual(lv.open_to(g), "while it is at c1")
        g.grudge, g.intent = None, "aim"
        self.assertIsNone(lv.open_to(one(lv, "c1")))
        g.awake = False
        self.assertIsNone(lv.open_to(g))
        self.assertEqual(self.level()[0].criticals, 0.0)
        self.assertEqual(self.level(criticals=True)[0].criticals, 2.0)
        lv.cfg = dict(lv.cfg, criticals=3)                      # the game's, where the level says nothing
        lv.spec = {k: v for k, v in lv.spec.items() if k != "criticals"}
        self.assertEqual(lv.criticals, 3.0)

    def test_a_shot_there_counts_twice(self):
        for k, took, words in ((2, 20, True), (None, 10, False)):
            lv, g = self.level(**({"criticals": k} if k else {}))
            g.heading, g.intent = 3.14159, "aim"
            lv.rng.random = lambda: 0.0
            lv.run_line("f")
            self.assertEqual(g.max_hp - g.hp, took)
            self.assertEqual("Critical, as it aims" in told(lv), words)
            self.assertEqual(lv.stats["criticals"], 1 if words else 0)
            self.assertEqual(any(t.startswith("criticals") for t, _r in lv.end_lines()), words)

    def test_it_is_not_sidestepped(self):
        lv, g = self.level(criticals=2)
        g.spec = dict(g.spec, dodge=1.0)
        g.heading, g.intent = 3.14159, "aim"
        lv.rng.random = lambda: 0.0
        lv.run_line("f")
        self.assertEqual(g.max_hp - g.hp, 20)
        self.assertNotIn("sidesteps", told(lv))

    def test_the_lines_mark_it(self):
        lv = made(["#########",
                   "#@..h...#",
                   "#########"], {"h": {"monster": "scout", "awake": True}}, criticals=2)   # (one with a 3D model)
        put(lv, 1, 1, 1)
        m = one(lv, "s1")
        m.heading = 3.14159
        thing = [t for t in ahead.LevelPlace(lv).things() if t.get("wire") is not None][0]
        self.assertFalse(thing["critical"])
        m.intent = "aim"
        thing = [t for t in ahead.LevelPlace(lv).things() if t.get("wire") is not None][0]
        self.assertTrue(thing["critical"])
        view = ahead.LevelView(120, 30, "lines")
        open_rows = view.render(lv)
        m.intent = None
        shut_rows = view.render(lv)
        self.assertNotEqual(open_rows, shut_rows)               # the mark is drawn


class Scans(unittest.TestCase):
    def level(self):
        lv = made(["####E####",
                   "#@..g.s.#",
                   "#.c...1.#",
                   "#########"], {"1": {"mark": "Store"}}, goggles="scan")
        put(lv, 1, 1, 1)
        return lv

    def test_what_a_scan_marks(self):
        lv = self.level()
        marks = {m["label"]: m for m in ahead.LevelPlace(lv).marks()}
        self.assertEqual(sorted(marks), ["+", "EXIT", "G", "STORE"])       # not the one that is asleep
        self.assertEqual((marks["STORE"]["at"], marks["STORE"]["ring"]), ((6, 2), True))
        self.assertEqual((marks["EXIT"]["at"], marks["EXIT"]["ring"]), ((4, 0), False))
        self.assertTrue(marks["G"]["blink"] and not marks["+"].get("blink"))
        self.assertEqual(marks["+"]["at"], (2, 2))
        one(lv, "g1").dead = True
        self.assertNotIn("G", [m["label"] for m in ahead.LevelPlace(lv).marks()])

    def test_the_scan_shows_them(self):
        lv = self.level()
        rows = ahead.LevelView(120, 30, "scan").render(lv)
        text = "\n".join("".join(c[0] or " " for c in row) for row in rows)
        for word in ("STORE", "EXIT", "SCAN"):
            self.assertIn(word, text)

    def test_a_level_without_end_is_scanned_round_him(self):
        from engine.data import GameData
        from test_levels import ROOTLESS
        lv = Level(GameData(ROOTLESS), "sim1", seed=1)             # two million cells a side
        rows = ahead.LevelView(100, 30, "scan").render(lv)
        self.assertEqual(len(rows), 30)
        self.assertIn("SCAN", "".join(c[0] or " " for c in rows[0]))
        self.assertEqual(len(ahead.heights_of(ahead.LevelPlace(lv), (5, 7, 3, 2))), 2)

    def test_goggles_that_are_a_scanner(self):
        lv = self.level()
        lv.run_line("scanner")
        self.assertIn("You have no scanner", told(lv))
        lv.player.goggles, lv.player.had_goggles = 6, True
        lv.run_line("scanner on")
        self.assertIn("Scanner on: the level from above", told(lv))
        term = Term(out=io.StringIO(), width=100, height=30, color=3, unicode=True, animate=False, env={})
        con = FrameConsole(term, "pixel", keys=False, keymap=KEYMAP, animate=False)
        con.layout()
        self.assertEqual((con.view_for(lv).__class__.__name__, con.view_for(lv).style), ("LevelView", "scan"))
        self.assertIn("scanner: 6", "".join(str(r) for r in con.rows(lv)))
        lv.run_line("w")
        self.assertIn("The scanner's battery is low", told(lv))
        lv.run_line("goggles off")                              # (the old word still works)
        self.assertIn("Scanner off", told(lv))
        lv.player.goggles, lv.player.goggles_on = 1, True
        lv.run_line("w")
        self.assertIn("The scanner goes dark", told(lv))


class OneColour(unittest.TestCase):
    def test_a_level_in_one_colour(self):
        rows = ["#####", "#@.z#", "#####"]
        plain, green = made(rows), made(rows, tint="green")
        self.assertFalse(firstperson.tinted(plain))
        self.assertTrue(firstperson.tinted(green))
        plain.cfg = dict(plain.cfg, tint="green")               # the game's, where the level says nothing
        self.assertTrue(firstperson.tinted(plain))
        plain.cfg = dict(plain.cfg, tint=None)
        term = Term(out=io.StringIO(), width=80, height=24, color=3, unicode=True, animate=False, env={})

        def colours(lv):
            con = FrameConsole(term, "pixel", keys=False, keymap=KEYMAP, animate=False)
            con.layout()
            put(lv, 1, 1, 1)
            return [c for row in con.snapshot(lv) for cell in row for c in cell[1:] if c]
        self.assertTrue(all(g >= r and g >= b for r, g, b in colours(green)))
        self.assertTrue(any(r > g or b > g for r, g, b in colours(plain)))


class Checks(unittest.TestCase):
    def problems(self, legend=None, scene=None, **spec):
        data = with_level(dict({"map": ["####E####", "#@.c.s.X#", "#########"],
                                "legend": dict(LEGEND, X={"wall": "steel", "opens_on": "quiet"}, **(legend or {}))}, **spec))
        data.monsters = dict(data.monsters, **OURS)
        if scene is not None:
            data.scenes = dict(data.scenes, t=dict({"id": "t", "name": "T", "level": "t"}, **scene))
        return " | ".join(p for p in validate(data) if "level 't'" in p)

    def test_what_is_right_passes(self):
        self.assertEqual(self.problems(on_clear="quiet", death_after="quiet", protect=1, criticals=2, tint="green",
                                       player={"health": 120}, scene={"on_level_death": [{"win": "x"}]}), "")
        self.assertEqual(self.problems(death_after=True, protect={"need": 1, "text": "Lost."}, criticals=True), "")

    def test_what_is_wrong_is_said(self):
        for spec, words in (({"on_clear": "noise"}, "on_clear sets off 'noise', but nothing opens, closes or wakes on it"),
                            ({"on_clear": 3}, "on_clear should be the name of the event"),
                            ({"death_after": "never"}, "death_after 'never' is an event nothing in the level sets off"),
                            ({"death_after": 5}, "death_after should be the name of an event"),
                            ({"protect": 2}, "protect needs 2 civilians alive, and its map has 1"),
                            ({"protect": 0}, "protect should be how many civilians must live"),
                            ({"criticals": 0.5}, "criticals should be what a shot is worth"),
                            ({"tint": "amber"}, "tint should be green"),
                            ({"player": ["1"]}, "player should be an object")):
            self.assertIn(words, self.problems(**spec), spec)
        self.assertIn("its scene has no on_level_death", self.problems(on_clear="quiet", death_after="quiet", scene={}))


class TheBot(unittest.TestCase):
    def test_it_leaves_ours_alone(self):
        lv = made(["#######E#",
                   "#@.c....#",
                   "#########"], weapons=PISTOL)
        c = one(lv, "c1")
        bot = levelbot.Bot(lv, ["E"])
        self.assertEqual(lv.run(bot), "exit")                   # through him, not over him
        self.assertEqual((c.hp, lv.stats["fired"]), (20, 0))

    def test_it_takes_the_weapon_it_has_rounds_for(self):
        cells = dict(PISTOL, **{"4": {"name": "cannon", "ammo": "cells", "damage": [9, 9], "burst": 2}})
        lv = made(["#########",
                   "#@...g..#",
                   "#########"], weapons=cells)
        put(lv, 1, 1, 1)
        lv.player.weapons, lv.player.weapon = ["1", "4"], "1"
        lv.player.ammo = {"bullets": 0, "cells": 10}
        bot = levelbot.Bot(lv, ["E"])
        self.assertEqual(bot.pick_weapon(lv), "4")              # its own rounds, not the pistol's
        lv.player.ammo = {"bullets": 0, "cells": 1}             # not enough for a burst: the fist it has in hand
        self.assertIsNone(bot.pick_weapon(lv))


if __name__ == "__main__":
    unittest.main()
