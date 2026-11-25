# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Daniel Sandner
"""--schema: JSON Schemas of a game's files for editors that complete from them. They describe; they do not judge."""
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from engine import jsonschema as J  # noqa: E402
from engine import schema  # noqa: E402

try:
    import jsonschema as lib                                 # not in the standard library: only some test runs have it
except ImportError:
    lib = None


def read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class SchemaFileTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="clio-schema-")
        self.addCleanup(shutil.rmtree, self.dir, True)

    def test_a_schema_for_each_file_and_the_settings_that_tie_them(self):
        said = []
        out = os.path.join(self.dir, "schemas")
        n = J.write(out, say=said.append)
        self.assertEqual(n, len(schema.KINDS))
        self.assertIn("%d schemas" % n, said[0])
        names = sorted(os.listdir(out))
        self.assertEqual(len(names), n + 1)
        ties = read(os.path.join(out, "vscode-settings.json"))["json.schemas"]
        self.assertEqual(ties[0]["fileMatch"][0], "games/*/game.json")
        self.assertEqual(ties[0]["url"], "./schemas/clio-game.schema.json")
        game = read(os.path.join(out, "clio-game.schema.json"))
        self.assertEqual(game["$schema"], J.DRAFT)
        self.assertEqual(game["properties"]["title"]["description"], "Title")
        self.assertIn("amber", game["properties"]["console"]["anyOf"][0]["enum"])
        self.assertIn("wheel", game["properties"]["menu_look"]["anyOf"][0]["enum"])
        self.assertIn("ink", game["properties"]["model_look"]["properties"])
        sims = read(os.path.join(out, "clio-sims.schema.json"))
        widget = sims["definitions"]["panel"]["properties"]["widgets"]["items"]["properties"]
        self.assertEqual(sorted(widget), sorted(J.WIDGET_KEYS))
        self.assertEqual(sims["additionalProperties"]["properties"]["panels"]["$ref"], "#/definitions/panel")
        scenes = read(os.path.join(out, "clio-scenes.schema.json"))
        self.assertIn("say", scenes["definitions"]["effect"]["properties"])
        self.assertIn("id", scenes["items"]["properties"])

    def test_every_widget_there_is_is_described(self):
        from engine import panels
        self.assertEqual(sorted(J.WIDGET_KEYS), sorted(panels.WIDGETS))

    @unittest.skipIf(lib is None, "checks the schemas with the jsonschema package (pip install jsonschema)")
    def test_they_are_schemas_and_forbid_nothing_the_games_have(self):
        for kind in schema.KINDS:
            made = J.for_kind(kind)
            lib.Draft7Validator.check_schema(made)
            for folder in ("games/erebus", "games/derelict", "games/depths", "games/rootless", "templates/station",
                           "templates/starter", "templates/realm"):
                path = os.path.join(ROOT, folder, kind["file"] + ".json")
                if os.path.isfile(path):
                    with open(path, encoding="utf-8") as f:
                        wrong = list(lib.Draft7Validator(made).iter_errors(json.load(f)))
                    self.assertEqual(wrong, [], path)


if __name__ == "__main__":
    unittest.main()
