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


if __name__ == "__main__":
    unittest.main()
