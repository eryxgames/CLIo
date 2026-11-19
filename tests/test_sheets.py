# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Sheets of pictures and the way back: PNG files read, pictures made sprites, edited sheets taken in."""
import base64
import contextlib
import io
import json
import os
import shutil
import struct
import sys
import tempfile
import unittest
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import ROOT                                        # noqa: E402

from engine import editor, sheets                               # noqa: E402
from engine.data import GameData                                # noqa: E402
from engine.editor import service                               # noqa: E402

ROOTLESS = os.path.join(ROOT, "games", "rootless")

# Small PNG files as other programs write them (made with Pillow): filtered RGBA, a 2-bit palette with a
# see-through colour, 8-bit grey.
RGBA = ("iVBORw0KGgoAAAANSUhEUgAAAAYAAAAECAYAAACtBE5DAAAAR0lEQVR42l3EsQ2AMBAEwTvQB3b8seVSvgRKcmUU5mQJIGKlWSNhJL1z"
        "z8F9peTjZO+NvkZ2Wmto1aTWZNYChAAEjghs6+8BKdsdWNcmz5wAAAAASUVORK5CYII=")
PALETTE = ("iVBORw0KGgoAAAANSUhEUgAAAAYAAAAEAgMAAADQaqbQAAAADFBMVEX/AAAA/wAAAP8AAAD7vkbkAAAABHRSTlP///8AQCqp9AAAABRJ"
           "REFUeF5jlP7KEviFxfU/i+gvABrIBLZuQXhMAAAAAElFTkSuQmCC")
GREY = "iVBORw0KGgoAAAANSUhEUgAAAAYAAAAECAAAAACIbxGfAAAAEUlEQVR4XmNk0AABJkYwQKUAFAkA4kzlVK8AAAAASUVORK5CYII="


def game_files(folder=ROOTLESS):
    return editor.current(folder)


def copy_of_rootless():
    folder = os.path.join(tempfile.mkdtemp(prefix="clio-sheets-"), "rootless")
    shutil.copytree(ROOTLESS, folder)
    return folder


def paint(rows, rect, colour, at=(0, 0), size=None):
    """Paint a square of a sheet's picture ``rect`` (as the atlas gives it)."""
    n = size or 1
    for y in range(rect["y"] + at[1], rect["y"] + at[1] + n):
        for x in range(rect["x"] + at[0], rect["x"] + at[0] + n):
            rows[y][x] = colour


class ReadTests(unittest.TestCase):
    def test_png_files_of_several_kinds(self):
        w, h, rows = sheets.read_png(base64.b64decode(RGBA))
        self.assertEqual((w, h), (6, 4))
        self.assertEqual(rows[0][:4], [(255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255), (0, 0, 0, 0)])
        self.assertEqual(rows[3][5], (10, 10, 10, 255))
        w, h, rows = sheets.read_png(base64.b64decode(PALETTE))
        self.assertEqual(rows[0][:4], [(255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255), (0, 0, 0, 0)])
        self.assertEqual(rows[1][0], (0, 255, 0, 255))
        w, h, rows = sheets.read_png(base64.b64decode(GREY))
        self.assertEqual(rows[0][:3], [(0, 0, 0, 255), (40, 40, 40, 255), (80, 80, 80, 255)])
        self.assertEqual(rows[1][1], (41, 41, 41, 255))

    def test_written_and_read_back(self):
        img = [[(x * 30, y * 60, 7, 255 if x % 2 else 0) for x in range(5)] for y in range(3)]
        self.assertEqual(sheets.read_png(sheets.png(img))[2], [[tuple(c) for c in r] for r in img])

    def test_what_cannot_be_read(self):
        with self.assertRaisesRegex(sheets.PictureError, "not a PNG"):
            sheets.read_png(b"GIF89a....")
        data = bytearray(sheets.png([[(1, 2, 3, 255)] * 2] * 2))
        data[28] = 1                                                  # "interlaced"
        data[29:33] = struct.pack(">I", zlib.crc32(bytes(data[12:29])) & 0xFFFFFFFF)
        with self.assertRaisesRegex(sheets.PictureError, "interlaced"):
            sheets.read_png(bytes(data))


class PictureTests(unittest.TestCase):
    def setUp(self):
        self.zombie = GameData(ROOTLESS).sprites["zombie"]
        self.drawing = sheets._drawing(self.zombie["pixels"], self.zombie["palette"])

    def rgba(self, drawing, k=1, back=None):
        return [[(c + (255,)) if c else ((back + (255,)) if back else (0, 0, 0, 0)) for c in r for _ in range(k)]
                for r in drawing for _ in range(k)]

    def test_a_pixel_picture_drawn_big_comes_back_to_its_pixels(self):
        made = sheets.to_sprite(self.rgba(self.drawing, 4), base=self.zombie["palette"])
        self.assertEqual(made["scale"], 4)
        trimmed = [r[1:] for r in self.zombie["pixels"]]                # the drawing's empty first column is cut
        self.assertEqual(made["pixels"], trimmed)
        self.assertTrue(set(made["palette"]) <= set(self.zombie["palette"]))   # the zombie's own letters

    def test_a_plain_background_cleared_and_dust_dropped(self):
        rows = self.rgba(self.drawing, 1, back=(250, 250, 250))
        rows[0][0] = (240, 244, 250, 255)                              # near enough to the background
        rows[17][0] = (9, 200, 9, 255)                                 # a speck of dust, on its own
        kept = sheets.to_sprite(rows)
        self.assertEqual(len(kept["pixels"]), 18)                      # nothing cleared: the background stays
        made = sheets.to_sprite(rows, clear="edges", base=self.zombie["palette"])
        self.assertEqual(made["pixels"], [r[1:] for r in self.zombie["pixels"]])
        clicked = sheets.to_sprite(rows, clear_at=[(0, 5), (11, 0), (11, 12), (6, 15)], base=self.zombie["palette"])
        self.assertEqual(clicked["pixels"], made["pixels"])            # clicks on the background do the same

    def test_smaller_fewer_colours_an_outline(self):
        big = [[(x * 4, y * 4, 128, 255) for x in range(60)] for y in range(60)]
        made = sheets.to_sprite(big, height=20, colours=5)
        self.assertEqual((len(made["pixels"]), len(made["pixels"][0])), (20, 20))
        self.assertLessEqual(made["colours"], 5)
        lined = sheets.to_sprite(self.rgba(self.drawing), outline=True)
        self.assertEqual(len(lined["pixels"]), 20)                     # a line all round: one pixel each side
        self.assertEqual(lined["pixels"][0].strip("."), lined["pixels"][0].strip(".")[0] * len(lined["pixels"][0].strip(".")))
        huge = sheets.to_sprite([[(9, 9, 9, 255)] * 300] * 100)
        self.assertLessEqual(len(huge["pixels"][0]), 64)               # no wider than a sprite may be

    def test_nothing_to_make(self):
        with self.assertRaisesRegex(sheets.PictureError, "clear"):
            sheets.to_sprite([[(0, 0, 0, 0)] * 3] * 3)


class BackInTests(unittest.TestCase):
    def sheet(self, what, scale=3, **kw):
        png, atlas = sheets.sheet(GameData(ROOTLESS), what, scale, **kw)
        return sheets.read_png(png)[2], atlas

    def test_an_untouched_sheet_changes_nothing(self):
        for what in sheets.WHAT:
            rows, atlas = self.sheet(what)
            out = sheets.import_sheet(game_files(), rows, atlas)
            self.assertEqual(out["files"], {}, what)
            self.assertEqual(out["report"]["same"], len(atlas["frames"]), what)

    def test_a_monster_its_step_and_its_attack(self):
        rows, atlas = self.sheet("monsters")
        frames = atlas["frames"]
        paint(rows, frames["zombie"]["frame"], (250, 0, 250, 255), size=3)             # one pixel, 3 x 3 on the sheet
        paint(rows, frames["kworker/step2"]["frame"], (0, 250, 0, 255), at=(3, 3), size=3)
        paint(rows, frames["shred/attack"]["frame"], (255, 255, 255, 255), at=(0, 0), size=3)
        out = sheets.import_sheet(game_files(), rows, atlas)
        self.assertEqual(sorted(out["report"]["changed"]), ["kworker/step2", "shred/attack", "zombie"])
        sprites = out["files"]["sprites"]
        z = sprites["zombie"]
        self.assertEqual(z["palette"][z["pixels"][0][0]], "#fa00fa")
        self.assertEqual(z["pixels"][1:], GameData(ROOTLESS).sprites["zombie"]["pixels"][1:])
        self.assertEqual(len(sprites["kworker"]["walk"]), 2)                           # both steps kept, one changed
        self.assertNotIn("walk", sprites["zombie"])                                    # its steps are still made
        self.assertIn("#ffffff", sprites["shred"]["palette"].values())
        self.assertEqual(GameData(ROOTLESS).validate(), [])

    def test_a_sheet_saved_on_its_background_without_see_through(self):
        rows, atlas = self.sheet("sprites", 2, background=sheets.DARK)
        rows = [[(c[0], c[1], c[2], 255) for c in r] for r in rows]
        paint(rows, atlas["frames"]["medkit"]["frame"], (1, 2, 3, 255), size=2)
        out = sheets.import_sheet(game_files(), rows, atlas)
        self.assertEqual(out["report"]["changed"], ["medkit"])

    def test_tiles_and_the_engines_own(self):
        rows, atlas = self.sheet("tiles", 1)
        paint(rows, atlas["frames"]["steel"]["frame"], (255, 0, 0, 255), at=(5, 5))
        paint(rows, atlas["frames"]["grate"]["frame"], (0, 0, 255, 255), at=(1, 1))
        out = sheets.import_sheet(game_files(), rows, atlas)
        tiles = out["files"]["tiles"]
        self.assertEqual(sorted(out["report"]["changed"]), ["grate", "steel"])
        self.assertIn("steel", tiles)                                                  # the engine's, now the game's
        self.assertNotIn("hazard", tiles)                                              # untouched: still the engine's
        self.assertEqual(len(tiles["steel"]["pixels"]), 32)

    def test_what_does_not_fit(self):
        rows, atlas = self.sheet("sprites")
        with self.assertRaisesRegex(sheets.PictureError, "the sheet it was written with"):
            sheets.import_sheet(game_files(), [r[:-3] for r in rows], atlas)
        with self.assertRaisesRegex(sheets.PictureError, "lists no pictures"):
            sheets.import_sheet(game_files(), rows, {"meta": {}})
        atlas["frames"]["nobody"] = dict(atlas["frames"]["zombie"])
        paint(rows, atlas["frames"]["zombie"]["frame"], (255, 0, 0, 255), size=3)     # painted over, but...
        files = game_files()
        files["sprites"] = dict(files["sprites"], zombie=dict(files["sprites"]["zombie"],
                                                              pixels=files["sprites"]["zombie"]["pixels"][:-1]))
        report = sheets.import_sheet(files, rows, atlas)["report"]
        self.assertEqual(report["unknown"], ["nobody"])
        self.assertTrue(any(n.startswith("zombie: drawn") for n in report["skipped"]))


class EditorTests(unittest.TestCase):
    def test_a_picture_through_the_editor(self):
        made = service.handle(ROOTLESS, "/api/fromimage", {"png": RGBA, "colours": 4})
        self.assertEqual(made["source"], [6, 4])
        self.assertLessEqual(made["colours"], 4)
        rgba = bytes(v for r in sheets.read_png(base64.b64decode(RGBA))[2] for c in r for v in c)
        same = service.handle(ROOTLESS, "/api/fromimage", {"rgba": base64.b64encode(rgba).decode(), "w": 6, "h": 4,
                                                            "colours": 4})
        self.assertEqual(same["pixels"], made["pixels"])
        with self.assertRaisesRegex(editor.EditorError, "not a PNG"):
            service.handle(ROOTLESS, "/api/fromimage", {"png": base64.b64encode(b"nonsense").decode()})
        with self.assertRaisesRegex(editor.EditorError, "No picture"):
            service.handle(ROOTLESS, "/api/fromimage", {})

    def test_a_sheet_back_through_the_editor(self):
        png, atlas = sheets.sheet(GameData(ROOTLESS), "monsters", 2)
        rows = sheets.read_png(png)[2]
        paint(rows, atlas["frames"]["crawler"]["frame"], (255, 255, 0, 255), size=2)
        body = {"png": base64.b64encode(sheets.png(rows)).decode(), "atlas": json.dumps(atlas)}
        out = service.handle(ROOTLESS, "/api/sheetimport", body)
        self.assertEqual(out["report"]["changed"], ["crawler"])
        self.assertEqual(list(out["files"]), ["sprites"])
        self.assertEqual(GameData(ROOTLESS).sprites["crawler"]["pixels"][0][0], ".")   # nothing written
        with self.assertRaisesRegex(editor.EditorError, "atlas"):
            service.handle(ROOTLESS, "/api/sheetimport", dict(body, atlas="{not json"))

    def test_a_sheet_back_from_the_command_line(self):
        import clio
        folder = copy_of_rootless()
        out = os.path.join(os.path.dirname(folder), "m.png")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(clio.main([folder, "--sheet", "monsters", "--scale", "2", "--export", out]), 0)
        with open(out, "rb") as f:
            rows = sheets.read_png(f.read())[2]
        with open(out[:-4] + ".json", encoding="utf-8") as f:
            atlas = json.load(f)
        paint(rows, atlas["frames"]["crawler"]["frame"], (255, 255, 0, 255), size=2)
        with open(out, "wb") as f:
            f.write(sheets.png(rows))
        with contextlib.redirect_stdout(io.StringIO()) as said:
            self.assertEqual(clio.main([folder, "--import-sheet", out]), 0)
        self.assertIn("1 picture(s) changed", said.getvalue())
        crawler = GameData(folder).sprites["crawler"]
        self.assertEqual(crawler["palette"][crawler["pixels"][0][0]], "#ffff00")
        with contextlib.redirect_stdout(io.StringIO()) as said:
            self.assertEqual(clio.main([folder, "--import-sheet", out]), 0)
        self.assertIn("0 picture(s) changed", said.getvalue())          # taken in once: the same now


if __name__ == "__main__":
    unittest.main()
