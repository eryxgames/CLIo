# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Daniel Sandner
"""Sound sets, and sound effects from the engine of Ballistic Foley Lab (engine/audio/ballistic).

The tests that render need Node.js and are skipped without it; the rest check what a game gets without it."""
import json
import os
import sys
import tempfile
import unittest
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from helpers import ROOT, Session                               # noqa: E402

from engine.audio import Audio, ballistic                       # noqa: E402
from engine.audio.backends import Backend, NullBackend          # noqa: E402
from engine.data import GameData                                # noqa: E402
from engine.level import Level, TextConsole                     # noqa: E402

ROOTLESS = os.path.join(ROOT, "games", "rootless")
NODE = ballistic.find_node()
NO_NODE = {"CLIO_NODE": "none"}
SHOT = {"ballistic": "pistol", "p": {"D": 0, "env": "indoor"}, "vol": 0.5, "variations": 3, "length": 0.4}
CHIP = {"wave": "noise", "freq": 0, "dur": 0.05, "vol": 0.3}


def folder():
    path = tempfile.mkdtemp(prefix="clio-test-ballistic-")
    return path


class Playing(Backend):
    """Plays nothing, logs what it would play, and is not the tests' recorder: work goes to the background."""

    def __init__(self):
        self.played = []

    def can_play(self, path):
        return True

    def play(self, path, volume=1.0):
        self.played.append((path, volume))


def audio(sets=None, sounds=None, env=None, backend=None, game_dir=None):
    a = Audio(game_dir, sounds=sounds, backend=backend or NullBackend(record=True), cache_dir=folder(), env=env,
              sound_sets=sets)
    return a


def frames(path):
    with wave.open(path) as w:
        raw = w.readframes(w.getnframes())
        peak = max(abs(int.from_bytes(raw[i:i + 2], "little", signed=True)) for i in range(0, len(raw), 2)) / 32767
        return w.getnchannels(), w.getframerate(), w.getsampwidth(), w.getnframes() / w.getframerate(), peak


class SpecTests(unittest.TestCase):
    def test_a_spec_is_read_with_defaults_and_limits(self):
        self.assertIsNone(ballistic.spec_of(CHIP))
        s = ballistic.spec_of({"ballistic": "pistol", "p": {"D": 3}, "action": "game"})
        self.assertEqual((s["preset"], s["p"], s["action"], s["vol"], s["variations"], s["length"], s["channels"]),
                         ("pistol", {"D": 3}, "game", 0.7, 4, 2.5, 2))
        s = ballistic.spec_of({"ballistic": {"kind": "discharge", "dcDist": 2}, "p": {"dcDist": 3}, "vol": 9,
                               "variations": 99, "length": "x", "channels": 1})
        self.assertEqual((s["preset"], s["p"], s["vol"], s["variations"], s["length"], s["channels"]),
                         ("", {"kind": "discharge", "dcDist": 3}, 1.0, 12, 2.5, 1))

    def test_the_engines_names_are_read_without_running_it(self):
        presets, keys, actions, action_keys = ballistic.known()
        self.assertTrue({"pistol", "ricochet", "charge", "tesla"} <= presets)
        self.assertTrue({"kind", "v0", "D", "miss", "env", "exW", "dcDist"} <= keys)
        self.assertIn("game", actions)
        self.assertIn("loud", action_keys)

    def test_check_names_what_is_wrong(self):
        self.assertEqual(ballistic.problems(SHOT, "s"), [])
        found = ballistic.problems({"ballistic": "pistl", "p": {"D": 0, "Dee": 1, "zz": 2}, "action": "loudest",
                                    "channels": 3}, "s")
        self.assertEqual(found, ["s: Ballistic has no preset 'pistl'", "s: Ballistic has no parameters Dee, zz",
                                 "s: Ballistic has no action preset 'loudest' (there are: block, far, game, none, slow)",
                                 "s: \"channels\" should be 1 or 2"])
        self.assertIn("should be the name of a preset", ballistic.problems({"ballistic": 7}, "s")[0])

    def test_rootless_has_a_ballistic_set_and_it_checks_clean(self):
        data = GameData(ROOTLESS)
        self.assertIn("ballistic", data.sound_sets)
        for name in ("pistol", "shotgun", "chaingun", "punch", "hit_body", "hit_wall", "fly_by", "explosion"):
            self.assertTrue(ballistic.is_spec(data.sound_sets["ballistic"][name]), name)
        self.assertEqual(data.validate(), [])
        data.config["sound_set"] = "kazoo"
        data.sound_sets["ballistic"]["pistol"] = dict(SHOT, p={"Dee": 1})
        problems = data.validate()
        self.assertIn("game.json: unknown sound_set 'kazoo' (there are: default, ballistic)", problems)
        self.assertIn("sounds.ballistic.json: sound 'pistol': Ballistic has no parameter Dee", problems)


class SetTests(unittest.TestCase):
    """Sound sets on their own: no Ballistic needed."""

    def test_a_set_plays_over_the_games_own_sounds(self):
        a = audio(sets={"loud": {"pickup": CHIP, "door": "pickup", "beep": CHIP}}, sounds={"door": CHIP})
        a.sfx("pickup")
        own = a.backend.log[-1][1]
        self.assertTrue(a.set_sound_set("LOUD"))
        a.sfx("pickup")
        self.assertNotEqual(a.backend.log[-1][1], own)
        a.sfx("door")                                             # the set's "door" is the game's "pickup"
        self.assertEqual(a.backend.log[-1][1], own)
        self.assertTrue(a.sfx("unlock"))                          # not in the set: the built-in sound
        self.assertFalse(a.set_sound_set("quiet"))
        self.assertEqual(a.sound_set, "loud")
        self.assertTrue(a.set_sound_set("default"))
        self.assertIsNone(a.sound_set)
        self.assertFalse(a.sfx("beep"))                           # only the set has it

    def test_the_sound_command_switches_sets(self):
        s = Session("derelict", record_audio=True).start()
        self.assertIn("This game has one set of sounds.", s.do("sound set"))
        s.game.audio.sets = {"loud": {"pickup": CHIP}}
        self.assertIn("Sound set: default. There are: default, loud.", s.do("sound set"))
        self.assertIn("Sound set: loud.", s.do("sound set loud"))
        self.assertIn("There is no sound set called 'kazoo'", s.do("sound set kazoo"))
        self.assertIn("Sound set: loud (sets: default, loud)", s.do("sound"))
        self.assertIn("Sound set: default.", s.do("sound set default"))

    def test_a_game_chooses_its_set_and_the_player_overrides_it(self):
        s = Session("derelict", record_audio=True)
        self.assertIsNone(s.game.audio.sound_set)
        old = os.environ.pop("CLIO_SOUNDS", None)
        try:
            os.environ["CLIO_SOUNDS"] = "nope"
            s = Session("derelict", record_audio=True)
            self.assertIsNone(s.game.audio.sound_set)
            self.assertIn("no sound set called 'nope'", s.game.audio.last_error)
        finally:
            os.environ.pop("CLIO_SOUNDS", None)
            if old is not None:
                os.environ["CLIO_SOUNDS"] = old


class Heard:
    """An audio stand-in that keeps the names a level plays."""

    sets = {}

    def __init__(self):
        self.names = []

    def sfx(self, name, fallback=None):
        self.names.append(name)
        return True


class LevelSoundTests(unittest.TestCase):
    def level(self, audio):
        lv = Level(GameData(ROOTLESS), "e1m1", seed=1, audio=audio)
        told = []
        lv.console = TextConsole(told.append, lambda prompt: None)
        lv.console.page = lambda lv, lines, automap=False: told.append(lines)
        lv.told = told
        return lv

    def test_shots_land_on_walls_and_bodies(self):
        heard = Heard()
        lv = self.level(heard)
        for m in lv.monsters:
            m.dead = True
        lv.player.x, lv.player.y, lv.player.facing = 17, 28, 0
        lv.player.weapon = "2"
        lv.update_seen()
        lv.run_line("f")
        self.assertEqual(heard.names[-2:], ["pistol", "hit_wall"])
        z = next(m for m in lv.monsters if not m.barrel)
        z.dead, z.hp = False, 999
        lv.player.x, lv.player.y, lv.player.facing = z.x, z.y + 1, 0
        lv.update_seen()
        for _ in range(6):                                        # one of them lands
            lv.run_line("f %s" % z.tag)
        self.assertIn("hit_body", heard.names)

    def test_a_monsters_shot_that_goes_wide_flies_by(self):
        heard = Heard()
        lv = self.level(heard)
        z = next(m for m in lv.monsters if m.kind == "zombie")
        lv.rng.random = lambda: 0.999                             # every shot misses
        lv.ranged(z, None, 8)
        self.assertEqual(heard.names[-2:], ["pistol", "fly_by"])

    def test_the_sound_set_command_in_a_level(self):
        a = audio(sets={"loud": {"pickup": CHIP}})
        lv = self.level(a)
        lv.run_line("sound set loud")
        self.assertEqual(a.sound_set, "loud")
        lv.run_line("sound")
        self.assertIn("Sound set: loud (sets: default, loud)", [l for l, _r in lv.told[-1]])


class WithoutNodeTests(unittest.TestCase):
    def test_without_node_the_games_own_sound_plays(self):
        a = audio(sets={"b": {"pistol": SHOT, "zap2": dict(SHOT, fallback="pickup"), "only": SHOT}},
                  sounds={"pistol": CHIP}, env=NO_NODE)
        a.sfx("pistol")
        own = a.backend.log[-1][1]
        self.assertIn("Node.js, which is not here", a.choose_set("b"))
        self.assertTrue(a.sfx("pistol"))
        self.assertEqual(a.backend.log[-1][1], own)
        self.assertTrue(a.sfx("zap2"))                            # its fallback
        self.assertFalse(a.sfx("only"))                           # nothing to fall back on: silence, no error
        self.assertEqual(a.last_error, "")
        self.assertTrue(any("Node.js not found" in l for l in a.status()))

    def test_baked_takes_play_without_node(self):
        game = folder()
        sounds = os.path.join(game, "sounds", "b")
        os.makedirs(sounds)
        spec = ballistic.spec_of(SHOT)
        for k in (1, 2):
            with open(os.path.join(sounds, "pistol.%d.wav" % k), "wb") as f:
                f.write(b"RIFF")
        with open(os.path.join(sounds, ballistic.BAKED), "w") as f:
            json.dump({"format": ballistic.BAKED_FORMAT, "version": 1,
                       "sounds": {"pistol": {"spec": "old", "files": ["pistol.1.wav", "pistol.2.wav", "gone.wav"]}}}, f)
        a = audio(sets={"b": {"pistol": SHOT}}, env=NO_NODE, game_dir=game)
        a.set_sound_set("b")
        got = set()
        for _ in range(4):
            a.sfx("pistol")
            path = a.backend.log[-1][1]
            got.add(os.path.basename(path))
            self.assertEqual(os.path.dirname(path), sounds)
        self.assertEqual(got, {"pistol.1.wav", "pistol.2.wav"})   # stale, but better than the chip without Node
        files, fresh = a.ballistic.baked("b", "pistol", spec)
        self.assertFalse(fresh)
        self.assertEqual(len(files), 2)


@unittest.skipUnless(NODE, "Node.js is not installed")
class RenderTests(unittest.TestCase):
    def test_takes_render_vary_and_are_kept(self):
        cache = folder()
        a = Audio(sounds={"pistol": CHIP}, backend=NullBackend(record=True), cache_dir=cache, sound_sets={"b": {"pistol": SHOT}})
        a.set_sound_set("b")
        paths = []
        for _ in range(4):
            self.assertTrue(a.sfx("pistol"))
            paths.append(a.backend.log[-1][1])
        self.assertEqual(len(set(paths)), 3)                      # three takes, each played before one repeats
        self.assertEqual(paths[0], paths[3])
        for p in set(paths):
            self.assertTrue(os.path.basename(p).startswith("ballistic-"))
            ch, rate, width, seconds, peak = frames(p)
            self.assertEqual((ch, rate, width), (2, 48000, 2))
            self.assertLessEqual(seconds, 0.4 + 1e-3)
            self.assertAlmostEqual(peak, 0.5 * a.sfx_volume, delta=0.01)     # its level, and the effects volume
        self.assertEqual(a.ballistic.rendered, 3)
        b = Audio(backend=NullBackend(record=True), cache_dir=cache, sound_sets={"b": {"pistol": SHOT}})
        b.set_sound_set("b")
        b.sfx("pistol")
        self.assertEqual((b.backend.log[-1][1], b.ballistic.rendered), (paths[0], 0))   # from the cache
        b.set_volume(sfx=0.4)
        b.sfx("pistol")
        self.assertAlmostEqual(frames(b.backend.log[-1][1])[4], 0.2, delta=0.01)
        a.shutdown()
        b.shutdown()

    def test_errors_come_back_as_words(self):
        r = ballistic.Renderer(NODE)
        try:
            info = r.call({"cmd": "info"})
            self.assertIn("pistol", info["presets"])
            self.assertEqual(r.call({"cmd": "render", "preset": "nope", "out": "x"})["error"],
                             'Ballistic has no preset called "nope"')
            self.assertEqual(r.call({"cmd": "render", "p": {"Dee": 1}, "out": "x"})["error"], "Ballistic has no parameter Dee")
            self.assertEqual(r.call({"cmd": "render", "preset": "pistol", "action": {"oomph": 1}, "out": "x"})["error"],
                             "Ballistic has no action parameter oomph")
            self.assertEqual(r.call({"cmd": "dance"})["error"], 'unknown request "dance"')
        finally:
            r.close()
        a = audio(sets={"b": {"bad": {"ballistic": "nope"}}})
        a.set_sound_set("b")
        self.assertFalse(a.sfx("bad"))
        self.assertIn("bad (Ballistic has no preset called \"nope\")", " ".join(a.status()))

    def test_takes_render_in_the_background_before_they_are_needed(self):
        backend = Playing()
        a = audio(sets={"b": {"pistol": dict(SHOT, variations=2), "wall": {"ballistic": "ricochet", "variations": 2,
                                                                           "length": 0.3}}}, backend=backend)
        a.set_sound_set("b")
        self.assertFalse(a.ballistic.sync)
        self.assertTrue(a.ballistic.settle(60))
        self.assertEqual(a.ballistic.rendered, 4)
        a.sfx("pistol")
        a.sfx("pistol")
        a.sfx("wall")
        self.assertEqual(len(set(p for p, _v in backend.played)), 3)
        self.assertEqual({v for _p, v in backend.played}, {1.0})  # the level is in the file
        self.assertIn("Ballistic sounds: 4 takes rendered", " ".join(a.status()))
        a.shutdown()

    def test_baking_writes_takes_that_play_without_node(self):
        game = folder()
        sounds = ballistic.Sounds(lambda: game, lambda: game, sync=True)
        lines = []
        self.assertEqual(sounds.bake("b", [("pistol", dict(SHOT, variations=2)), ("chip", CHIP)], lines.append), [])
        sounds.close()
        self.assertEqual(len(lines), 1)
        where = os.path.join(game, "sounds", "b")
        self.assertEqual(sorted(os.listdir(where)), ["baked.json", "pistol.1.wav", "pistol.2.wav"])
        self.assertAlmostEqual(frames(os.path.join(where, "pistol.1.wav"))[4], 0.5, delta=0.01)   # its own level
        a = audio(sets={"b": {"pistol": dict(SHOT, variations=2)}}, env=NO_NODE, game_dir=game)
        a.set_sound_set("b")
        a.sfx("pistol")
        self.assertEqual(os.path.dirname(a.backend.log[-1][1]), where)
        self.assertTrue(a.ballistic.baked("b", "pistol", ballistic.spec_of(dict(SHOT, variations=2)))[1])
        sounds = ballistic.Sounds(lambda: game, lambda: game, sync=True)
        self.assertEqual(sounds.bake("b", [("pistol", dict(SHOT, variations=1))]), [])          # fewer takes: one goes
        sounds.close()
        self.assertEqual(sorted(os.listdir(where)), ["baked.json", "pistol.1.wav"])

    def test_every_sound_of_rootless_renders(self):
        data = GameData(ROOTLESS)
        a = audio(sets=data.sound_sets, sounds=data.sounds)
        a.set_sound_set("ballistic")
        for name, spec in data.sound_sets["ballistic"].items():
            self.assertTrue(a.sfx(name), name)
            path = a.backend.log[-1][1]
            self.assertTrue(os.path.basename(path).startswith("ballistic-"), name)
            seconds, peak = frames(path)[3:]
            self.assertLessEqual(seconds, spec["length"] + 1e-3, name)
            self.assertAlmostEqual(peak, spec["vol"] * a.sfx_volume, delta=0.01, msg=name)
        self.assertEqual(a.ballistic.failed, {})
        a.shutdown()


if __name__ == "__main__":
    unittest.main()
