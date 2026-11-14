# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""The editor: reading, checking and writing a game's files, and the local server."""
import inspect
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import ROOT                                        # noqa: E402

from engine import conditions, editor, schema                   # noqa: E402
from engine.data import GameData, find_games                    # noqa: E402
from engine.editor import hosted, service                       # noqa: E402
from engine.editor.server import make_server                    # noqa: E402

TYPES = {"text", "long", "number", "bool", "choice", "tags", "ref", "refs", "sprite", "group", "rows", "map",
         "effects", "condition"}


def copy_of(name):
    """A game to scribble on."""
    folder = os.path.join(tempfile.mkdtemp(prefix="clio-editor-test-"), name)
    shutil.copytree(os.path.join(ROOT, "games", name), folder)
    return folder


class SchemaTests(unittest.TestCase):
    def test_the_description_is_well_formed(self):
        keys = [k["key"] for k in schema.KINDS]
        self.assertEqual(len(keys), len(set(keys)))
        def fields_ok(fields, where):
            seen = set()
            for f in fields:
                self.assertIn(f["type"], TYPES, f)
                self.assertNotIn(f["key"], seen, "%s.%s is listed twice" % (where, f["key"]))
                seen.add(f["key"])
                if f["type"] in ("ref", "refs"):
                    self.assertIn(f["of"], keys, f)
                if f["type"] == "choice":
                    self.assertTrue(f["options"])
                if f["type"] in ("group", "rows", "map"):                # parts with fields of their own
                    fields_ok(f["fields"], "%s.%s" % (where, f["key"]))
            return seen

        for kind in schema.KINDS:
            self.assertIn(kind["shape"], ("map", "list", "object"))
            seen = fields_ok(kind["fields"], kind["key"])
            if kind.get("title"):
                self.assertIn(kind["title"], seen)
        json.dumps(schema.KINDS)                                        # it is sent to the page as it is

    def test_the_vocabularies_are_the_engines(self):
        """What the editor offers as effects and conditions is exactly what engine/conditions.py understands."""
        self.assertEqual(sorted(e["key"] for e in schema.EFFECTS), sorted(conditions._EFFECTS))
        source = inspect.getsource(conditions._check_one)
        asked = set(re.findall(r'key == "(\w+)"', source))
        for group in re.findall(r"key in \(([^)]*)\)", source):
            asked |= {k.strip().strip('"') for k in group.split(",")}
        self.assertEqual({c["key"] for c in schema.CONDITIONS}, asked)
        kinds = {k["key"] for k in schema.KINDS}

        def arg_ok(arg, word):
            if isinstance(arg, str):
                self.assertIn(arg, ("text", "long", "number", "flag", "none", "json"), word)
                return
            self.assertEqual(len([k for k in ("ref", "words", "choice", "pair", "way", "measure") if k in arg]), 1, word)
            if "ref" in arg:
                self.assertIn(arg["ref"], kinds, word)
            for part in arg.get("pair", []) + arg.get("measure", []):
                arg_ok(part, word)
            if "measure" in arg:
                self.assertTrue(arg["ops"], word)
                self.assertLessEqual(len(arg["measure"]), 1, word)

        for word in schema.EFFECTS + schema.CONDITIONS:
            self.assertTrue(word["label"], word)
            arg_ok(word["arg"], word)
        for words in (schema.EFFECTS, schema.CONDITIONS):
            self.assertEqual(len(words), len({w["key"] for w in words}))
        json.dumps([schema.EFFECTS, schema.CONDITIONS])

    def test_the_games_speak_the_vocabulary(self):
        """Every effect and condition of the demo games, in the places the schema names, is made of known words."""
        effects = {e["key"] for e in schema.EFFECTS} | {"if", "then", "else", "style", "effect", "title", "quiet",
                                                         "fixture", "copy", "can_flee"}
        asked = {c["key"] for c in schema.CONDITIONS}
        seen = {"effects": 0, "condition": 0}

        def condition_ok(cond, where):
            if isinstance(cond, str):
                text = cond[1:] if cond.startswith("!") else cond
                if ":" in text:
                    self.assertIn(text.partition(":")[0].strip(), asked, where)
            elif isinstance(cond, list):
                for c in cond:
                    condition_ok(c, where)
            elif isinstance(cond, dict):
                for key, arg in cond.items():
                    self.assertIn(key, asked, where)
                    if key in ("all", "any"):
                        condition_ok(list(arg), where)
                    elif key == "not":
                        condition_ok(arg, where)

        def effects_ok(effs, where):
            for eff in effs if isinstance(effs, list) else [effs]:
                if isinstance(eff, list):
                    effects_ok(eff, where)
                elif isinstance(eff, dict):
                    self.assertFalse(set(eff) - effects, "%s: %s" % (where, sorted(set(eff) - effects)))
                    if "if" in eff:
                        condition_ok(eff["if"], where)
                    for key in ("then", "else", "do"):
                        effects_ok(eff.get(key) or [], where)
                    for branch in eff.get("random") or []:
                        effects_ok(branch, where)

        def walk(fields, obj, where):
            for f in fields:
                value = obj.get(f["key"])
                if value is None:
                    continue
                here = "%s/%s" % (where, f["key"])
                if f["type"] == "effects":
                    seen["effects"] += 1
                    effects_ok(value, here)
                elif f["type"] == "condition":
                    seen["condition"] += 1
                    condition_ok(value, here)
                elif f["type"] == "group" and isinstance(value, dict):
                    walk(f["fields"], value, here)
                elif f["type"] == "rows" and isinstance(value, list):
                    for i, row in enumerate(value):
                        if isinstance(row, dict):
                            walk(f["fields"], row, "%s/%d" % (here, i))
                elif f["type"] == "map" and isinstance(value, dict):
                    for name, row in value.items():
                        if isinstance(row, dict):
                            walk(f["fields"], row, "%s/%s" % (here, name))

        for name in ("derelict", "depths"):
            game = editor.load(os.path.join(ROOT, "games", name))
            for key, file in game["files"].items():
                kind = schema.BY_FILE[key]
                data = file["data"]
                things = [(None, data)] if kind["shape"] == "object" else (
                    data.items() if kind["shape"] == "map" else [(t.get("id"), t) for t in data])
                for tid, thing in things:
                    if isinstance(thing, dict):
                        walk(kind["fields"], thing, "%s %s/%s" % (name, key, tid))
        self.assertGreater(seen["effects"], 50)
        self.assertGreater(seen["condition"], 60)

    def test_it_fits_the_games_that_exist(self):
        """Every data file of every game has a kind, in the shape the schema says, and typed fields hold that type."""
        for path, _title, _desc in find_games(ROOT):
            if not os.path.isfile(os.path.join(path, "game.json")):
                continue                                        # the CLIo 1 sandbox keeps its files elsewhere
            game = editor.load(path)
            self.assertEqual(game["problems"], [], path)
            for key, file in game["files"].items():
                kind = schema.BY_FILE[key]
                self.assertIsInstance(file["data"], list if kind["shape"] == "list" else dict, "%s %s" % (path, key))


class ServiceTests(unittest.TestCase):
    def test_saving_changes_only_what_changed(self):
        folder = copy_of("derelict")
        game = editor.load(folder)
        self.assertEqual((game["id"], game["title"]), ("derelict", "Derelict"))
        before = {}
        for key, file in game["files"].items():
            if file["exists"]:
                with open(os.path.join(folder, file["name"]), encoding="utf-8") as f:
                    before[key] = f.read()
        for key in before:                                      # written back untouched, every file is byte for byte the same
            editor.save(folder, key, game["files"][key]["data"])
            with open(os.path.join(folder, game["files"][key]["name"]), encoding="utf-8") as f:
                self.assertEqual(f.read(), before[key], key)
        crlf = os.path.join(folder, "quests.json")              # a Windows checkout keeps its line ends
        with open(crlf, "rb") as f:
            windows = f.read().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        with open(crlf, "wb") as f:
            f.write(windows)
        editor.save(folder, "quests", game["files"]["quests"]["data"])
        with open(crlf, "rb") as f:
            self.assertEqual(f.read(), windows)
        scenes = game["files"]["scenes"]["data"]
        scenes[0]["description"] = "Changed."
        out = editor.save(folder, "scenes", scenes)
        self.assertEqual((out["saved"], out["problems"]), ("scenes.json", []))
        with open(os.path.join(folder, "scenes.json"), encoding="utf-8") as f:
            after = f.read()
        changed = [(a, b) for a, b in zip(before["scenes"].split("\n"), after.split("\n")) if a != b]
        self.assertEqual(len(changed), 1)
        self.assertIn('"description": "Changed."', changed[0][1])
        self.assertEqual(GameData(folder).scenes[scenes[0]["id"]]["description"], "Changed.")
        kept = os.listdir(os.path.join(folder, editor.BACKUP))  # the day's first version of each file is kept
        self.assertEqual(len(kept), len(before))
        with open(os.path.join(folder, editor.BACKUP, [n for n in kept if n.endswith("-scenes.json")][0]), encoding="utf-8") as f:
            self.assertEqual(f.read(), before["scenes"])

    def test_checking_before_saving(self):
        folder = copy_of("derelict")
        scenes = editor.load(folder)["files"]["scenes"]["data"]
        scenes[0]["exits"][0]["scene_id"] = "nowhere"
        found = editor.check(folder, {"scenes": scenes})
        self.assertEqual(len(found), 1)
        self.assertEqual((found[0]["kind"], found[0]["id"]), ("scenes", scenes[0]["id"]))
        self.assertIn("unknown scene 'nowhere'", found[0]["text"])
        self.assertEqual(editor.check(folder), [])              # nothing was written
        broken = editor.check(folder, {"items": {"lamp": "not an item"}})
        self.assertTrue(broken and "text" in broken[0])         # data too wrong to load is reported, not raised

    def test_what_it_refuses(self):
        folder = copy_of("depths")
        with self.assertRaisesRegex(editor.EditorError, "not a file of this game"):
            editor.save(folder, "../clio.py", {})
        with self.assertRaisesRegex(editor.EditorError, "must be a JSON list"):
            editor.save(folder, "scenes", {})
        with self.assertRaisesRegex(editor.EditorError, "must be a JSON object"):
            editor.save(folder, "items", [])
        with self.assertRaisesRegex(editor.EditorError, "no game.json"):
            editor.load(tempfile.mkdtemp())
        game = dict(editor.load(folder)["files"]["game"]["data"], files={"items": "../../elsewhere.json"})
        editor.save(folder, "game", game)
        self.assertNotIn("items", editor.paths(folder))         # a file outside the folder is not the editor's to write
        editor.save(folder, "sounds", {"ping": {"wave": "sine"}})   # a file that did not exist yet is created
        self.assertTrue(os.path.isfile(os.path.join(folder, "sounds.json")))


class TextTableTests(unittest.TestCase):
    def files(self, name="derelict"):
        return {key: file["data"] for key, file in editor.load(os.path.join(ROOT, "games", name))["files"].items()}

    def test_what_counts_as_text(self):
        from engine.editor import texts
        for key, value in (("name", "Hatch"), ("lock_text", "Locked."), ("description", "A room."), ("say", "It is cold here"),
                           ("name_prompt", "Name?"), ("aliases", "bot")):
            self.assertTrue(texts.is_text(key, value), (key, value))
        for key, value in (("if", "has:lamp"), ("scene_id", "corridor"), ("author", "Daniel Sandner"), ("set", "door open"),
                           ("description", "  "), ("give", "red_apple"), ("intro", "intro")):
            self.assertFalse(texts.is_text(key, value), (key, value))

    def test_out_and_back_in(self):
        from engine.editor import texts
        files = self.files()
        table = texts.rows(files)
        self.assertGreater(len(table), 400)
        places = [r["where"] for r in table]
        self.assertEqual(len(places), len(set(places)))
        self.assertIn("game/title", places)
        self.assertIn("scenes/utility_room/description", places)                # a list file is addressed by id, not position
        self.assertTrue(any(w.startswith("scenes/utility_room/exits/0/") for w in places))
        self.assertTrue(any(w.startswith("dialogues/") and w.endswith("/text") for w in places))
        self.assertFalse(any(w.split("/")[0] in texts.SKIP_FILES for w in places))
        self.assertTrue(all(r["kind"] in files for r in table))
        csv_text = texts.to_csv(table)
        self.assertTrue(csv_text.startswith("where,text\n"))
        again = texts.from_csv("\ufeff" + csv_text.replace("\n", "\r\n"))    # as a spreadsheet on Windows writes it
        self.assertEqual([(r["where"], r["text"]) for r in again], [(r["where"], r["text"]) for r in table])
        before = json.dumps(files, sort_keys=True)
        report = texts.apply(files, again)
        self.assertEqual((report["changed"], report["same"], report["missing"]), (0, len(table), []))
        self.assertEqual(json.dumps(files, sort_keys=True), before)             # untouched texts change nothing
        report = texts.apply(files, [
            {"where": "scenes/utility_room/description", "text": "Une pièce.\nDeux lignes."},
            {"where": "scenes/nowhere/description", "text": "Lost"},
            {"where": "scenes/utility_room/exits", "text": "not a text"},
            {"where": "music/theme/title", "text": "Not offered, not accepted"},
            {"where": "items", "text": "too short"}, {"where": "", "text": "skipped"}])
        self.assertEqual((report["changed"], report["files"]), (1, ["scenes"]))
        self.assertEqual(len(report["missing"]), 4)
        self.assertEqual(files["scenes"][0]["description"], "Une pièce.\nDeux lignes.")
        semicolons = texts.from_csv("where;text\ngame/title;\"A; B\"\n")       # a spreadsheet in a comma-decimal locale
        self.assertEqual(semicolons, [{"where": "game/title", "text": "A; B"}])
        with self.assertRaisesRegex(ValueError, "no text column"):
            texts.from_csv("where,text\ngame/title\n")

    def test_keys_with_slashes_survive(self):
        from engine.editor import texts
        files = {"items": {"a/b~c": {"name": "Odd one", "states": {"open/shut": {"text": "It is open now"}}}}}
        table = texts.rows(files)
        self.assertEqual([r["where"] for r in table], ["items/a~1b~0c/name", "items/a~1b~0c/states/open~1shut/text"])
        self.assertEqual(table[0]["id"], "a/b~c")
        texts.apply(files, [{"where": table[1]["where"], "text": "Open."}])
        self.assertEqual(files["items"]["a/b~c"]["states"]["open/shut"]["text"], "Open.")

    def test_the_service_changes_nothing_on_disk(self):
        folder = copy_of("depths")
        table = editor.text_table(folder)
        self.assertGreater(len(table), 300)
        result = editor.put_texts(folder, [{"where": "game/title", "text": "The Hollow, Deeper"}])
        self.assertEqual((list(result["files"]), result["report"]["changed"]), (["game"], 1))
        self.assertEqual(GameData(folder).title, "The Hollow")                  # for the caller to check and save
        seen = editor.text_table(folder, {"game": result["files"]["game"]})
        self.assertEqual([r["text"] for r in seen if r["where"] == "game/title"], ["The Hollow, Deeper"])

    def test_archive(self):
        import io
        import zipfile
        folder = copy_of("derelict")
        editor.save(folder, "texts", editor.load(folder)["files"]["texts"]["data"])    # leaves a backup behind
        names = zipfile.ZipFile(io.BytesIO(editor.archive(folder))).namelist()
        self.assertIn("derelict/game.json", names)
        self.assertTrue(any(n.startswith("derelict/art/") for n in names))
        self.assertFalse(any(editor.BACKUP in n or "__pycache__" in n for n in names))

    def test_command_line(self):
        import io
        from contextlib import redirect_stdout
        import clio
        folder = copy_of("derelict")
        table = os.path.join(os.path.dirname(folder), "texts.csv")
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(clio.main([folder, "--export-text", table]), 0)
        with open(table, "rb") as f:
            raw = f.read()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbfwhere,text"))             # marked, so a spreadsheet reads it as UTF-8
        text = raw.decode("utf-8-sig").replace("game/title,Derelict", "game/title,Wreck") + "scenes/gone/name,Gone\n"
        with open(table, "w", encoding="utf-8-sig", newline="") as f:
            f.write(text)
        with redirect_stdout(out):
            self.assertEqual(clio.main([folder, "--import-text", table]), 0)
        self.assertIn("1 texts changed in 1 file(s)", out.getvalue())
        self.assertIn("no text at scenes/gone/name", out.getvalue())
        self.assertEqual(GameData(folder).title, "Wreck")
        with redirect_stdout(out):
            self.assertEqual(clio.main([folder, "--import-text", os.path.join(folder, "missing.csv")]), 2)


class EnemyTests(unittest.TestCase):
    DEPTHS = os.path.join(ROOT, "games", "depths")

    def test_strength_is_the_generators_own_measure(self):
        from engine import maze
        from engine.editor import balance
        data = GameData(self.DEPTHS)
        holder = balance._Holder(data)
        levels = balance.floors(data)
        written = data.dungeon["floors"]
        self.assertEqual([f["n"] for f in levels], list(range(1, len(written) + 4)))       # and three floors below
        self.assertEqual(levels[0]["power"], round(maze.floor_power(holder, written[0])))
        self.assertEqual([f["power"] for f in levels], sorted(f["power"] for f in levels))  # deeper is stronger
        rat = data.characters["bone_rat"]["stats"]
        for factor in (1.3, 2.0, 3.5):                                                      # the same rule as the game's
            want = maze.scaled(holder, "bone_rat", factor)["stats"]
            got = balance.scale(rat, factor)
            self.assertEqual({k: got[k] for k in want}, want)
        self.assertLess(balance.scale(rat, 0.5)["max_health"], rat["max_health"])           # and it works downwards
        flat = balance.floors(GameData(os.path.join(ROOT, "games", "derelict")))
        self.assertEqual((len(flat), flat[0]["n"]), (1, 0))                                 # no dungeon: the game's own enemies

    def test_an_enemy_is_made_to_measure(self):
        from engine.editor import balance
        plain = balance.make_enemy(self.DEPTHS)
        self.assertEqual((plain["id"], plain["floor"]["n"], plain["enemy"]["type"]), ("new_enemy", 1, "hostile"))
        self.assertAlmostEqual(plain["power"] / plain["target"], 1.0, delta=0.08)
        self.assertEqual([m["type"] for m in plain["enemy"]["moves"]], ["attack", "heavy"])
        made = balance.make_enemy(self.DEPTHS, like="bone_rat", floor=3, rank="elite", name="Grave Hound")
        self.assertEqual((made["id"], made["enemy"]["name"]), ("grave_hound", "Grave Hound"))
        self.assertAlmostEqual(made["power"] / made["target"], 1.0, delta=0.05)
        self.assertEqual(made["target"], round(made["floor"]["power"] * balance.RANKS["elite"]))
        rat = GameData(self.DEPTHS).characters["bone_rat"]
        self.assertEqual(made["enemy"]["moves"], rat["moves"])                              # it fights like the one it came from
        self.assertGreater(made["enemy"]["xp"], rat["xp"])
        tough = balance.make_enemy(self.DEPTHS, like="bone_rat", floor=3, rank="elite", lean=-1)
        sharp = balance.make_enemy(self.DEPTHS, like="bone_rat", floor=3, rank="elite", lean=1)
        self.assertGreater(tough["enemy"]["stats"]["max_health"], 1.8 * sharp["enemy"]["stats"]["max_health"])
        self.assertLess(tough["enemy"]["stats"]["attack"], sharp["enemy"]["stats"]["attack"])
        for one in (tough, sharp):                                                          # the same strength either way
            self.assertAlmostEqual(one["power"] / one["target"], 1.0, delta=0.06)
        king = balance.make_enemy(self.DEPTHS, like="hollow_king", name="Bone Rat")
        self.assertEqual(king["id"], "bone_rat_2")                                          # never an id that is taken
        self.assertNotIn("dialogue_tree", king["enemy"])
        with self.assertRaisesRegex(editor.EditorError, "rank"):
            balance.make_enemy(self.DEPTHS, rank="god")
        with self.assertRaisesRegex(editor.EditorError, "not a character with stats"):
            balance.make_enemy(self.DEPTHS, like="maren")

    def test_fights_are_tried_not_calculated(self):
        from engine.editor import balance
        folder = copy_of("depths")
        before = sorted(os.listdir(folder))
        easy = balance.odds(folder, ["bone_rat"], fights=12)
        self.assertEqual([r["class"] for r in easy["rows"]], ["warrior", "rogue", "mystic"])
        self.assertTrue(all(r["wins"] >= 0.9 and r["health_left"] > 0.6 and r["turns"] >= 1 for r in easy["rows"]), easy)
        self.assertEqual(easy, balance.odds(folder, ["bone_rat"], fights=12))               # the same dice, the same fights
        king = balance.odds(folder, ["hollow_king"], fights=8)
        self.assertTrue(all(r["wins"] <= 0.25 for r in king["rows"]), king)                 # at level 1 that is not a fight
        later = balance.odds(folder, ["hollow_king"], level=12, fights=8)
        self.assertGreater(sum(r["wins"] for r in later["rows"]), sum(r["wins"] for r in king["rows"]))
        pack = balance.odds(folder, ["bone_rat"] * 3, fights=12)
        self.assertLess(sum(r["health_left"] or 0 for r in pack["rows"]), sum(r["health_left"] for r in easy["rows"]))
        made = balance.make_enemy(folder, like="bone_rat", floor=2, rank="regular")
        tried = balance.odds(folder, [made["id"]], extra={made["id"]: made["enemy"]}, level=3, fights=8)
        self.assertEqual(len(tried["rows"]), 3)
        self.assertNotIn(made["id"], GameData(folder).characters)                           # trying is not adding
        self.assertEqual(sorted(os.listdir(folder)), before)                                # and nothing was written or saved
        with self.assertRaisesRegex(editor.EditorError, "cannot be fought"):
            balance.odds(folder, ["maren"])
        solo = balance.odds(os.path.join(ROOT, "games", "derelict"), ["mutated_bugrat"], fights=6)
        self.assertEqual([r["name"] for r in solo["rows"]], ["The player"])                 # a game without classes


class AdviceTests(unittest.TestCase):
    def test_the_demo_games_need_none(self):
        for name in ("derelict", "depths"):
            self.assertEqual(editor.advice(os.path.join(ROOT, "games", name)), [], name)

    def test_unreachable_rooms_and_unused_things(self):
        folder = copy_of("derelict")
        files = editor.current(folder)
        scenes, items = files["scenes"], files["items"]
        scenes.append({"id": "attic", "name": "Attic", "description": "Dust.", "exits": [{"door_name": "Ladder", "scene_id": scenes[0]["id"]}]})
        items["orphan_spoon"] = {"name": "Spoon", "description": "A spoon."}
        found = editor.advice(folder, {"scenes": scenes, "items": items})
        self.assertEqual(sorted((a["kind"], a["id"]) for a in found), [("items", "orphan_spoon"), ("scenes", "attic")])
        self.assertIn("cannot be reached", [a["text"] for a in found if a["kind"] == "scenes"][0])
        self.assertEqual(editor.check(folder, {"scenes": scenes, "items": items}), [])      # advice, not a problem
        scenes[0]["exits"].append({"door_name": "Hatch up", "scene_id": "attic"})           # a way in
        scenes[1].setdefault("hint", [])
        scenes[1]["hint"] = [{"if": "has:orphan_spoon", "text": "You have a spoon."}]       # named inside a condition
        self.assertEqual(editor.advice(folder, {"scenes": scenes, "items": items}), [])
        self.assertEqual(editor.advice(folder), [])                                         # and nothing was written


class ViewTests(unittest.TestCase):
    DERELICT = os.path.join(ROOT, "games", "derelict")

    def test_the_map_is_the_players_map(self):
        from engine import automap
        from engine.editor import views
        import copy
        data = GameData(self.DERELICT)
        want = automap.layout(copy.deepcopy(data.scenes), data.config.get("initial_scene"))
        got = views.world_map(self.DERELICT)
        self.assertEqual({r["id"]: (r["x"], r["y"], r["z"]) for r in got["rooms"]}, {k: tuple(v) for k, v in want.items()})
        self.assertEqual((got["start"], got["levels"], got["generated"]), (data.config.get("initial_scene"), [1, 0], False))
        self.assertTrue(all(r["placed"] and r["pinned"] and r["reached"] for r in got["rooms"]))
        ways = {(w["from"], w["to"]): w for w in got["ways"]}
        self.assertEqual(ways[("corridor", "storage_bay")]["barred"], "locked")
        self.assertEqual(ways[("utility_room", "corridor")]["barred"], "guarded")
        self.assertEqual(ways[("corridor", "bridge")]["level"], 1)                         # a lift up
        self.assertFalse(any(w["missing"] or w["one_way"] for w in got["ways"]))
        folder = copy_of("derelict")
        scenes = editor.current(folder)["scenes"]
        scenes.append({"id": "attic", "name": "Attic", "description": "Dust.", "exits": [{"door_name": "Ladder", "scene_id": "corridor"}]})
        scenes[0]["exits"].append({"door_name": "Crack", "scene_id": "nowhere"})
        changed = views.world_map(folder, {"scenes": scenes})
        attic = [r for r in changed["rooms"] if r["id"] == "attic"][0]
        self.assertEqual((attic["placed"], attic["reached"]), (True, False))               # set aside: nothing leads there
        self.assertEqual(sum(1 for r in changed["rooms"] if not r["reached"]), 1)
        ways = {(w["from"], w["to"]): w for w in changed["ways"]}
        self.assertTrue(ways[("attic", "corridor")]["one_way"])
        self.assertTrue(ways[(scenes[0]["id"], "nowhere")]["missing"])
        hollow = views.world_map(os.path.join(ROOT, "games", "depths"))                     # most of it is made in play
        self.assertTrue(hollow["generated"])
        self.assertEqual([(w["generated"], w["missing"], w["level"]) for w in hollow["ways"]], [(True, False, -1)])

    def test_a_conversation_as_the_engine_runs_it(self):
        from engine.editor import views
        with open(os.path.join(self.DERELICT, "dialogues.json"), encoding="utf-8") as f:
            bolt = json.load(f)["bolt"]
        g = views.dialogue_graph(bolt)
        by_id = {n["id"]: n for n in g["nodes"]}
        self.assertEqual([n["id"] for n in g["nodes"] if n["start"]], ["hello", "again", "after"])   # three ways in, by condition
        self.assertEqual((by_id["menu"]["depth"], by_id["menu"]["stays"]), (1, 5))
        self.assertEqual({(j["from"], j["to"], j["kind"]) for j in g["jumps"]},
                         {("hello", "menu", "then"), ("again", "menu", "then"), ("after", "menu", "then")})
        self.assertEqual(g["missing"], [])
        tree = {"start": "a", "nodes": {
            "a": {"text": "Hello.", "choices": [{"text": "Who are you?", "say": "Nobody."}, {"text": "Trade?", "goto": "shop"},
                                                {"text": "Bye.", "goto": "end"}, {"text": "Odd.", "goto": "nowhere"}]},
            "shop": {"text": "Look.", "goto": "a"},
            "orphan": {"variants": [{"if": "x", "text": "Never said."}]}}}
        g = views.dialogue_graph(tree)
        by_id = {n["id"]: n for n in g["nodes"]}
        self.assertEqual([n["id"] for n in g["nodes"]], ["a", "shop", "orphan"])            # in the order they are reached
        self.assertEqual((by_id["a"]["stays"], by_id["a"]["ends"], by_id["a"]["depth"]), (1, True, 0))
        self.assertEqual((by_id["orphan"]["reached"], by_id["orphan"]["ends"], by_id["orphan"]["text"]), (False, True, "Never said."))
        self.assertEqual([(j["from"], j["to"], j["by"], j["kind"]) for j in g["jumps"]],
                         [("a", "shop", "Trade?", "choice"), ("shop", "a", "", "then")])
        self.assertEqual([(m["from"], m["to"]) for m in g["missing"]], [("a", "nowhere")])
        self.assertEqual(views.dialogue_graph({"start": "gone", "nodes": {"x": {"text": "Hi"}}})["nodes"][0]["start"], True)
        with self.assertRaisesRegex(editor.EditorError, "no nodes"):
            views.dialogue_graph({"start": "a"})


class FinishTests(unittest.TestCase):
    DERELICT = os.path.join(ROOT, "games", "derelict")

    def test_reading_a_walkthrough(self):
        from engine.editor import finish
        walks = finish.parse("# a note\n\ntake wire   # why not\n== second way\nseed 7\nGo North\nseed 9\n==\nlook\n")
        self.assertEqual([(w["name"], w["seed"]) for w in walks], [("walkthrough", 1), ("second way", 7), ("walkthrough 3", 1)])
        self.assertEqual(walks[0]["lines"], [(3, "take wire")])                 # with the line it stands on
        self.assertEqual(walks[1]["lines"], [(6, "Go North"), (7, "seed 9")])   # only a first line sets the dice
        self.assertEqual(finish.parse(""), [])

    def test_derelict_can_be_finished_three_ways(self):
        from engine.editor import finish
        result = finish.play(self.DERELICT)
        self.assertTrue(result["finished"])
        self.assertEqual([(w["name"], w["result"], w["left"], w["refused"], w["stopped"]) for w in result["walkthroughs"]],
                         [("the escape pod", "win", 0, [], None), ("the rescue call", "win", 0, [], None),
                          ("the captain's chair", "win", 0, [], None)])
        self.assertEqual(result["coverage"]["scenes"], {"total": 8, "missing": []})
        self.assertEqual(result["coverage"]["quests"]["missing"], ["chip", "remote", "fruit"])   # side quests no route needs

    def test_a_change_that_breaks_the_game_is_noticed(self):
        from engine.editor import finish
        folder = copy_of("derelict")
        scenes = editor.current(folder)["scenes"]
        for s in scenes:
            if s["id"] == "storage_bay":
                s["exits"] = []                                                 # walk in, never out
        result = finish.play(folder, pending={"scenes": scenes})
        self.assertFalse(result["finished"])
        first = result["walkthroughs"][0]
        self.assertEqual((first["won"], first["result"]), (False, None))
        self.assertIn("not over", first["stopped"]["why"])
        self.assertTrue(first["refused"] and first["tail"])
        self.assertTrue(finish.play(folder)["finished"])                        # the files themselves were not touched
        short = finish.play(folder, "take wire\nfly to the moon\nunlock locker\n")
        self.assertEqual([(r["line"], r["command"]) for r in short["walkthroughs"][0]["refused"]], [(2, "fly to the moon")])
        self.assertEqual(short["walkthroughs"][0]["stopped"]["line"], 3)
        self.assertEqual(finish.play(folder, "")["walkthroughs"], [])
        self.assertFalse(finish.play(folder, "")["finished"])                   # nothing played is nothing shown

    def test_keeping_and_the_command_line(self):
        import io
        from contextlib import redirect_stdout
        import clio
        from engine.editor import finish
        folder = copy_of("derelict")
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(clio.main([folder, "--walkthrough"]), 0)
        self.assertIn("ok   the rescue call: win", out.getvalue())
        self.assertEqual(finish.write(folder, "take wire"), "walkthrough.txt")
        self.assertEqual(finish.read(folder), "take wire\n")
        with redirect_stdout(out):
            self.assertEqual(clio.main([folder, "--walkthrough"]), 1)
        self.assertIn("FAIL walkthrough: not finished", out.getvalue())
        os.remove(os.path.join(folder, "walkthrough.txt"))
        with redirect_stdout(out):
            self.assertEqual(clio.main([folder, "--walkthrough"]), 2)
        self.assertEqual(finish.read(folder), "")


class SpriteTests(unittest.TestCase):
    def test_a_grown_sprite_is_the_one_the_game_draws(self):
        from engine import sprite
        from engine.editor import looks
        made = looks.grow("Bone Rat", 10)
        game = sprite.generate("Bone Rat", 10)
        self.assertEqual(made["pixels"], list(game.pixels))
        self.assertEqual(looks.grow("Bone Rat", 10), made)                      # the same words, the same creature
        self.assertNotEqual(looks.grow("Bone Rat 2", 10)["pixels"], made["pixels"])
        used = set("".join(made["pixels"])) - {"."}
        self.assertEqual(set(made["palette"]), used)                            # only the colours it uses, as hex
        for colour in made["palette"].values():
            self.assertRegex(colour, r"^#[0-9a-f]{6}$")
        again = sprite.Sprite.from_data(made, "copy")                           # and the engine reads it back the same
        self.assertEqual(again.pixels, game.pixels)
        for letter in used:
            self.assertEqual(sprite._rgb(made["palette"][letter]), tuple(game.palette[letter]))
        self.assertEqual(len(looks.grow("x", 99)["pixels"]), 32)                # kept to a sensible size
        self.assertEqual(looks.colours({"a": "#2B3340", "b": 202, "c": [1, 2, 3], "d": "none", "e": "no such colour"}),
                         {"a": "#2b3340", "b": "#ff5f00", "c": "#010203", "d": None, "e": None})


class HostedTests(unittest.TestCase):
    """The editor opened from a web address: the same service, a game held in memory, a list of files to fetch."""

    def files(self, name, under=""):
        folder = os.path.join(ROOT, "games", name)
        out = []
        for where, _dirs, names in os.walk(folder):
            for n in names:
                path = os.path.join(where, n)
                with open(path, "rb") as f:
                    out.append((under + os.path.relpath(path, folder).replace(os.sep, "/"), f.read()))
        return out

    def test_the_list_of_files_is_current(self):
        with open(hosted.MANIFEST, encoding="utf-8") as f:
            listed = json.load(f)
        self.assertEqual(listed, hosted.manifest(), "run: python -m engine.editor.hosted")
        for path in listed["engine"] + listed["starter"]["files"] + [p for g in listed["games"] for p in g["files"]]:
            self.assertTrue(os.path.isfile(os.path.join(ROOT, path)), path)
        self.assertIn("engine/editor/service.py", listed["engine"])
        self.assertEqual([g["id"] for g in listed["games"]], ["depths", "derelict"])
        for game in listed["games"] + [listed["starter"]]:
            self.assertIn(game["folder"] + "/game.json", game["files"])

    def test_the_site_is_served_as_it_is(self):
        # GitHub Pages leaves out files that start with an underscore (engine/__init__.py) unless told not to
        self.assertTrue(os.path.isfile(os.path.join(ROOT, ".nojekyll")))
        with open(os.path.join(ROOT, "index.html"), encoding="utf-8") as f:
            self.assertIn('url=engine/editor/web/index.html', f.read())   # by name: not every host finds a folder's page
        web = os.path.dirname(hosted.MANIFEST)
        with open(os.path.join(web, "worker.js"), encoding="utf-8") as f:
            worker = f.read()
        self.assertIn('new URL("../../../", self.location.href)', worker)      # from the page's folder to the root
        self.assertIn("service.handle", worker)

    def test_a_game_is_placed_and_asked_about(self):
        into = tempfile.mkdtemp(prefix="clio-hosted-test-")
        folder = hosted.place("my game!", self.files("derelict"), into)
        self.assertEqual(os.path.basename(folder), "my_game")
        self.assertEqual(hosted.found_in[folder], "")
        game = service.handle(folder, "/api/game")
        self.assertEqual((game["title"], game["problems"]), ("Derelict", []))
        self.assertTrue(service.handle(folder, "/api/finish")["finished"])
        self.assertTrue(service.handle(folder, "/api/archive").startswith(b"PK"))
        with self.assertRaises(service.Unknown):
            service.handle(folder, "/api/nothing")

        # nothing has been written yet; a save writes the file and, the first time that day, its backup
        self.assertEqual(hosted.changed(folder), [])
        data = game["files"]["game"]["data"]
        data["title"] = "Adrift"
        service.handle(folder, "/api/save", {"file": "game", "data": data})
        written = dict(hosted.changed(folder))
        self.assertEqual(sorted(p.split("/")[0] for p in written), [editor.BACKUP, "game.json"])
        self.assertEqual(json.loads(written["game.json"])["title"], "Adrift")
        self.assertEqual(hosted.changed(folder), [])

        # the whole game, as the page keeps it between visits: placing it again gives the same game
        kept = hosted.files(folder)
        self.assertIn("art/title.art", [path for path, _data in kept])
        again = hosted.place("again", kept, into)
        self.assertEqual(service.handle(again, "/api/game")["title"], "Adrift")
        self.assertTrue(os.path.isdir(os.path.join(again, editor.BACKUP)))

    def test_the_site_packs_into_one_file(self):
        import zipfile
        path = os.path.join(tempfile.mkdtemp(prefix="clio-hosted-test-"), "site.zip")
        count = hosted.pack(path)
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            listed = json.loads(z.read("engine/editor/web/manifest.json"))
        self.assertEqual(count, len(names))
        self.assertLess(count, 1000)                                     # itch.io takes no more files than that
        self.assertEqual(listed, hosted.manifest())
        for name in ["index.html", "engine/__init__.py", "engine/editor/web/index.html", "engine/editor/web/worker.js",
                     "engine/editor/web/app.js", "games/derelict/game.json", "templates/starter/game.json"]:
            self.assertIn(name, names)
        for name in listed["engine"] + listed["starter"]["files"] + [f for g in listed["games"] for f in g["files"]]:
            self.assertIn(name, names)
        self.assertFalse([n for n in names if n.startswith(("tests/", "utils/", "docs/")) or "__pycache__" in n])

    def test_the_game_is_found_inside_what_was_opened(self):
        into = tempfile.mkdtemp(prefix="clio-hosted-test-")
        # an archive of the folder, as "Download game" makes it; and what is not part of a game is left behind
        extra = [("derelict/.git/HEAD", b"ref"), ("derelict/saves/slot1.json", b"{}"), ("../outside.txt", b"no")]
        folder = hosted.place("whatever", self.files("derelict", "derelict/") + extra, into)
        self.assertEqual((os.path.basename(folder), hosted.found_in[folder]), ("derelict", "derelict"))
        self.assertEqual(sorted(os.listdir(into)), ["derelict"])
        self.assertFalse(os.path.exists(os.path.join(folder, ".git")))
        self.assertFalse(os.path.exists(os.path.join(folder, "saves")))
        self.assertEqual(service.handle(folder, "/api/game")["title"], "Derelict")

        # the same through a zip file
        packed = editor.archive(os.path.join(ROOT, "games", "depths"))
        folder = hosted.place("x", hosted.unzip(packed), into)
        self.assertEqual(service.handle(folder, "/api/game")["title"], "The Hollow")
        with self.assertRaises(editor.EditorError):
            hosted.unzip(b"this is not a zip file")

        with self.assertRaisesRegex(editor.EditorError, "no game.json"):
            hosted.place("x", [("notes/readme.txt", b"hello")], into)
        with self.assertRaisesRegex(editor.EditorError, "several games"):
            hosted.place("x", self.files("derelict", "a/") + self.files("depths", "b/"), into)


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.folder = copy_of("derelict")
        self.server, self.address = make_server(self.folder, 0)
        self.base, self.key = self.address.split("/?key=")
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def ask(self, path, body=None, key=None, host=None):
        req = urllib.request.Request(self.base + path, data=None if body is None else json.dumps(body).encode("utf-8"))
        req.add_header("X-CLIo-Token", self.key if key is None else key)
        if host:
            req.add_header("Host", host)
        try:
            with urllib.request.urlopen(req, timeout=10) as res:
                return res.status, res.read()
        except urllib.error.HTTPError as err:
            return err.code, err.read()

    def test_the_page_and_its_parts_are_served(self):
        self.assertTrue(self.base.startswith("http://127.0.0.1:"))
        code, page = self.ask("/", key="")
        self.assertEqual(code, 200)
        self.assertIn(b"<title>CLIo editor</title>", page)
        for part in ("/app.js", "/app.css"):
            self.assertEqual(self.ask(part, key="")[0], 200)
        self.assertEqual(self.ask("/../../clio.py")[0], 404)

    def test_only_the_page_with_the_key_may_read_or_write(self):
        self.assertEqual(self.ask("/api/game", key="")[0], 403)
        self.assertEqual(self.ask("/api/game", key="guess")[0], 403)
        self.assertEqual(self.ask("/api/save", {"file": "texts", "data": {}}, key="")[0], 403)
        self.assertEqual(self.ask("/api/game", host="evil.example")[0], 403)      # another site pointing a name at this machine
        code, body = self.ask("/api/game")
        self.assertEqual(code, 200)
        game = json.loads(body)
        self.assertEqual(game["title"], "Derelict")
        self.assertEqual([k["key"] for k in game["schema"]], [k["key"] for k in schema.KINDS])

    def test_check_and_save_through_the_server(self):
        game = json.loads(self.ask("/api/game")[1])
        texts = game["files"]["texts"]["data"]
        first = next(iter(texts))
        texts[first]["text"] = "Rewritten."
        code, body = self.ask("/api/check", {"pending": {"texts": texts}})
        self.assertEqual((code, json.loads(body)), (200, {"problems": []}))
        code, body = self.ask("/api/save", {"file": "texts", "data": texts})
        self.assertEqual((code, json.loads(body)["saved"]), (200, "texts.json"))
        self.assertEqual(GameData(self.folder).texts[first]["text"], "Rewritten.")
        code, body = self.ask("/api/save", {"file": "scenes", "data": {}})
        self.assertEqual(code, 400)
        self.assertIn("JSON list", json.loads(body)["error"])
        self.assertEqual(self.ask("/api/nothing", {})[0], 404)

    def test_texts_and_archive_through_the_server(self):
        code, body = self.ask("/api/texts", {})
        rows = json.loads(body)["rows"]
        self.assertEqual(code, 200)
        self.assertGreater(len(rows), 400)
        code, body = self.ask("/api/texts", {"csv": True, "pending": {"game": {"title": "Unsaved title"}}})
        out = json.loads(body)
        self.assertIn("game/title,Unsaved title\n", out["csv"])                 # what is in the page, not only what is on disk
        code, body = self.ask("/api/texts/apply", {"rows": [{"where": "game/title", "text": "Renamed"}]})
        result = json.loads(body)
        self.assertEqual((code, result["report"]["changed"], result["files"]["game"]["title"]), (200, 1, "Renamed"))
        self.assertEqual(GameData(self.folder).title, "Derelict")               # applying does not save
        code, body = self.ask("/api/texts/apply", {"csv": "where,text\ngame/title\n"})
        self.assertEqual(code, 400)
        self.assertIn("could not be read", json.loads(body)["error"])
        code, body = self.ask("/api/archive", {})
        self.assertEqual((code, body[:2]), (200, b"PK"))
        self.assertEqual(self.ask("/api/archive", {}, key="")[0], 403)

    def test_enemies_through_the_server(self):
        code, body = self.ask("/api/enemy", {"rank": "boss", "name": "Bilge King"})
        made = json.loads(body)
        self.assertEqual((code, made["id"]), (200, "bilge_king"))
        self.assertTrue(made["like"] and made["floors"] and made["ranks"])
        code, body = self.ask("/api/odds", {"enemies": [made["id"]], "extra": {made["id"]: made["enemy"]}, "fights": 4})
        self.assertEqual((code, len(json.loads(body)["rows"])), (200, 1))
        code, body = self.ask("/api/odds", {"enemies": ["nobody"]})
        self.assertEqual(code, 400)
        self.assertIn("cannot be fought", json.loads(body)["error"])
        self.assertEqual(self.ask("/api/enemy", {"rank": "god"})[0], 400)

    def test_views_through_the_server(self):
        code, body = self.ask("/api/map", {})
        self.assertEqual((code, len(json.loads(body)["rooms"])), (200, 8))
        code, body = self.ask("/api/dialogue", {"tree": {"nodes": {"a": {"text": "Hi", "goto": "b"}, "b": {"text": "Bye"}}}})
        self.assertEqual((code, [n["depth"] for n in json.loads(body)["nodes"]]), (200, [0, 1]))
        self.assertEqual(self.ask("/api/dialogue", {"tree": {}})[0], 400)

    def test_walkthrough_through_the_server(self):
        code, body = self.ask("/api/walkthrough", {})
        self.assertEqual(code, 200)
        self.assertIn("== the escape pod", json.loads(body)["text"])
        code, body = self.ask("/api/finish", {"text": "take wire\n"})
        self.assertEqual((code, json.loads(body)["finished"]), (200, False))
        code, body = self.ask("/api/walkthrough", {"text": "look"})
        self.assertEqual((code, json.loads(body)), (200, {"saved": "walkthrough.txt"}))
        with open(os.path.join(self.folder, "walkthrough.txt"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "look\n")

    def test_advice_through_the_server(self):
        items = json.loads(self.ask("/api/game")[1])["files"]["items"]["data"]
        items["orphan_spoon"] = {"name": "Spoon"}
        code, body = self.ask("/api/advice", {"pending": {"items": items}})
        self.assertEqual((code, [a["id"] for a in json.loads(body)["advice"]]), (200, ["orphan_spoon"]))

    def test_sprites_through_the_server(self):
        code, body = self.ask("/api/sprite", {"seed": "Bugrat", "size": 8})
        made = json.loads(body)
        self.assertEqual((code, len(made["pixels"]), sorted(made)), (200, 8, ["palette", "pixels"]))
        code, body = self.ask("/api/sprite", {"palette": {"r": "red", "x": "#010203"}})
        self.assertEqual((code, json.loads(body)["colours"]["x"]), (200, "#010203"))
        self.assertRegex(json.loads(body)["colours"]["r"], r"^#[0-9a-f]{6}$")

    def test_the_usual_address_is_tried_first(self):
        from engine.editor import server as module
        usual, address = make_server(self.folder)                               # 8420 when free, any port when not
        try:
            port = usual.server_address[1]
            self.assertTrue(address.startswith("http://127.0.0.1:%d/?key=" % port))
            other, _ = make_server(self.folder)                                 # the usual one is now taken
            try:
                self.assertNotEqual(other.server_address[1], port)
            finally:
                other.server_close()
            if port == module.DEFAULT_PORT:
                with self.assertRaises(OSError):
                    make_server(self.folder, port)                              # asked for by number: say so, do not move
        finally:
            usual.server_close()


if __name__ == "__main__":
    unittest.main()
