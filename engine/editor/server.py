# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""The editor as a page in your browser, served from this machine only.

    python clio.py mygame --edit

Standard library only.  The server listens on 127.0.0.1, answers only requests
that carry the token it printed in the address, and writes only the data files
of the one game it was started for.
"""
import json
import os
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import EditorError, archive, balance, check, load, put_texts, save, text_table, texts

WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
PAGES = {"/": ("index.html", "text/html; charset=utf-8"), "/index.html": ("index.html", "text/html; charset=utf-8"),
         "/app.js": ("app.js", "text/javascript; charset=utf-8"), "/app.css": ("app.css", "text/css; charset=utf-8")}
LIMIT = 16 * 1024 * 1024
DEFAULT_PORT = 8420


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    # Windows would let a second editor share a port that is in use; elsewhere reuse only skips the wait after a restart
    allow_reuse_address = os.name != "nt"


def make_server(game_dir, port=None):
    """``(server, address)``; call ``server.serve_forever()``. The address carries the token.

    Without a ``port`` the usual one is tried first and any free one after it; ``0`` asks for any.
    """
    token = secrets.token_urlsafe(18)
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        server_version = "CLIoEditor"

        def log_message(self, *_args):                      # the terminal stays quiet
            pass

        def reply(self, code, body, kind="application/json; charset=utf-8"):
            data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def allowed(self):
            """Only this machine's own page may use the API: right host name, right token."""
            host = (self.headers.get("Host") or "").split(":")[0]
            return host in ("127.0.0.1", "localhost") and secrets.compare_digest(
                self.headers.get("X-CLIo-Token") or "", token)

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path in PAGES:
                name, kind = PAGES[path]
                with open(os.path.join(WEB, name), "rb") as f:
                    return self.reply(200, f.read(), kind)
            if path == "/api/game":
                if not self.allowed():
                    return self.reply(403, {"error": "This address is missing its key. Start the editor again."})
                return self.answer(lambda: load(game_dir))
            self.reply(404, {"error": "Nothing here."})

        def do_POST(self):
            path = self.path.split("?", 1)[0]
            if not self.allowed():
                return self.reply(403, {"error": "This address is missing its key. Start the editor again."})
            try:
                size = int(self.headers.get("Content-Length") or 0)
                if size > LIMIT:
                    return self.reply(413, {"error": "That is too much to save at once."})
                body = json.loads(self.rfile.read(size).decode("utf-8") or "{}")
            except (ValueError, UnicodeDecodeError):
                return self.reply(400, {"error": "The request was not valid JSON."})
            if path == "/api/check":
                return self.answer(lambda: {"problems": check(game_dir, body.get("pending") or {})})
            if path == "/api/save":
                return self.answer(lambda: save(game_dir, str(body.get("file")), body.get("data")))
            if path == "/api/texts":                        # every line a player can read
                def table():
                    found = text_table(game_dir, body.get("pending") or {})
                    return {"csv": texts.to_csv(found), "count": len(found)} if body.get("csv") else {"rows": found}
                return self.answer(table)
            if path == "/api/texts/apply":                  # put texts back: a table from the page, or a CSV file's text
                def put():
                    try:
                        rows = texts.from_csv(body["csv"]) if isinstance(body.get("csv"), str) else body.get("rows") or []
                    except (ValueError, KeyError) as err:
                        raise EditorError("That file could not be read as a table of texts: %s" % err)
                    return put_texts(game_dir, rows, body.get("pending") or {})
                return self.answer(put)
            if path == "/api/enemy":                        # a new enemy of a chosen strength, to look at
                return self.answer(lambda: balance.make_enemy(
                    game_dir, body.get("like") or None, body.get("floor"), body.get("rank") or "regular",
                    body.get("lean") or 0.0, body.get("name"), body.get("pending") or {}))
            if path == "/api/odds":                         # how fights against some characters go
                return self.answer(lambda: balance.odds(
                    game_dir, [str(e) for e in body.get("enemies") or []], body.get("pending") or {},
                    body.get("extra") or None, body.get("level") or 1, body.get("fights") or 30))
            if path == "/api/archive":
                try:
                    with lock:
                        return self.reply(200, archive(game_dir), "application/zip")
                except Exception as err:
                    return self.reply(500, {"error": "%s: %s" % (type(err).__name__, err)})
            self.reply(404, {"error": "Nothing here."})

        def answer(self, work):
            try:
                with lock:                                  # one change at a time
                    result = work()
            except EditorError as err:
                return self.reply(400, {"error": str(err)})
            except Exception as err:
                return self.reply(500, {"error": "%s: %s" % (type(err).__name__, err)})
            self.reply(200, result)

    try:                                                    # the same address every time, when it is free: the
        server = _Server(("127.0.0.1", DEFAULT_PORT if port is None else int(port)), Handler)
    except OSError:                                         # browser then remembers the page's settings
        if port is not None:
            raise
        server = _Server(("127.0.0.1", 0), Handler)
    return server, "http://127.0.0.1:%d/?key=%s" % (server.server_address[1], token)


def serve(game_dir, port=None, open_browser=True, say=print):
    """Run the editor until Ctrl+C."""
    server, address = make_server(game_dir, port)
    say("Editing %s" % os.path.abspath(game_dir))
    say("Open %s" % address)
    say("Changes are written to the game's files when you press Save. Ctrl+C here ends the editor.")
    if open_browser:
        try:
            webbrowser.open(address)
        except Exception:                                   # no browser to open: the address was printed
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        say("\nEditor closed.")
    finally:
        server.server_close()
    return 0
