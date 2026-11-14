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

from . import EditorError, check, load, save

WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
PAGES = {"/": ("index.html", "text/html; charset=utf-8"), "/index.html": ("index.html", "text/html; charset=utf-8"),
         "/app.js": ("app.js", "text/javascript; charset=utf-8"), "/app.css": ("app.css", "text/css; charset=utf-8")}
LIMIT = 16 * 1024 * 1024


def make_server(game_dir, port=0):
    """``(server, address)``; call ``server.serve_forever()``. The address carries the token."""
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

    server = ThreadingHTTPServer(("127.0.0.1", int(port or 0)), Handler)
    server.daemon_threads = True
    return server, "http://127.0.0.1:%d/?key=%s" % (server.server_address[1], token)


def serve(game_dir, port=0, open_browser=True, say=print):
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
