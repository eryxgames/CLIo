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
        self.assertEqual(make({"WT_SESSION": "1"}, unicode=True).glyph_mode, "full")    # (not Windows' console)
        from unittest import mock
        with mock.patch("engine.term._WINDOWS", True):                # Windows' own console: its fonts' glyphs
            self.assertEqual(make({}, unicode=True).glyph_mode, "console")
            self.assertEqual(make({"WT_SESSION": "1"}, unicode=True).glyph_mode, "full")
        with mock.patch("engine.term._WINDOWS", False):
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

    def test_menu_takes_a_trailing_number_when_asked_to(self):
        answers = iter(["heavy 2", "s3", "2", "strike", "strike 2"] + ["strike 2"] * 6)
        t = Term(out=io.StringIO(), inp=lambda p: next(answers), width=40, color=0, animate=False, env={})
        ui = UI(t, load_theme("minimal"))
        options = ["Strike", "Heavy blow", "Guard"]
        got = []
        for _ in range(4):
            got.append((ui.menu(options, numbered=True, cancel=False), ui.menu_number))
        self.assertEqual(got, [(1, 2), (0, 3), (1, None), (0, None)])
        self.assertEqual(ui.menu(options, cancel=False, aliases={"strike 2": 2}), 2)   # aliases come first
        self.assertIsNone(ui.menu(options))                     # without "numbered" it is no answer
        self.assertIsNone(ui.menu_number)


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

    def test_slides_and_levels_in_track_notation(self):
        self.assertEqual(synth.split_note("c4"), ("c4", None, 1.0, 1.0))
        name, target, start, end = synth.split_note("c3>c5@3>9")
        self.assertEqual((name, target, end), ("c3", "c5", 1.0))
        self.assertAlmostEqual(start, 3 / 9.0)
        self.assertEqual(synth.split_note("k@0")[2:], (0.0, 0.0))
        self.assertEqual(synth.split_note("c4@loud")[2:], (1.0, 1.0))      # nonsense is ignored, not fatal
        events, length = synth.parse_track("c4@5:2 - [c4 e4 g4]@6:4 | c3>c5:8")
        self.assertEqual(length, 15)
        self.assertEqual(events, [(0, 3, ["c4@5"]), (3, 4, ["c4@6", "e4@6", "g4@6"]), (7, 8, ["c3>c5"])])
        # a glide is even in pitch: from c4 to c5 in a second there are (f2 - f1) / ln 2 cycles
        s = synth.tone(261.63, 1.0, "sine", attack=0, decay=0, sustain=1, release=0, tail=False,
                       slide_to=523.25, glide=True)
        crossings = sum(1 for a, b in zip(s, s[1:]) if a < 0 <= b)
        self.assertTrue(374 <= crossings <= 380, crossings)
        half = sum(1 for a, b in zip(s[:len(s) // 2], s[1:len(s) // 2]) if a < 0 <= b)
        self.assertTrue(153 <= half <= 159, half)                         # f# after half the time, not g

        def song(track, wave="square"):
            return {"tempo": 120, "steps_per_beat": 4, "loop": False, "sequence": ["p"], "patterns": {"p": {"a": track}},
                    "instruments": {"a": {"wave": wave, "volume": 0.5, "attack": 0.001, "decay": 0.01,
                                          "sustain": 1.0, "release": 0.01}}}

        step = int(60.0 / 120 / 4 * synth.RATE)

        def peak(samples, at):
            return max(abs(v) for v in samples[int(at * step) + 60:int((at + 1) * step) - 60])

        plain = synth.render_song(song("c4:4 c4:4"))
        self.assertEqual(synth.render_song(song("c4@9:4 c4:4")), plain)   # full level is the old sound
        soft = synth.render_song(song("c4:4 c4@3:4"))
        self.assertAlmostEqual(peak(soft, 5) / peak(soft, 1), 3 / 9.0, delta=0.02)
        swell = synth.render_song(song("c4@1>9:16"))
        self.assertLess(peak(swell, 1), 0.3 * peak(swell, 14))
        self.assertGreater(peak(swell, 8), peak(swell, 2))
        riser = synth.render_song(song("c3>c5@2>9:16 .:2", "sine"))
        early = sum(1 for a, b in zip(riser[:4 * step], riser[1:4 * step]) if a < 0 <= b)
        late = sum(1 for a, b in zip(riser[10 * step:14 * step], riser[10 * step + 1:14 * step]) if a < 0 <= b)
        self.assertGreater(late, 2.3 * early)                             # two octaves up by the end
        hiss = synth.render_song(song("c3>c6:8", "noise"))
        self.assertGreater(max(abs(v) for v in hiss), 0.05)
        kit = dict(song("k k@3"), instruments={"a": {"wave": "drums", "volume": 0.6}})
        hits = synth.render_song(kit)
        self.assertLess(max(abs(v) for v in hits[step:2 * step]), 0.5 * max(abs(v) for v in hits[:step]))
        chord = synth.render_song(song("[c4 e4 g4]@4:4"))
        self.assertLess(max(abs(v) for v in chord), 0.6 * max(abs(v) for v in synth.render_song(song("[c4 e4 g4]:4"))))

    def test_an_overdriven_instrument(self):
        def song(track, **inst):
            return {"tempo": 120, "steps_per_beat": 4, "loop": False, "sequence": ["p"], "patterns": {"p": {"a": track}},
                    "instruments": {"a": dict({"wave": "sine", "volume": 0.5, "attack": 0.001, "decay": 0.01,
                                               "sustain": 1.0, "release": 0.01}, **inst)}}

        def loud(samples):
            return (sum(v * v for v in samples) / len(samples)) ** 0.5

        clean = synth.render_song(song("[e2 b2]:8 .:8"))
        self.assertEqual(synth.render_song(song("[e2 b2]:8 .:8", drive=0)), clean)       # no drive: the old sound
        hard = synth.render_song(song("[e2 b2]:8 .:8", drive=0.8))
        self.assertAlmostEqual(max(abs(v) for v in hard), max(abs(v) for v in clean), places=6)   # the peak stays
        self.assertGreater(loud(hard), 1.3 * loud(clean))                                 # and the rest comes up to it
        some = synth.render_song(song("[e2 b2]:8 .:8", drive=0.2))
        self.assertTrue(loud(clean) < loud(some) < loud(hard))
        step = int(60.0 / 120 / 4 * synth.RATE)
        self.assertEqual(max(abs(v) for v in hard[10 * step:15 * step]), 0.0)             # silence stays silent
        self.assertEqual(synth.drive([], 1.0), [])
        self.assertEqual(synth.drive([0.0, 0.0], 1.0), [0.0, 0.0])
        self.assertEqual(synth.drive([0.2, -0.4], 9.0)[1], -0.4)                          # out of range: as hard as it goes
        # with a low-pass after it: darker, still a valid song
        dark = synth.render_song(song("[e2 b2]:8 .:8", drive=0.8, lowpass=0.6))
        edges = lambda samples: sum(abs(b - a) for a, b in zip(samples, samples[1:]))
        self.assertLess(edges(dark), edges(hard))

    def test_detune_a_moving_filter_and_a_room(self):
        def song(track, **inst):
            return {"tempo": 120, "steps_per_beat": 4, "loop": False, "sequence": ["p"], "patterns": {"p": {"a": track}},
                    "instruments": {"a": dict({"wave": "saw", "volume": 0.5, "attack": 0.001, "decay": 0.01,
                                               "sustain": 1.0, "release": 0.01}, **inst)}}

        step = int(60.0 / 120 / 4 * synth.RATE)
        loud = lambda samples: (sum(v * v for v in samples) / max(1, len(samples))) ** 0.5
        # how sharp-edged a stretch of sound is: high where there is treble, low where there is none
        edges = lambda samples: sum((b - a) ** 2 for a, b in zip(samples, samples[1:])) / max(1e-9, sum(v * v for v in samples))
        plain = synth.render_song(song("c3:8 .:8"))
        for nothing in ({"detune": 0}, {"filter": None}, {"room": 0}):
            self.assertEqual(synth.render_song(song("c3:8 .:8", **nothing)), plain, nothing)     # the old sound
        # detune: three oscillators beat against each other, so the level wanders where one alone is steady
        wide = synth.render_song(song("c3:16", detune=12))
        blocks = lambda samples: [loud(samples[i:i + step]) for i in range(step, 13 * step, step)]
        self.assertGreater(max(blocks(wide)) / min(blocks(wide)), 1.15)
        self.assertLess(max(blocks(synth.render_song(song("c3:16")))) / min(blocks(synth.render_song(song("c3:16")))), 1.05)
        # a filter that closes: bright at the start of the note, dull at its end; one that opens, the other way
        closing = synth.render_song(song("c3:8 .:8", filter=[2400, 300, 0.8, 0.15]))
        late = slice(5 * step, 7 * step)
        self.assertGreater(edges(closing[:step // 2]), 3.0 * edges(closing[late]))
        opening = synth.render_song(song("c3:8 .:8", filter=[300, 2600, 0.2, 0.5]))
        self.assertLess(edges(opening[:step // 2]), 0.5 * edges(opening[late]))
        self.assertLess(edges(closing[late]), 0.5 * edges(plain[late]))
        ringing = synth.render_song(song("c3:8 .:8", filter=[3000, 200, 1.0, 0.3]))
        self.assertLess(max(abs(v) for v in ringing), 3.0 * max(abs(v) for v in plain))      # loud, not out of bounds
        self.assertEqual(len(synth._swept([0.0] * 100, 99999, 1, 5, 0)), 100)                # nonsense is brought into range
        # a room: sound goes on after the note has stopped, and a larger room keeps it longer
        after = lambda samples: loud(samples[int(8.6 * step):12 * step])
        self.assertEqual(after(plain), 0.0)
        small = synth.render_song(song("c3:8 .:8", room=0.5))
        large = synth.render_song(song("c3:8 .:8", room=[0.5, 2.0]))
        self.assertGreater(after(small), 0.0)
        self.assertGreater(after(large), 1.5 * after(small))
        self.assertEqual(small[:int(0.03 * synth.RATE)], plain[:int(0.03 * synth.RATE)])     # the note itself comes first
        self.assertEqual(synth.room([], 0.5), [])

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

    def test_composer_sound_and_form_are_the_designers_choice(self):
        from engine.audio.compose import LONG, RICH
        self.assertEqual(set(RICH), set(MOODS))
        shaped = ("drive", "detune", "filter", "room")
        for mood in MOODS:
            chip = compose(7, mood)
            self.assertEqual(compose(7, mood, sound="chip", form=None), chip, mood)          # the default: as ever
            self.assertFalse([k for inst in chip["instruments"].values() for k in inst if k in shaped], mood)
            rich = compose(7, mood, sound="rich")
            self.assertEqual((rich["patterns"], rich["sequence"], rich["tempo"]),
                             (chip["patterns"], chip["sequence"], chip["tempo"]), mood)      # the same notes
            self.assertTrue(any(k in inst for inst in rich["instruments"].values() for k in shaped), mood)
            self.assertEqual(set(rich["instruments"]), set(chip["instruments"]), mood)
        self.assertEqual(compose(7, "dark", sound="brass band"), compose(7, "dark"))          # unknown: the chip
        # each rich voice is about as loud as its chip counterpart
        loud = lambda samples: (sum(v * v for v in samples) / len(samples)) ** 0.5
        chip, rich = synth.render_tracks(compose(1, "dark")), synth.render_tracks(compose(1, "dark", sound="rich"))
        for name in ("lead", "arp", "bass"):
            self.assertTrue(0.7 < loud(rich[name]) / loud(chip[name]) < 1.4, name)
        # a form: how the two halves are laid out, and how each is played
        plain = compose(7, "battle")
        long = compose(7, "battle", form="long")
        self.assertEqual(" ".join(long["sequence"]), LONG)
        self.assertEqual((long["patterns"]["A"], long["patterns"]["B"]), (plain["patterns"]["A"], plain["patterns"]["B"]))
        self.assertEqual(sorted(long["patterns"]["(A)"]), ["arp", "bass", "kit"])           # without the tune
        self.assertEqual(sorted(long["patterns"]["B-"]), ["arp", "lead"])                    # quiet: no bass, no drums
        self.assertEqual(long["patterns"]["A+"]["kit"], plain["patterns"]["A"]["kit"])       # drums are not notes
        first = lambda text: synth.note_freq(text.replace("[", "").split(":")[0].split()[0])
        for name in ("lead", "arp", "bass"):                                                  # a tone higher
            self.assertAlmostEqual(first(long["patterns"]["A+"][name]) / first(plain["patterns"]["A"][name]),
                                   2 ** (2 / 12.0), places=4)
        self.assertGreater(len(synth.render_song(long)), 1.9 * len(synth.render_song(plain)))
        own = compose(7, "battle", form="(a) b-+ A")
        self.assertEqual(own["sequence"], ["(A)", "B-+", "A"])
        self.assertEqual(sorted(own["patterns"]["B-+"]), ["arp", "lead"])
        for unreadable in ("A C", "(A B", "A * B", ""):
            self.assertEqual(compose(7, "battle", form=unreadable), plain, unreadable)       # ignored, never fatal
        quiet = compose(7, "space", form="(A)- A")                                           # space has no drums
        self.assertEqual(sorted(quiet["patterns"]["(A)-"]), ["arp"])

    def test_generated_music_takes_the_sound_and_form_set_for_the_game(self):
        audio = Audio(backend=NullBackend(record=True))
        spec = {"generate": {"mood": "dark", "seed": 7}}
        self.assertEqual(audio.resolve_track(spec), ("gen:dark:7:16", "gen", {"mood": "dark", "seed": 7, "bars": 16}))
        self.assertEqual(audio.resolve_track("battle")[0], "gen:battle:0:16")                 # as it has always been
        audio.music_sound, audio.music_form = "rich", "long"
        key, _kind, payload = audio.resolve_track(spec)
        self.assertEqual((key, payload["sound"], payload["form"]), ("gen:dark:7:16:rich:long", "rich", "long"))
        self.assertEqual(audio.resolve_track("battle")[0], "gen:battle:0:16:rich:long")
        own = {"generate": {"mood": "dark", "seed": 7, "sound": "chip", "form": None}}       # a track's own word wins
        self.assertEqual(audio.resolve_track(own)[0], "gen:dark:7:16")
        audio.music(spec)
        self.assertEqual(audio.playing, "gen:dark:7:16:rich:long")
        audio.music_sound = "kazoo"                                                           # nonsense: the chip
        self.assertEqual(audio.resolve_track(spec)[0], "gen:dark:7:16:long")

    def test_a_game_and_a_scene_choose_the_sound_of_their_music(self):
        session = Session("derelict", record_audio=True)
        game = session.game
        scene = game.world.scene
        saved = {key: scene.get(key) for key in ("music", "music_sound", "music_form")}
        try:
            scene.pop("music", None)                                # the scene's default: generated from its mood
            game.resume_music()
            self.assertEqual((game.audio.music_sound, game.audio.music_form), ("chip", None))
            plain = game.audio.wanted
            self.assertTrue(plain.startswith("gen:") and not plain.endswith(":rich"))
            game.cfg["music_sound"], game.cfg["music_form"] = "rich", "long"      # the game's designer
            game.resume_music()
            self.assertEqual(game.audio.wanted, plain + ":rich:long")
            scene["music_sound"], scene["music_form"] = "chip", "(A) A"           # this scene's designer
            game.resume_music()
            self.assertEqual(game.audio.wanted, plain + ":(A) A")
            self.assertEqual(game.audio.resolve_track("battle")[0], "gen:battle:0:16:(A) A")   # a fight here sounds alike
        finally:
            game.cfg.pop("music_sound", None)
            game.cfg.pop("music_form", None)
            for key, value in saved.items():
                if value is None:
                    scene.pop(key, None)
                else:
                    scene[key] = value

    def test_a_song_track_by_track(self):
        song = compose(3, "battle")
        whole, tracks = synth.render_song(song), synth.render_tracks(song)
        self.assertEqual(list(tracks), ["lead", "arp", "bass", "kit"])
        self.assertEqual({len(samples) for samples in tracks.values()}, {len(whole)})
        together = [sum(values) for values in zip(*tracks.values())]
        self.assertLess(max(abs(a - b) for a, b in zip(whole, together)), 1e-9)              # they add up to the song
        self.assertEqual(synth.render_tracks({"patterns": {}}), {})

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

    def test_talked_is_a_condition(self):
        # the dialogue runner records a conversation as the flag "talked:<character>"; it has to be askable
        from engine import dialogue
        s = Session("derelict").start()
        g = s.game
        self.assertFalse(conditions.check("talked:friendly_robot", g))
        self.assertTrue(conditions.check("!talked:friendly_robot", g))
        self.assertEqual(dialogue._start_node(g.data.dialogues["bolt"], g), "hello")
        g.world.flags["talked:friendly_robot"] = True
        self.assertTrue(conditions.check("talked:friendly_robot", g))
        self.assertTrue(conditions.check({"talked": ["friendly_robot"]}, g))
        self.assertFalse(conditions.check({"talked": ["friendly_robot", "ship_ai"]}, g))
        self.assertEqual(dialogue._start_node(g.data.dialogues["bolt"], g), "again")


if __name__ == "__main__":
    unittest.main()
