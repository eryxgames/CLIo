# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""First-person levels in Rootless: the picture, the level's rules, the game played through."""
import copy
import io
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from engine import keys as keys_mod  # noqa: E402
from engine.data import GameData  # noqa: E402
from engine.firstperson import FX, STYLES, View  # noqa: E402
from engine.level import Level, TextConsole, validate  # noqa: E402
from engine.term import Term  # noqa: E402

ROOTLESS = os.path.join(ROOT, "games", "rootless")


class Quiet(TextConsole):
    """A console that answers from a list and keeps what it was told."""

    def __init__(self, lines=()):
        self.lines = list(lines)
        self.told = []
        super().__init__(self.told.append, lambda prompt: self.lines.pop(0) if self.lines else None)

    def page(self, lv, lines, automap=False):
        self.told.append(lines)


def level(seed=1):
    lv = Level(GameData(ROOTLESS), "e1m1", seed=seed)
    lv.console = Quiet()
    return lv


def put(lv, x, y, facing):
    lv.player.x, lv.player.y, lv.player.facing = x, y, facing
    lv.update_seen()


class LevelTests(unittest.TestCase):
    def test_the_map(self):
        lv = level()
        self.assertEqual((lv.player.x, lv.player.y, lv.player.facing), (15, 28, 0))
        self.assertEqual(lv.total_secrets, 3)
        z1 = next(m for m in lv.monsters if m.tag == "z1")
        self.assertEqual((z1.x, z1.y), (16, 25))              # numbered in the order they are met
        self.assertIsNotNone(lv.boss)
        self.assertEqual(validate(lv.data), [])

    def test_turning_is_free_and_walking_is_a_beat(self):
        lv = level()
        lv.run_line("turn right")
        self.assertEqual((lv.player.facing, lv.beat), (1, 0))
        lv.run_line("j")
        self.assertEqual(((lv.player.x, lv.player.y), lv.beat), ((14, 28), 1))
        lv.run_line("h")                                       # strafe left = north when facing east
        self.assertEqual((lv.player.x, lv.player.y), (14, 27))

    def test_doors_and_keys(self):
        lv = level()
        put(lv, 15, 25, 0)
        lv.run_line("k")                                       # bump: the door opens
        self.assertEqual(lv.cell(15, 24).open, 1.0)
        put(lv, 15, 12, 0)
        lv.run_line("use")
        self.assertLess(lv.cell(15, 11).open, 1.0)
        self.assertIn("Permission denied", lv.log[-1][0])
        lv.player.keys.add("x")
        lv.run_line("use")
        self.assertEqual(lv.cell(15, 11).open, 1.0)

    def test_pickups(self):
        lv = level()
        med = next(it for it in lv.items if it.iid == "medkit")
        put(lv, med.x, med.y + 1, 0)
        lv.player.x, lv.player.y = med.x, med.y
        lv.arrive()
        self.assertFalse(med.taken)                            # full health: left for later
        lv.player.hp = 50
        lv.arrive()
        self.assertTrue(med.taken)
        self.assertEqual(lv.player.hp, 75)
        gun = next(it for it in lv.items if it.iid == "shotgun")
        lv.player.x, lv.player.y = gun.x, gun.y
        lv.arrive()
        self.assertIn("3", lv.player.weapons)
        self.assertEqual(lv.player.ammo["shells"], 8)

    def test_secrets(self):
        lv = level()
        put(lv, 18, 26, 1)                                     # facing the hollow wall of the boot bay
        lv.run_line("1")
        lv.run_line("f")
        self.assertEqual(lv.cell(19, 26).kind, "floor")
        self.assertEqual(lv.stats["secrets"], 1)
        put(lv, 12, 17, 3)                                     # the vent in the hall, three cells away
        for m in lv.monsters:
            m.dead = True                                      # nothing else to aim at
        lv.run_line("2")
        lv.run_line("f")
        self.assertEqual(lv.cell(9, 17).kind, "floor")
        self.assertEqual(lv.stats["secrets"], 2)

    def test_the_key_room_closets(self):
        lv = level()
        key = next(it for it in lv.items if it.iid == "key_x")
        daemon = next(m for m in lv.monsters if m.kind == "daemon")
        self.assertFalse(daemon.awake)
        lv.player.x, lv.player.y = key.x, key.y
        lv.arrive()
        self.assertIn("keyroom", lv.events)
        self.assertEqual(lv.cell(29, 14).kind, "floor")
        self.assertTrue(daemon.awake)

    def test_cron_waits_then_fights_then_escapes(self):
        lv = level()
        cron = lv.boss
        put(lv, 15, 12, 0)
        lv.player.keys.add("x")
        lv.run_line("use")
        lv.damage([(cron, 50)])
        self.assertEqual(cron.hp, cron.max_hp)                 # not time yet
        put(lv, 15, 11, 0)
        lv.run_line("k")                                       # onto the trap: the door shuts
        self.assertIn("arena", lv.events)
        self.assertLess(lv.cell(15, 11).open, 1.0)
        self.assertTrue(cron.awake)
        for _ in range(3):
            lv.end_beat()
        self.assertTrue(lv.marks)                              # the crontab's rain, a beat ahead
        lv.damage([(cron, int(cron.max_hp * 0.6))])
        self.assertTrue(cron.enraged)
        lv.damage([(cron, int(cron.max_hp * 0.3))])
        self.assertTrue(cron.gone)
        self.assertFalse(cron.dead)                            # escaped, not killed
        self.assertEqual(lv.cell(15, 3).open, 1.0)             # the sealed door to the exit
        self.assertEqual(lv.cell(15, 11).open, 1.0)

    def test_the_exit(self):
        lv = level()
        put(lv, 15, 1, 0)
        lv.run_line("use")
        self.assertEqual(lv.over, "exit")
        self.assertTrue(any("FINISHED" in t for t, _r in lv.end_lines()))


class ShellLineTests(unittest.TestCase):
    def test_and_or_alias_history(self):
        lv = level()
        put(lv, 13, 28, 0)
        lv.run_line("k && k")
        self.assertEqual((lv.player.x, lv.player.y), (13, 26))
        put(lv, 12, 28, 0)
        lv.run_line("h || l")                                  # a wall on the left: go right instead
        self.assertEqual((lv.player.x, lv.player.y), (13, 28))
        lv.run_line("alias two='k; k'")
        lv.run_line("two")
        self.assertEqual((lv.player.x, lv.player.y), (13, 26))
        lv.run_line("!!")
        self.assertEqual((lv.player.x, lv.player.y), (13, 25))   # blocked by the wall after one step
        lv.run_line("xyzzy; k")
        self.assertIn("command not found", lv.log[-1][0])

    def test_a_surprise_stops_the_line(self):
        lv = level()
        lv.player.keys.add("x")
        put(lv, 15, 12, 0)
        lv.run_line("use")
        put(lv, 15, 11, 0)
        lv.run_line("k; k; k")                                 # the first step springs the arena's trap
        self.assertEqual((lv.player.x, lv.player.y), (15, 10))
        self.assertIn("^C", " ".join(t for t, _r in lv.log))

    def test_sudo(self):
        lv = level()
        lv.run_line("sudo rm -rf /")
        self.assertIn("sudoers", lv.log[-1][0])


class CombatTests(unittest.TestCase):
    def test_no_barrel_at_arms_length(self):
        lv = level()
        for m in lv.monsters:
            if not m.barrel:
                m.dead = True
        put(lv, 17, 26, 0)                                     # the barrel b1 right in front
        self.assertEqual(lv.cone()[0].tag, "b1")
        lv.run_line("f")
        self.assertFalse(lv.monster_at(17, 25).dead)
        lv.run_line("f b1")                                    # on purpose: it goes off, and it hurts
        self.assertLess(lv.player.hp, 100)

    def test_a_barrel_takes_its_neighbours(self):
        lv = level()
        put(lv, 15, 28, 0)
        b1 = lv.monster_at(17, 25)
        z1 = lv.monster_at(16, 25)
        lv.damage([(b1, 5)])
        self.assertTrue(z1.dead)


class PictureTests(unittest.TestCase):
    def test_every_style(self):
        lv = level()
        put(lv, 15, 20, 0)
        for style in STYLES:
            for W, VR in ((80, 17), (40, 11)):
                cells = View(W, VR, style).render(lv, FX(hurt=0.5, booms=[(15, 17, 0.3)], shake=1), 1)
                self.assertEqual(len(cells), VR, style)
                self.assertTrue(all(len(r) == W for r in cells), style)

    def test_labels_behind_walls_are_hidden(self):
        lv = level()
        put(lv, 15, 28, 0)
        lv.update_seen()
        self.assertTrue(lv.monster_at(16, 25).seen)
        put(lv, 13, 22, 0)                                     # inside the wall west of the corridor: no sight
        self.assertFalse(any(m.seen for m in lv.monsters if m.kind == "zombie"))


class EditorTests(unittest.TestCase):
    def test_monster_far_versions_and_distances(self):
        from engine.editor import service
        made = service.handle(ROOTLESS, "/api/monster", {"seed": "x", "body": "floater", "size": 20})
        self.assertTrue(made["pixels"] and made["lod"])
        self.assertIn("crawler", made["bodies"])
        far = service.handle(ROOTLESS, "/api/far", {"pixels": made["pixels"], "keep": made["keep"]})
        self.assertEqual(far["lod"], made["lod"])
        seen = service.handle(ROOTLESS, "/api/distances", {"sprite": made})["distances"]
        self.assertEqual([d["cells"] for d in seen], [1, 2, 3, 4, 5, 6])
        heights = [len(d["pixels"]) for d in seen]
        self.assertEqual(heights, sorted(heights, reverse=True))
        self.assertTrue(any(d["drawing"] for d in seen))         # far away, a far version is used

    def test_levels_and_monsters_are_kinds(self):
        from engine import schema
        self.assertIn("levels", schema.BY_FILE)
        self.assertIn("monsters", schema.BY_FILE)


class ChecksAndGameTests(unittest.TestCase):
    def test_validate_finds_mistakes(self):
        data = GameData(ROOTLESS)
        data.levels = copy.deepcopy(data.levels)
        data.levels["e1m1"]["legend"]["z"] = {"monster": "nobody"}
        data.levels["e1m1"]["map"][1] = data.levels["e1m1"]["map"][1].replace(".", "?", 1)
        problems = " ".join(validate(data))
        self.assertIn("unknown monster 'nobody'", problems)
        self.assertIn("does not explain", problems)

    def test_played_through_clio_in_text(self):
        from engine.audio import Silent
        from engine.game import Game
        answers = iter(["", "k", "map", "ps", "man zombie", "turn right", "q"])
        term = Term(out=io.StringIO(), inp=lambda p: next(answers, None), width=80, height=24, color=0,
                    unicode=True, animate=False, env={})
        g = Game(ROOTLESS, term=term, audio=Silent())
        g.run()
        out = term.out.getvalue()
        self.assertIn("BOOT SECTOR", out)
        self.assertIn("ZOMBIE_PROCESS(6)", out)
        self.assertIn("facing east", out)

    def test_played_with_keys_in_a_redrawn_screen(self):
        from engine.level import KEYMAP, FrameConsole
        term = Term(out=io.StringIO(), width=80, height=24, color=3, unicode=True, animate=False, env={})
        con = FrameConsole(term, "pixel", keys=False, keymap=KEYMAP, animate=False)
        # Enter past the intro; a step, a look round, a shot, the map and back, the fist, a typed line
        con.screen.keys = keys_mod.ScriptedKeys(["enter", "up", "right", "left", "space", "tab", "esc", "1",
                                                 "f", "space", "z", "1", "enter"])
        lv = Level(GameData(ROOTLESS), "e1m1", seed=1)
        start = (lv.player.x, lv.player.y)
        self.assertEqual(lv.run(con), "quit")                  # the keys ran out: Ctrl-D
        self.assertEqual(lv.beat, 3)                           # step, shot, punch; turning is free
        self.assertEqual((lv.player.x, lv.player.y), (start[0], start[1] - 1))
        self.assertEqual((lv.player.weapon, lv.player.ammo["bullets"]), ("1", 49))
        out = term.out.getvalue()
        self.assertTrue(out.startswith("\x1b[?1049h"))           # its own screen...
        self.assertIn("\x1b[?1049l", out[-100:])                # ...given back at the end
        self.assertNotIn("command not found", out)

    def test_the_bot_finishes_the_level(self):
        import levelbot
        for seed in (0, 1, 2):
            outcome, lv = levelbot.play(seed=seed)
            self.assertEqual(outcome, "exit", "seed %d" % seed)
            self.assertTrue(lv.boss.gone)


if __name__ == "__main__":
    unittest.main()
