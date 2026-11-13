"""Whole-game tests: every demo can be finished, and old game data still loads."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bot import DepthsBot                                   # noqa: E402
from helpers import ROOT, Session                           # noqa: E402

from engine.data import GameData, find_games                # noqa: E402
from engine.term import visible_len                         # noqa: E402

# ---- Derelict: the shared opening, then one script per ending ------------- #
OPENING = [
    "take wire", "unlock locker", "take screwdriver", "take apple", "take log", "take communicator",
    "give apple to bugrat",                       # Pest Control, the peaceful way
    "e", "s",                                     # corridor -> storage bay (key from the bugrat)
    "take chip", "repair chip", "give chip to terminal",
    "unlock crate", "take cutter", "equip cutter", "take all",
    "n", "w", "unlock suitcase", "735", "take passcard",
    "e", "e",                                     # hydroponics
    "take all", "open container", "take specimen",
    "give specimen to replicator", "give coolant to replicator",
    "w", "s", "w",                                # engine room
]
POWER = ["give coolant canister to droid", "use relay on reactor", "e", "n", "u"]


class DerelictTests(unittest.TestCase):
    def play(self, *parts, **kw):
        s = Session("derelict", **kw).start()
        for part in parts:
            s.do(*part)
        return s

    def test_data_is_valid(self):
        self.assertEqual(GameData(os.path.join(ROOT, "games", "derelict")).validate(), [])

    def test_escape_pod_ending(self):
        s = self.play(OPENING, POWER, ["combine goo with suit", "equip suit", "talk to marigold", "authorize", "0",
                                       "e", "use pod"])
        self.assertEqual(s.game.over, "win")
        self.assertIn("salvage tug", s.text)

    def test_rescue_ending(self):
        s = self.play(OPENING, POWER, ["combine communicator with cells", "use communicator on console"])
        self.assertEqual(s.game.over, "win")
        self.assertIn("MAYDAY", s.text)

    def test_pilot_ending(self):
        s = self.play(OPENING, POWER, ["talk to marigold", "fly", "0"])
        self.assertIsNone(s.game.over)                         # reactor not stable, manual unread
        s.do("w", "read manual", "e", "d", "s", "w", "use minty coolant on reactor", "e", "n", "u",
             "talk to marigold", "fly")
        self.assertEqual(s.game.over, "win")
        self.assertIn("captain's chair", s.text)

    def test_fighting_route_and_remote(self):
        s = Session("derelict", seed=11).start()
        s.do("take wire", "unlock locker", "take all", "fight bugrat", *["strike"] * 6)
        self.assertTrue(s.world.flags.get("mutated_bugrat_defeated"))
        s.do("take key", "e", "e", "take all", "give red apple to replicator", "w", "s",
             "unlock crate", "take all", "equip cutter", "equip suit", "n",
             "give orange to bolt", "give wire to bolt")
        self.assertIn("remote_control", s.world.inventory)
        s.do("s", "repair chip", "give chip to terminal", "n", "w", "unlock suitcase", "735", "take all",
             "e", "s", "w")
        self.assertEqual(s.world.scene_id, "engine_room")
        s.do("fight droid", "remote override", *["strike"] * 60)
        self.assertTrue(s.game.over == "lose" or s.world.flags.get("hostile_droid_defeated"))
        if not s.game.over:
            self.assertIn("fission_relay", s.world.scene["items"])

    def test_wire_cannot_be_given_away_too_early(self):
        s = self.play(["take wire", "unlock locker", "take all", "give apple to bugrat", "e", "give wire to bolt"])
        self.assertIn("bent_wire", s.world.inventory)

    def test_blocked_and_locked_exits(self):
        s = self.play(["e"])
        self.assertEqual(s.world.scene_id, "utility_room")     # the bugrat guards the hatch
        s.do("take wire", "unlock locker", "take apple", "give apple to bugrat", "e", "u")
        self.assertEqual(s.world.scene_id, "corridor")         # no power, no turbolift
        s.do("e", "w", "s")
        self.assertEqual(s.world.scene_id, "storage_bay")      # the key came from the bugrat
        s.do("w")
        self.assertEqual(s.world.scene_id, "storage_bay")      # engine room needs the passcard

    def test_save_and_load_restore_the_whole_world(self):
        s = self.play(OPENING)
        before = (s.world.scene_id, sorted(s.world.inventory), dict(s.world.flags), s.world.turn)
        s.do("save slot-a", "give coolant canister to droid", "use relay on reactor", "drop cutter")
        self.assertTrue(s.world.flags.get("reactor_online"))
        s.do("load slot-a")
        after = (s.world.scene_id, sorted(s.world.inventory), dict(s.world.flags), s.world.turn)
        self.assertEqual(before, after)
        self.assertEqual(s.world.items["rusty_metal_locker"]["current_state"], "empty")
        self.assertIn("hostile_droid", s.world.scenes["engine_room"]["characters"])
        self.assertFalse(s.world.scenes["corridor"]["exits"][2].get("locked"))

    def test_fits_a_phone_screen(self):
        for width, uni in ((40, True), (36, False)):
            s = Session("derelict", width=width, unicode=uni).start()
            for part in (OPENING, POWER, ["map", "journal", "inventory", "stats", "help", "talk to marigold", "0"]):
                s.do(*part)
            for line in s.text.splitlines():
                self.assertLessEqual(visible_len(line), width, repr(line))
            if not uni:
                self.assertTrue(s.text.isascii())

    def test_music_and_sound_are_requested(self):
        s = Session("derelict", record_audio=True).start()
        s.do("take wire", "unlock locker")
        kinds = [k for k, _p in s.backend.log]
        self.assertIn("loop", kinds)
        self.assertIn("play", kinds)


class DepthsTests(unittest.TestCase):
    def test_data_is_valid(self):
        self.assertEqual(GameData(os.path.join(ROOT, "games", "depths")).validate(), [])

    def test_same_seed_same_dungeon(self):
        a, b, c = DepthsBot(seed=5), DepthsBot(seed=5), DepthsBot(seed=6)
        layout = lambda bot: sorted((sid, sc["name"], tuple(sorted(e["scene_id"] for e in sc["exits"])))    # noqa: E731
                                    for sid, sc in bot.world.scenes.items())
        self.assertEqual(layout(a), layout(b))
        self.assertNotEqual(layout(a), layout(c))

    def test_every_floor_is_reachable_and_has_its_boss(self):
        for seed in range(1, 16):
            w = DepthsBot(seed=seed).world
            seen, queue = {"camp"}, ["camp"]
            while queue:
                for ex in w.scenes[queue.pop()]["exits"]:
                    if ex["scene_id"] not in seen:
                        seen.add(ex["scene_id"])
                        queue.append(ex["scene_id"])
            self.assertEqual(seen, set(w.scenes), "seed %d has unreachable rooms" % seed)
            kinds = [sc.get("kind") for sc in w.scenes.values()]
            self.assertEqual(kinds.count("boss"), 1)
            self.assertEqual(kinds.count("stairs"), 2)
            self.assertEqual(kinds.count("shrine"), 3)
            bosses = [c for sc in w.scenes.values() for c in sc["characters"]
                      if w.characters[c].get("template") == "hollow_king"]
            self.assertEqual(len(bosses), 1)

    def test_the_dungeon_can_be_won_by_every_class(self):
        for klass in (1, 2, 3):
            results = [DepthsBot(seed=seed, klass=klass).play() for seed in range(1, 13)]
            self.assertTrue(all(r in ("win", "lose") for r in results), results)
            self.assertGreaterEqual(results.count("win"), 6, "class %d: %s" % (klass, results))

    def test_fits_a_phone_screen(self):
        bot = DepthsBot(seed=2, klass=2)
        bot.term.forced_width = 40
        bot.play()
        for line in bot.text.splitlines():
            self.assertLessEqual(visible_len(line), 40, repr(line))

    def test_save_and_load_mid_dungeon(self):
        bot = DepthsBot(seed=4)
        bot.play(max_steps=40)
        g, w = bot.game, bot.world
        snap = (w.scene_id, sorted(w.inventory), w.player["level"], w.player["gold"], len(w.scenes), sorted(w.visited))
        g.execute("save mid")
        bot.play(max_steps=80)
        g.over = None
        g.execute("load mid")
        w = bot.world
        self.assertEqual(snap, (w.scene_id, sorted(w.inventory), w.player["level"], w.player["gold"],
                                len(w.scenes), sorted(w.visited)))


class LegacyTests(unittest.TestCase):
    """The original CLIo game files must keep working, unmodified in format."""

    def test_original_game_files_load_and_play(self):
        path = os.path.join(ROOT, "game_files")
        self.assertEqual(GameData(path).validate(), [])
        s = Session("game_files").start()
        out = s.do("look", "take bent wire", "take storage room key", "take fission relay", "take screwdriver",
                   "take broken chip", "repair chip",
                   "combine fission relay with screwdriver", "equip charged screwdriver",
                   "unlock suitcase", "ROSEBUD", "take blue apple", "give blue apple to replicator",
                   "talk to friendly robot", "1", "0",
                   "exit", "1",                                  # the old numbered exit menu
                   "take energy cells", "inventory", "hint", "map", "save", "load")
        w = s.world
        self.assertEqual(w.scene_id, "scene2")
        self.assertIn("charged_screwdriver", w.equipped)
        self.assertIn("fixed_chip", w.inventory)
        self.assertIn("blue_banana", w.inventory)
        self.assertEqual(w.stats["attack"], 20)
        self.assertIn("Game loaded", out)

    def test_original_npc_crafting(self):
        s = Session("game_files").start()
        s.do("take storage room key", "take broken communicator", "exit", "1", "take energy cells",
             "give energy cells to friendly robot", "give broken communicator to friendly robot")
        self.assertIn("remote_control", s.world.inventory)

    def test_all_games_are_listed(self):
        names = [os.path.basename(p) for p, _t, _d in find_games(ROOT)]
        self.assertEqual(names[:2], ["derelict", "depths"])
        self.assertIn("game_files", names)


if __name__ == "__main__":
    unittest.main()
