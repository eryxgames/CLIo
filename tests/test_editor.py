# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""The editor: reading, checking and writing a game's files, and the local server."""
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import ROOT                                        # noqa: E402

from engine import editor, schema                               # noqa: E402
from engine.data import GameData, find_games                    # noqa: E402
from engine.editor.server import make_server                    # noqa: E402

TYPES = {"text", "long", "number", "bool", "choice", "tags", "ref", "refs"}


def copy_of(name):
    """A game to scribble on."""
    folder = os.path.join(tempfile.mkdtemp(prefix="clio-editor-test-"), name)
    shutil.copytree(os.path.join(ROOT, "games", name), folder)
    return folder


class SchemaTests(unittest.TestCase):
    def test_the_description_is_well_formed(self):
        keys = [k["key"] for k in schema.KINDS]
        self.assertEqual(len(keys), len(set(keys)))
        for kind in schema.KINDS:
            self.assertIn(kind["shape"], ("map", "list", "object"))
            seen = set()
            for f in kind["fields"]:
                self.assertIn(f["type"], TYPES, f)
                self.assertNotIn(f["key"], seen, "%s.%s is listed twice" % (kind["key"], f["key"]))
                seen.add(f["key"])
                if f["type"] in ("ref", "refs"):
                    self.assertIn(f["of"], keys, f)
                if f["type"] == "choice":
                    self.assertTrue(f["options"])
            if kind.get("title"):
                self.assertIn(kind["title"], seen)

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
