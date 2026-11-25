# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Daniel Sandner
"""docs/COOKBOOK.md: every block marked *checked* is built, and has to be sound - and a console has to be one
the autopilot can do. So the cookbook cannot go stale without a test saying so."""
import json
import os
import re
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from engine import menu, model  # noqa: E402
from engine import sim as S  # noqa: E402

BLOCK = re.compile(r"<!-- checked: ([a-z ]+) -->\s*```json\n(.*?)```", re.S)


def blocks():
    with open(os.path.join(ROOT, "docs", "COOKBOOK.md"), encoding="utf-8") as f:
        return [(kind.strip(), json.loads(text)) for kind, text in BLOCK.findall(f.read())]


class CookbookTests(unittest.TestCase):
    def test_every_checked_block_works(self):
        found = blocks()
        kinds = [k for k, _ in found]
        self.assertGreaterEqual(kinds.count("sim") + kinds.count("sim with door"), 5)
        self.assertEqual((kinds.count("model"), kinds.count("menu")), (1, 1))
        door = next(spec for kind, spec in found if kind == "model")
        self.assertEqual(model.problems({"door": door}), [])
        self.assertEqual(model.Model("door", door).clips, ["open"])
        for kind, spec in found:
            if kind.startswith("sim"):
                data = types.SimpleNamespace(sims={"it": spec}, models={"door": door}, planets={}, scenes={}, config={})
                self.assertEqual(S.problems(data), [], spec["title"])
                sim = S.make(data, "it")
                S.fly(sim)
                self.assertEqual(sim.result, "won", spec["title"])           # and it can be done
            elif kind == "menu":
                data = types.SimpleNamespace(menus={"orders": spec}, config={}, scenes={"core": {}, "scan": {}})
                self.assertEqual(menu.problems(data), [])

    def test_every_json_block_is_json(self):
        with open(os.path.join(ROOT, "docs", "COOKBOOK.md"), encoding="utf-8") as f:
            text = f.read()
        for block in re.findall(r"```json\n(.*?)```", text, re.S):
            block = block.strip()
            json.loads(block if block[0] in "{[" else "{%s}" % block)        # (a key of game.json alone: in braces)


if __name__ == "__main__":
    unittest.main()
