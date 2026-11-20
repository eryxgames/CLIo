"""Saves that hold the level's state (engine/snapshot.py): a level put back from its snapshot is the same
level - it plays on exactly as the first would have, on any machine - and loading no longer plays the
whole game again."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine import levelbot, snapshot  # noqa: E402
from engine.data import GameData  # noqa: E402
from engine.level import CELL_STATE, JOURNAL_KEEP, Cell, Level, resume  # noqa: E402
from engine.world import read_save, write_save  # noqa: E402
from test_levels import ROOTLESS, room_with  # noqa: E402

GAMES = {}


def game(lid, seed, beats=None):
    """A bot's game of a level (kept for the tests here): its journal."""
    key = (lid, seed, beats)
    if key not in GAMES:
        data = GameData(ROOTLESS)
        lv = Level(data, lid, seed=seed)
        bot = levelbot.Bot(lv, lv.spec.get("bot") or ["E"])
        if beats:
            read = bot.read
            bot.read = lambda prompt: None if lv.beat >= beats else read(prompt)
        lv.run(bot)
        GAMES[key] = (data, lv)
    return GAMES[key]


class ForkTests(unittest.TestCase):
    """Snapshot a level half way, put it back on a new one, play the rest of the lines on both."""

    def fork(self, lid, seed, beats=None, at=(1 / 3, 2 / 3)):
        data, played = game(lid, seed, beats)
        lines = played.journal
        for k in [int(len(lines) * f) for f in at]:
            a = Level(data, lid, seed=seed)
            a.replay(lines[:k])
            snap = snapshot.capture(a)
            b = snapshot.restore(Level(data, lid, seed=seed), json.loads(json.dumps(snap)))
            self.assertEqual(b.state_hash(), a.state_hash(), "%s at line %d" % (lid, k))
            a.replay(lines[k:])
            b.replay(lines[k:])
            self.assertEqual(b.state_hash(), a.state_hash(), "%s from line %d on" % (lid, k))
            self.assertEqual((b.beat, b.over, b.player.hp), (a.beat, a.over, a.player.hp))

    def test_rooms(self):
        self.fork("e1m1", 0)                                 # a boss, lifts, a teleporter, crates

    def test_belts_oil_and_fire(self):
        self.fork("e1m9", 2)

    def test_balls_a_flier_and_fuel(self):
        self.fork("e1m3", 2, at=(0.8,))                     # the hopper is boarded late

    def test_open_land(self):
        self.fork("e1m4", 1, beats=150, at=(0.6,))

    def test_a_dungeon_floor_from_a_seed(self):
        self.fork("sim2", 1)

    def test_rooms_without_end(self):
        self.fork("sim3", 2)

    def test_land_without_end(self):
        self.fork("sim1", 3, beats=120, at=(0.6,))


class StateTests(unittest.TestCase):
    def test_only_the_named_cell_state_changes_in_play(self):
        """CELL_STATE is all that a save keeps of a cell: nothing else may change while a level is played."""
        for lid, seed in (("e1m1", 0), ("e1m2", 1), ("e1m3", 2), ("e1m9", 2)):
            data, played = game(lid, seed)
            fresh = Level(data, lid, seed=seed)
            others = [s for s in Cell.__slots__ if s not in CELL_STATE]
            for row_a, row_b in zip(fresh.grid, played.grid):
                for a, b in zip(row_a, row_b):
                    self.assertEqual([getattr(a, s) for s in others], [getattr(b, s) for s in others],
                                     "%s cell %d,%d" % (lid, a.x, a.y))

    def test_everything_is_kept_unless_it_is_made_again(self):
        data, played = game("e1m3", 2)
        snap = snapshot.capture(played)
        kept = set(snap["attrs"])
        for name in vars(played):
            cache = name.startswith("_") and name not in snapshot.KEPT
            self.assertTrue(name in kept or name in snapshot.DERIVED or cache, name)
        self.assertIn("_tags", kept)
        self.assertIn("rng", kept)
        self.assertNotIn("data", kept)

    def test_what_cannot_be_saved_says_where_it_is(self):
        lv = room_with(["###", "#@#", "###"])
        lv.player.oops = lambda: None
        with self.assertRaises(snapshot.SnapshotError) as e:
            snapshot.capture(lv)
        self.assertIn("player.oops", str(e.exception))

    def test_the_same_game_sums_up_the_same_on_another_machine(self):
        """The digest does not depend on the process (Python's hash seed): two machines can compare it."""
        code = ("import sys; sys.path.insert(0, %r)\n"
                "from engine.data import GameData\nfrom engine import levelbot\n"
                "o, lv = levelbot.play(GameData(%r), 'sim3', 2)\nprint(lv.state_hash())\n") % (ROOT, ROOTLESS)
        sums = set()
        for hs in ("1", "4242"):
            env = dict(os.environ, PYTHONHASHSEED=hs)
            out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=300)
            self.assertEqual(out.returncode, 0, out.stderr)
            sums.add(out.stdout.strip())
        self.assertEqual(len(sums), 1)
        self.assertEqual(sums, {game("sim3", 2)[1].state_hash()})

    def test_big_snapshots_are_squeezed(self):
        big = {"v": 1, "attrs": {"seen_cells": {"$xy": list(range(100000))}}}
        packed = snapshot.pack(big)
        self.assertEqual(set(packed), {"z"})
        self.assertLess(len(packed["z"]), 300000)
        self.assertEqual(snapshot.unpack(packed), big)
        small = {"v": 1}
        self.assertIs(snapshot.pack(small), small)


class SaveTests(unittest.TestCase):
    def block(self, lid="e1m3", seed=2, k=None):
        data, played = game(lid, seed)
        lv = Level(data, lid, seed=seed)
        lv.replay(played.journal[:k or len(played.journal) // 2])
        return data, lv, json.loads(json.dumps(lv.save_block()))

    def test_loading_puts_the_snapshot_back_without_playing_the_lines(self):
        data, lv, block = self.block()
        self.assertIn("snapshot", block)
        with mock.patch.object(Level, "replay", side_effect=AssertionError("played back")):
            back, note = resume(data, block)
        self.assertIsNone(note)
        self.assertEqual(back.state_hash(), lv.state_hash())
        self.assertEqual(back.journal, block["lines"])

    def test_an_old_save_still_plays_its_lines(self):
        data, lv, block = self.block()
        old = {k: v for k, v in block.items() if k not in ("snapshot", "digest", "depth")}
        old["lines"] = [line for _beat, line in block["lines"]]          # lines as they were kept before
        back, note = resume(data, old)
        self.assertIsNone(note)
        self.assertEqual(back.state_hash(), lv.state_hash())

    def test_a_snapshot_that_does_not_come_back_the_same_falls_back_on_the_lines(self):
        data, lv, block = self.block()
        block["digest"] = "0" * 16
        back, note = resume(data, block)
        self.assertEqual(back.state_hash(), lv.state_hash())           # played back instead
        block["snapshot"] = {"v": 999}
        self.assertEqual(resume(data, block)[0].state_hash(), lv.state_hash())

    def test_a_long_game_keeps_its_last_lines_and_its_snapshot(self):
        data, lv, block = self.block("sim3", 2)
        with mock.patch("engine.level.JOURNAL_KEEP", 20):
            short = json.loads(json.dumps(lv.save_block()))
        self.assertEqual(len(short["lines"]), 20)
        self.assertEqual(short["lines_from"], short["lines"][0][0])
        back, note = resume(data, short)
        self.assertIsNone(note)
        self.assertEqual(back.state_hash(), lv.state_hash())
        self.assertGreater(JOURNAL_KEEP, 10000)

    def test_lines_come_on_their_beat(self):
        data, lv, block = self.block()
        lines = [list(e) for e in block["lines"]]
        lines[3][0] += 1                                     # not what was played: the play-back stops
        self.assertFalse(Level(data, "e1m3", seed=2).replay(lines))

    def test_a_save_is_made_when_its_line_is_done(self):
        lv = room_with(["#####",
                        "#.!.#",
                        "#...#",
                        "#.@.#",
                        "#####"], {"!": {"savepoint": True}})
        beats = []
        lv.host = mock.Mock()
        lv.host.save.side_effect = lambda lv_, slot, how="save": beats.append((how, lv_.beat, lv_.player.y))
        lv.run_line("k; k; w")
        self.assertEqual(beats, [("checkpoint", 3, 1)])         # after the whole line: whole beats
        lv.run_line("w; save; w")
        self.assertEqual(beats[-1], ("save", 5, 1))

    def test_a_damaged_save_falls_back_on_the_one_before(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "save.json")
            write_save(path, {"turn": 1})
            write_save(path, {"turn": 2})
            self.assertEqual(read_save(path), {"turn": 2})
            with open(path, "w") as f:
                f.write("{\"turn\": ")                       # cut off half way
            self.assertEqual(read_save(path), {"turn": 1, "_backup": True})
            self.assertEqual(sorted(os.listdir(d)), ["save.json", "save.json.bak"])


if __name__ == "__main__":
    unittest.main()
