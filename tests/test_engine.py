# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Unit tests for the engine's building blocks."""
import io
import os
import sys
import unittest
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import ROOT, Session                           # noqa: E402

from engine import automap, conditions                      # noqa: E402
from engine.art import Art                                  # noqa: E402
from engine.audio import Audio, synth                       # noqa: E402
from engine.audio.backends import NullBackend, detect       # noqa: E402
from engine.audio.compose import MOODS, compose             # noqa: E402
from engine.audio.sfx import SFX                            # noqa: E402
from engine.data import GameData, find_games                # noqa: E402
from engine.maze import carve                               # noqa: E402
from engine.parser import Parser                            # noqa: E402
from engine.sprite import Sprite, generate                  # noqa: E402
from engine.term import Term, strip_ansi, to_ascii, visible_len, wrap_ansi   # noqa: E402
from engine.theme import available_themes, load_theme       # noqa: E402
from engine.ui import UI                                    # noqa: E402


def term(color=2, unicode=True, width=60):
    return Term(out=io.StringIO(), width=width, color=color, unicode=unicode, animate=False, env={})


class TermTests(unittest.TestCase):
    def test_markup_nests_and_restores_base(self):
        t = term()
        s = t.markup("a {red}b {b}c{/} d{/} e", base="cyan")
        self.assertEqual(strip_ansi(s), "a b c d e")
        self.assertIn("\x1b[", s)

    def test_unknown_braces_are_literal(self):
        t = term()
        self.assertEqual(strip_ansi(t.markup("use {not a colour} and {{braces}}")),
                         "use {not a colour} and {braces}")

    def test_no_colour_terminal_gets_plain_text(self):
        t = term(color=0)
        self.assertEqual(t.markup("{red}danger{/}", base="blue"), "danger")

    def test_colour_depth_downgrade(self):
        self.assertIn("38;2;", term(color=3).markup("{#ff8800}x{/}"))
        self.assertIn("38;5;", term(color=2).markup("{#ff8800}x{/}"))
        self.assertNotIn("38;", term(color=1).markup("{#ff8800}x{/}"))

    def test_wrap_keeps_every_line_within_width(self):
        t = term()
        text = t.markup("{green}" + "word " * 60 + "{/} supercalifragilisticexpialidocious-and-then-some " * 2)
        for width in (20, 33, 58):
            for line in wrap_ansi(text, width, "  "):
                self.assertLessEqual(visible_len(line), width)

    def test_wrap_preserves_paragraphs(self):
        self.assertEqual(wrap_ansi("one\n\ntwo", 20), ["one", "", "two"])

    def test_environment_switches(self):
        make = lambda env, **kw: Term(out=io.StringIO(), width=40, animate=False, env=env, **kw)    # noqa: E731
        self.assertEqual(make({}, unicode=True).glyph_mode, "full")
        self.assertEqual(make({"CLIO_GLYPHS": "safe"}, unicode=True).glyph_mode, "safe")
        self.assertEqual(make({"CLIO_GLYPHS": "safe"}, unicode=False).glyph_mode, "ascii")
        self.assertEqual(make({}, unicode=True, glyphs="safe").glyphs["heart"], "HP")
        self.assertFalse(make({}, unicode=True).limited_glyphs)
        self.assertTrue(make({"TERM": "linux"}, unicode=True).limited_glyphs)      # kernel console font
        self.assertEqual(make({"NO_COLOR": "1"}).color_depth, 0)
        self.assertEqual(make({"CLIO_COLOR": "3"}).color_depth, 3)

    def test_ascii_fallback_is_pure_ascii(self):
        self.assertTrue(to_ascii("╭─♥ ▀▄█ … ✔ ·╯").isascii())


class UiTests(unittest.TestCase):
    def test_every_theme_renders_within_narrow_and_wide_screens(self):
        for name in available_themes():
            for width in (36, 40, 80):
                for color, uni in ((2, True), (0, False)):
                    t = term(color, uni, width)
                    ui = UI(t, load_theme(name))
                    ui.say("A fairly long line of {item}description{/} that must wrap. " * 3, "description",
                           title="A Room With A Rather Long Name Indeed")
                    ui.say("Spoken words.", "dialogue", title="Somebody")
                    ui.bullets(["{item}one{/}", "two " * 20], title="List")
                    ui.hud(["HP 10/10", "Somewhere With A Long Name", "turn 3"], "x")
                    ui.heading("TITLE")
                    for line in t.out.getvalue().splitlines():
                        self.assertLessEqual(visible_len(line), width, "%s @%d: %r" % (name, width, line))
                    if not uni:
                        self.assertTrue(strip_ansi(t.out.getvalue()).isascii(), name)

    def test_menu_accepts_numbers_text_and_cancel(self):
        answers = iter(["2", "blu", ""])
        t = Term(out=io.StringIO(), inp=lambda p: next(answers), width=40, color=0, animate=False, env={})
        ui = UI(t, load_theme("minimal"))
        self.assertEqual(ui.menu(["red", "green", "blue"]), 1)
        self.assertEqual(ui.menu(["red", "green", "blue"]), 2)
        self.assertIsNone(ui.menu(["red", "green", "blue"]))


class ArtTests(unittest.TestCase):
    SRC = "# c\n@palette\na = red\n@art\n\n /\\\n/__\\\n@mask\n a\naaaa\n@small\n^\n"

    def test_mask_and_variants(self):
        art = Art.parse(self.SRC)
        self.assertEqual(art.size(), (4, 2))
        self.assertEqual([strip_ansi(l) for l in art.render(term(), 10)], [" /\\ ", "/__\\"])
        self.assertEqual(art.render(term(), 2), ["^"])
        self.assertEqual(art.render(term(), 0), [])
        self.assertIn("\x1b[", "".join(art.render(term(), 10)))

    def test_all_game_art_parses_and_fits_a_phone(self):
        count = 0
        for path, _title, _desc in find_games(ROOT):
            art_dir = os.path.join(path, "art")
            if not os.path.isdir(art_dir):
                continue
            for f in os.listdir(art_dir):
                art = Art.load(os.path.join(art_dir, f))
                count += 1
                self.assertTrue(art.variants, f)
                lines = art.render(term(width=40), 36)
                self.assertTrue(lines, "%s has no variant that fits 36 columns" % f)
        self.assertGreater(count, 20)


class SpriteTests(unittest.TestCase):
    def test_half_blocks_and_ascii_fallback(self):
        sp = Sprite(["ab", "ba", "..", "a."], {"a": "#ff0000", "b": "blue"})
        lines = sp.render(term())
        self.assertEqual(len(lines), 2)
        self.assertIn("▀", lines[0])
        plain = sp.render(term(color=0, unicode=False))
        self.assertTrue("".join(plain).isascii())

    def test_generated_sprites_are_stable_and_symmetric(self):
        a, b = generate("Bone Rat", 12), generate("Bone Rat", 12)
        self.assertEqual(a.pixels, b.pixels)
        self.assertNotEqual(a.pixels, generate("Gloom Bat", 12).pixels)
        for row in a.pixels:
            self.assertEqual(row, row[::-1])


class AudioTests(unittest.TestCase):
    def test_note_frequencies(self):
        self.assertAlmostEqual(synth.note_freq("a4"), 440.0, places=3)
        self.assertAlmostEqual(synth.note_freq("c4"), 261.626, places=2)
        self.assertAlmostEqual(synth.note_freq("eb3"), synth.note_freq("d#3"), places=6)
        self.assertEqual(synth.note_freq("."), 0.0)

    def test_tone_has_the_right_pitch(self):
        s = synth.tone(440, 1.0, "sine", attack=0, decay=0, sustain=1, release=0, tail=False)
        crossings = sum(1 for a, b in zip(s, s[1:]) if a < 0 <= b)
        self.assertTrue(437 <= crossings <= 443, crossings)

    def test_track_notation(self):
        events, length = synth.parse_track("c4:2 - . [c4 e4 g4]:4 | d4")
        self.assertEqual(length, 9)
        self.assertEqual(events[0], (0, 3, ["c4"]))
        self.assertEqual(events[1], (4, 4, ["c4", "e4", "g4"]))

    def test_every_builtin_sfx_renders(self):
        for name, spec in SFX.items():
            samples = synth.render_sfx(spec)
            self.assertTrue(samples, name)
            self.assertGreater(max(abs(x) for x in samples), 0.02, name)
            self.assertLess(len(samples) / synth.RATE, 3.0, name)

    def test_composer_is_deterministic_and_audible(self):
        for mood in MOODS:
            song = compose(7, mood, bars=8)
            self.assertEqual(song, compose(7, mood, bars=8))
            samples = synth.render_song(song)
            self.assertGreater(len(samples), synth.RATE * 4, mood)
            self.assertGreater(max(abs(x) for x in samples), 0.05, mood)
        self.assertNotEqual(compose(1, "dark"), compose(2, "dark"))

    def test_wav_file_is_valid(self):
        import tempfile
        path = os.path.join(tempfile.mkdtemp(), "t.wav")
        synth.write_wav(path, synth.render_sfx(SFX["pickup"]))
        with wave.open(path) as w:
            self.assertEqual((w.getnchannels(), w.getsampwidth(), w.getframerate()), (1, 2, synth.RATE))
            self.assertGreater(w.getnframes(), 100)

    def test_game_songs_render(self):
        data = GameData(os.path.join(ROOT, "games", "derelict"))
        samples = synth.render_song(data.songs["theme"])
        self.assertGreater(len(samples) / synth.RATE, 20)

    def test_audio_routes_to_backend_and_survives_silence(self):
        backend = NullBackend(record=True)
        audio = Audio(backend=backend)
        self.assertTrue(audio.sfx("pickup"))
        self.assertFalse(audio.sfx("no-such-sound"))
        audio.music("battle")
        audio.music("battle")                   # same track: no restart
        audio.music(None)
        kinds = [k for k, _p in backend.log]
        self.assertEqual(kinds.count("loop"), 1)
        self.assertIn("stop", kinds)
        silent = Audio(enabled=False)
        self.assertFalse(silent.sfx("pickup"))
        silent.music("battle")                  # must not raise

    def test_backend_detection(self):
        # the rules are checked for a named platform, so this passes on any machine
        none = lambda name: None                                    # noqa: E731
        quiet = {"CLIO_NO_PYGAME": "1"}
        b, note = detect({"CLIO_AUDIO": "off"})
        self.assertIsInstance(b, NullBackend)
        b, note = detect(quiet, which=none, platform="linux")
        self.assertIsInstance(b, NullBackend)
        self.assertIn("no audio player", note)
        b, note = detect(dict(quiet, TERMUX_VERSION="0.118"), which=none)
        self.assertIsInstance(b, NullBackend)
        self.assertIn("pkg install", note)
        b, note = detect(quiet, which=lambda n: "/usr/bin/aplay" if n == "aplay" else None, platform="linux")
        self.assertEqual(b.name, "aplay")
        self.assertTrue(b.can_play("x.wav"))
        self.assertFalse(b.can_play("x.mp3"))
        b, note = detect(quiet, which=lambda n: "/usr/bin/afplay" if n == "afplay" else None, platform="mac")
        self.assertEqual(b.name, "afplay")
        self.assertTrue(b.can_play("x.mp3"))
        b, note = detect(dict(quiet, CLIO_AUDIO="mpv"), which=none, platform="linux")
        self.assertIsInstance(b, NullBackend)
        self.assertIn("not found", note)

    @unittest.skipUnless(sys.platform.startswith("win"), "Windows only")
    def test_windows_needs_no_extra_player(self):
        b, note = detect({"CLIO_NO_PYGAME": "1"}, which=lambda name: None)
        self.assertEqual(b.name, "winmm")
        self.assertTrue(b.can_play("x.wav"))
        self.assertTrue(b.can_play("x.mp3"))
        b.shutdown()


class ParserTests(unittest.TestCase):
    def setUp(self):
        self.p = Parser()

    def check(self, line, verb, obj="", target=""):
        c = self.p.parse(line)
        self.assertEqual((c.verb, c.obj, c.target), (verb, obj, target), line)

    def test_sentences(self):
        self.check("look", "look")
        self.check("l", "look")
        self.check("look at the rusty locker", "examine", "rusty locker")
        self.check("x locker", "examine", "locker")
        self.check("take the bent wire", "take", "bent wire")
        self.check("pick up wire", "take", "wire")
        self.check("take all", "take", "all")
        self.check("give the red apple to the bugrat", "give", "red apple", "bugrat")
        self.check("use relay on reactor", "use", "relay", "reactor")
        self.check("combine goo with suit", "combine", "goo", "suit")
        self.check("combine goo and suit", "combine", "goo", "suit")
        self.check("unlock door with key", "unlock", "door", "key")
        self.check("pick lock of locker", "unlock", "locker")
        self.check("talk to bolt", "talk", "bolt")
        self.check("n", "go", "n")
        self.check("go north", "go", "north")
        self.check("go to storage bay door", "go", "storage bay door")
        self.check("exit", "go", "")
        self.check("take off suit", "unequip", "suit")
        self.check("i", "inventory")
        self.check("look at myself", "stats")
        self.check("music off", "sound", "music off")
        self.check("volume 40", "sound", "volume 40")

    def test_unknown_verbs_become_custom(self):
        c = self.p.parse("pray")
        self.assertEqual((c.verb, c.word), ("custom", "pray"))
        c = self.p.parse("exmine locker")
        self.assertIn("examine", c.error)


class MapAndMazeTests(unittest.TestCase):
    def test_layout_follows_directions_and_fills_gaps(self):
        scenes = {
            "a": {"exits": [{"scene_id": "b", "dir": "e"}, {"scene_id": "c"}]},
            "b": {"exits": [{"scene_id": "a", "dir": "w"}]},
            "c": {"exits": [{"scene_id": "a"}]},
        }
        pos = automap.layout(scenes, "a")
        self.assertEqual(pos["b"], (pos["a"][0] + 1, pos["a"][1], 0))
        self.assertEqual(len(set(pos.values())), 3)
        self.assertTrue(scenes["a"]["exits"][1].get("_dir"))

    def test_maze_is_connected(self):
        import random
        for seed in range(25):
            edges, start, far, dist = carve(random.Random(seed), 5, 4, 0.2)
            self.assertEqual(len(dist), 20)
            self.assertGreaterEqual(len(edges), 19)
            self.assertNotEqual(start, far)


class ConditionTests(unittest.TestCase):
    def test_conditions_and_effects(self):
        s = Session("derelict").start()
        g, w = s.game, s.world
        self.assertTrue(conditions.check("!nope", g))
        self.assertFalse(conditions.check("nope", g))
        self.assertTrue(conditions.check({"in_scene": "utility_room"}, g))
        self.assertTrue(conditions.check({"stat": ["health", ">=", 10]}, g))
        self.assertFalse(conditions.check({"all": ["!nope", "has:passcard"]}, g))
        self.assertTrue(conditions.check({"any": ["nope", {"not": "nope"}]}, g))
        conditions.run([{"set": "nope"}, {"give": "passcard", "quiet": True}, {"var": ["n", "+=", 2]}], g)
        self.assertTrue(conditions.check({"all": ["nope", "has:passcard", {"var": ["n", ">=", 2]}]}, g))
        conditions.run({"if": "nope", "then": [{"stat": {"health": -5}}], "else": [{"heal": "full"}]}, g)
        self.assertEqual(w.stats["health"], 55)


if __name__ == "__main__":
    unittest.main()
