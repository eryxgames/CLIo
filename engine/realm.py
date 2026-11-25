# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Realms: turn-based strategy as data - a hold and its people, a season at a time.

A realm (``realms.json``) is stocks, people set to works, a calendar whose tides are told ahead,
events with choices, and threats that show themselves before they come::

    "calendar": {"seasons": ["Sowing", "High Sun", "Reaping", "Frost"], "length": 16},
    "stocks": {"food": {"start": 12, "max": "20 + 20 * granary"}, "stone": 6},
    "people": {"start": 5, "eats": {"food": 1}, "growth": "0.34 if food > people * 2 else 0", "room": "3 * huts"},
    "works": {"fields": {"start": 1, "cost": {"stone": 4}, "hands": 3, "yields": {"food": "2 - frost"}}},
    "threats": {"wolves": {"if": "frost", "chance": 0.5, "strength": "2 + turn / 4", "against": "watch"}}

A season: the player sets hands to works and gives the season's orders (build, find), then ends it -
works yield, people eat and grow, threats that were sighted arrive, events fire, new threats are
sighted. Every number may be a formula (the simulators' formulas: numbers, + - * /, comparisons,
``a if c else b``, min, max...) over the stocks, the works (how many) and ``<work>_hands``, ``people``,
``idle``, ``turn``, ``year``, ``left``, ``tide``, the season's and the tide's names (1 or 0), flags, and
the realm's own ``values``.

Nothing is left to the clock or to the order of a dictionary: every roll comes from the game's seed,
the realm, the season and what is rolled for, so the same orders play the same years, and the sky can
be read ahead. The state is plain numbers and lists: it is saved with the game.

    python -m engine.realm GAME [REALM] [SEEDS]   # a steward plays each realm: stands or falls, the score
"""

from __future__ import annotations

import copy
import hashlib
import math

from .sim import FormulaError, formula

RESERVED = ("people", "idle", "busy", "turn", "season", "year", "left", "length", "tide", "works")
ORDERS = {"build": 1, "find": 1}
ODDS = ((0.95, "sure to hold"), (0.7, "likely to hold"), (0.4, "it could go either way"),
        (0.1, "unlikely to hold"), (-1.0, "no hope of holding"))
HELP = ("{key}end{/} the season {hint}(e){/} " "{key}build{/} [work] " "{key}find{/} [finding] "
        "{key}put{/} N work {hint}(hands to a work){/} " "{key}works{/} " "{key}sky{/} " "{key}news{/} "
        "{key}steward{/} [N] {hint}(the steward plays N seasons){/} " "{key}save{/} " "{key}load{/} "
        "{key}menu{/} " "{key}quit{/}")


def name_of(text):
    """A name as a formula reads it: lower case, anything else an underscore."""
    out = "".join(c if c.isalnum() else "_" for c in str(text).lower()).strip("_")
    return out if out and not out[0].isdigit() else "_" + out


def number(x):
    """A number as a person reads it: whole when it is whole, else one decimal."""
    x = float(x)
    if abs(x - round(x)) < 0.05:
        return "%d" % int(round(x))
    return "%.1f" % x


def as_list(x):
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


class Realm:
    """One realm: its rules (``spec``, never changed) and its state (a plain dict, saved with the game)."""

    def __init__(self, spec, rid="realm", seed=1, state=None, formulas=None, sky=None):
        self.spec = spec if isinstance(spec, dict) else {}
        self.rid = rid
        self.seed = int(seed or 0)
        cal = self.spec.get("calendar") or {}
        self.seasons = [str(s) for s in (cal.get("seasons") or ["Spring", "Summer", "Autumn", "Winter"])]
        self.length = int(cal.get("length") or 0)
        self.calendar = cal
        tides = self.spec.get("tides") or {}
        self.tides = tides
        self.levels = [str(s) for s in (tides.get("levels") or [])]
        self.stocks = {k: (dict(v) if isinstance(v, dict) else {"start": v})
                       for k, v in (self.spec.get("stocks") or {}).items()}
        self.works = {k: v for k, v in (self.spec.get("works") or {}).items() if isinstance(v, dict)}
        self.values = {k: (dict(v) if isinstance(v, dict) else {"formula": v})
                       for k, v in (self.spec.get("values") or {}).items()}
        self.folk = self.spec.get("people") if isinstance(self.spec.get("people"), dict) else {}
        self.events = [e for e in as_list(self.spec.get("events")) if isinstance(e, dict)]
        self.threats = {k: v for k, v in (self.spec.get("threats") or {}).items() if isinstance(v, dict)}
        self.orders = dict(ORDERS, **(self.spec.get("orders") or {}))
        self._f = formulas if formulas is not None else {}
        self._sky = sky if sky is not None else {}       # the tides worked out so far, by season
        self.season_names = [name_of(x) for x in self.seasons]
        self.level_names = [name_of(x) for x in self.levels]
        self.outbox = []                                 # effects for the game that holds the realm
        self.state = state if state else self.fresh()

    # ------------------------------------------------------------------ #
    # state
    # ------------------------------------------------------------------ #
    def fresh(self):
        people = int(self.folk.get("start", 4))
        state = {"turn": 0, "stocks": {k: float(v.get("start", 0)) for k, v in self.stocks.items()},
                 "people": people, "grown": 0.0,
                 "works": {k: int(w.get("start", 0)) for k, w in self.works.items()},
                 "hands": {k: 0 for k in self.works}, "flags": [], "fired": [], "coming": [],
                 "used": {}, "news": [], "result": None, "why": "", "salt": 0}
        left = people
        for k, w in self.works.items():                  # the hands a work starts with
            n = min(left, int(w.get("staff", 0)), state["works"][k] * int(w.get("hands", 0)))
            state["hands"][k] = max(0, n)
            left -= max(0, n)
        return state

    def clone(self, blind=0):
        """A copy to try things on. ``blind`` (1, 2...): its luck is not the luck that is coming."""
        c = Realm(self.spec, self.rid, self.seed, copy.deepcopy(self.state), self._f, self._sky)
        if blind:
            c.state["salt"] = int(c.state.get("salt", 0)) + int(blind)
        return c

    def f(self, text):
        fn = self._f.get(text) if isinstance(text, (str, int, float)) else None
        if fn is None:
            try:
                fn = formula(text)
            except FormulaError:
                fn = formula(0)
            if isinstance(text, (str, int, float)):
                self._f[text] = fn
        return fn

    def roll(self, *what):
        """A number from 0 to 1 that depends on the seed, the realm and what it is for, and nothing else."""
        key = repr((self.seed, self.rid, self.state.get("salt", 0)) + what).encode("utf-8")
        return int.from_bytes(hashlib.sha256(key).digest()[:7], "big") / float(1 << 56)

    # ------------------------------------------------------------------ #
    # the calendar and the sky
    # ------------------------------------------------------------------ #
    @property
    def turn(self):
        return int(self.state["turn"])

    def season_index(self, turn=None):
        turn = self.turn if turn is None else turn
        return (turn + int(self.calendar.get("start_season", 0))) % len(self.seasons)

    def season(self, turn=None):
        return self.seasons[self.season_index(turn)]

    def year(self, turn=None):
        turn = self.turn if turn is None else turn
        first = int(self.calendar.get("start_season", 0))
        return int(self.calendar.get("start_year", 1)) + (turn + first) // len(self.seasons)

    def date(self, turn=None):
        return "%s %d, %s" % (self.calendar.get("year", "Year"), self.year(turn), self.season(turn))

    def tide(self, turn=None):
        """The tide of a season (an index into its levels): the same for a seed whoever asks, and whenever."""
        if not self.levels:
            return 0
        turn = self.turn if turn is None else turn
        if turn in self._sky:
            return self._sky[turn]
        weights = [max(0.0, float(x)) for x in (self.tides.get("weights") or [1] * len(self.levels))]
        weights = (weights + [1.0] * len(self.levels))[:len(self.levels)]
        key = repr((self.seed, self.rid, "tide", turn)).encode("utf-8")
        d = hashlib.sha256(key).digest()
        a = int.from_bytes(d[:7], "big") / float(1 << 56)
        b = int.from_bytes(d[7:14], "big") / float(1 << 56)
        at, idx = a * (sum(weights) or 1.0), 0
        for i, wgt in enumerate(weights):
            idx = i
            if at < wgt:
                break
            at -= wgt
        lift = float((self.tides.get("by_season") or {}).get(self.season(turn), 0))
        if self.length:
            lift += float(self.tides.get("rise", 0)) * min(1.0, turn / float(self.length))
        whole = math.floor(lift)
        idx += int(whole) + (1 if b < lift - whole else 0)
        self._sky[turn] = max(0, min(len(self.levels) - 1, idx))
        return self._sky[turn]

    def forecast(self):
        """The tides that can be read ahead: this season's and the next ``forecast`` (2; a formula may say)."""
        if not self.levels:
            return []
        n = max(0, int(self.f(self.tides.get("forecast", 2))(self.env()) + 1e-9))
        return [self.levels[self.tide(self.turn + i)] for i in range(n + 1)
                if not self.length or self.turn + i < self.length or i == 0]

    # ------------------------------------------------------------------ #
    # names and numbers
    # ------------------------------------------------------------------ #
    def env(self):
        s = self.state
        e = {k: float(v) for k, v in s["stocks"].items()}
        busy = built = 0
        for k, w in self.works.items():
            n = s["works"].get(k, 0)
            h = s["hands"].get(k, 0)
            e[k] = float(n)
            e[k + "_hands"] = float(h)
            busy += h
            built += 0 if w.get("finding") else n
        season, tide = self.season_index(), self.tide()
        e.update(people=float(s["people"]), busy=float(busy), idle=float(s["people"] - busy), turn=float(s["turn"]),
                 season=float(season), year=float(self.year()), length=float(self.length),
                 left=float(max(0, self.length - s["turn"])), tide=float(tide), works=float(built))
        for i, name in enumerate(self.season_names):
            e[name] = 1.0 if i == season else 0.0
        for i, name in enumerate(self.level_names):
            e[name] = 1.0 if i == tide else 0.0
        for k in s["flags"]:
            e[k] = 1.0
        for k, v in self.values.items():
            e[k] = self.f(v.get("formula", 0))(e)
        return e

    def names(self):
        """Every name a formula of this realm may read."""
        out = set(RESERVED) | set(self.stocks) | set(self.works) | {k + "_hands" for k in self.works}
        out |= {name_of(s) for s in self.seasons} | {name_of(s) for s in self.levels} | set(self.values)
        out |= set(self.flag_names())
        return out

    def flag_names(self):
        found = set(as_list(self.spec.get("flags")))

        def walk(effects):
            for eff in as_list(effects):
                if not isinstance(eff, dict):
                    continue
                for k in ("set", "clear"):
                    found.update(str(x) for x in as_list(eff.get(k)))
                for k in ("then", "else"):
                    walk(eff.get(k))
                for branch in as_list(eff.get("random")):
                    walk(branch)
        for ev in self.events:
            walk(ev.get("do"))
            for ch in as_list(ev.get("choices")):
                if isinstance(ch, dict):
                    walk(ch.get("do"))
        for t in self.threats.values():
            walk(t.get("on_held"))
            walk(t.get("on_lost"))
        for w in self.works.values():
            walk(w.get("on_built"))
        return found

    def label(self, key):
        for table in (self.stocks, self.works, self.values, self.threats):
            if key in table:
                return str(table[key].get("name") or key.replace("_", " ").capitalize())
        return key.replace("_", " ").capitalize()

    def slots(self, wid):
        return self.state["works"].get(wid, 0) * int(self.works[wid].get("hands", 0))

    def idle(self):
        return self.state["people"] - sum(self.state["hands"].values())

    def room(self, e=None):
        if "room" not in self.folk:
            return None
        return int(math.floor(self.f(self.folk["room"])(e or self.env()) + 1e-9))

    def bounds(self, sid, e):
        sp = self.stocks[sid]
        lo = self.f(sp.get("min", 0))(e)
        hi = self.f(sp["max"])(e) if "max" in sp else None
        return lo, hi

    def flows(self, e=None):
        """What each stock gains this season as things stand - before luck has its say."""
        e = e or self.env()
        s = self.state
        d = {k: 0.0 for k in self.stocks}

        def add(stock, amount):
            if stock in d:
                d[stock] += amount
        for k, w in self.works.items():
            n, h = s["works"].get(k, 0), s["hands"].get(k, 0)
            for stock, text in (w.get("yields") or {}).items():
                add(stock, h * self.f(text)(e))
            for stock, text in (w.get("makes") or {}).items():
                add(stock, n * self.f(text)(e))
            for stock, text in (w.get("upkeep") or {}).items():
                add(stock, -n * self.f(text)(e))
        for k, sp in self.stocks.items():
            if "rate" in sp:
                add(k, self.f(sp["rate"])(e))
        for stock, text in (self.folk.get("eats") or {}).items():
            add(stock, -s["people"] * self.f(text)(e))
        return d

    def score(self, e=None):
        e = e or self.env()
        if self.spec.get("score") is not None:
            return self.f(self.spec["score"])(e)
        return self.state["people"] * 10 + sum(self.state["stocks"].values())

    def worth(self):
        """How well it stands, for the steward: the score, and far less when it has fallen."""
        if self.state["result"] == "lost":
            return -1e6 + self.turn * 100
        return self.score() + (1e4 if self.state["result"] == "won" else 0)

    def exposure(self):
        """What the threats would cost as things stand, for the steward: for each one that is coming, or
        may be sighted (by its chance; half of it out of its season), what its breaking in would take
        from the score, by how far the defence falls short of it."""
        s = self.state
        if s["result"]:
            return 0.0
        e = self.env()
        base = self.score(e)
        coming = {c["id"]: c for c in s["coming"]}
        total = 0.0
        for tid, t in self.threats.items():
            if tid in coming:
                likely, strength = 1.0, float(coming[tid]["strength"])
            elif t.get("called"):
                continue
            else:
                likely = max(0.0, min(1.0, self.f(t.get("chance", 1))(e)))
                if "if" in t and not self.f(t["if"])(e):
                    likely *= 0.5
                strength = max(1.0, self.f(t.get("strength", 1))(e))
            short = max(0.0, min(1.0, 1.25 - self.defence(tid, e) / strength))
            if short <= 0 or likely <= 0:
                continue
            c = self.clone()
            c.do(t.get("on_lost"), [])
            fail = self.spec.get("fail_if")
            if c.state["people"] <= 0 or (fail is not None and self.f(fail)(c.env())):
                loss = abs(base) + 100.0
            else:
                loss = max(0.0, base - c.score())
            total += likely * short * loss
        return total

    def means(self):
        """What is in store towards the works that could be built, for the steward: each stock counts
        up to the most that one of them costs."""
        if self.state["result"]:
            return 0.0
        e = self.env()
        need = {}
        for wid, _why in self.open_works(None, e, orders=False):
            for k, n in self.cost(wid, e).items():
                need[k] = max(need.get(k, 0), n)
        return sum(min(self.state["stocks"].get(k, 0), n) for k, n in need.items())

    # ------------------------------------------------------------------ #
    # orders
    # ------------------------------------------------------------------ #
    def kind(self, wid):
        return "find" if self.works[wid].get("finding") else "build"

    def orders_left(self, kind):
        return int(self.orders.get(kind, 1)) - int(self.state["used"].get(kind, 0))

    def most(self, wid, e=None):
        w = self.works[wid]
        if w.get("finding"):
            return 1
        if "max" not in w:
            return None
        return int(math.floor(self.f(w["max"])(e or self.env()) + 1e-9))

    def cost(self, wid, e=None):
        w = self.works[wid]
        dearer = 1.0 + float(w.get("dearer", 0)) * self.state["works"].get(wid, 0)
        e = e or self.env()
        return {k: math.ceil(self.f(v)(e) * dearer - 1e-9) for k, v in (w.get("cost") or {}).items()}

    def why_not(self, wid, e=None, orders=True):
        """Why a work cannot be built now ('' when it can). ``orders``: count the season's orders too."""
        if wid not in self.works:
            return "There is no such work."
        e = e or self.env()
        w = self.works[wid]
        kind = self.kind(wid)
        most = self.most(wid, e)
        if most is not None and self.state["works"].get(wid, 0) >= most:
            return "It is known already." if w.get("finding") else "There is no room for another."
        if "needs" in w and not self.f(w["needs"])(e):
            return str(w.get("needs_text") or "It cannot be done yet.")
        if orders and self.orders_left(kind) <= 0:
            return "This season's order to %s is given already." % kind
        short = ["%s %s" % (number(n - self.state["stocks"].get(k, 0)), self.label(k).lower())
                 for k, n in self.cost(wid, e).items() if self.state["stocks"].get(k, 0) < n]
        if short:
            return "It wants %s more." % " and ".join(short)
        return ""

    def open_works(self, kind=None, e=None, orders=True):
        """The works that could be built this season if they could be paid for: ``[(id, why not)]``."""
        e = e or self.env()
        out = []
        for wid, w in self.works.items():
            if kind and self.kind(wid) != kind:
                continue
            most = self.most(wid, e)
            if most is not None and self.state["works"].get(wid, 0) >= most:
                continue
            if "needs" in w and not self.f(w["needs"])(e):
                continue
            out.append((wid, self.why_not(wid, e, orders)))
        return out

    def build(self, wid):
        """Build a work (or make a finding). Returns ``(done, what to say)``."""
        why = self.why_not(wid)
        if why:
            return False, why
        w = self.works[wid]
        for k, n in self.cost(wid).items():
            self.state["stocks"][k] -= n
        self.state["works"][wid] = self.state["works"].get(wid, 0) + 1
        self.state["used"][self.kind(wid)] = self.state["used"].get(self.kind(wid), 0) + 1
        news = []
        self.do(w.get("on_built"), news)
        said = str(w.get("built_text") or ("%s: known." if w.get("finding") else "%s: built.") % self.label(wid))
        return True, " ".join([said] + [t for t, _ in news])

    def put(self, wid, n):
        """Set a work's hands to ``n``, as far as its places and the idle hands allow."""
        if wid not in self.works:
            return False, "There is no such work."
        n = max(0, int(n))
        have = self.state["hands"].get(wid, 0)
        n = min(n, self.slots(wid), have + self.idle())
        self.state["hands"][wid] = n
        if n == have:
            if not self.slots(wid):
                return False, "%s takes no hands." % self.label(wid)
            return False, "%s keeps %d." % (self.label(wid), n)
        return True, "%s: %d of %d." % (self.label(wid), n, self.slots(wid))

    def find_work(self, text):
        """A work from what was typed: its id, its name, the start of either, or its number in the list."""
        text = " ".join(str(text).lower().split())
        if not text:
            return None
        ids = list(self.works)
        for wid in ids:
            if text in (wid.lower(), self.label(wid).lower(), wid.lower().replace("_", " ")):
                return wid
        for wid in ids:
            if wid.lower().startswith(text) or self.label(wid).lower().startswith(text):
                return wid
        return None

    # ------------------------------------------------------------------ #
    # effects
    # ------------------------------------------------------------------ #
    def do(self, effects, news):
        """Run effects (a dict, or a list of them); what they say goes onto ``news`` as ``(text, role)``."""
        s = self.state
        for eff in as_list(effects):
            if not isinstance(eff, dict) or s["result"]:
                continue
            if "if" in eff and ("then" in eff or "else" in eff):
                self.do(eff.get("then") if self.f(eff["if"])(self.env()) else eff.get("else"), news)
                continue
            for key, val in eff.items():
                if key == "say":
                    news.append((str(val), str(eff.get("role", "default"))))
                elif key == "stock" and isinstance(val, dict):
                    e = self.env()
                    for k, amount in val.items():
                        if k in s["stocks"]:
                            lo, hi = self.bounds(k, e)
                            v = s["stocks"][k] + self.f(amount)(e)
                            s["stocks"][k] = max(lo, v if hi is None else min(hi, v))
                elif key == "people":
                    self.lose_people(-int(round(self.f(val)(self.env()))))
                elif key == "work" and isinstance(val, dict):
                    for k, amount in val.items():
                        if k in s["works"]:
                            s["works"][k] = max(0, s["works"][k] + int(round(self.f(amount)(self.env()))))
                    self.settle_hands()
                elif key == "set":
                    for name in as_list(val):
                        if name not in s["flags"]:
                            s["flags"].append(str(name))
                elif key == "clear":
                    s["flags"] = [x for x in s["flags"] if x not in as_list(val)]
                elif key == "threat":
                    for tid in as_list(val):
                        self.sight(tid, news, self.env())
                elif key == "random":
                    branches = as_list(val)
                    if branches:
                        self.do(branches[int(self.roll("random", s["turn"], len(news), repr(val)[:40]) * len(branches))
                                         % len(branches)], news)
                elif key == "game":
                    self.outbox.append(val)
                elif key in ("win", "lose"):
                    s["result"] = "won" if key == "win" else "lost"
                    s["why"] = str(val) if isinstance(val, str) else ""

    def lose_people(self, n):
        """``n`` people go (fewer than none: they come)."""
        s = self.state
        s["people"] = max(0, s["people"] - int(n))
        self.settle_hands()

    def settle_hands(self):
        """No work has more hands than places, and no more hands work than there are people."""
        s = self.state
        for k in self.works:
            s["hands"][k] = min(s["hands"].get(k, 0), self.slots(k))
        over = sum(s["hands"].values()) - s["people"]
        for k in reversed(list(self.works)):
            if over <= 0:
                break
            cut = min(over, s["hands"][k])
            s["hands"][k] -= cut
            over -= cut

    # ------------------------------------------------------------------ #
    # threats
    # ------------------------------------------------------------------ #
    def sight(self, tid, news, e):
        t = self.threats.get(tid)
        s = self.state
        if not t or any(c["id"] == tid for c in s["coming"]):
            return
        strength = max(1, int(round(self.f(t.get("strength", 1))(e))))
        warn = max(0, int(t.get("warn", 1)))
        s["coming"].append({"id": tid, "strength": strength, "at": s["turn"] + warn})
        if warn:
            news.append((str(t.get("text") or "%s have been sighted." % self.label(tid)), "warning"))
        else:
            self.arrive(s["coming"][-1], news)

    def defence(self, tid, e=None):
        return self.f(self.threats[tid].get("against", "watch"))(e or self.env())

    def odds(self, coming, e=None):
        """The chance of holding against a threat that is coming, as things stand."""
        t = self.threats[coming["id"]]
        swing = max(1e-6, float(t.get("swing", 0.25)))
        need = float(coming["strength"])
        return max(0.0, min(1.0, (self.defence(coming["id"], e) / need - 1.0 + swing) / (2 * swing)))

    def arrive(self, coming, news):
        s = self.state
        tid = coming["id"]
        t = self.threats[tid]
        s["coming"] = [c for c in s["coming"] if c is not coming]
        swing = float(t.get("swing", 0.25))
        need = coming["strength"] * (1.0 + (self.roll("fight", tid, s["turn"]) * 2 - 1) * swing)
        held = self.defence(tid) >= need
        if held:
            news.append((str(t.get("held_text") or "%s came, and the hold stood." % self.label(tid)), "success"))
            self.do(t.get("on_held"), news)
        else:
            news.append((str(t.get("lost_text") or "%s broke in." % self.label(tid)), "combat"))
            self.do(t.get("on_lost"), news)
        s.setdefault("fought", []).append([tid, 1 if held else 0])

    # ------------------------------------------------------------------ #
    # the season
    # ------------------------------------------------------------------ #
    def end_season(self, choose=None):
        """The season passes. ``choose(realm, event, options)`` answers an event's choices (none: the
        first). Returns the news as ``[(text, role), ...]``."""
        s = self.state
        news = []
        if s["result"]:
            return news
        e = self.env()
        # works yield, people eat
        eats = self.folk.get("eats") or {}
        hunger = 0.0
        for k, delta in self.flows(e).items():
            lo, hi = self.bounds(k, e)
            v = s["stocks"][k] + delta
            if v < lo:
                if k in eats and s["people"]:
                    need = s["people"] * self.f(eats[k])(e)
                    hunger = max(hunger, min(1.0, (lo - v) / need) if need > 0 else 0.0)
                    news.append((str(self.stocks[k].get("short_text") or "There is not enough %s."
                                     % self.label(k).lower()), "warning"))
                v = lo
            s["stocks"][k] = v if hi is None else min(hi, v)
        if hunger > 0:
            gone = min(s["people"], int(math.ceil(s["people"] * hunger * float(self.folk.get("starve", 0.5)) - 1e-9)))
            if gone:
                self.lose_people(gone)
                text = str(self.folk.get("starve_text") or "%d of the people are lost to want.")
                news.append((text % gone if "%d" in text else text, "combat"))
            s["grown"] = min(s["grown"], 0.0)
        elif "growth" in self.folk:
            s["grown"] += self.f(self.folk["growth"])(self.env())
            room = self.room()
            while s["grown"] >= 1.0:
                if room is not None and s["people"] >= room:
                    s["grown"] = 0.99
                    break
                s["grown"] -= 1.0
                s["people"] += 1
                news.append((str(self.folk.get("grow_text") or "The %s grow by one." % self.folk_name()), "success"))
            while s["grown"] <= -1.0 and s["people"] > 0:
                s["grown"] += 1.0
                self.lose_people(1)
                news.append((str(self.folk.get("shrink_text") or "One of the %s leaves." % self.folk_name()),
                             "warning"))
        # threats that were sighted arrive
        for coming in [c for c in s["coming"] if c["at"] <= s["turn"]]:
            if not s["result"]:
                self.arrive(coming, news)
        # events
        fired = 0
        most = int(self.spec.get("events_a_season", 2))
        for i, ev in enumerate(self.events):
            if s["result"] or fired >= most:
                break
            eid = str(ev.get("id") or "event_%d" % i)
            if ev.get("once", True) and eid in s["fired"]:
                continue
            if ev.get("every") and (s["turn"] + 1) % max(1, int(ev["every"])):
                continue
            e = self.env()
            if "if" in ev and not self.f(ev["if"])(e):
                continue
            if self.roll("event", eid, s["turn"]) >= self.f(ev.get("chance", 1))(e):
                continue
            fired += 1
            if ev.get("once", True):
                s["fired"].append(eid)
            if ev.get("text"):
                news.append((str(ev["text"]), str(ev.get("role", "story"))))
            self.do(ev.get("do"), news)
            options = [c for c in as_list(ev.get("choices")) if isinstance(c, dict)
                       and ("if" not in c or self.f(c["if"])(self.env()))]
            if options and not s["result"]:
                pick = choose(self, ev, options, news) if choose else 0
                pick = options[pick if isinstance(pick, int) and 0 <= pick < len(options) else 0]
                if pick.get("say"):
                    news.append((str(pick["say"]), str(pick.get("role", "story"))))
                self.do(pick.get("do"), news)
        # new threats are sighted
        e = self.env()
        for tid, t in self.threats.items():
            if s["result"]:
                break
            if t.get("called") or ("if" in t and not self.f(t["if"])(e)):
                continue
            if self.roll("threat", tid, s["turn"]) < self.f(t.get("chance", 1))(e):
                self.sight(tid, news, e)
        # the year turns
        s["turn"] += 1
        s["used"] = {}
        if not s["result"]:
            e = self.env()
            if s["people"] <= 0:
                s["result"], s["why"] = "lost", str(self.spec.get("empty_text") or "No one is left.")
            elif self.spec.get("fail_if") is not None and self.f(self.spec["fail_if"])(e):
                s["result"], s["why"] = "lost", str(self.spec.get("fail_text") or "")
            elif self.spec.get("win_if") is not None and self.f(self.spec["win_if"])(e):
                s["result"], s["why"] = "won", str(self.spec.get("win_text") or "")
            elif self.length and s["turn"] >= self.length:
                s["result"], s["why"] = "won", str(self.spec.get("end_text") or "")
        s["news"] = [[t, r] for t, r in news][-12:]
        return news

    def folk_name(self):
        return str(self.folk.get("name") or "people")

    def stats(self):
        s = self.state
        return {"result": s["result"], "seasons": s["turn"], "people": s["people"], "score": int(round(self.score())),
                "held": sum(h for _, h in s.get("fought", [])), "lost": sum(1 - h for _, h in s.get("fought", []))}

    def state_hash(self):
        return hashlib.sha256(repr(sorted((k, repr(v)) for k, v in self.state.items() if k != "news"))
                              .encode("utf-8")).hexdigest()[:16]


def make(data, rid, seed=1, state=None):
    return Realm((getattr(data, "realms", None) or {}).get(rid) or {}, rid, seed, state)


# --------------------------------------------------------------------------- #
# The steward: a player that tries things on copies
# --------------------------------------------------------------------------- #
LUCKS = 2                                            # how many kinds of luck the steward tries a thing against
MEANS = 0.5                                          # what a measure in store towards a work is worth to it


def ahead(realm, seasons, lucks=None):
    """What a realm is worth some seasons on, left as it is - with luck that is not the luck to come
    (the mean over a few kinds of it) - less what the threats would cost it as it then stands, and
    with a little for what it has in store towards the works it could build."""
    total = 0.0
    lucks = lucks or LUCKS
    for i in range(lucks):
        c = realm.clone(blind=i + 1)
        for _ in range(seasons):
            if c.state["result"]:
                break
            c.end_season()
        total += c.worth() - c.exposure() + MEANS * c.means()
    return total / lucks


def shift(realm, src, dst):
    """Move one hand from a work (None: an idle one) to another (None: to rest)."""
    h = realm.state["hands"]
    if src is not None:
        h[src] -= 1
    if dst is not None:
        h[dst] += 1


def set_hands(realm, seasons=3, only=None, rounds=None):
    """Move hands one at a time for as long as it makes the seasons ahead better. Returns how many moved."""
    s = realm.state
    best = ahead(realm, seasons)
    moved = 0
    for _ in range(rounds if rounds is not None else s["people"] + 2):
        pick = None
        sources = ([None] if realm.idle() > 0 else []) + [k for k in realm.works if s["hands"].get(k, 0) > 0]
        targets = [k for k in realm.works if s["hands"].get(k, 0) < realm.slots(k) and (only is None or k == only)]
        for src in sources:
            for dst in targets:
                if src == dst:
                    continue
                c = realm.clone()
                shift(c, src, dst)
                v = ahead(c, seasons)
                if v > best + 1e-9:
                    best, pick = v, (src, dst)
        if not pick:
            break
        shift(realm, *pick)
        moved += 1
    return moved


def tend(realm, seasons=None):
    """The steward's season: hands, then the orders. Returns what it did, as a player would type it.
    It looks a year ahead (``seasons``), and a little further before it builds."""
    did = []
    seasons = seasons or max(3, len(realm.seasons))
    set_hands(realm, seasons)
    for kind in ("find", "build"):
        while realm.orders_left(kind) > 0 and not realm.state["result"]:
            best, pick = ahead(realm, seasons + 3), None
            for wid, why in realm.open_works(kind):
                if why:
                    continue
                c = realm.clone()
                c.build(wid)
                set_hands(c, 2, only=wid, rounds=realm.works[wid].get("hands", 0) and 3)
                v = ahead(c, seasons + 3)
                if v > best + 1e-9:
                    best, pick = v, wid
            if not pick:
                break
            realm.build(pick)
            did.append("%s %s" % (kind, pick))
            set_hands(realm, seasons)
    for k in realm.works:
        did.append("put %d %s" % (realm.state["hands"].get(k, 0), k))
    return did


def answer(realm, event, options, news=None):
    """The steward's answer to an event: the choice that leaves the realm best some seasons on."""
    best, pick = None, 0
    for i, opt in enumerate(options):
        c = realm.clone()
        c.do(opt.get("do"), [])
        v = ahead(c, 4)
        if best is None or v > best + 1e-9:
            best, pick = v, i
    return pick


def steward(realm, seasons=None, journal=None):
    """Play a realm to its end (or for some seasons). Returns the realm."""
    n = 0
    while not realm.state["result"] and (seasons is None or n < seasons):
        did = tend(realm)
        if journal is not None:
            journal.append((realm.turn, did))
        realm.end_season(answer)
        n += 1
        if not realm.length and seasons is None and n >= 400:
            break
    return realm


# --------------------------------------------------------------------------- #
# Playing it
# --------------------------------------------------------------------------- #
def delta(x):
    if abs(x) < 0.05:
        return ""
    return " {%s}(%s%s){/}" % ("success" if x > 0 else "warning", "+" if x > 0 else "-", number(abs(x)))


def status_lines(realm):
    """The season's page as ``[(kind, content)]``: rule, text (markup, role), table (rows)."""
    s, e = realm.state, realm.env()
    out = [("rule", "%s  %s" % (realm.spec["name"], realm.date()) if realm.spec.get("name") else realm.date(),
            realm.date())]
    sky = realm.forecast()
    if sky:
        text = "%s: {key}%s{/}" % (realm.tides.get("name", "Tide"), sky[0])
        if len(sky) > 1:
            text += " {hint}then %s{/}" % ", ".join(sky[1:])
        out.append(("text", text, "default"))
    notes = [(realm.calendar.get("notes") or {}).get(realm.season()),
             (realm.tides.get("notes") or {}).get(sky[0]) if sky else None]
    for note in notes:
        if note:
            out.append(("text", str(note), "hint"))
    if realm.length:
        left = realm.length - s["turn"]
        out.append(("text", "%d season%s to go." % (left, "" if left == 1 else "s"), "hint"))
    flows = realm.flows(e)
    bits = []
    for k, sp in realm.stocks.items():
        if sp.get("show", True):
            lo, hi = realm.bounds(k, e)
            cap = "" if hi is None or not sp.get("show_max", True) else "{hint}/%s{/}" % number(hi)
            warn = "warn" in sp and s["stocks"][k] <= realm.f(sp["warn"])(e)
            bits.append("%s {%s}%d{/}%s%s" % (realm.label(k), "warning" if warn else "key",
                                              math.floor(s["stocks"][k] + 1e-9), cap, delta(flows[k])))
    for k, v in realm.values.items():
        if v.get("show"):
            bits.append("%s {key}%s{/}" % (realm.label(k), number(e[k])))
    if bits:
        out.append(("text", ", ".join(bits), "default"))
    room = realm.room(e)
    folk = "%s {key}%d{/}" % (realm.folk_name().capitalize(), s["people"])
    if room is not None:
        folk += "{hint}/%d{/}" % room
    folk += ", idle {%s}%d{/}" % ("warning" if realm.idle() > 0 else "key", realm.idle())
    out.append(("text", folk, "default"))
    rows = []
    for k, w in realm.works.items():
        n = s["works"].get(k, 0)
        if not n or w.get("finding"):
            continue
        hands = "%d/%d" % (s["hands"].get(k, 0), realm.slots(k)) if w.get("hands") else ""
        rows.append(["{item}%s{/}" % realm.label(k), "x%d" % n if n > 1 else "", hands])
    if rows:
        out.append(("table", rows, ["Work", "", "Hands"]))
    known = [realm.label(k) for k, w in realm.works.items() if w.get("finding") and s["works"].get(k, 0)]
    if known:
        out.append(("text", "Known: %s." % ", ".join(known), "hint"))
    for c in s["coming"]:
        n = c["at"] - s["turn"] + 1
        against = realm.threats[c["id"]].get("against", "watch")
        guard = realm.label(against) if against in realm.values or against in realm.stocks else "Defence"
        out.append(("text", "%s: strength %d, %s. %s %s - %s." % (
            realm.label(c["id"]), c["strength"], "this season" if n <= 1 else "in %d seasons" % n, guard,
            number(realm.defence(c["id"], e)), next(word for p, word in ODDS if realm.odds(c, e) >= p)), "combat"))
    return out


def works_lines(realm, kind=None, orders=True):
    """What can be built (or found), each with its number, cost and why not now."""
    rows = []
    for i, (wid, why) in enumerate(realm.open_works(kind, orders=orders)):
        w = realm.works[wid]
        cost = ", ".join("%s %s" % (number(n), realm.label(k).lower()) for k, n in realm.cost(wid).items()) or "free"
        rows.append((i + 1, wid, "{item}%s{/} {hint}(%s)%s{/}" % (realm.label(wid), cost, " " + why if why else ""),
                     str(w.get("text") or "")))
    return rows


def panel_lines(realm, ui, models=None, planets=None):
    """The realm's own screen (its ``"panels"``: engine/panels.py) as lines to write, its widgets showing
    the realm's values by name (stocks, works, hands...) - or [] if it has none, or the screen is too
    narrow for it. ``"lines"`` in the layout is how many rows it takes (14)."""
    layout = realm.spec.get("panels")
    if not isinstance(layout, dict) or ui.width < 60:
        return []
    from . import panels
    from .frame import Painter
    from .sim import formula
    view = realm.__dict__.get("_view")
    if view is None:
        view = realm.__dict__["_view"] = panels.View(layout, formula, models, planets)
    rows = view.rows(min(ui.width - 1, 110), max(5, min(40, int(layout.get("lines", 14) or 14))), realm.env(),
                     float(realm.state.get("season", 0)), unicode=ui.term.unicode)
    paint = Painter(ui.term.color_depth, getattr(ui.term, "subst", None) if ui.term.unicode else None)
    reset = "\x1b[0m" if ui.term.color_depth else ""
    return [paint.cells(r, ui.term.unicode) + reset for r in rows]


def tell(ui, lines):
    for line in lines:
        if line[0] == "rule":
            ui.gap()
            label = line[1] if len(line[1]) + 5 <= ui.width else line[2]      # a narrow screen: the date alone
            ui.rule(label[:max(1, ui.width - 5)])
        elif line[0] == "table":
            ui.table(line[1], header=line[2])
        else:
            for l in ui.wrap(line[1], line[2], indent=" "):
                ui.line(l)


def show(ui, realm):
    """How the realm stands: its own screen of panels where it has one, then the words."""
    for line in panel_lines(realm, ui, getattr(realm, "models", None), getattr(realm, "planets", None)):
        ui.term.line(line)
    tell(ui, status_lines(realm))


def play(realm, ui, read, save=None, audio=None, after=None, menu=None):
    """A realm at a prompt: orders typed, a season at a time. Returns won, lost, quit or load."""
    s = realm.state

    def say(text, role="default", indent=" "):
        for l in ui.wrap(text, role, indent=indent):
            ui.line(l)

    def sfx(name):
        if audio:
            try:
                audio.sfx(name)
            except Exception:
                pass

    def choose(r, event, options, news):
        report(news)
        del news[:]
        for i, opt in enumerate(options):
            say("{key}%d{/} %s" % (i + 1, opt.get("text", "...")), "menu")
        while True:
            line = read("%s " % ui.g("arrow"))
            if line is None:
                return 0
            line = line.strip()
            if line.isdigit() and 1 <= int(line) <= len(options):
                return int(line) - 1
            say("A number from 1 to %d." % len(options), "error")

    def report(news):
        for text, role in news:
            say(text, role)

    def season():
        news = realm.end_season(choose)
        ui.gap()
        report(news)
        if any(role == "combat" for _, role in news):
            sfx("hurt")
        if after:
            after(realm)

    def listed(kind):
        spent = realm.orders_left(kind) <= 0
        rows = works_lines(realm, kind, orders=not spent)
        if not rows:
            say("There is nothing to %s now." % kind, "hint")
        elif spent:
            say("This season's order to %s is given already. Next season:" % kind, "hint")
        for n, wid, head, text in rows:
            say("{key}%d{/} %s" % (n, head))
            if text:
                say(text, "hint", "   ")
        return rows

    if s["turn"] == 0 and not s.get("met"):
        s["met"] = 1
        intro = realm.spec.get("intro") or []
        for t in intro if isinstance(intro, list) else [intro]:
            say(str(t), "story")
        say(HELP, "hint")
    show(ui, realm)
    while not s["result"]:
        line = read(None)
        if line is None:
            return "quit"
        words = line.strip().split()
        if not words:
            show(ui, realm)
            continue
        verb, rest = words[0].lower(), words[1:]
        if verb in ("quit", "q", "exit"):
            return "quit"
        if verb in ("help", "h", "?"):
            say(HELP, "hint")
        elif verb in ("end", "e", "next", "n", "pass"):
            season()
            if not s["result"]:
                show(ui, realm)
        elif verb in ("build", "b", "find", "f", "learn"):
            kind = "build" if verb in ("build", "b") else "find"
            if not rest:
                listed(kind)
                continue
            rows = works_lines(realm, kind)
            wid = rows[int(rest[0]) - 1][1] if rest[0].isdigit() and 1 <= int(rest[0]) <= len(rows) \
                else realm.find_work(" ".join(rest))
            if wid is None or realm.kind(wid) != kind:
                say("There is no such thing to %s. Try {key}%s{/} alone for the list." % (kind, kind), "error")
                continue
            done, text = realm.build(wid)
            say(text, "success" if done else "error")
            if done:
                sfx("craft")
        elif verb in ("put", "set", "hands") or (len(words) == 2 and (words[1].lstrip("+-").isdigit())
                                                 and realm.find_work(words[0])):
            if verb not in ("put", "set", "hands"):
                rest = [words[1], words[0]]
            nums = [w for w in rest if w.lstrip("+-").isdigit()]
            wid = realm.find_work(" ".join(w for w in rest if not w.lstrip("+-").isdigit()
                                           and w not in ("to", "on", "in")))
            if not nums or wid is None:
                say("Say how many and where: {key}put 3 fields{/}.", "error")
                continue
            n = int(nums[0])
            if nums[0][0] in "+-":
                n += s["hands"].get(wid, 0)
            done, text = realm.put(wid, n)
            say(text + " Idle: %d." % realm.idle(), "default" if done else "hint")
        elif verb in ("works", "w"):
            for k, w in realm.works.items():
                if w.get("finding") or not s["works"].get(k, 0):
                    continue
                gives = ["%s %s a hand" % (number(realm.f(t)(realm.env())), realm.label(st).lower())
                         for st, t in (w.get("yields") or {}).items()]
                hands = ", hands %d/%d" % (s["hands"].get(k, 0), realm.slots(k)) if w.get("hands") else ""
                say("{item}%s{/} x%d%s%s" % (realm.label(k), s["works"][k], hands,
                                             ": " + ", ".join(gives) if gives else ""))
            listed("build")
            listed("find")
        elif verb in ("sky", "tide", "forecast"):
            sky = realm.forecast()
            if not sky:
                say("The sky says nothing here.", "hint")
            for i, name in enumerate(sky):
                note = (realm.tides.get("notes") or {}).get(name, "")
                say("{key}%s{/}: %s%s" % (realm.season(realm.turn + i), name, (" - " + note) if note else ""))
        elif verb in ("news", "log"):
            report([(t, r) for t, r in s.get("news", [])] or [("Nothing of note last season.", "hint")])
        elif verb in ("steward", "auto"):
            n = int(rest[0]) if rest and rest[0].isdigit() else 1
            for _ in range(max(1, min(n, 400))):
                if s["result"]:
                    break
                did = [d for d in tend(realm) if not d.startswith("put")]
                say("%s. The steward %s." % (realm.date(), "orders: " + ", ".join(did) if did else "sets the hands"),
                    "hint")
                news = realm.end_season(answer)
                report(news)
                if after:
                    after(realm)
            if not s["result"]:
                show(ui, realm)
        elif verb in ("menu", "options", "settings") and menu:
            act = menu("menu" if verb == "menu" else "options")
            if act in ("quit", "load"):
                return act
            if act == "save" and save:
                save()
            elif act == "help":
                say(HELP, "hint")
        elif verb == "save":
            if save:
                save()
            else:
                say("There is nowhere to save here.", "error")
        elif verb == "load":
            return "load"
        elif verb in ("look", "l", "status"):
            show(ui, realm)
        else:
            say("Orders: " + HELP, "hint")
    if s.get("why"):
        say(s["why"], "story")
    return s["result"]


def play_scene(game, scene):
    """Play the realm of a CLIo scene, then the scene's (or the realm's) effects: won, lost (none: the
    game is won or lost), left (none: the game ends). The realm's state is kept in the game's variables,
    so a save holds it and a load goes on with it."""
    from . import conditions
    w, ui = game.world, game.ui
    rid = scene.get("realm")
    spec = (getattr(game.data, "realms", None) or {}).get(rid) or {}
    kept = w.vars.setdefault("realms", {})
    realm = Realm(spec, rid, w.seed, kept.get(rid) if isinstance(kept.get(rid), dict) else None)
    if realm.state.get("result") in ("won", "lost"):     # played to its end already: the scene is a scene again
        return "played"
    realm.state["result"] = None
    kept[rid] = realm.state
    if spec.get("music"):
        try:
            game.audio.music(spec["music"])
        except Exception:
            pass

    def read(prompt):
        try:
            return ui.prompt(prompt)
        except Exception as e:
            if e.__class__.__name__ == "QuitGame":
                return None
            raise

    def menu(word):                                      # the game's menu, or its options: what was chosen
        from . import menu as menus
        if word == "options":
            menus.show(ui, menus.options(game))
            return None
        got = menus.show(ui, menus.game_menu(game, ("save", "load", "help", "quit")))
        return got.id if got is not None else None

    def after(r):                                        # a season is a turn of the game: its triggers and quests
        while r.outbox and not game.over:
            conditions.run(r.outbox.pop(0), game)
        if not game.over:
            game.end_turn()
        if game.over and not r.state["result"]:
            r.state["result"] = "quit"

    while True:
        outcome = play(realm, ui, read, save=game.save_slot, audio=game.audio, after=after, menu=menu)
        if outcome != "load":
            break
        if getattr(game, "permadeath", False):
            game.say("There is no going back on a one-life run.", "error")
        elif game.load_slot():                           # the loaded game plays on from its own scene
            return "load"
    if game.over:
        return outcome
    stats = realm.stats()
    w.vars["realm_score"] = stats["score"]
    w.vars["seasons"] = stats["seasons"]
    if outcome == "won":
        w.flags["%s_won" % rid] = True
        effects = scene.get("on_realm_won") or spec.get("on_won")
        if effects:
            conditions.run(effects, game)
        else:
            game.end_game("win", spec.get("won_text") or "outro_win")
    elif outcome == "lost":
        effects = scene.get("on_realm_lost") or spec.get("on_lost")
        if effects:
            conditions.run(effects, game)
        else:
            game.end_game("lose", spec.get("lost_text") or "outro_lose")
    else:
        effects = scene.get("on_realm_quit")
        if effects:
            conditions.run(effects, game)
        else:
            game.over = "quit"
    if not game.over:
        game.resume_music()
    return outcome


# --------------------------------------------------------------------------- #
# Checking
# --------------------------------------------------------------------------- #
EFFECTS = ("say", "role", "stock", "people", "work", "set", "clear", "threat", "random", "game", "win", "lose",
           "if", "then", "else")


def problems(data):
    out = []
    realms = getattr(data, "realms", None) or {}
    for rid, spec in realms.items():
        where = "realm '%s'" % rid
        if not isinstance(spec, dict):
            out.append("%s should be an object" % where)
            continue
        r = Realm(spec, rid)
        if spec.get("panels") is not None:               # a screen of its own: its widgets show the realm's values
            from . import panels
            try:
                names = set(r.env())
            except Exception:
                names = None
            out += panels.problems(spec["panels"], names, "%s: panels" % where, None,
                                   getattr(data, "models", None) or {}, getattr(data, "planets", None) or {})
        if not r.stocks:
            out.append("%s: it has no stocks" % where)
        cal = spec.get("calendar") or {}
        if "seasons" in cal and (not isinstance(cal["seasons"], list) or not cal["seasons"]):
            out.append("%s: calendar seasons should be a list of names" % where)
        if spec.get("tides") and not r.levels:
            out.append("%s: tides need levels (a list of names)" % where)
        names = r.names()
        taken = {}
        for group, keys in (("a stock", r.stocks), ("a work", r.works), ("a value", r.values),
                            ("a season", [name_of(x) for x in r.seasons]), ("a tide", [name_of(x) for x in r.levels]),
                            ("a word of the engine's", RESERVED),
                            ("a work's hands", [k + "_hands" for k in r.works])):
            for k in keys:
                if k in taken and taken[k] != group:
                    out.append("%s: '%s' is both %s and %s" % (where, k, taken[k], group))
                taken[k] = group

        def read(what, text):
            if text is None:
                return
            if isinstance(text, bool) or not isinstance(text, (str, int, float)):
                out.append("%s: %s should be a number or a formula" % (where, what))
                return
            try:
                f = formula(text)
            except FormulaError as e:
                out.append("%s: %s: %s" % (where, what, e))
                return
            unknown = sorted(getattr(f, "names", set()) - names)
            if unknown:
                out.append("%s: %s reads %s, which nothing gives" % (where, what, ", ".join(unknown)))

        def amounts(what, table, known, kind="stock"):
            if table is None:
                return
            if not isinstance(table, dict):
                out.append("%s: %s should be an object of %ss and amounts" % (where, what, kind))
                return
            for k, v in table.items():
                if k not in known:
                    out.append("%s: %s names '%s', which is not a %s" % (where, what, k, kind))
                read("%s %s" % (what, k), v)

        def effects(what, effs):
            for eff in as_list(effs):
                if not isinstance(eff, dict):
                    out.append("%s: %s: an effect should be an object" % (where, what))
                    continue
                for k in eff:
                    if k not in EFFECTS:
                        out.append("%s: %s: unknown effect '%s'" % (where, what, k))
                amounts(what + " stock", eff.get("stock"), r.stocks)
                amounts(what + " work", eff.get("work"), r.works, "work")
                if "people" in eff:
                    read(what + " people", eff["people"])
                if "if" in eff:
                    read(what + " if", eff["if"])
                for tid in as_list(eff.get("threat")):
                    if tid not in r.threats:
                        out.append("%s: %s calls the threat '%s', which there is none of" % (where, what, tid))
                for k in ("then", "else"):
                    effects(what, eff.get(k))
                for branch in as_list(eff.get("random")):
                    effects(what, branch)

        for k, sp in r.stocks.items():
            for key in ("start", "min", "max", "rate", "warn"):
                if key in sp:
                    read("stock %s %s" % (k, key), sp[key])
        for k, v in r.values.items():
            read("value %s" % k, v.get("formula"))
        if "forecast" in r.tides:
            read("tides forecast", r.tides["forecast"])
        for key in ("growth", "room"):
            if key in r.folk:
                read("people %s" % key, r.folk[key])
        amounts("people eats", r.folk.get("eats"), r.stocks)
        for k, w in (spec.get("works") or {}).items():
            what = "work '%s'" % k
            if not isinstance(w, dict):
                out.append("%s: %s should be an object" % (where, what))
                continue
            for key in ("cost", "yields", "makes", "upkeep"):
                amounts("%s %s" % (what, key), w.get(key), r.stocks)
            for key in ("needs", "max"):
                if key in w:
                    read("%s %s" % (what, key), w[key])
            if w.get("yields") and not w.get("hands"):
                out.append("%s: %s yields by the hand, and takes no hands" % (where, what))
            effects(what + " on_built", w.get("on_built"))
        seen = set()
        for i, ev in enumerate(as_list(spec.get("events"))):
            what = "event '%s'" % (ev.get("id", i) if isinstance(ev, dict) else i)
            if not isinstance(ev, dict):
                out.append("%s: %s should be an object" % (where, what))
                continue
            if ev.get("id") in seen:
                out.append("%s: two events are called '%s'" % (where, ev.get("id")))
            seen.add(ev.get("id") or object())
            for key in ("if", "chance"):
                if key in ev:
                    read("%s %s" % (what, key), ev[key])
            effects(what, ev.get("do"))
            for ch in as_list(ev.get("choices")):
                if not isinstance(ch, dict) or not ch.get("text"):
                    out.append("%s: %s: a choice needs a text" % (where, what))
                    continue
                if "if" in ch:
                    read(what + " choice if", ch["if"])
                effects(what + " choice", ch.get("do"))
        for k, t in (spec.get("threats") or {}).items():
            what = "threat '%s'" % k
            if not isinstance(t, dict):
                out.append("%s: %s should be an object" % (where, what))
                continue
            for key in ("if", "chance", "strength"):
                if key in t:
                    read("%s %s" % (what, key), t[key])
            read(what + " against", t.get("against", "watch"))
            effects(what + " on_held", t.get("on_held"))
            effects(what + " on_lost", t.get("on_lost"))
        for key in ("win_if", "fail_if", "score"):
            if spec.get(key) is not None:
                read(key, spec[key])
        if not r.length and spec.get("win_if") is None and spec.get("fail_if") is None:
            out.append("%s: it never ends: give the calendar a length, or a win_if or fail_if" % where)
    for sid, sc in (getattr(data, "scenes", None) or {}).items():
        if sc.get("realm") and sc["realm"] not in realms:
            out.append("scene '%s': unknown realm '%s'" % (sid, sc["realm"]))
    return out


def main(argv=None):
    import os
    import sys
    import time
    from .data import GameData
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(__doc__.strip().splitlines()[-1].strip())
        return 2
    path = argv.pop(0)
    seeds = int(argv.pop()) if argv and argv[-1].isdigit() else 5
    data = GameData(path if os.path.isdir(path) else os.path.join("games", path))
    stood_any = True
    for rid in argv or sorted(data.realms):
        t0 = time.time()
        runs = [steward(make(data, rid, seed)).stats() for seed in range(1, seeds + 1)]
        stood = [r for r in runs if r["result"] == "won"]
        scores = sorted(r["score"] for r in runs)
        stood_any = stood_any and bool(stood)
        print("%s: stood %d of %d, score %d (the middle one; %d to %d), %d seasons at the least, "
              "threats held %d of %d (%.1fs)" % (
                  rid, len(stood), len(runs), scores[len(scores) // 2], scores[0], scores[-1],
                  min(r["seasons"] for r in runs), sum(r["held"] for r in runs),
                  sum(r["held"] + r["lost"] for r in runs), time.time() - t0))
    return 0 if stood_any else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
