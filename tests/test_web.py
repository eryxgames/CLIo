"""CLIo in a web browser (engine/web.py, engine/editor/web/play.*): the engine on a page's terminal.

The browser itself is not here: a page made of a script stands in for it (keys to give, the screen gathered), and
the engine runs on it in a Python process of its own - engine.web replaces that process's terminal, as it does in
the browser's worker."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)

from engine import web  # noqa: E402
from engine.editor import hosted  # noqa: E402

PAGE = r'''
import json, os, sys
sys.path.insert(0, ROOT)
from engine import web

class Page:
    def __init__(self, keys, cols=100, rows=30):
        self.keys = [k.encode("utf-8") for k in keys]
        self.shown, self.sounds, self.saves, self.slept = [], [], {}, 0
        self.cols, self.rows = cols, rows
        self.waits = 0
    def write(self, text):
        self.shown.append(text)
    def read(self, n, ms):
        self.waits += 1
        if ms == 0 and self.waits % 3:
            return b""
        if self.keys:
            k = self.keys.pop(0)
            return k[:n]
        if ms != 0:
            raise SystemExit(99)              # nothing left to type: the game is stopped
        return b""
    def size(self):
        return (self.cols, self.rows)
    def sleep(self, ms):
        self.slept += ms
    def sound(self, what, path, data, volume):
        self.sounds.append([what, os.path.basename(path), None if data is None else len(data)])
    def saved(self, path, data):
        self.saves[path] = len(data)
    def removed(self, path):
        self.saves.pop(path, None)

page = Page(KEYS)
code = web.run(page, ARGV, data=DATA, cache=CACHE, threads=False)   # as in the browser: the same every time
text = "".join(page.shown)
plain = re.sub(r"\x1b\[[0-9;?<>]*[a-zA-Z~]|\x1b\][^\x07]*\x07|\x1b[()][0-9A-Z]", "", text)
sys.__stderr__.write(json.dumps({"code": code, "plain": plain, "raw": len(text), "sounds": page.sounds,
                                 "saves": page.saves, "slept": page.slept}) + "\n")
'''


def play(argv, keys, data=None):
    """Run clio.py ARGV on a scripted page; what it showed (escape sequences left out), played and kept."""
    tmp = tempfile.mkdtemp(prefix="clio-web-test-")
    data = data or os.path.join(tmp, "data")
    script = "import re\nROOT, KEYS, ARGV, DATA, CACHE = %r, %r, %r, %r, %r\n" % (
        os.path.abspath(ROOT), keys, argv, data, os.path.join(tmp, "cache")) + PAGE
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    run = subprocess.run([sys.executable, "-c", script], cwd=ROOT, env=env, capture_output=True, timeout=300)
    lines = run.stderr.decode("utf-8", "replace").strip().splitlines()
    try:
        return json.loads(lines[-1])
    except (IndexError, ValueError):
        raise AssertionError("the page script failed:\n" + run.stderr.decode("utf-8", "replace")[-3000:])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


class PlayedTests(unittest.TestCase):
    def test_a_text_game_is_played_with_lines_typed_and_edited(self):
        got = play(["derelict"], ["\r", "\r", "lo\x7fok\r", "inventory\r", "quit\r", "y\r"])
        self.assertEqual(got["code"], 0)
        self.assertIn("Utility Room", got["plain"])
        self.assertIn("You are carrying nothing.", got["plain"])
        self.assertIn("Thank you for playing.", got["plain"])
        self.assertNotIn("I don't understand", got["plain"])  # "lo", Backspace, "ok": the game read "look"
        played = [s for s in got["sounds"] if s[0] == "play"]
        self.assertTrue(played and played[0][2])             # a sound's bytes go to the page the first time

    def test_the_first_person_game_draws_frames_and_music(self):
        got = play(["rootless"], ["\r"] * 6 + ["\x1b[A", "\x1b[C", " "])
        self.assertEqual(got["code"], 99)                     # stopped when the keys ran out
        self.assertIn("pistol", got["plain"])
        self.assertIn("▀", got["plain"])                 # the picture, in half blocks
        loops = [s for s in got["sounds"] if s[0] == "loop"]
        self.assertTrue(loops and loops[0][2] > 100000)       # the music, as a WAV for the page's WebAudio
        names = [s[1] for s in got["sounds"]]
        for i, s in enumerate(got["sounds"]):
            if s[1] in names[:i]:
                self.assertIsNone(s[2])                       # sent once: after that by its name

    def test_a_save_is_handed_to_the_page(self):
        tmp = tempfile.mkdtemp(prefix="clio-web-test-")
        data = os.path.join(tmp, "data")
        try:
            got = play(["rootless"], ["\r"] * 6 + ["\x1b[15~"], data=data)   # F5: save
            saves = [p for p in got["saves"] if "/saves/rootless/" in p.replace(os.sep, "/")]
            self.assertTrue(saves, got["saves"])
            self.assertTrue(all(n > 0 for n in got["saves"].values()))
            here = os.path.abspath(data) + os.sep
            self.assertTrue(all(os.path.abspath(p).startswith(here) for p in saves))   # in the page's folder
        finally:                                                                     # (not the player's own)
            shutil.rmtree(tmp, ignore_errors=True)


    def test_a_game_from_the_editor_is_played_from_its_own_folder(self):
        tmp = tempfile.mkdtemp(prefix="clio-web-edited-")              # play.html?edited=ID: the editor's game, as
        try:                                                            # saved there, in a folder of its own
            game = os.path.join(tmp, "edited", "mygame")
            shutil.copytree(os.path.join(ROOT, "templates", "starter"), game)
            got = play([game], ["\r", "\r", "look\r", "quit\r", "y\r"])
            self.assertEqual(got["code"], 0)
            self.assertIn("Wine Cellar", got["plain"])
            self.assertNotIn("No game", got["plain"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class SizeTests(unittest.TestCase):
    def test_the_page_says_how_often_its_terminal_changed_size(self):
        from unittest import mock
        from engine import web

        class Page:
            def size(self):
                return [72, 40]

            def changes(self):
                return 7

        class OlderPage:
            def size(self):
                return [80, 24]

        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CLIO_TERM_CHANGES", None)
            web._note_size(OlderPage())
            self.assertEqual((os.environ["COLUMNS"], os.environ["LINES"]), ("80", "24"))
            self.assertNotIn("CLIO_TERM_CHANGES", os.environ)
            web._note_size(Page())
            self.assertEqual((os.environ["COLUMNS"], os.environ["LINES"], os.environ["CLIO_TERM_CHANGES"]), ("72", "40", "7"))


class StandInTests(unittest.TestCase):
    class Page:
        def __init__(self, keys=b""):
            self.keys, self.out = keys, []

        def write(self, text):
            self.out.append(text)

        def read(self, n, ms):
            got, self.keys = self.keys[:n], self.keys[n:]
            return got

    def test_a_line_is_edited_as_a_terminal_edits_it(self):
        page = self.Page("hé\x7f\x7fhéllo\x7fy\x1b[A\r".encode("utf-8"))
        out = web._Out(page)
        inp = web._In(page, out)
        self.assertEqual(inp.readline(), "hélly\n")
        out.flush()
        self.assertIn("\b \b", "".join(page.out))
        self.assertTrue(inp.isatty() and out.isatty())

    def test_keys_are_bytes_and_wait_as_select_would(self):
        page = self.Page(b"\x1b[A")
        inp = web._In(page, web._Out(page))
        self.assertTrue(inp.ready(0))
        self.assertEqual(inp.take(1), b"\x1b")
        self.assertEqual(inp.take(8), b"[A")
        self.assertFalse(inp.ready(0))

    def test_termios_keeps_what_it_is_given(self):
        t = web._Termios(web._In(self.Page(), web._Out(self.Page())))
        attrs = t.tcgetattr(0)
        attrs[3] &= ~(t.ICANON | t.ECHO)
        t.tcsetattr(0, t.TCSANOW, attrs)
        self.assertEqual(t.tcgetattr(0)[3], attrs[3])
        t.tcflush(0, t.TCIFLUSH)

    def test_a_page_has_nothing_to_download(self):
        from engine import downloads
        old = os.environ.get("CLIO_WEB")
        os.environ["CLIO_WEB"] = "1"
        try:
            self.assertTrue(web.in_browser())
            self.assertEqual(downloads.offers(plat="linux-x64"), [])
        finally:
            if old is None:
                os.environ.pop("CLIO_WEB", None)
            else:
                os.environ["CLIO_WEB"] = old

    def test_bytes_from_the_page_whatever_they_come_as(self):
        class Typed:
            def to_bytes(self):
                return b"ok"
        self.assertEqual(web._bytes(Typed()), b"ok")
        self.assertEqual(web._bytes(None), b"")
        self.assertEqual(web._bytes(bytearray(b"x")), b"x")


class PageFilesTests(unittest.TestCase):
    WEB = os.path.join(ROOT, "engine", "editor", "web")

    def read(self, name):
        with open(os.path.join(self.WEB, name), encoding="utf-8") as f:
            return f.read()

    def test_the_play_list_has_what_a_game_needs(self):
        play = hosted.manifest()["play"]
        for name in ("clio.py", "engine/art/clio_logo.art", "engine/demos/clio.json", "games/rootless/game.json",
                     "games/depths/game.json", "games/derelict/game.json"):
            self.assertIn(name, play)
        self.assertFalse([n for n in play if n.startswith(("engine/editor/", "engine/audio/ballistic/"))
                          or n.endswith(".py") and n != "clio.py"])
        for name in play:
            self.assertTrue(os.path.isfile(os.path.join(ROOT, name)), name)

    def test_the_page_the_worker_and_the_engine_meet(self):
        page, script, worker = self.read("play.html"), self.read("play.mjs"), self.read("play.js")
        self.assertIn('src="play.mjs"', page)
        self.assertIn('new Worker("play.js"', script)
        self.assertIn("SharedArrayBuffer", script)
        self.assertIn('registerJsModule("clio_page", io)', worker)
        self.assertIn("web.run(clio_page", worker)
        for name in ("write", "read", "size", "sleep", "sound", "saved", "removed"):
            self.assertRegex(worker, r"\n  %s\(" % name)      # every call engine/web.py makes
        self.assertIn('register("coi.js")', script)
        self.assertIn("Cross-Origin-Embedder-Policy", self.read("coi.js"))

    def test_the_editor_hands_its_game_to_the_play_page(self):
        editor, script, worker, page = self.read("app.js"), self.read("play.mjs"), self.read("play.js"), self.read("play.html")
        store = '"clio-editor-play"'
        self.assertIn("const TRIED = " + store, editor)                   # both pages name the same place
        self.assertIn('indexedDB.open(' + store, script)
        self.assertIn('pageUrl("play.html", { edited: state.game.id })', editor)
        self.assertIn('query.get("edited")', script)
        self.assertIn("if (EDITED) return [EDITED_DIR];", script)          # played by its folder, as clio.py plays one
        self.assertIn("game.files", worker)
        self.assertIn('editorUrl({ open: EDITED })', script)              # back in the same frame: opened again there
        self.assertIn('PARAMS.get("open")', editor)
        self.assertIn("new Int32Array(shared, 0, 8)", script)            # the page and the worker share one layout
        self.assertIn("new Int32Array(shared, 0, 8)", worker)
        self.assertIn("new Uint8Array(shared, 32, RING)", script)
        self.assertIn("new Uint8Array(shared, 32, RING)", worker)
        self.assertIn("changes() { return Atomics.load(ctl, 4); }", worker)
        self.assertIn('setAttribute("inputmode", "none")', script)          # a phone: no keyboard on a tap
        self.assertIn('send((QUIET.test(key) ? "\\x15" : "") + key)', script)   # moves clear a half-typed line
        self.assertIn("term.clearTextureAtlas()", script)
        self.assertIn("gl.onContextLoss(() => gl.dispose())", script)
        self.assertIn('query.get("renderer") !== "dom"', script)
        self.assertIn("Atomics.add(ctl, 4, 1)", script)
        for name in ("bar-title", "bar-again", "bar-back"):
            self.assertIn('id="%s"' % name, page)
        index = self.read("index.html")
        for name in ("play", "games"):
            self.assertIn('id="%s"' % name, index)
            self.assertIn('$("%s")' % name, editor)

    def test_the_scripts_parse(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is not installed")
        for name in ("play.mjs", "play.js", "coi.js", "app.js", "worker.js"):
            run = subprocess.run([node, "--check", os.path.join(self.WEB, name)], capture_output=True)
            self.assertEqual(run.returncode, 0, name + ": " + run.stderr.decode("utf-8", "replace"))


if __name__ == "__main__":
    unittest.main()
