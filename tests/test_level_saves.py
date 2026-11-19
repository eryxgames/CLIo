"""Saving and loading in first-person levels: a save is how the level began and every line played since,
played back; checkpoints; a limit on saves; --level and *LEVEL for trying levels out."""
import io
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine import levelbot  # noqa: E402
from engine.audio import Silent  # noqa: E402
from engine.data import GameData  # noqa: E402
from engine.level import META, Host, Level, resume  # noqa: E402
from engine.term import Term  # noqa: E402
from engine.world import read_save, slot_path  # noqa: E402
from test_levels import ROOTLESS, room_with, told  # noqa: E402


def state(lv):
    p = lv.player
    return ((p.x, p.y, p.facing, p.hp, p.armor, sorted(p.ammo.items()), sorted(p.keys)), lv.beat,
            sorted(lv.stats.items()), lv.rng.getstate(),
            sorted((m.kind, m.x, m.y, m.hp, m.dead) for m in lv.monsters),
            [(c.open, c.crate, c.sunk, c.scorched) for row in lv.grid for c in row])


class JournalTests(unittest.TestCase):
    def test_lines_are_kept_but_not_the_ones_about_the_game(self):
        lv = room_with(["#####",
                        "#...#",
                        "#.@.#",
                        "#####"])
        for line in ("w", "turn left; w", "save", "load slot2", "saves", "*e1m2", "  ", "q"):
            lv.run_line(line)
        self.assertEqual(lv.journal, ["w", "turn left; w"])     # quitting is not kept either
        self.assertTrue(META.fullmatch("save quick") and not META.fullmatch("saved"))

    def test_a_game_played_back_ends_as_it_did(self):
        data = GameData(ROOTLESS)
        for lid, seed in (("e1m1", 0), ("e1m2", 1), ("e1m9", 2)):
            outcome, lv = levelbot.play(data, lid, seed)
            again = Level(data, lid, seed=seed)
            again.replay(lv.journal)
            self.assertEqual(state(again), state(lv), "%s seed %d" % (lid, seed))
            self.assertEqual(again.over, outcome)

    def test_a_save_that_no_longer_plays_back_starts_the_level_again(self):
        data = GameData(ROOTLESS)
        lv, note = resume(data, {"id": "e1m2", "seed": 1, "start": None, "lines": ["w", "q", "w"]})
        self.assertIn("starts again", note)                     # it ended the level as it played: from the start
        self.assertEqual(lv.beat, 0)
        lv, note = resume(data, {"id": "e1m2", "seed": 1, "start": None, "lines": ["w"] * 3,
                                 "fingerprint": "00000000"})
        self.assertIn("changed", note)
        self.assertEqual(lv.beat, 3)


class CheckTests(unittest.TestCase):
    def test_check_knows_saves_and_autosave(self):
        from engine.level import validate
        d = GameData(ROOTLESS)
        self.assertEqual(validate(d), [])
        d.config = dict(d.config, first_person=dict(d.config["first_person"], saves=-1, autosave="yes"))
        problems = " ".join(validate(d))
        self.assertIn('"saves"', problems)
        self.assertIn('"autosave"', problems)


class Saves(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        patch = mock.patch.dict(os.environ, {"CLIO_SAVES": self.dir})
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(shutil.rmtree, self.dir, True)

    def game(self, lines=(), **settings):
        from engine.game import Game
        feed = iter(list(lines))
        self.out = io.StringIO()

        def inp(prompt):
            try:
                return next(feed)
            except StopIteration:
                return "q"
        term = Term(out=self.out, inp=inp, width=80, height=24, color=0, unicode=True, animate=False, env={})
        return Game(ROOTLESS, term=term, audio=Silent(), settings=settings)

    def level(self, g, lid="e1m2"):
        lv = Level(g.data, lid, seed=g.seed)
        lv.host = Host(g)
        lv.console = room_with(["###", "#@#", "###"]).console
        return lv


class SaveTests(Saves):
    def test_a_save_keeps_the_world_and_the_journal(self):
        g = self.game()
        lv = self.level(g)
        lv.run_line("turn right; k")
        lv.run_line("save")
        blob = read_save(slot_path(g.saves(), g.slot))
        self.assertEqual(blob["level"]["lines"], ["turn right; k"])
        self.assertEqual((blob["level"]["id"], blob["level"]["saves_left"]), ("e1m2", 2))
        self.assertIn("2 left", told(lv))
        lv.run_line("save quick")
        self.assertTrue(os.path.isfile(slot_path(g.saves(), "quick")))
        lv.run_line("save; save")
        self.assertIn("No saves left", told(lv))               # three a level in Rootless
        label = g.resumable()[0][1]
        self.assertIn("Dynamic Loader, beat 1", label)

    def test_with_dev_saves_are_not_counted(self):
        g = self.game(dev=True)
        lv = self.level(g)
        lv.dev = True
        for _ in range(5):
            lv.run_line("save")
        self.assertNotIn("No saves left", told(lv))
        self.assertEqual(lv.saves_left, 3)

    def test_load_ends_the_level_with_the_save_to_go_on_with(self):
        g = self.game()
        lv = self.level(g)
        lv.run_line("k")
        lv.run_line("save")
        lv.run_line("k; k")
        lv.run_line("load")
        self.assertEqual(lv.over, "load")
        self.assertEqual(lv.loaded["level"]["lines"], ["k"])
        lv2 = self.level(g)
        lv2.run_line("load nothing")
        self.assertIn("no saved game called 'nothing'", told(lv2))

    def test_a_checkpoint_saves_when_it_is_first_reached(self):
        lv = room_with(["#####",
                        "#.!.#",
                        "#.@.#",
                        "#####"], {"!": {"savepoint": True}})
        saved = []
        lv.host = mock.Mock()
        lv.host.save.side_effect = lambda lv_, slot, how="save": saved.append(how)
        lv.run_line("k; j; k")
        self.assertEqual(saved, ["checkpoint"])                 # once
        lv.replay(["k"])                                        # played back: no saving
        self.assertEqual(saved, ["checkpoint"])


class PlayTests(Saves):
    def test_save_then_load_plays_on_from_the_save(self):
        g = self.game(["k", "save", "k", "k", "load", "whoami", "q"])
        g.world.scene_id = "dynamic_loader"
        from engine import level
        level.play_scene(g, g.world.scene)
        out = self.out.getvalue()
        self.assertIn("Loaded - beat 1", out)
        blob = read_save(slot_path(g.saves(), g.slot))
        self.assertEqual(blob["level"]["lines"], ["k"])
        self.assertEqual(g.over, "quit")

    def test_the_level_start_is_saved_and_dying_can_go_back_to_it(self):
        g = self.game(["q"])
        g.world.scene_id = "dynamic_loader"
        from engine import level
        level.play_scene(g, g.world.scene)
        blob = read_save(slot_path(g.saves(), g.slot))          # autosave: the level as it began
        self.assertEqual((blob["level"]["id"], blob["level"]["lines"]), ("e1m2", []))
        g2 = self.game(["w", "q"])
        self.assertTrue(g2.load_slot())                         # as the death menu's "Load your last save"
        self.assertIn("DYNAMIC LOADER", self.out.getvalue())

    def test_level_starts_a_game_in_that_level(self):
        g = self.game(["q"], start_level="e1m9", dev=True)
        g.begin_story()
        self.assertEqual(g.world.scene_id, "swap_partition")
        self.assertIn("SWAP PARTITION", self.out.getvalue())

    def test_star_jumps_to_a_level_with_dev_only(self):
        g = self.game(["*e1m9", "*", "*e1m3", "q"], dev=True)
        g.world.scene_id = "boot_sector"
        from engine import level
        level.play_scene(g, g.world.scene)
        out = self.out.getvalue()
        self.assertEqual(g.world.scene_id, "swap_partition")
        self.assertIn("SWAP PARTITION", out)
        self.assertIn("e1m2 (Dynamic Loader)", out)
        self.assertIn("There is no level 'e1m3'", out)
        g = self.game(["*e1m9", "q"])
        g.world.scene_id = "boot_sector"
        level.play_scene(g, g.world.scene)
        self.assertIn("*e1m9: command not found", self.out.getvalue())
        self.assertEqual(g.world.scene_id, "boot_sector")


if __name__ == "__main__":
    unittest.main()
