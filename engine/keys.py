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
    """The name of a key from the characters after ESC (``"[A"`` -> ``"up"``); ``"esc"`` if unknown."""
    if not seq:
        return "esc"
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


class KeyReader:
    """Keys from the real terminal.  ``start()`` before reading, ``stop()`` after (it restores the terminal)."""

    def __init__(self, stream=None):
        self.win = os.name == "nt"
        self.stream = stream or sys.stdin
        self.fd = None
        self.old = None

    def start(self):
        if self.win:
            return
        import termios
        self.fd = self.stream.fileno()
        self.old = termios.tcgetattr(self.fd)
        new = termios.tcgetattr(self.fd)
        new[3] &= ~(termios.ICANON | termios.ECHO)
        new[6][termios.VMIN], new[6][termios.VTIME] = 1, 0
        termios.tcsetattr(self.fd, termios.TCSANOW, new)

    def stop(self):
        if self.old is not None:
            import termios
            try:
                termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old)
            finally:
                self.old = None

    def get(self, timeout):
        """The next key's name, or None if none came within ``timeout`` seconds."""
        return self._win(timeout) if self.win else self._posix(timeout)

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

    When the list is used up it answers Ctrl-D, the end of input, so a test cannot hang."""

    def __init__(self, keys=()):
        self.keys = list(keys)

    def start(self):
        pass

    def stop(self):
        pass

    def get(self, timeout):
        return self.keys.pop(0) if self.keys else "ctrl-d"

    def drain(self):
        return []
