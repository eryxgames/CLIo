# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Logos, banners and art animations: what a game can choose for how it looks."""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import ROOT                                    # noqa: E402

from engine import banner, fx, pixels                       # noqa: E402
from engine.art import LOGO_DIR, LOGOS, Art, load_logo, logo_names   # noqa: E402
from engine.audio import Audio                              # noqa: E402
from engine.audio.backends import NullBackend               # noqa: E402
from engine.data import GameData                            # noqa: E402
from engine.game import Game                                # noqa: E402
from engine.term import Term, strip_ansi, to_ascii, visible_len   # noqa: E402
from engine.theme import load_theme                         # noqa: E402

WIDTHS = (24, 40, 78)


class Quick(Term):
    """An animating terminal that does not wait (so animations run in tests)."""

    def sleep(self, seconds):
        self.slept = getattr(self, "slept", 0) + seconds


def term(color=3, unicode=True, width=78, animate=False):
    cls = Quick if animate else Term
    return cls(out=io.StringIO(), width=width, height=40, color=color, unicode=unicode, animate=animate, env={})


def shown(t):
    """What a terminal shows, as plain lines (cursor jumps leave the last frame on top)."""
    text = strip_ansi(t.out.getvalue())
    return [l for l in text.replace("\r", "").split("\n")]


SAMPLE = """# sample
@palette
a = #ff8800   # orange, after a space
b = steel # a name
c=#ffffff b
@effect shine speed=2
@fps 4
@art
 /##\\
 \\##/
@mask
 aaaa
 bbcc
@ascii
 [##]
@frame
 /--\\
 \\--/
"""


class ArtFormatTests(unittest.TestCase):
    def test_hex_colours_may_follow_a_space(self):
        art = Art.parse(SAMPLE)
        self.assertEqual(art.palette, {"a": "#ff8800", "b": "steel", "c": "#ffffff b"})

    def test_effect_fps_and_the_ascii_version(self):
        art = Art.parse(SAMPLE)
        self.assertEqual(art.effect, {"name": "shine", "speed": 2})
        self.assertEqual(art.fps, 4)
        self.assertEqual(art.render(term(unicode=False)), art._render(term(), [" [##]"], None))
        self.assertIn("/##", strip_ansi(art.render(term())[0]))

    def test_written_and_read_back(self):
        art = Art.parse(SAMPLE)
        again = Art.parse(art.to_text("sample"))
        self.assertEqual(again.palette, art.palette)
        self.assertEqual(again.variants, art.variants)
        self.assertEqual(again.frames, art.frames)
        self.assertEqual(again.effect, art.effect)

    def test_frames_play_and_end_on_the_art(self):
        art = Art.parse(SAMPLE)
        t = term()
        frames, reveals = art.animation(t, effect="frames")
        self.assertFalse(reveals)
        self.assertEqual(len(frames), 2)
        self.assertEqual(frames[-1][0], art.render(t))
        self.assertEqual(frames[0][1], 0.25)
        self.assertEqual(art.animation(t, effect="none"), ([], False))
        self.assertTrue(art.animation(t, effect="frames reveal=1")[1])

    def test_braille_and_quadrants_have_ascii(self):
        self.assertEqual(to_ascii("⣿⣀⠉ ▖▗▘▝▚▞"), "#.' ..''\\/")
        self.assertTrue(to_ascii("".join(chr(c) for c in range(0x2800, 0x2900))).isascii())

    def test_accents_are_dropped_not_turned_into_question_marks(self):
        self.assertEqual(to_ascii("Příběh žluťoučký kůň"), "Pribeh zlutoucky kun")


class LogoTests(unittest.TestCase):
    def test_the_list_of_logos_is_current(self):
        files = sorted(f[:-4] for f in os.listdir(LOGO_DIR) if f.endswith(".art"))
        self.assertEqual(files, sorted(LOGOS[1:]))
        self.assertEqual(logo_names()[0], "clio")
        self.assertIs(load_logo("no such logo"), None)

    def test_the_clio_logo_is_the_terminal(self):
        clio = load_logo(None)
        self.assertEqual(load_logo("terminal").variants, clio.variants)
        self.assertIn("clio", strip_ansi(clio.render(term())[1]))
        self.assertTrue(clio.frames)                                # it types its name
        self.assertIn("_____", "".join(load_logo("classic").variants["art"][0]))

    def test_every_logo_fits_and_degrades(self):
        for name in logo_names():
            art = load_logo(name)
            for width in WIDTHS:
                for uni in (True, False):
                    for colour in (0, 1, 3):
                        t = term(colour, uni, width)
                        lines = art.render(t, width - 4)
                        self.assertTrue(lines, "%s does not show at %d" % (name, width))
                        for l in lines:
                            self.assertLessEqual(visible_len(l), width - 4, name)
                            if not uni:
                                self.assertTrue(to_ascii(strip_ansi(l)).isascii(), name)
                                self.assertNotIn("?", to_ascii(strip_ansi(l)), name)

    def test_every_animation_keeps_the_size_and_ends_on_the_logo(self):
        for name in logo_names():
            art = load_logo(name)
            for width in WIDTHS:
                t = term(3, True, width)
                base = art.render(t, width - 4)
                frames, _reveals = art.animation(t, width - 4, seed=1)
                if not frames:
                    continue
                self.assertEqual(frames[-1][0], base, name)
                size = {(len(f), visible_len(f[0])) for f, _s in frames}
                self.assertEqual(size, {(len(base), visible_len(base[0]))}, name)
                self.assertLess(sum(s for _f, s in frames), 3.0, name)


class EffectTests(unittest.TestCase):
    def setUp(self):
        self.art = load_logo("pixel")

    def test_every_effect_on_every_terminal(self):
        for name in fx.NAMES:
            for colour in (0, 1, 3):
                for uni in (True, False):
                    t = term(colour, uni)
                    frames, reveals = self.art.animation(t, 74, effect=name, seed=5)
                    if name in fx.COLOUR_ONLY and not colour:
                        self.assertEqual(frames, [], name)
                    if name in ("none", "frames"):
                        self.assertEqual(frames, [], name)
                    if frames:
                        self.assertEqual(reveals, name in fx.REVEALS)
                        self.assertEqual(frames[-1][0], self.art.render(t, 74))

    def test_the_same_seed_the_same_glitch(self):
        a = self.art.animation(term(), 74, effect="glitch", seed=3)
        b = self.art.animation(term(), 74, effect="glitch", seed=3)
        c = self.art.animation(term(), 74, effect="glitch", seed=4)
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)

    def test_specs(self):
        self.assertEqual(fx.parse("glitch loops=2 speed=0.5"), {"name": "glitch", "loops": 2, "speed": 0.5})
        self.assertEqual(fx.parse({"name": "Shine"}), {"name": "shine"})
        self.assertEqual(fx.parse(False), {"name": "none"})
        self.assertIsNone(fx.parse(None))
        self.assertFalse(fx.known("sparkle"))
        self.assertEqual(fx.describe("glitch loops=2"), "glitch loops=2")
        slow = self.art.animation(term(), 74, effect="pulse speed=0.5")[0]
        fast = self.art.animation(term(), 74, effect="pulse")[0]
        self.assertAlmostEqual(sum(s for _f, s in slow), 2 * sum(s for _f, s in fast))


class BannerTests(unittest.TestCase):
    TEXTS = ("CLIo", "The Hollow", "Příběh 2: Návrat!", "A")

    def test_every_style_fits_every_screen(self):
        for style in banner.STYLES:
            for text in self.TEXTS:
                for width in (20, 32, 36, 74):
                    art = banner.make({"text": text, "style": style}, width)
                    self.assertIsNotNone(art, (style, text, width))
                    for uni in (True, False):
                        for l in art.render(term(3, uni, width + 4), width):
                            self.assertLessEqual(visible_len(l), width, (style, text, width))
                    self.assertTrue(all(l.isascii() for l in art.variants["ascii"][0]), (style, text))

    def test_big_and_wrapped(self):
        wide = banner.make({"text": "The Hollow", "style": "pixel"}, 74)
        narrow = banner.make({"text": "The Hollow", "style": "pixel"}, 36)
        self.assertEqual(wide.size()[1], 4)
        self.assertGreater(narrow.size()[1], 4)            # two lines of text
        double = banner.make({"text": "CLIo", "style": "pixel", "scale": 2}, 74)
        self.assertEqual(double.size()[1], 7)

    def test_lower_case_is_small_capitals(self):
        rows, kind = banner.glyph("o")
        self.assertEqual(kind, "l")
        self.assertEqual(rows[:2], [".....", "....."])
        self.assertEqual(banner.glyph("é")[0], banner.glyph("e")[0])
        self.assertEqual(banner.glyph("~")[0], banner.glyph("?")[0])

    def test_style_effects_and_palettes(self):
        self.assertEqual(banner.make({"text": "x", "style": "glitch"}, 74).effect["name"], "glitch")
        self.assertIsNone(banner.make({"text": "x", "style": "glitch", "effect": None}, 74).effect)
        main, accent = banner.palette_of({"palette": "fire"}, "pixel")
        self.assertEqual(main, banner.PALETTES["fire"][0])
        main, accent = banner.palette_of({"colors": ["#ff0000", "#00ff00"], "accent": "#0000ff"}, "pixel")
        self.assertEqual((main, accent), (["#ff0000", "#00ff00"], ["#0000ff"]))

    def test_a_games_own_palettes_and_house_style(self):
        own = {"dusk": ["#ffd27a", "#ff6f91"], "brand": {"colors": ["#ffffff", "#ff0000"], "accent": ["#00ff00"]}}
        self.assertEqual(banner.palette_of({"palette": "dusk"}, "pixel", own), (["#ffd27a", "#ff6f91"], None))
        self.assertEqual(banner.palette_of({"palette": "brand"}, "led", own), (["#ffffff", "#ff0000"], ["#00ff00"]))
        self.assertEqual(banner.palette_of({"palette": "ice"}, "pixel", own)[0], banner.PALETTES["ice"][0])
        house = {"style": "led", "palette": "brand", "effect": "none"}
        spec = banner.normalise({"text": "x"}, defaults=house, theme=load_theme("techno"))
        self.assertEqual((spec["style"], spec["palette"], spec["effect"]), ("led", "brand", "none"))
        spec = banner.normalise({"text": "x", "style": "chrome"}, defaults=house)
        self.assertEqual((spec["style"], spec["palette"]), ("chrome", "brand"))     # the house colours stay
        art = banner.make({"text": "Hi"}, 74, palettes=own, defaults=house)
        self.assertEqual(art.style, "led")
        self.assertIn("#ffffff", " ".join(art.palette.values()))
        self.assertIsNone(art.effect)

    def test_the_theme_chooses_the_style(self):
        retro = banner.normalise({"text": "x"}, theme=load_theme("retro"))
        self.assertEqual((retro["style"], retro["palette"]), ("led", "phosphor"))
        chosen = banner.normalise({"text": "x", "style": "dots"}, theme=load_theme("retro"))
        self.assertNotIn("palette", chosen)

    def test_export(self):
        art = banner.export({"text": "The Hollow", "style": "shadow"})
        self.assertEqual(sorted(art.variants), ["art", "ascii", "small"])
        again = Art.parse(art.to_text())
        self.assertEqual(again.variants, art.variants)
        self.assertEqual(again.palette, art.palette)


TORCH = {"pixels": ["..yy..", ".yrry.", "yrbbry", ".yrry.", "..ss..", "..ss.."],
         "palette": {"y": "#ffd23f", "r": "#ff5533", "b": "#ffffff", "s": "#8a5a2b"},
         "frames": [[".yy...", ".yrry.", "yrbbry", ".yrry.", "..ss..", "..ss.."]], "fps": 5}


class PictureTests(unittest.TestCase):
    def test_every_style(self):
        for style in pixels.STYLES:
            art = pixels.picture(dict(TORCH, style=style), "torch")
            w, h = art.size("art")
            self.assertLessEqual(w, pixels.cols(6, style), style)
            self.assertEqual(h, {"dots": 2, "pixel": 3}.get(style, 6), style)
            self.assertTrue(all(l.isascii() for l in art.variants["ascii"][0]), style)
            self.assertEqual(len(art.frames), 1)
            self.assertEqual(len(art.frames[0][0]), h)
            self.assertEqual("small" in art.variants, style != "dots")
            for colour in (0, 3):
                for uni in (True, False):
                    for l in art.render(term(colour, uni, 40), 36):
                        self.assertLessEqual(visible_len(l), 36)

    def test_drawings_play_in_turn(self):
        art = pixels.picture(dict(TORCH, loops=3), "torch")
        frames, reveals = art.animation(term())
        self.assertEqual(len(frames), 6)                            # (the second drawing, the first) three times
        self.assertEqual(frames[0][1], 0.2)
        self.assertEqual(frames[-1][0], art.render(term()))
        still = pixels.picture(dict(TORCH, frames=None), "torch")
        self.assertEqual(still.animation(term()), ([], False))
        lit = pixels.picture(dict(TORCH, frames=None, effect="twinkle"), "torch")
        self.assertTrue(lit.animation(term())[0])

    def test_a_sprite_in_combat_takes_its_columns(self):
        from engine.sprite import Sprite
        for style, cols in (("pixel", 6), ("blocks", 12), ("dots", 3), ("led", 12), ("ascii", 12)):
            sp = Sprite.from_data(dict(TORCH, style=style))
            self.assertEqual(sp.cols, cols)
            for tint in (None, "flash", "hurt"):
                lines = sp.render(term(), tint=tint)
                self.assertTrue(all(visible_len(l) <= cols for l in lines), style)
            self.assertTrue(all(strip_ansi(l).isascii() for l in sp.render(term(unicode=False))))


class GameLooksTests(unittest.TestCase):
    def game(self, extra, width=40, uni=True, animate=True):
        folder = tempfile.mkdtemp(prefix="clio-looks-")
        self.addCleanup(shutil.rmtree, folder, True)
        shutil.copytree(os.path.join(ROOT, "templates", "starter"), os.path.join(folder, "g"))
        path = os.path.join(folder, "g", "game.json")
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
        cfg.update(extra)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f)
        t = term(3, uni, width, animate)
        t.inp = lambda prompt: (_ for _ in ()).throw(EOFError())
        return Game(os.path.join(folder, "g"), term=t, audio=Audio(backend=NullBackend(), enabled=False), seed=1)

    def test_a_title_banner_on_every_screen(self):
        for style in banner.STYLES:
            for width in (24, 34, 40, 78):
                for uni in (True, False):
                    g = self.game({"title_banner": {"style": style}, "title_effect": "glitch"}, width, uni)
                    lines, frames, reveals, kind = g.title_picture()
                    self.assertEqual(kind, "banner")
                    self.assertTrue(frames, (style, width))
                    g.ui.title_screen(lines, "", "", "", frames, reveals)
                    for l in shown(g.term):
                        self.assertLessEqual(visible_len(l), width, (style, width, l))

    def test_the_banner_replaces_the_title_text(self):
        g = self.game({"title_banner": {"style": "pixel"}}, 78, animate=False)
        try:
            g.start()
        except EOFError:
            pass
        text = "\n".join(shown(g.term))
        self.assertNotIn("The Cellar", text)                # drawn, not written

    def test_a_chosen_logo(self):
        g = self.game({"logo": "terminal"}, 40, animate=False)
        lines, frames, reveals, kind = g.title_picture()
        self.assertEqual(kind, "logo")
        self.assertIn("clio", strip_ansi(lines[1]))

    def test_banner_and_art_effects_in_the_story(self):
        g = self.game({"on_start": [{"banner": "Chapter II", "style": "led", "effect": "flicker"}]}, 78)
        g.begin_story()
        self.assertGreater(getattr(g.term, "slept", 0), 0)  # it animated
        self.assertIn("●", g.term.out.getvalue())

    def test_a_sprite_is_a_picture(self):
        g = self.game({}, 78, animate=False)
        g.data.sprites["torch"] = dict(TORCH, style="dots")
        g.data.sprites["title"] = dict(TORCH, style="blocks")
        g.art._cache.clear()
        self.assertEqual(strip_ansi(g.art_lines("torch")[0]).strip(), strip_ansi(
            pixels.picture(dict(TORCH, style="dots")).render(g.term)[0]).strip())
        lines, frames, reveals, kind = g.title_picture()
        self.assertEqual(kind, "title")
        self.assertIn("█", strip_ansi(lines[0]))
        art_file = os.path.join(g.data.dir, "art", "torch.art")    # a file of the same name comes first
        os.makedirs(os.path.dirname(art_file), exist_ok=True)
        with open(art_file, "w", encoding="utf-8") as f:
            f.write("@art\n(torch)\n")
        g.art._cache.clear()
        self.assertEqual(strip_ansi(g.art_lines("torch")[0]).strip(), "(torch)")

    def test_bad_pictures_are_reported(self):
        g = self.game({})
        path = os.path.join(g.data.dir, "sprites.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"a": dict(TORCH, style="mosaic"), "b": dict(TORCH, effect="wobble"),
                       "c": dict(TORCH, frames=["no"]), "d": dict(TORCH, frames=[["..zz.."]])}, f)
        problems = " ".join(GameData(g.data.dir).validate())
        for word in ("mosaic", "wobble", "frames should be drawings", "letters with no colour: z"):
            self.assertIn(word, problems)

    def test_bad_looks_are_reported(self):
        g = self.game({"logo": "nope", "title_effect": "sparkle",
                       "title_banner": {"style": "fancy", "palette": "pink", "effect": "wobble"},
                       "palettes": {"empty": {"colors": []}}, "banner_defaults": {"style": "wavy"}})
        problems = " ".join(GameData(g.data.dir).validate())
        for word in ("nope", "sparkle", "fancy", "pink", "wobble", "empty", "wavy"):
            self.assertIn(word, problems)
        g = self.game({"logo": "terminal", "palettes": {"pink": ["#ff88cc"]},
                       "title_banner": {"style": "led", "palette": "pink"}})
        self.assertEqual(GameData(g.data.dir).validate(), [])

    def test_an_end_banner_says_the_end(self):
        g = self.game({"win_banner": {"style": "plain"}}, 78, animate=False)
        g.begin_story()
        g.show_banner(g.cfg["win_banner"], text="The End")
        self.assertIn("T h e   E n d", strip_ansi(g.term.out.getvalue()))

    def test_no_animation_when_it_is_off(self):
        g = self.game({"title_banner": {"style": "glitch"}}, 78, animate=False)
        self.assertEqual(g.title_picture()[1], [])
        g = self.game({"title_banner": {"style": "glitch"}, "title_effect": "none"}, 78)
        self.assertEqual(g.title_picture()[1], [])
        g = self.game({"title_banner": {"style": "glitch"}, "settings": {"art": False}}, 78)
        self.assertEqual(g.title_picture()[0], [])


if __name__ == "__main__":
    unittest.main()
