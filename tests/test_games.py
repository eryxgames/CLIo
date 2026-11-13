# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Whole-game tests: every demo can be finished, and old game data still loads."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bot import DepthsBot                                   # noqa: E402
from helpers import ROOT, Scripted, Session, private_saves   # noqa: E402

from engine import maze, records                            # noqa: E402
from engine.data import GameData, find_games                # noqa: E402
from engine.term import QuitGame, visible_len               # noqa: E402
from engine.world import slot_path                          # noqa: E402

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

    def test_fits_very_narrow_screens(self):
        """Smaller than any phone in portrait: nothing may overflow, art simply steps aside."""
        for width in (24, 30):
            s = Session("derelict", width=width).start()
            for part in (OPENING, POWER, ["map", "journal", "inventory", "stats", "help", "help fight", "about",
                                          "sound", "style list", "talk to marigold", "0", "hint"]):
                s.do(*part)
            for line in s.text.splitlines():
                self.assertLessEqual(visible_len(line), width, repr(line))

    def test_title_screens_fit_too(self):
        for name, answers in (("derelict", ["look"]), ("depths", ["Ash", "1", "look"]),
                              ("game_files", ["look"]), (os.path.join("templates", "starter"), ["look"])):
            for width in (24, 34, 40):
                s = Session(name, commands=list(answers), width=width)
                s.run()                                     # the full start-up, title screen included
                for line in s.text.splitlines():
                    self.assertLessEqual(visible_len(line), width, "%s @%d: %r" % (name, width, line))

    def test_safe_symbols(self):
        s = Session("derelict", width=40)
        from engine.term import GLYPHS_SAFE
        s.term.glyph_mode, s.term.glyphs = "safe", GLYPHS_SAFE
        s.start()
        s.do(*OPENING)
        s.do("journal", "stats", "fight droid", *["strike"] * 30)
        for symbol in "♥♪★✔✘⚑◆◈†▸":
            self.assertNotIn(symbol, s.text)
        self.assertTrue(any(corner in s.text for corner in "╭┌╔"))     # frames are still drawn
        for line in s.text.splitlines():
            self.assertLessEqual(visible_len(line), 40, repr(line))

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
        for width in (40, 28):
            bot = DepthsBot(seed=2, klass=2)
            bot.term.forced_width = width
            bot.play()
            for line in bot.text.splitlines():
                self.assertLessEqual(visible_len(line), width, repr(line))

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


def pack(session, *templates, **stats):
    """Put fresh monsters in the player's room. Returns their ids."""
    w = session.world
    over = {"stats": dict(stats)} if stats else None
    return [w.spawn(t, w.scene_id, over) for t in templates]


class GroupFightTests(unittest.TestCase):
    def begin(self, klass="1", width=80, seed=3, mode=None):
        s = Scripted("depths", ["Tess", klass], seed=seed, width=width, mode=mode).start()
        s.world.stats["health"] = s.world.stats["max_health"] = 900
        return s

    def test_everyone_in_the_room_joins_and_everyone_pays_out(self):
        s = self.begin()
        ids = pack(s, "bone_rat", "bone_rat", "gloom_bat", health=1, max_health=1)
        self.assertEqual(s.game.fight_group(ids[0]), ids)
        s.queue.extend(["strike 3"] * 3)
        self.assertEqual(s.game.start_fight(ids[0]), "win")
        text = s.text
        for name in ("Bone Rat A", "Bone Rat B", "Gloom Bat"):
            self.assertIn(name, text)
        self.assertEqual(text.count(" falls."), 2)              # the last one "is defeated"
        self.assertIn("The fight is yours.", text)
        self.assertEqual(s.world.vars["kills"], 3)
        self.assertTrue(all(s.world.characters[c]["defeated"] for c in ids))
        self.assertFalse(set(ids) & set(s.world.scene["characters"]))

    def test_targets_by_number_or_by_asking(self):
        s = self.begin()
        ids = pack(s, "bone_rat", "bone_rat", health=500, max_health=500, attack=0)
        b_stats = s.world.characters[ids[1]]["stats"]
        s.default = "flee"
        s.queue.extend(["focus", "strike 2", "focus", "heavy", "2", "focus", "s2"])
        s.game.start_fight(ids[0])
        self.assertIn("Target>", s.text)
        self.assertEqual(s.world.characters[ids[0]]["stats"]["health"], 500)    # never aimed at
        self.assertLess(b_stats["health"], 500)
        self.assertEqual(s.text.count("Bone Rat B for"), 3)

    def test_a_loner_fights_alone(self):
        s = self.begin()
        ids = pack(s, "bone_rat", "bone_rat")
        s.world.characters[ids[1]]["solo"] = True
        self.assertEqual(s.game.fight_group(ids[0]), [ids[0]])

    def test_area_item_hits_the_whole_pack(self):
        s = self.begin(klass="2")                               # the rogue carries a firebomb
        ids = pack(s, "bone_rat", "bone_rat", health=20, max_health=20)
        s.queue.extend(["item", "firebomb"])
        self.assertEqual(s.game.start_fight(ids[0]), "win")
        self.assertIn("It deals 28 to Bone Rat A", s.text)
        self.assertIn("It deals 28 to Bone Rat B", s.text)
        self.assertNotIn("Target>", s.text)

    def test_area_skills_and_splash(self):
        s = self.begin()
        s.world.player["abilities"] += ["cleave", "smoke", "nova"]
        s.world.player["focus_start"] = 5
        s.world.stats["critical_hit_chance"] = 0                # no lucky hits: compare plain damage
        ids = pack(s, "bone_rat", "bone_rat", health=500, max_health=500, attack=0)
        hp = lambda i: s.world.characters[ids[i]]["stats"]["health"]         # noqa: E731
        s.default = "flee"
        s.queue.append("cleave 1")
        s.game.start_fight(ids[0])
        self.assertIn("The sweep catches Bone Rat B", s.text)
        self.assertLess(hp(0), hp(1))                           # the target takes the full blow
        self.assertLess(hp(1), 500)
        before = (hp(0), hp(1))
        s.queue.extend(["smoke", "ember nova"])
        s.game.start_fight(ids[0])
        self.assertIn("Bone Rat A is blinded", s.text)
        self.assertIn("Bone Rat B is blinded", s.text)
        self.assertLess(hp(0), before[0])
        self.assertLess(hp(1), before[1])

    def test_running_away_keeps_what_was_won(self):
        s = self.begin()
        weak = pack(s, "bone_rat", health=1, max_health=1)[0]
        tough = pack(s, "gloom_bat", health=500, max_health=500, attack=0)[0]
        s.queue.extend(["strike 1"] * 4)
        s.default = "flee"
        self.assertEqual(s.game.start_fight(weak), "fled")
        self.assertTrue(s.world.characters[weak].get("defeated"))
        self.assertFalse(s.world.characters[tough].get("defeated"))
        self.assertIn(tough, s.world.scene["characters"])
        self.assertEqual(s.world.vars["kills"], 1)

    def test_a_crowd_fits_a_narrow_screen(self):
        for width in (24, 30, 40, 64):
            s = self.begin(width=width)
            ids = pack(s, "hollow_guard", "ash_wraith", "drowned_thrall", "hollow_guard",
                       health=40, max_health=40)
            s.queue.extend(["heavy", "2", "guard", "item", "1"])
            s.game.start_fight(ids[0])
            self.assertIn("Hollow Guard B", s.text) if width >= 30 else None
            for line in s.text.splitlines():
                self.assertLessEqual(visible_len(line), width, "%d: %r" % (width, line))

    def test_generated_packs(self):
        sizes = []
        for seed in range(1, 9):
            w = DepthsBot(seed=seed).world
            for sc in w.scenes.values():
                if sc.get("kind") == "monster":
                    sizes.append(len(sc["characters"]))
                    if len(sc["characters"]) > 1:
                        self.assertTrue(sc["items"], "a pack guards something")
        self.assertIn(2, sizes)
        self.assertGreater(sizes.count(1), sizes.count(2))      # packs are the exception


class ModeTests(unittest.TestCase):
    def rogue(self, **kw):
        s = Scripted("depths", ["Tess", "1"], mode="rogue", **kw)
        folder = private_saves(s)
        s.start()
        return s, folder

    @staticmethod
    def floor_start(w, n):
        return next(sid for sid, sc in w.scenes.items() if sc.get("floor") == n and sc.get("kind") == "start")

    def test_the_player_is_asked_how_to_play(self):
        s = Scripted("depths", ["2", "Tess", "1"], mode="?")
        private_saves(s)
        s.start()
        self.assertIn("How will you go down?", s.text)
        self.assertEqual(s.game.mode, "rogue")
        self.assertTrue(s.game.permadeath)
        self.assertTrue(s.world.flags.get("endless") and s.world.flags.get("mode_rogue"))
        self.assertEqual(s.game.slot, "rogue")
        story = Scripted("depths", ["Tess", "1"]).start()         # the first mode, without asking
        self.assertNotIn("How will you go down?", story.text)
        self.assertEqual((story.game.mode, story.game.slot, story.game.permadeath), ("story", "save", False))
        plain = Session("derelict").start()                       # a game without modes
        self.assertEqual((plain.game.mode, plain.game.slot, plain.game.permadeath), (None, "save", False))

    def test_the_dungeon_goes_on_only_in_endless_mode(self):
        story = Scripted("depths", ["Tess", "1"])
        private_saves(story)
        story.start()
        story.game.enter_scene(self.floor_start(story.world, 3))
        self.assertEqual(max(sc.get("floor", 0) for sc in story.world.scenes.values()), 3)

        s, _folder = self.rogue(seed=5)
        g, w = s.game, s.world
        g.enter_scene(self.floor_start(w, 2))
        self.assertEqual(w.vars["floors"], 3)                     # not yet: one floor ahead is enough
        g.enter_scene(self.floor_start(w, 3))
        self.assertEqual(w.vars["floors"], 4)
        lair = next(sc for sc in w.scenes.values() if sc.get("floor") == 3 and sc.get("kind") == "boss")
        down = [ex for ex in lair["exits"] if ex.get("dir") == "d"]
        self.assertEqual(len(down), 1)
        self.assertEqual(w.characters[down[0]["guard"]]["template"], "hollow_king")
        self.assertEqual(w.scenes[down[0]["scene_id"]]["floor"], 4)
        for n in (4, 5, 6, 7):
            g.enter_scene(self.floor_start(w, n))
            self.assertEqual((w.vars["floors"], w.vars["depth"]), (n + 1, n))
        # deeper floors: renamed, with a merchant, and their creatures named for their rank
        self.assertIn("The Lower Crypt", w.scenes[self.floor_start(w, 4)]["area"])
        deep = [w.characters[c] for sc in w.scenes.values() if sc.get("floor") == 4 for c in sc["characters"]]
        self.assertTrue(any(ch.get("template") == "merchant" for ch in deep))
        rats = [ch for ch in deep if ch.get("template") == "bone_rat"]
        self.assertTrue(rats and all(ch["name"] == "Elder Bone Rat" for ch in rats))
        self.assertGreater(rats[0]["stats"]["max_health"], 22 * 2)
        echo = [ch for ch in w.characters.values() if ch.get("name") == "Echo of the Hollow King"]
        self.assertEqual(len(echo), 1)                            # floor 6 uses the Court again
        self.assertGreater(echo[0]["stats"]["max_health"], 250)

    def test_every_floor_is_harder_than_the_one_above(self):
        g = Session("depths").game
        last = maze.floor_power(g, g.data.dungeon["floors"][-1])
        power = []
        for n in range(3, 16):
            fl, factor, rank, hazard = maze.floor_plan(g, n)
            power.append(maze.floor_power(g, fl) * factor * factor)
            self.assertGreaterEqual(hazard, 1.0)
            self.assertEqual(rank, (n - 1) // 3)
        self.assertAlmostEqual(power[0], last)
        self.assertEqual(power, sorted(power))
        self.assertGreater(power[-1], power[0] * 5)
        ch = maze.scaled(g, "tide_hag", 2.0, 1)
        self.assertEqual((ch["stats"]["max_health"], ch["name"]), (208, "The Elder Tide Hag"))
        self.assertEqual(maze.scaled(g, "tide_hag", 1.0, 0), {})

    def test_check_finds_mistakes_in_modes_and_dungeons(self):
        data = GameData(os.path.join(ROOT, "games", "depths"))
        self.assertEqual(data.validate(), [])
        data.config["score"]["depth"] = "lots"
        data.config["modes"]["rogue"] = "yes"
        data.dungeon["floors"][0]["packs"].append([["bone_rat", "dragon"], 1])
        data.dungeon["floors"][1]["elite"] = "kraken"
        data.dungeon["endless"]["floor"]["loot"].append(["excalibur", 1])
        data.dungeon["endless"]["cycle"] = [0, 7]
        found = "\n".join(data.validate())
        for word in ("'depth' is not a number", "mode 'rogue'", "'dragon' in a pack", "elite 'kraken'",
                     "'excalibur'", "index 7"):
            self.assertIn(word, found)
        plain = GameData(os.path.join(ROOT, "games", "derelict"))
        plain.config["modes"] = {"deep": {"endless": True}}
        self.assertIn("needs a dungeon generator", "\n".join(plain.validate()))

    def test_one_life(self):
        s, folder = self.rogue()
        g = s.game
        save = slot_path(folder, "rogue")
        self.assertIn("erased when the run ends", s.do("save"))
        self.assertTrue(os.path.isfile(save))
        self.assertIn("single save", s.do("save backup"))
        self.assertIn("no going back", s.do("load"))
        self.assertEqual(os.listdir(folder), ["rogue.json"])
        s.do("quit")                                              # leaving keeps the run
        self.assertTrue(os.path.isfile(save))
        g.over = None
        g.end_game("lose")
        self.assertFalse(os.path.isfile(save))
        self.assertIn("Score:", s.text)
        table = records.load(folder)["rogue"]
        self.assertEqual((table[0]["name"], table[0]["result"]), ("Tess", "lose"))

    def test_a_story_save_survives_and_can_be_loaded_back(self):
        s = Scripted("depths", ["Tess", "1"])
        folder = private_saves(s)
        s.start()
        s.do("save", "save spare")
        self.assertEqual(sorted(os.listdir(folder)), ["save.json", "spare.json"])
        s.game.end_game("lose")
        self.assertTrue(os.path.isfile(slot_path(folder, "save")))
        s.game.over = None
        self.assertIn("Game loaded.", s.do("load"))

    def test_no_slipping_out_of_a_fight(self):
        first = Session("depths", ["Tess", "1"], mode="rogue")
        folder = private_saves(first)
        first.start()
        rat = pack(first, "bone_rat", health=30, max_health=30)[0]
        first.queue.extend(["guard"])                             # ...and then the window is closed
        with self.assertRaises(QuitGame):
            first.game.start_fight(rat)
        again = Scripted("depths", mode="rogue")
        again.game.save_dir = folder
        self.assertTrue(again.game.load_slot("rogue"))
        self.assertIn("still waiting for you", again.text)
        self.assertTrue(again.world.characters[rat].get("defeated"))
        self.assertNotIn("_fight", again.world.vars)

    def test_scores_and_records(self):
        s = Scripted("depths", ["Tess", "1"])
        folder = private_saves(s)
        s.start()
        w = s.world
        w.vars.update(depth=2, kills=3)
        w.player["gold"] = 40
        self.assertEqual(records.score(s.game), 2 * 100 + 3 * 5 + 1 * 20 + 40)
        self.assertIn("275", s.do("stats"))
        self.assertIn("No finished runs yet", s.do("records"))
        s.game.end_game("lose")
        self.assertIn("a new record", s.text)
        places = [records.add(folder, "story", {"score": 1000 - i, "name": "Run %d" % i}) for i in range(12)]
        self.assertEqual(places, list(range(1, 11)) + [None, None])     # only the best ten are kept
        self.assertIsNone(records.add(folder, "story", {"score": 1, "name": "Worst"}))
        table = records.load(folder)["story"]
        self.assertEqual(len(table), records.KEEP)
        self.assertEqual([e["score"] for e in table], sorted((e["score"] for e in table), reverse=True))
        s.game.over = None
        out = s.do("records")
        self.assertIn("RECORDS", out)
        self.assertIn("Run 0", out)
        self.assertNotIn("Worst", out)
        self.assertEqual(records.load(os.path.join(folder, "nowhere")), {})

    def test_a_rogue_run_goes_below_the_court(self):
        depths = []
        for seed, klass in ((1, 1), (4, 1), (9, 2), (12, 3)):
            bot = DepthsBot(seed=seed, klass=klass, mode="rogue")
            folder = private_saves(bot)
            self.assertEqual(bot.play(4000), "lose")              # nobody wins a rogue run
            depths.append(bot.world.vars["depth"])
            entry = records.load(folder)["rogue"][0]
            self.assertEqual(entry["depth"], depths[-1])
            self.assertTrue(entry["note"].startswith(("slain by", "died")), entry["note"])
            self.assertEqual(os.listdir(folder), [records.FILE])   # the save is gone
        self.assertGreaterEqual(max(depths), 5, depths)

    def test_a_rogue_run_fits_a_phone_screen(self):
        bot = DepthsBot(seed=4, klass=1, mode="rogue")
        private_saves(bot)
        bot.term.forced_width = 30
        bot.play(4000)
        bot.game.over = None
        bot.game.execute("records")
        for line in bot.text.splitlines():
            self.assertLessEqual(visible_len(line), 30, repr(line))


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

    def test_starter_template_is_a_finished_game(self):
        path = os.path.join(ROOT, "templates", "starter")
        self.assertEqual(GameData(path).validate(), [])
        s = Session(os.path.join("templates", "starter")).start()
        s.do("up")
        self.assertEqual(s.world.scene_id, "cellar")           # locked
        s.do("take corkscrew", "use corkscrew on barrel", "up")
        self.assertEqual(s.game.over, "win")

    def test_all_games_are_listed(self):
        names = [os.path.basename(p) for p, _t, _d in find_games(ROOT)]
        self.assertEqual(names[:2], ["derelict", "depths"])
        self.assertIn("game_files", names)


if __name__ == "__main__":
    unittest.main()
