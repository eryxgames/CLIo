# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Real time: games that move on whether the player presses a key or not.

A game in real time is stepped ``rate`` times a second (20) by a :class:`Clock`. The game itself
never looks at the clock: each tick it is given what the keys did (:class:`Controls`: the keys held
down, pressed and let go) and moves on by one tick. So what happens depends only on the ticks and the
keys - a run is its keys, tick by tick (the journal) - and played back it comes out the same, on any
machine and at any speed (:func:`replay`).

Held keys: terminals that say when a key is let go (the kitty keyboard protocol; the Windows
console) are believed; elsewhere a key counts as held while its repeats keep coming (:class:`Held`),
which is measured in ticks too, so even the guess plays back the same.

The loop (:class:`Loop`) reads keys while it waits for the next tick, runs the ticks that are due
(at most ``behind`` at once: a slow machine slows the game rather than making it jump), and draws once
after them. A game for the loop has ``step(controls)``, ``draw()`` and ``over`` (true to stop).
"""
from __future__ import annotations

import time

from .keys import PRESS, RELEASE, KeyEvent

RATE = 20                    # ticks a second


class Clock:
    """Ticks at a fixed rate. ``due()`` says how many ticks are owed now; ``until()`` how long to the next."""

    def __init__(self, rate=RATE, now=time.monotonic, behind=5):
        self.rate = float(rate)
        self.dt = 1.0 / self.rate
        self.now = now
        self.behind = max(1, int(behind))        # the most ticks run at once to catch up; any more are let go
        self.next = None
        self.dropped = 0                         # ticks let go because the machine fell behind

    def start(self):
        self.next = self.now()

    def due(self):
        t = self.now()
        if self.next is None:
            self.next = t
        if t < self.next:
            return 0
        n = int((t - self.next) / self.dt) + 1
        if n > self.behind:
            self.dropped += n - self.behind
            self.next += (n - self.behind) * self.dt
            n = self.behind
        self.next += n * self.dt
        return n

    def until(self):
        return max(0.0, (self.next if self.next is not None else self.now()) - self.now())


class FakeClock:
    """Time that only moves when told to (tests): ``now()``, ``sleep(dt)``, ``advance(dt)``."""

    def __init__(self, t=1000.0):
        self.t = float(t)

    def now(self):
        return self.t

    def sleep(self, dt):
        self.t += max(0.0, dt)

    advance = sleep


class Controls:
    """What the keys did in one tick: ``held`` (a frozenset of names), ``pressed`` and ``released`` (in
    order), and the ``tick``; ``events``, the tick's key events as they came (``(name, kind)``: mouse
    clicks are read from these, each one counting)."""
    __slots__ = ("tick", "held", "pressed", "released", "events")

    def __init__(self, tick, held=frozenset(), pressed=(), released=(), events=()):
        self.tick, self.held, self.pressed, self.released = tick, frozenset(held), tuple(pressed), tuple(released)
        self.events = tuple(events)

    def down(self, *names):
        """Whether any of these keys is held (or was pressed this tick)."""
        return any(n in self.held or n in self.pressed for n in names)

    def hit(self, *names):
        """Whether any of these keys went down this tick (a jump, a shot: once a press)."""
        return any(n in self.pressed for n in names)

    def axis(self, minus, plus):
        """-1, 0 or 1: e.g. ``axis(("left", "a"), ("right", "d"))``."""
        minus = (minus,) if isinstance(minus, str) else minus
        plus = (plus,) if isinstance(plus, str) else plus
        return int(self.down(*plus)) - int(self.down(*minus))

    def __repr__(self):
        return "Controls(%d, held=%s, pressed=%s, released=%s)" % (self.tick, sorted(self.held), self.pressed,
                                                                   self.released)


class Held:
    """Which keys are down, tick by tick. ``exact``: the terminal says when a key is let go (kitty, the
    Windows console); a key nothing has been heard of for ``lost`` seconds is let go all the same (the
    window lost the focus). Otherwise a key is held while it keeps repeating: until ``first`` seconds
    after its press (a terminal waits that long before it repeats) and ``gap`` seconds after each repeat."""

    def __init__(self, rate=RATE, exact=False, first=0.5, gap=0.15, lost=1.0):
        self.exact = exact
        self.first = max(1, int(round(first * rate)))
        self.gap = max(1, int(round(gap * rate)))
        self.lost = max(1, int(round(lost * rate)))
        self.keys = {}                           # name -> [tick of the last news of it, times heard]

    def feed(self, tick, events):
        """The events of a tick: :class:`Controls` for it."""
        pressed, released = [], []
        for name in sorted(self.keys):           # keys not heard of for long enough are let go first
            last, n = self.keys[name]
            limit = self.lost if self.exact else (self.first if n == 1 else self.gap)
            if tick - last >= limit:
                del self.keys[name]
                released.append(name)
        for e in events:
            if e.kind == RELEASE:
                if self.keys.pop(e.name, None) is not None:
                    released.append(e.name)
            elif e.name in self.keys:
                k = self.keys[e.name]
                k[0], k[1] = tick, k[1] + 1      # a repeat (or, guessing, a press that is one)
            else:
                self.keys[e.name] = [tick, 1]
                pressed.append(e.name)
                if e.name in released:
                    released.remove(e.name)      # let go and pressed again in one tick: still down
        return Controls(tick, self.keys, pressed, released)


class Recorder:
    """Turns key events into :class:`Controls`, a tick at a time, and keeps the journal: ``[[tick,
    [[name, kind], ...]], ...]`` for the ticks that had events (with ``mode``, how keys were read)."""

    def __init__(self, rate=RATE, exact=False):
        self.rate = rate
        self.held = Held(rate, exact)
        self.tick = 0
        self.journal = []

    def next(self, events=()):
        events = list(events)
        if events:
            self.journal.append([self.tick, [[e.name, e.kind] for e in events]])
        c = self.held.feed(self.tick, events)
        c.events = tuple((e.name, e.kind) for e in events)
        self.tick += 1
        return c


def replay(game, journal, rate=RATE, exact=False, ticks=None):
    """Play a journal back on ``game`` (``step(controls)``, ``over``): the same keys at the same ticks. It
    runs to the journal's last tick (and ``ticks`` more), or until the game is over. The Recorder used."""
    rec = Recorder(rate, exact)
    by_tick = {int(t): [KeyEvent(n, k) for n, k in evs] for t, evs in journal}
    last = max(by_tick) if by_tick else -1
    end = last + 1 + (ticks or 0)
    while rec.tick < end and not game.over:
        game.step(rec.next(by_tick.get(rec.tick, ())))
    return rec


class Pointer:
    """Taps and clicks as keys: parts of the picture that stand for a key.

    ``hits``: ``[(x0, y0, x1, y1, key), ...]`` in cells of the screen, set by who draws it. A press on
    one is a press of its key, and the key stays down until the finger (the button) is let go - so a
    thing that has to be held can be held. A press anywhere else is nothing. What a game sees, and
    what its journal keeps, are keys."""

    def __init__(self):
        self.hits = []
        self.down = None                         # the key a finger is on now

    def key_at(self, x, y):
        for x0, y0, x1, y1, key in self.hits:
            if x0 <= x < x1 and y0 <= y < y1:
                return key
        return None

    def turn(self, events):
        """Key events with the mouse reports among them made keys (those on nothing are dropped)."""
        out = []
        for e in events:
            name = e.name
            if not name.startswith(("mouse:", "mouseup:")):
                out.append(e)
                continue
            try:
                kind, b, x, y = name.split(":")
                b, x, y = int(b), int(x), int(y)
            except ValueError:
                continue
            if kind == "mouseup" or e.kind == RELEASE:
                if self.down is not None:
                    out.append(KeyEvent(self.down, RELEASE))
                    self.down = None
            elif not b & 64 and not b & 32 and not b & 3:        # the first button going down: not the wheel, not a drag
                key = self.key_at(x, y)
                if key is not None:
                    if self.down is not None and self.down != key:
                        out.append(KeyEvent(self.down, RELEASE))
                    self.down = key
                    out.append(KeyEvent(key))
        return out

    def held(self):
        """Once a tick: the key under the finger said again, as a key that is held down repeats."""
        return [KeyEvent(self.down)] if self.down is not None else []


class Loop:
    """A game in real time: keys in, ticks at a fixed rate, a picture after them.

    ``game``: ``step(controls)``, ``draw()``, ``over``. ``keys``: a :class:`engine.keys.KeyReader` (or
    ``ScriptedKeys``). ``clock``: a :class:`Clock` (its ``now`` may be a :class:`FakeClock`'s).

    ``menu``: a function called with the loop when a key is pressed that the game says pauses it now
    (``game.pause_key(name)``): time stands while it runs - no tick is owed for it, the key is not
    given to the game and is not in the journal, so a journal plays back the same with or without the
    stops. A game with a ``pointer`` (a :class:`Pointer`) gets its taps as keys."""

    def __init__(self, game, keys, rate=RATE, clock=None, behind=5, menu=None):
        self.game, self.keys = game, keys
        self.clock = clock or Clock(rate, behind=behind)
        self.rate = rate
        self.recorder = None
        self.mode = None
        self.menu = menu
        self.stops = 0                           # times the menu was opened

    def _read(self, timeout):
        events = self.keys.events(timeout)
        pointer = getattr(self.game, "pointer", None)
        return pointer.turn(events) if pointer is not None and events else events

    def _stopped(self, pending):
        """The menu, if a key just pressed asks for it: True when it was shown (the keys so far are let go)."""
        asks = getattr(self.game, "pause_key", None)
        if self.menu is None or asks is None or not pending:
            return False
        if not any(e.kind == PRESS and asks(e.name) for e in pending):
            return False
        keys, pointer = self.keys, getattr(self.game, "pointer", None)
        if pointer is not None:
            pointer.down = None
        self.stops += 1
        keys.stop()
        keys.start(events=False)                 # the menu reads keys one by one
        try:
            self.menu(self)
        finally:
            keys.stop()
            keys.start(events=True)
            self.clock.start()                   # no tick is owed for the time it was open
        return True

    def run(self):
        g, keys, clock = self.game, self.keys, self.clock
        keys.start(events=True)
        self.mode = getattr(keys, "mode", None) or "guess"
        self.recorder = rec = Recorder(self.rate, exact=self.mode in ("kitty", "console"))
        pending = []
        clock.start()
        pointer = getattr(g, "pointer", None)
        try:
            g.draw()
            while not g.over:
                n = clock.due()
                if n == 0:
                    pending.extend(self._read(min(0.05, clock.until())))
                    continue
                pending.extend(self._read(0))
                if self._stopped(pending):
                    pending = []
                    if not g.over:
                        g.draw()
                    continue
                if pointer is not None:
                    pending.extend(pointer.held())
                for i in range(n):
                    g.step(rec.next(pending if i == 0 else ()))
                    if i == 0:
                        pending = []
                    if g.over:
                        break
                g.draw()
        finally:
            keys.stop()
        return rec


class KeyTest:
    """``clio.py --keys``: what this terminal tells a game in real time - how keys are read, which are held
    down now, the last events. Esc or q ends it."""

    def __init__(self, out, rate=RATE):
        self.out, self.rate = out, rate
        self.over = False
        self.held = frozenset()
        self.log = []
        self.tick = 0
        self.mode = "?"

    def step(self, c):
        self.tick = c.tick
        self.held = c.held
        for n in c.pressed:
            self.log.append("+%s" % n)
        for n in c.released:
            self.log.append("-%s" % n)
        self.log = self.log[-12:]
        if c.hit("esc", "q", "ctrl-d"):
            self.over = True

    def draw(self):
        lines = ["CLIo keys in real time  (Esc or q: done)", "",
                 "keys read by: %s" % {"kitty": "the kitty keyboard protocol - presses and releases",
                                       "console": "the Windows console - presses and releases",
                                       "guess": "plain keys - held is guessed from the repeats"}.get(self.mode, self.mode),
                 "tick %d (%d a second)" % (self.tick, int(self.rate)), "",
                 "held: " + (" ".join(sorted(self.held)) or "-"), "",
                 "last: " + " ".join(self.log)]
        self.out.write("\x1b[H" + "".join("\x1b[2K%s\r\n" % l for l in lines))
        self.out.flush()


def key_test(out=None, keys=None, rate=RATE, clock=None):
    """Run :class:`KeyTest` on the terminal (its own screen; the old one comes back after)."""
    import sys
    from .keys import KeyReader
    out = out or sys.stdout
    keys = keys or KeyReader()
    t = KeyTest(out, rate)
    loop = Loop(t, keys, rate, clock=clock)
    out.write("\x1b[?1049h\x1b[2J\x1b[?25l")
    out.flush()
    try:
        keys_start = keys.start

        def start(events=True):                  # learn how the keys are read before the first picture
            keys_start(events=events)
            t.mode = getattr(keys, "mode", None) or "guess"
        keys.start = start
        try:
            loop.run()
        except KeyboardInterrupt:
            pass
    finally:
        out.write("\x1b[0m\x1b[?25h\x1b[?1049l")
        out.flush()
    return t
