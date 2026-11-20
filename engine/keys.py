# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Single keys straight from the terminal.

Everywhere else CLIo reads whole lines.  A first-person level reads keys, so
an arrow can move at once while typed commands still work (see
:mod:`engine.frame`, which builds a line editor on top of this).

* POSIX terminals (Linux, macOS, Termux, SSH): the terminal is put in cbreak
  mode - no line editing, no echo, Ctrl-C still interrupts - and the escape
  sequences the terminal sends are decoded.
* Windows (the console and Windows Terminal): ``msvcrt``.

Keys are named: ``"up" "down" "left" "right" "home" "end" "pgup" "pgdn"
"insert" "delete" "center" "f1".."f9" "enter" "tab" "space" "backspace" "esc"
"ctrl-u" "ctrl-d"``, a modified arrow as ``"ctrl-left"``, ``"alt-up"``,
``"shift-right"``, and any other key as the character it types.

What a terminal cannot tell a program: that a key was let go, that Ctrl or Shift
alone is down, or which of two keys held together came first.  A held key
repeats.  The numpad sends arrows and the like only with NumLock off; with
NumLock on it types digits, the same as the row above the letters.

**Key events** (for games in real time, :mod:`engine.realtime`): ``KeyReader.events()``
gives each key as pressed, repeated or let go, from the best source there is:

* ``"kitty"``: terminals that speak the kitty keyboard protocol (kitty, WezTerm, foot,
  Ghostty, Alacritty, recent iTerm2) report presses, repeats and releases of every key,
  Shift and Ctrl alone too. CLIo asks the terminal whether it does, and turns it on only
  then (and off again when it is done).
* ``"console"``: on Windows the console itself says when a key goes down and up
  (``ReadConsoleInputW``).
* ``"guess"``: anywhere else every key is a press; :class:`engine.realtime.Held` guesses
  that a key is held while its repeats keep coming.
"""
from __future__ import annotations

import os
import sys
import time

# xterm-style sequences after ESC (the ESC itself is not included)
SEQ = {"[A": "up", "[B": "down", "[C": "right", "[D": "left",
       "OA": "up", "OB": "down", "OC": "right", "OD": "left",
       "[H": "home", "[F": "end", "OH": "home", "OF": "end", "[1~": "home", "[4~": "end",
       "[7~": "home", "[8~": "end", "[2~": "insert", "[3~": "delete", "[5~": "pgup", "[6~": "pgdn",
       "[E": "center", "OE": "center", "[G": "center", "OP": "f1", "OQ": "f2", "OR": "f3", "OS": "f4",
       "[15~": "f5", "[17~": "f6", "[18~": "f7", "[19~": "f8", "[20~": "f9", "[11~": "f1", "[12~": "f2",
       "[13~": "f3", "[14~": "f4", "OM": "enter", "Oj": "*", "Ok": "+", "Om": "-", "On": ".", "Oo": "/",
       "[Z": "shift-tab"}
SEQ.update({"O" + chr(ord("p") + i): str(i) for i in range(10)})        # keypad in application mode
# the modifier digit in "ESC [1;5D": 2 Shift, 3 Alt, 5 Ctrl (and sums of them, plus one)
MODIFIERS = {"2": "shift", "3": "alt", "4": "alt", "5": "ctrl", "6": "ctrl", "7": "ctrl", "8": "ctrl"}
ARROWS = {"A": "up", "B": "down", "C": "right", "D": "left", "H": "home", "F": "end"}

# Windows: the second code after a 0x00 / 0xE0 prefix
WIN = {"H": "up", "P": "down", "K": "left", "M": "right", "G": "home", "O": "end", "I": "pgup",
       "Q": "pgdn", "R": "insert", "S": "delete", "L": "center", ";": "f1", "<": "f2", "=": "f3",
       ">": "f4", "?": "f5", "@": "f6", "A": "f7", "B": "f8", "C": "f9",
       "s": "ctrl-left", "t": "ctrl-right", "\x8d": "ctrl-up", "\x91": "ctrl-down",
       "\x9b": "alt-left", "\x9d": "alt-right", "\x98": "alt-up", "\xa0": "alt-down",
       "\x97": "alt-home", "\x9f": "alt-end"}
CTRL = {"\r": "enter", "\n": "enter", "\t": "tab", " ": "space", "\x7f": "backspace", "\x08": "backspace",
        "\x1b": "esc", "\x15": "ctrl-u", "\x04": "ctrl-d"}


def decode(seq):
    """The name of a key from the characters after ESC (``"[A"`` -> ``"up"``); ``"esc"`` if unknown. A mouse
    report (SGR, ``"[<0;12;5M"``) is ``"mouse:0:11:4"`` (button, column, row from 0), ``"mouseup:..."``
    when let go; button 2 is the right one, +32 while moving with it held."""
    if not seq:
        return "esc"
    if seq.startswith("[<") and seq[-1:] in ("M", "m"):
        try:
            b, x, y = (int(v) for v in seq[2:-1].split(";"))
        except ValueError:
            return "esc"
        return "%s:%d:%d:%d" % ("mouse" if seq[-1] == "M" else "mouseup", b, x - 1, y - 1)
    if seq in SEQ:
        return SEQ[seq]
    # "[1;5D" (Ctrl+Left), also "[5D" from some terminals, and "[3;5~" (Ctrl+Delete)
    if seq.startswith("[") and len(seq) >= 3 and seq[-1] in ARROWS:
        mod = seq[1:-1].split(";")[-1]
        name = MODIFIERS.get(mod)
        return ("%s-%s" % (name, ARROWS[seq[-1]])) if name else ARROWS[seq[-1]]
    if seq.startswith("[") and seq.endswith("~") and ";" in seq:
        return SEQ.get(seq.split(";")[0] + "~", "esc")
    if len(seq) == 1 and seq.isprintable():               # Alt + a letter arrives as ESC + letter
        return "alt-" + seq
    return "esc"


# ---------------------------------------------------------------------- #
# key events: pressed, repeated, let go
# ---------------------------------------------------------------------- #
PRESS, REPEAT, RELEASE = "press", "repeat", "release"
KINDS = {"1": PRESS, "2": REPEAT, "3": RELEASE}
# the kitty keyboard protocol's numbers for keys that are not characters
KITTY = {9: "tab", 13: "enter", 27: "esc", 32: "space", 127: "backspace", 8: "backspace",
         57441: "shift", 57447: "shift", 57442: "ctrl", 57448: "ctrl", 57443: "alt", 57449: "alt",
         57444: "super", 57450: "super", 57399: "0", 57400: "1", 57401: "2", 57402: "3", 57403: "4",
         57404: "5", 57405: "6", 57406: "7", 57407: "8", 57408: "9", 57414: "enter", 57417: "left",
         57418: "right", 57419: "up", 57420: "down", 57421: "pgup", 57422: "pgdn", 57423: "home",
         57424: "end", 57425: "insert", 57426: "delete", 57427: "center"}
KITTY_TILDE = {"2": "insert", "3": "delete", "5": "pgup", "6": "pgdn", "7": "home", "8": "end",
               "15": "f5", "17": "f6", "18": "f7", "19": "f8", "20": "f9", "11": "f1", "12": "f2", "13": "f3",
               "14": "f4"}
KITTY_LETTER = {"A": "up", "B": "down", "C": "right", "D": "left", "H": "home", "F": "end", "E": "center",
                "P": "f1", "Q": "f2", "R": "f3", "S": "f4"}
# Windows virtual-key codes (the console's KEY_EVENT_RECORD)
VK = {0x25: "left", 0x26: "up", 0x27: "right", 0x28: "down", 0x20: "space", 0x0D: "enter", 0x1B: "esc",
      0x08: "backspace", 0x09: "tab", 0x10: "shift", 0xA0: "shift", 0xA1: "shift", 0x11: "ctrl", 0xA2: "ctrl",
      0xA3: "ctrl", 0x12: "alt", 0xA4: "alt", 0xA5: "alt", 0x24: "home", 0x23: "end", 0x21: "pgup",
      0x22: "pgdn", 0x2D: "insert", 0x2E: "delete", 0x0C: "center"}
VK.update({0x70 + i: "f%d" % (i + 1) for i in range(9)})


class KeyEvent:
    """A key ``name`` (as :func:`decode` names it, without modifiers) pressed, repeated or let go (``kind``)."""
    __slots__ = ("name", "kind")

    def __init__(self, name, kind=PRESS):
        self.name, self.kind = name, kind

    def __repr__(self):
        return "KeyEvent(%r, %r)" % (self.name, self.kind)

    def __eq__(self, other):
        return isinstance(other, KeyEvent) and (self.name, self.kind) == (other.name, other.kind)

    def __hash__(self):
        return hash((self.name, self.kind))


def kitty_event(seq):
    """A :class:`KeyEvent` from the characters after ESC of a kitty-protocol key (``"[97;1:3u"``: ``a`` let
    go), or None if it is not one."""
    if not seq.startswith("[") or len(seq) < 2:
        return None
    end = seq[-1]
    body = seq[1:-1]
    parts = body.split(";")
    kind, mods = PRESS, 0
    if len(parts) > 1:
        mod = parts[1].split(":")
        if len(mod) > 1:
            kind = KINDS.get(mod[1], PRESS)
        mods = int(mod[0]) - 1 if mod[0].isdigit() and int(mod[0]) > 0 else 0
    if end == "u":
        try:
            code = int(parts[0].split(":")[0])
        except ValueError:
            return None
        if code in (99, 100) and mods & 4 and kind == PRESS:      # Ctrl+C, Ctrl+D: the protocol sends no ^C
            return KeyEvent("ctrl-c" if code == 99 else "ctrl-d", PRESS)
        name = KITTY.get(code)
        if name is None:
            if 0 <= code < 0x110000 and chr(code).isprintable():
                name = chr(code).lower()
            else:
                return None
        return KeyEvent(name, kind)
    if end in KITTY_LETTER and (not parts[0] or parts[0] == "1"):
        return KeyEvent(KITTY_LETTER[end], kind)
    if end == "~" and parts[0] in KITTY_TILDE:
        return KeyEvent(KITTY_TILDE[parts[0]], kind)
    return None


def vk_name(vk, char):
    """The name of a key from a Windows virtual-key code and the character it types."""
    if vk in VK:
        return VK[vk]
    if 0x41 <= vk <= 0x5A or 0x30 <= vk <= 0x39:
        return chr(vk).lower()
    if char and char.isprintable():
        return char.lower()
    return None


class KeyReader:
    """Keys from the real terminal.  ``start()`` before reading, ``stop()`` after (it restores the terminal).

    ``start(events=True)``: :meth:`events` will be read (a game in real time) - the terminal's way of telling
    presses from releases is turned on if it has one; ``mode`` says which (``"kitty"``, ``"console"``,
    ``"guess"``)."""

    def __init__(self, stream=None, out=None):
        self.win = os.name == "nt"
        self.stream = stream or sys.stdin
        self.out = out or sys.stdout
        self.fd = None
        self.old = None
        self.mode = None
        self.held = set()                                  # console: the keys down now (a down again is a repeat)
        self.pushed = False

    def start(self, events=False):
        self.mode = None
        if self.win:
            if events:
                self.mode = "console" if self._console() is not None else "guess"
            return
        import termios
        self.fd = self.stream.fileno()
        self.old = termios.tcgetattr(self.fd)
        new = termios.tcgetattr(self.fd)
        new[3] &= ~(termios.ICANON | termios.ECHO)
        new[6][termios.VMIN], new[6][termios.VTIME] = 1, 0
        termios.tcsetattr(self.fd, termios.TCSANOW, new)
        if events:
            self.mode = "kitty" if self._kitty() else "guess"

    def stop(self):
        if self.pushed:
            self.pushed = False
            try:
                self.out.write("\x1b[<u")                    # the terminal's keys as they were
                self.out.flush()
            except Exception:
                pass
        self.held = set()
        if self.old is not None:
            import termios
            try:
                termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old)
            finally:
                self.old = None

    def _kitty(self):
        """Ask the terminal whether it speaks the kitty keyboard protocol (its flags, then the device
        attributes every terminal answers); if it does, ask for every key's press, repeat and release."""
        import re
        import select
        try:
            self.out.write("\x1b[?u\x1b[c")
            self.out.flush()
        except Exception:
            return False
        got, end = b"", time.monotonic() + 0.25
        while time.monotonic() < end and not re.search(rb"\x1b\[\?[\d;]*c", got):
            if not select.select([self.fd], [], [], max(0.0, end - time.monotonic()))[0]:
                break
            got += os.read(self.fd, 64)
        if not re.search(rb"\x1b\[\?\d*u", got):
            return False
        self.out.write("\x1b[>11u")                         # 1 + 2 + 8: unambiguous, event types, every key
        self.out.flush()
        self.pushed = True
        return True

    def get(self, timeout):
        """The next key's name, or None if none came within ``timeout`` seconds."""
        return self._win(timeout) if self.win else self._posix(timeout)

    def events(self, timeout):
        """Key events: those waiting, or the first to come within ``timeout`` seconds (an empty list if none)."""
        if self.mode == "console":
            got = self._console_events(timeout)
            if got is not None:
                return got
            self.mode = "guess"
        if self.mode == "kitty":
            return self._kitty_events(timeout)
        out = []
        k = self.get(timeout)
        while k is not None and len(out) < 64:
            out.append(KeyEvent(k, PRESS))
            k = self.get(0)
        return out

    def _kitty_events(self, timeout):
        import select
        out = []
        wait = timeout
        while len(out) < 64:
            if not select.select([self.fd], [], [], wait)[0]:
                break
            wait = 0
            b = os.read(self.fd, 1)
            if b != b"\x1b":
                ch = b.decode("latin-1")
                out.append(KeyEvent(CTRL.get(ch, ch).lower() if len(ch) == 1 else ch, PRESS))
                continue
            seq = b""
            while select.select([self.fd], [], [], 0.03)[0]:
                seq += os.read(self.fd, 1)
                if len(seq) >= 2 and (seq[-1:].isalpha() or seq[-1:] == b"~"):
                    break
                if len(seq) > 32:
                    break
            text = seq.decode("latin-1")
            ev = kitty_event(text)
            if ev is not None and ev.name == "ctrl-c":
                raise KeyboardInterrupt
            if ev is None and text.startswith("[<"):
                name = decode(text)
                ev = KeyEvent(name, PRESS) if name != "esc" else None
            elif ev is None:
                name = decode(text)
                if name != "esc" or not text:
                    ev = KeyEvent(name.split("-")[-1] if "-" in name and len(name) > 2 else name, PRESS)
            if ev is not None:
                out.append(ev)
        return out

    def _console(self):
        """The Windows console's input handle, or None."""
        try:
            import ctypes
            k32 = ctypes.windll.kernel32
            h = k32.GetStdHandle(-10)                      # STD_INPUT_HANDLE
            n = ctypes.c_ulong(0)
            if not h or not k32.GetNumberOfConsoleInputEvents(h, ctypes.byref(n)):
                return None
            return h
        except Exception:
            return None

    def _console_events(self, timeout):
        """Key downs and ups from the Windows console (None if it cannot be read)."""
        try:
            import ctypes
            from ctypes import wintypes

            class KEY(ctypes.Structure):
                _fields_ = [("down", wintypes.BOOL), ("repeat", wintypes.WORD), ("vk", wintypes.WORD),
                            ("scan", wintypes.WORD), ("char", wintypes.WCHAR), ("state", wintypes.DWORD)]

            class EVENT(ctypes.Union):
                _fields_ = [("key", KEY), ("pad", ctypes.c_byte * 16)]

            class RECORD(ctypes.Structure):
                _fields_ = [("type", wintypes.WORD), ("event", EVENT)]

            k32 = ctypes.windll.kernel32
            h = self._console()
            if h is None:
                return None
            if k32.WaitForSingleObject(h, int(max(0.0, timeout) * 1000)) != 0:
                return []
            n = ctypes.c_ulong(0)
            k32.GetNumberOfConsoleInputEvents(h, ctypes.byref(n))
            if not n.value:
                return []
            buf = (RECORD * min(64, n.value))()
            got = ctypes.c_ulong(0)
            if not k32.ReadConsoleInputW(h, buf, len(buf), ctypes.byref(got)):
                return None
            out = []
            for rec in buf[:got.value]:
                if rec.type != 1:                          # KEY_EVENT
                    continue
                key = rec.event.key
                name = vk_name(key.vk, key.char)
                if name is None:
                    continue
                if key.down:
                    if name == "c" and key.state & 0x0C:      # Ctrl+C
                        raise KeyboardInterrupt
                    out.append(KeyEvent(name, REPEAT if name in self.held else PRESS))
                    self.held.add(name)
                else:
                    self.held.discard(name)
                    out.append(KeyEvent(name, RELEASE))
            return out
        except KeyboardInterrupt:
            raise
        except Exception:
            return None

    def drain(self):
        """All keys pressed meanwhile, in order (without waiting)."""
        keys = []
        while len(keys) < 256:
            k = self.get(0)
            if k is None:
                break
            keys.append(k)
        return keys

    # ------------------------------------------------------------------ #
    def _posix(self, timeout):
        import select
        if not select.select([self.fd], [], [], timeout)[0]:
            return None
        b = os.read(self.fd, 1)
        if not b:
            return "ctrl-d"
        if b == b"\x1b":
            seq = b""
            while select.select([self.fd], [], [], 0.03)[0]:
                seq += os.read(self.fd, 1)
                if seq.startswith(b"[<"):                  # a mouse report: up to its M or m
                    if seq[-1:] in (b"M", b"m") or len(seq) > 24:
                        break
                    continue
                if (len(seq) >= 2 and (seq[-1:].isalpha() or seq[-1:] == b"~")) or len(seq) > 7 \
                        or (len(seq) == 1 and seq not in (b"[", b"O")):
                    break
            return decode(seq.decode("latin-1"))
        if b[0] >= 0xC0:                                   # a character of more than one byte
            more = 1 if b[0] < 0xE0 else 2 if b[0] < 0xF0 else 3
            b += os.read(self.fd, more)
            return b.decode("utf-8", "replace")
        ch = b.decode("latin-1")
        return CTRL.get(ch, ch)

    def _win(self, timeout):
        import msvcrt
        end = time.time() + timeout
        while not msvcrt.kbhit():
            if time.time() >= end:
                return None
            time.sleep(0.01)
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            return WIN.get(msvcrt.getwch())
        if ch == "\x03":
            raise KeyboardInterrupt
        if ch == "\x1a":
            return "ctrl-d"
        return CTRL.get(ch, ch)


class ScriptedKeys:
    """Keys from a list (tests): the same interface as :class:`KeyReader`.

    When the list is used up it answers Ctrl-D, the end of input, so a test cannot hang. ``None`` in the
    list is a wait in which no key came."""

    mode = "guess"

    def __init__(self, keys=(), mode="guess", clock=None):
        self.keys = list(keys)
        self.mode = mode
        self.clock = clock                                 # a FakeClock: each entry takes the time a read waits

    def start(self, events=False):
        pass

    def stop(self):
        pass

    def get(self, timeout):
        k = self.keys.pop(0) if self.keys else "ctrl-d"
        if self.clock is not None:
            self.clock.advance(timeout)
        return k.name if isinstance(k, KeyEvent) else k

    def events(self, timeout):
        """The next entry: a key event (a name is a press), a list of them, or None - nothing came in time.
        With a ``clock``, each entry takes the time asked for."""
        if self.clock is not None:
            self.clock.advance(timeout)
        if not self.keys:
            return [KeyEvent("ctrl-d")]
        k = self.keys.pop(0)
        if k is None:
            return []
        if isinstance(k, list):
            return [e if isinstance(e, KeyEvent) else KeyEvent(e) for e in k]
        return [k if isinstance(k, KeyEvent) else KeyEvent(k)]

    def drain(self):
        return []
