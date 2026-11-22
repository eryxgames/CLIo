# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Daniel Sandner
"""CLIo in a web browser: the engine, unchanged, in Python compiled for the web (Pyodide), in a worker.

The page shows a terminal (xterm.js) and runs this in a web worker. ``run(io, argv)`` gives the engine what a
terminal gives it on a desktop, made of ``io`` - the page's side, handed in by engine/editor/web/play.js:

- ``io.write(text)``: show text (escape sequences and all) on the page's terminal;
- ``io.read(n, ms)``: up to n bytes the player typed (keys arrive as a terminal sends them), waiting up to ms
  milliseconds (-1: until something comes); b"" if nothing came;
- ``io.size()``: the terminal's (columns, rows);
- ``io.sleep(ms)``: wait, without spinning;
- ``io.sound(what, path, data, volume)``: "play", "loop" or "stop" a WAV (its bytes the first time a path is
  played, None after);
- ``io.saved(path, data)`` and ``io.removed(path)``: a file in the data folder was written or deleted (the page
  keeps saves and records between visits and hands them back next time).

What is put in place: standard input and output that are a terminal (``isatty``), a stand-in ``termios``
(raw mode is the only mode there is: the page sends every key; ``input()`` gets its line edited here),
``select.select`` and ``os.read`` on standard input, ``time.sleep``, the terminal's size, a sound backend, and
the data folder's writes reported. Nothing else changes: the same engine runs on a desktop and here."""
from __future__ import annotations

import os
import sys

STDIN = 0


def _bytes(value):
    """What io.read gave - bytes here, a JavaScript Uint8Array in the browser - as bytes."""
    if value is None:
        return b""
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value)
    to_bytes = getattr(value, "to_bytes", None)
    return to_bytes() if callable(to_bytes) else bytes(value)
DATA = "/data"                     # saves and records: kept by the page between visits
CACHE = "/cache"                   # rendered sounds: made again when needed


class _Out:
    """Standard output: text gathered and shown on the page at each flush (a frame of the game is one)."""
    encoding = "utf-8"
    errors = "replace"

    def __init__(self, io):
        self.io = io
        self.parts = []
        self.size = 0

    def write(self, text):
        if not isinstance(text, str):
            text = str(text)
        self.parts.append(text)
        self.size += len(text)
        if self.size > 1 << 16:
            self.flush()
        return len(text)

    def flush(self):
        if self.parts:
            text = "".join(self.parts)
            self.parts, self.size = [], 0
            self.io.write(text)

    def isatty(self):
        return True

    def fileno(self):
        return 1

    def writable(self):
        return True


class _In:
    """Standard input: the keys the page sends. ``readline`` edits a line as a terminal would for ``input()``:
    typed characters shown, Backspace taking the last back, Enter ending it."""
    encoding = "utf-8"

    def __init__(self, io, out):
        self.io, self.out = io, out
        self.pending = b""
        self.size_seen = None

    def isatty(self):
        return True

    def fileno(self):
        return STDIN

    def readable(self):
        return True

    # -- bytes, as os.read and select see them --------------------------- #
    def ready(self, timeout):
        """Whether a byte waits, waiting up to ``timeout`` seconds for one (None: as long as it takes)."""
        if self.pending:
            return True
        self.out.flush()
        ms = -1 if timeout is None else max(0, int(timeout * 1000))
        got = _bytes(self.io.read(4096, ms))
        _note_size(self.io)
        self.pending += got
        return bool(self.pending)

    def take(self, n):
        while not self.pending:
            self.ready(None)
        out, self.pending = self.pending[:n], self.pending[n:]
        return out

    def drop(self):
        self.pending = b""
        while _bytes(self.io.read(4096, 0)):
            pass

    # -- a line, for input() ---------------------------------------------- #
    def readline(self, limit=-1):
        line = bytearray()
        while True:
            b = self.take(1)
            if b in (b"\r", b"\n"):
                self.out.write("\r\n")
                self.out.flush()
                return line.decode("utf-8", "replace") + "\n"
            if b in (b"\x7f", b"\x08"):
                if line:
                    while line and (line[-1] & 0xC0) == 0x80:      # the rest of a character of several bytes
                        line.pop()
                    if line:
                        line.pop()
                    self.out.write("\b \b")
                    self.out.flush()
                continue
            if b == b"\x03":
                raise KeyboardInterrupt
            if b == b"\x04" and not line:
                return ""
            if b == b"\x1b":                                 # a key with no place in a line (arrows...): left out
                while self.ready(0.02):
                    c = self.take(1)
                    if c.isalpha() or c == b"~":
                        break
                continue
            if b < b" ":
                continue
            line += b
            try:
                self.out.write(b.decode("utf-8"))
            except UnicodeDecodeError:
                if (b[0] & 0xC0) == 0x80 or b[0] >= 0xC0:      # part of a character: shown when whole
                    try:
                        start = len(line) - 1
                        while start > 0 and (line[start] & 0xC0) == 0x80:
                            start -= 1
                        self.out.write(bytes(line[start:]).decode("utf-8"))
                    except UnicodeDecodeError:
                        pass
            self.out.flush()

    def read(self, n=-1):
        return self.readline()


def _note_size(io):
    """The page's terminal size into COLUMNS and LINES, where shutil.get_terminal_size reads it."""
    try:
        cols, rows = (int(v) for v in io.size())
    except Exception:
        return
    os.environ["COLUMNS"], os.environ["LINES"] = str(cols), str(rows)


class _Termios:
    """``termios`` for a terminal that is always raw: the settings are kept and given back, and do nothing."""
    error = OSError
    TCSANOW, TCSADRAIN, TCSAFLUSH = 0, 1, 2
    TCIFLUSH, TCOFLUSH, TCIOFLUSH = 0, 1, 2
    ICANON, ECHO, ISIG, IEXTEN, ICRNL, IXON, OPOST = 2, 8, 1, 32768, 256, 1024, 1
    VMIN, VTIME = 6, 5

    def __init__(self, stdin):
        self.stdin = stdin
        self.attrs = [ICRNL_IXON, 1, 0, 2 | 8 | 1, 38400, 38400, [0] * 32]

    def tcgetattr(self, fd):
        return [list(v) if isinstance(v, list) else v for v in self.attrs]

    def tcsetattr(self, fd, when, attrs):
        self.attrs = [list(v) if isinstance(v, list) else v for v in attrs]

    def tcflush(self, fd, queue):
        if queue in (self.TCIFLUSH, self.TCIOFLUSH):
            self.stdin.drop()

    def tcdrain(self, fd):
        pass


ICRNL_IXON = 256 | 1024


class WebBackend:
    """Sound through the page (WebAudio): each WAV's bytes go over once, then it is played by its path."""
    description = "the browser"
    record = False

    def __init__(self, io):
        self.io = io
        self.sent = set()

    def _data(self, path):
        if path in self.sent:
            return None
        with open(path, "rb") as f:
            data = f.read()
        self.sent.add(path)
        return data

    def can_play(self, path):
        return str(path).lower().endswith(".wav")

    def play(self, path, volume=1.0):
        self.io.sound("play", path, self._data(path), float(volume))

    def loop(self, path, volume=1.0):
        self.io.sound("loop", path, self._data(path), float(volume))

    def stop_loop(self):
        self.io.sound("stop", "", None, 0.0)

    def shutdown(self):
        self.stop_loop()


def install(io, data=DATA):
    """Put the page's terminal, sleep, sound and data folder in place of the machine's. Returns (out, in)."""
    import select
    import shutil
    import time

    out = _Out(io)
    inp = _In(io, out)
    sys.stdout = sys.__stdout__ = out
    sys.stdin = sys.__stdin__ = inp
    sys.modules["termios"] = _Termios(inp)
    _note_size(io)

    real_read, real_select = os.read, select.select

    def read(fd, n):
        if fd == STDIN:
            return inp.take(n)
        return real_read(fd, n)

    def select_(r, w, x, timeout=None):
        ours = [f for f in r if f is inp or f == STDIN or getattr(f, "fileno", lambda: None)() == STDIN]
        if ours and len(ours) == len(r) and not w and not x:
            return (ours, [], []) if inp.ready(timeout) else ([], [], [])
        return real_select(r, w, x, timeout)

    def sleep(seconds):
        out.flush()
        if seconds and seconds > 0:
            io.sleep(int(seconds * 1000))

    def size(fallback=(80, 24)):
        _note_size(io)
        return os.terminal_size((int(os.environ.get("COLUMNS", fallback[0])), int(os.environ.get("LINES", fallback[1]))))

    os.read = read
    select.select = select_
    time.sleep = sleep
    shutil.get_terminal_size = size

    real_replace, real_remove = os.replace, os.remove

    root = os.path.abspath(data) + os.sep

    def kept(path):
        p = os.path.abspath(str(path))
        return p.startswith(root) and not p.endswith((".tmp", ".w"))

    def replace(src, dst, **kw):
        real_replace(src, dst, **kw)
        if kept(dst):
            try:
                with open(dst, "rb") as f:
                    io.saved(os.path.abspath(str(dst)), f.read())
            except OSError:
                pass

    def remove(path, **kw):
        real_remove(path, **kw)
        if kept(path):
            io.removed(os.path.abspath(str(path)))

    os.replace, os.remove, os.unlink = replace, remove, remove
    return out, inp


def run(io, argv=(), data=DATA, cache=CACHE, threads=None):
    """Run CLIo as ``clio.py ARGV`` would, on the page's terminal. Returns the exit code. ``data``: where saves
    and records go (and are reported to the page); ``cache``: rendered sounds. ``threads``: False does a thread's
    work where it starts, as the browser must (it has none); by default only there."""
    os.environ["TERM"] = "xterm-256color"
    os.environ["COLORTERM"] = "truecolor"
    os.environ["XDG_DATA_HOME"] = data
    os.environ["XDG_CACHE_HOME"] = cache
    os.environ["CLIO_DATA"] = os.path.join(data, "clio")             # where XDG puts them - on Windows too,
    os.environ["CLIO_SAVES"] = os.path.join(data, "clio", "saves")   # whose own folders are elsewhere
    os.environ["CLIO_WEB"] = "1"
    for name in ("CLIO_CACHE", "NO_COLOR"):
        os.environ.pop(name, None)
    for d in (data, cache):
        os.makedirs(d, exist_ok=True)
    out, _inp = install(io, data)
    from . import audio
    from .audio import backends
    web = WebBackend(io)
    backends.detect = audio.detect = lambda env=None: (web, web.description)
    if threads is None:
        threads = sys.platform != "emscripten"
    if not threads:                                      # no threads in the browser: a thread's work is done where it starts
        import threading

        def start(self):
            self._started.set()
            self.run()
        threading.Thread.start = start
    code = 0
    try:
        import clio
        result = clio.main(list(argv))
        code = int(result or 0) if isinstance(result, int) or result is None else 0
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    except KeyboardInterrupt:
        code = 130
    finally:
        try:
            out.write("\x1b[0m\x1b[?25h")
            out.flush()
        except Exception:
            pass
    return code


def in_browser():
    """Whether this is Python in a web page (no downloads, no other programs, the page's sound)."""
    return sys.platform == "emscripten" or os.environ.get("CLIO_WEB") == "1"
