# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Daniel Sandner
"""--shots: a game's consoles, menus and models as pictures in a folder, without playing it."""
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from engine import shots  # noqa: E402
from engine.data import GameData  # noqa: E402

STATION = os.path.join(ROOT, "templates", "station")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class ShotsTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="clio-shots-")
        self.addCleanup(shutil.rmtree, self.dir, True)

    def test_a_folder_of_pictures(self):
        said = []
        n = shots.write(STATION, self.dir, (100, 30), ("full", "ascii"), say=said.append)
        names = sorted(os.listdir(self.dir))
        self.assertEqual(len(names), n + 1)                      # a text file each, and the page
        self.assertIn("index.html", names)
        self.assertIn("%d pictures of Erebus: Last Watch" % n, said[0])
        page = read(os.path.join(self.dir, "index.html"))
        for word in ("reactor", "helm", "scan", "menu bay", "model hauler", "planet Gordian Moon", "the autopilot does it in"):
            self.assertIn(word, page)
        self.assertEqual(page.count('<canvas class="shot"'), n)
        self.assertIn("function paintCells(", page)              # the editor's painter, in the page
        self.assertIn("function paintLines(", page)
        self.assertNotIn("// ---- cells: end", page)
        import json
        data = json.loads(page[page.index('id="shots">') + 11:page.index("</script>")].replace("<\\/", "</"))
        self.assertEqual((len(data), data[0]["cols"], data[0]["lines"]), (n, 100, 28))                  # (a console leaves two lines for what is said under it)
        self.assertTrue(any(run[1] and run[1].startswith("#") for row in data[0]["rows"] for run in row))
        text = read(os.path.join(self.dir, next(x for x in names if "reactor--70" in x)))
        self.assertIn("[X] SCRAM", text)
        self.assertIn("100 by 30", text)
        plain = [x for x in names if "reactor" in x and x.endswith(".txt")]
        self.assertEqual(len(plain), 2 * len(shots.MOMENTS))     # each moment on each kind of terminal
        ascii_one = read(os.path.join(self.dir, plain[1]))
        self.assertTrue(ascii_one.isascii(), plain[1])

    def test_each_part_alone(self):
        data = GameData(STATION)
        got = shots.consoles(data, (80, 24), ("none",), moments=(0.0, 1.0))
        self.assertEqual([name for name, _n, _r in got][:2], ["helm  before it begins", "helm  100% through"])
        self.assertTrue(all(run[1] is None for _n, _note, runs in got for row in runs for run in row))   # no colour
        self.assertEqual(max(len(r) for r in got[0][2]), 1)      # a line of no colour is one run
        models = shots.models(data, (40, 16))
        self.assertEqual([m[0] for m in models], ["model mast", "model hopper", "model hauler", "planet Gordian Moon"])
        self.assertEqual(len(models[0][2]), 16)
        html = shots.block([[["a<b", "#ff0000", None, True]]])
        self.assertEqual(html, '<pre class="shot"><span style="color:#ff0000;font-weight:bold;">a&lt;b</span></pre>')

    def test_a_sim_that_cannot_be_made_is_said(self):
        from unittest import mock
        from engine import sim as S
        data = GameData(STATION)
        data.sims = {"broken": {}}
        with mock.patch.object(S, "make", side_effect=ValueError("no map")):
            got = shots.consoles(data, (80, 24))
        self.assertEqual(len(got), 1)
        self.assertIn("it cannot be drawn", got[0][1])


class EditorConsoleTests(unittest.TestCase):
    """The editor's page of a simulator: its screen at a moment, whether it can be done, where widgets go."""

    def test_a_console_at_a_moment_and_where_its_widgets_are(self):
        from engine.editor import looks, service
        got = looks.console(STATION, "reactor", moment=0.7, cols=100, rows=30)
        self.assertEqual((got["problems"], got["result"], got["cols"], got["lines"]), ([], "won", 100, 28))
        self.assertIn("The autopilot does it in", got["verdict"])
        text = "".join(run[0] for row in got["rows"] for run in row)
        self.assertIn("[X] SCRAM", text)
        self.assertTrue(got["has_panels"] and got["panels"])
        first = got["places"][0]
        self.assertEqual(sorted(first), ["path", "title", "widgets"])
        spec = GameData(STATION).sims["reactor"]["panels"]
        node = spec
        for step in first["path"]:
            node = node[step]
        self.assertEqual(len(node["widgets"]), len(first["widgets"]))            # the path leads to that panel
        self.assertEqual(len(got["widgets"]), 15)
        self.assertEqual(sorted(got["widgets"][0]), ["kind", "spec", "what"])
        begun = service.handle(STATION, "/api/console", {"name": "reactor", "moment": 0, "cols": 48, "rows": 20})
        self.assertFalse(begun["panels"])                                         # too small for panels: the column
        self.assertNotEqual(begun["rows"], got["rows"])
        self.assertEqual(len(shots._flown), 1)                                   # flown once for both
        with self.assertRaises(Exception):
            looks.console(STATION, "nothing")

    def test_what_is_on_the_page_is_what_is_drawn_and_judged(self):
        from engine.editor import looks
        sims = dict(GameData(STATION).sims)
        sims["reactor"] = dict(sims["reactor"], fail_if="time >= 2")             # it cannot be done like this
        hard = looks.console(STATION, "reactor", {"sims": sims}, moment=1.0, cols=100, rows=30)
        self.assertEqual(hard["result"], "lost")
        self.assertIn("The autopilot fails", hard["verdict"])
        sims["reactor"] = dict(sims["reactor"], win_if="nothing_there >= 1")
        wrong = looks.console(STATION, "reactor", {"sims": sims})
        self.assertEqual(wrong["rows"], [])
        self.assertEqual(len(wrong["problems"]), 1)
        bare = dict(GameData(STATION).sims["reactor"])
        bare.pop("panels")
        sims["reactor"] = bare
        self.assertFalse(looks.console(STATION, "reactor", {"sims": sims})["has_panels"])


if __name__ == "__main__":
    unittest.main()
