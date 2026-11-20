# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Demos: a playlist of clips that play themselves, with a caption line - levels a bot plays,
sims an autopilot flies, stages and skirmishes the computer plays, models turning in a showroom,
a text adventure typed out, and title cards between them. Any key ends a demo.

A game can have its own (``demo.json``, played from its title screen); CLIo's tech demo is
``engine/demos/clio.json`` (from the launcher). A playlist::

    {"title": "RØØTLESS", "game": "rootless", "clips": [
      {"card": "RØØTLESS", "text": ["Episode 1"], "seconds": 4},
      {"level": "e1m1", "seconds": 25, "caption": "Boot Sector: the shotgun"},
      {"level": "e1m3", "skip_until": "vehicle", "views": ["pixel", "dots"]},
      {"sim": "sim8"}, {"stage": "sim6"}, {"skirmish": "sim7"},
      {"models": ["drone_hornet", "hopper"], "seconds": 4},
      {"adventure": "derelict", "commands": "walkthrough", "seconds": 30}]}

A clip's ``game`` (a folder under games/) is the playlist's unless it names its own; ``seconds`` is
how long it plays (a clip whose game ends sooner moves on). Adding a clip, or a kind of clip
(``KINDS``), is all it takes to make a demo longer.
"""
import copy
import os
import time

from .term import strip_ansi, visible_len

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TECH = os.path.join(ROOT, "engine", "demos", "clio.json")
KINDS = ("card", "logo", "level", "sim", "stage", "skirmish", "models", "adventure")
SECONDS = {"card": 4, "logo": 5, "level": 25, "sim": 20, "stage": 20, "skirmish": 25, "models": 4,
           "adventure": 30}
def _idle():
    try:
        return max(0.0, float(os.environ.get("CLIO_DEMO_IDLE", 45)))
    except ValueError:
        return 45.0


IDLE = _idle()                # seconds on a menu without a key before a demo starts by itself (0: never)


def idle_play(term, spec):
    """For a menu's ``idle``: the demo, over and over, when nobody has pressed a key for IDLE seconds -
    or None (no demo, or CLIO_DEMO_IDLE=0)."""
    if not spec or IDLE <= 0:
        return None
    return (IDLE, lambda: play(term, spec, loop=True))


class Stop(Exception):
    """A key was pressed: the demo is over."""


def kind_of(clip):
    return next((k for k in KINDS if k in clip), None)


def load(path):
    from .data import read_json
    try:
        spec = read_json(path)
    except Exception:
        return None
    return spec if isinstance(spec, dict) and spec.get("clips") else None


def of_game(game_dir):
    """A game's own demo (its demo.json), or None."""
    p = os.path.join(game_dir, "demo.json")
    return load(p) if os.path.isfile(p) else None


def problems(spec, data=None, where="demo.json"):
    """What is wrong with a playlist; ``data``: the game it belongs to (clips naming no other game are
    checked against it)."""
    out = []
    clips = spec.get("clips") if isinstance(spec, dict) else None
    if not isinstance(clips, list) or not clips:
        return ["%s: \"clips\" should be a list of clips" % where]
    datas = {}
    for i, clip in enumerate(clips):
        at = "%s: clip %d" % (where, i + 1)
        if not isinstance(clip, dict):
            out.append("%s should be an object" % at)
            continue
        kind = kind_of(clip)
        if kind is None:
            out.append("%s: a clip is one of %s" % (at, ", ".join(KINDS)))
            continue
        secs = clip.get("seconds", SECONDS[kind])
        if not isinstance(secs, (int, float)) or secs <= 0:
            out.append("%s: \"seconds\" should be a number above 0" % at)
        if kind in ("card", "logo"):
            continue
        game = clip.get("game") or spec.get("game")
        d = data if data is not None and not clip.get("game") else None
        if d is None and game:
            if game not in datas:
                try:
                    from .data import GameData
                    datas[game] = GameData(os.path.join(ROOT, "games", game))
                except Exception:
                    datas[game] = None
            d = datas[game]
        if d is None:
            out.append("%s: no game '%s'" % (at, game))
            continue
        table = {"level": d.levels, "sim": d.sims, "stage": d.stages, "skirmish": d.skirmishes,
                 "models": d.models}.get(kind)
        names = clip[kind] if isinstance(clip[kind], list) else [clip[kind]]
        if table is not None:
            for n in names:
                if n not in table:
                    out.append("%s: %s has no %s '%s'" % (at, d.title, "model" if kind == "models" else kind, n))
        for v in clip.get("views") or []:
            if v not in ("pixel", "dots", "dots-fill"):
                out.append("%s: no view '%s' (pixel, dots, dots-fill)" % (at, v))
        if clip.get("skip_until") not in (None, "vehicle", "fight"):
            out.append("%s: \"skip_until\" is vehicle or fight" % at)
    return out


# --------------------------------------------------------------------------- #
# the player
# --------------------------------------------------------------------------- #
class Player:
    """Plays a playlist on the terminal's screen. ``loop``: from the start again at the end (the attract
    mode); else once. ``run()`` answers "done" (played to the end) or "key" (a key stopped it)."""

    def __init__(self, term, spec, keys=None, clock=None, loop=False, games=None):
        from .frame import Screen
        if keys is None:
            from .keys import KeyReader
            keys = KeyReader()
        self.term, self.spec, self.loop = term, spec, loop
        self.screen = Screen(term, keys, {}, animate=term.animate)
        self.keys = keys
        self.now = clock.now if clock is not None else time.monotonic
        self.screen.now = self.now
        self.games = games or os.path.join(ROOT, "games")
        self.datas = {}
        self.clip = None
        self.ends = 0.0
        self.ms = None                        # how long the last picture took to draw
        self.note = ""                        # the clip's caption

    # -- the frame and its line ---------------------------------------------- #
    def data(self, clip):
        from .data import GameData
        game = clip.get("game") or self.spec.get("game")
        if game not in self.datas:
            self.datas[game] = GameData(os.path.join(self.games, game))
        return self.datas[game]

    def left(self):
        return self.ends - self.now()

    def wait(self, seconds):
        """Let ``seconds`` go by, watching the keys: a key stops the demo."""
        end = self.now() + max(0.0, seconds)
        while True:
            left = end - self.now()
            if left <= 0:
                return
            k = self.keys.get(min(left, 0.05))
            if k is not None:
                raise Stop()

    def caption(self, extra=""):
        """The line under the picture: what the clip shows, and how fast it draws."""
        from . import picture
        sc = self.screen
        W = sc.size()[0]
        bits = []
        if extra:
            bits.append(extra)
        if self.ms is not None:
            v = picture.version() if picture.load() else None
            bits.append(("CLIo Picture %s" % v) if v else "Python")
            bits.append("%.1f ms a picture" % self.ms)
        right = "  ".join(bits + ["any key: back"])
        left = " " + sc.glyphs["run"] + " " + self.note
        room = max(0, W - len(right) - 2)
        if len(left) > room:
            left = left[:max(0, room - 1)] + sc.glyphs["ell"]
        return sc.paint.text([(left.ljust(room), "title"), ("  " + right, "dim")], W, sc.glyphs["ell"])

    def show(self, rows, status="", extra=""):
        """A frame: ``rows`` from the top, the caption on the last line."""
        H = self.screen.size()[1]
        rows = list(rows)[:max(0, H - 2)]
        self.screen.frame(rows + [""] * (H - 2 - len(rows)), prompt=None, status=status, footer=self.caption(extra))

    # -- playing ------------------------------------------------------------- #
    def run(self):
        clips = [c for c in self.spec.get("clips") or [] if isinstance(c, dict) and kind_of(c)]
        if not clips:
            return "done"
        self.screen.start()
        try:
            while True:
                for clip in clips:
                    self.play(clip)
                if not self.loop:
                    return "done"
        except (Stop, KeyboardInterrupt):
            return "key"
        finally:
            self.screen.stop()

    def play(self, clip):
        kind = kind_of(clip)
        self.clip, self.ms = clip, None
        self.note = clip.get("caption", "") or (self.spec.get("title", "") if kind in ("card", "logo") else "")
        self.ends = self.now() + float(clip.get("seconds", SECONDS[kind]))
        try:
            getattr(self, "play_" + kind)(clip)
        except Stop:
            raise
        except (KeyError, ValueError, OSError) as e:      # a clip that cannot play is passed over
            self.note = "(%s: %s)" % (kind, e)
            self.show([""] * 3)
            self.wait(1.0)

    # -- cards: a title in big letters ----------------------------------------- #
    def centred(self, lines, W, H):
        top = max(0, (H - len(lines)) // 2)
        rows = [""] * top
        for l in lines:
            rows.append(" " * max(0, (W - visible_len(l)) // 2) + l)
        return rows[:H]

    def play_card(self, clip):
        from . import banner
        sc = self.screen
        W, H = sc.size()
        spec = {"text": clip["card"]}
        for k in ("style", "palette", "effect"):
            if clip.get(k):
                spec[k] = clip[k]
        art = banner.make(spec, W - 4, max(4, H - 8))
        lines = art.render(self.term, W - 4, H - 8) if art is not None else [clip["card"]]
        text = [sc.paint.text([(t, "dim")], W) for t in clip.get("text") or []]
        frames = []
        if art is not None and self.term.animate:
            frames, _ = art.animation(self.term, W - 4, H - 8, clip.get("effect"), seed=clip["card"])
        for block, secs in frames:
            self.show(self.centred(list(block) + [""] + text, W, H - 3))
            self.wait(secs)
        self.show(self.centred(lines + [""] + text, W, H - 3))
        self.wait(self.left())

    def play_logo(self, clip):
        from .art import load_logo
        sc = self.screen
        W, H = sc.size()
        logo = load_logo(clip.get("logo") if isinstance(clip.get("logo"), str) else None) or load_logo(None)
        lines = logo.render(self.term, W - 4) if logo else []
        text = [sc.paint.text([(t, "dim")], W) for t in clip.get("text") or []]
        if logo is not None and self.term.animate:
            frames, _ = logo.animation(self.term, W - 4, None, clip.get("effect"), seed="clio")
            for block, secs in frames:
                self.show(self.centred(list(block) + [""] + text, W, H - 3))
                self.wait(secs)
        self.show(self.centred(lines + [""] + text, W, H - 3))
        self.wait(self.left())

    # -- a first-person level, played by its bot --------------------------- #
    def play_level(self, clip):
        from . import levelbot
        from .level import Level, TextConsole
        data = self.data(clip)
        lv = Level(data, clip["level"], seed=int(clip.get("seed", 1)))
        lv.host = None
        lv._assume_duels = "won"
        bot = levelbot.Bot(lv, clip.get("goals") or lv.spec.get("bot") or ["E"])
        if not self.note:
            self.note = lv.spec.get("title") or lv.name
        until = clip.get("skip_until")
        skip = int(clip.get("skip", 0))
        if skip or until:                                 # on to where it gets going, unseen
            lv.console = TextConsole(lambda _t: None, None)
            for _ in range(3000):
                if lv.over or (lv.beat >= skip and (until is None or (until == "vehicle" and lv.player.vehicle)
                                                    or (until == "fight" and lv.visible()))):
                    break
                line = bot.read(lv)
                if line is None:
                    break
                lv.run_line(line)
        if lv.over:
            return
        lv.run(level_console(self, bot, clip))

    # -- real time: sims, stages, skirmishes ------------------------------ #
    def realtime(self, game, steps, draw, rate):
        """``steps(n)`` moves the game on ``n`` ticks; ``draw()`` draws it; ``rate`` ticks a second. Until
        the clip's time is up, or a moment after the game is over."""
        start, done = self.now(), 0
        over_at = None
        while self.left() > 0:
            due = int((self.now() - start) * rate) + 1
            n = min(5, max(1, due - done))
            if over_at is None:
                steps(n)
            done += n
            t = time.perf_counter()
            draw()
            self.ms = (time.perf_counter() - t) * 1000.0
            if game.over and over_at is None:
                over_at = self.now()
            if over_at is not None and self.now() - over_at > 2.0:
                return
            self.wait(max(0.0, start + done / float(rate) - self.now()))

    def play_sim(self, clip):
        from . import sim as S
        from .realtime import Controls
        data = self.data(clip)
        sim = S.make(data, clip["sim"])
        runner = S.Runner(sim, self.screen)
        if not self.note:
            self.note = sim.name
        sim.step(Controls(0, frozenset(["enter"]), ("enter",), ()))
        state = {"held": set(), "plan": set(), "tick": 1}

        def steps(n):
            for _ in range(n):
                if sim.result:
                    return
                t = state["tick"]
                if sim.mode == "systems":
                    if t == 1 or sim.ticks % int(2.0 * sim.rate) == 0:
                        state["plan"] = S.best_controls(sim, 2.0)
                    keys = set(state["plan"])
                else:
                    keys = S.autopilot_keys(sim)
                held = state["held"]
                sim.step(Controls(t, frozenset(keys), tuple(sorted(keys - held)), tuple(sorted(held - keys))))
                state["held"], state["tick"] = keys, t + 1

        def draw():
            sc = self.screen
            W, H = sc.size()
            unicode = sc.unicode and sc.glyphs.get("half") == "▀"
            rows = runner.rows(W, H, sc.paint.depth, unicode, sc.glyphs.get("heading") if unicode else None)
            text, _role, until = sim.note
            self.show(rows, status=text if text and sim.tick < until else "")
        self.realtime(sim, steps, draw, sim.rate)

    def play_stage(self, clip):
        from . import arcade, stagebot
        from .keys import KeyEvent
        from .realtime import Recorder
        data = self.data(clip)
        journal = clip.get("journal")
        if journal is None:
            self.note = self.note or clip["stage"]
            self.show([""] * 3, status="(the computer looks for a way through)")
            _moves, journal = stagebot.solve(arcade.make(data, clip["stage"]), budget=8000)
        stage = arcade.make(data, clip["stage"])
        if not self.note or self.note == clip["stage"]:
            self.note = stage.name
        runner = arcade.Runner(stage, self.screen)
        by_tick = {int(t): [KeyEvent(n, k) for n, k in evs] for t, evs in (journal or [])}
        rec = Recorder(stage.rate, exact=True)

        def steps(n):
            for _ in range(n):
                if not stage.over:
                    runner.step(rec.next(by_tick.get(rec.tick, ())))

        def draw():
            sc = self.screen
            W, H = sc.size()
            unicode = sc.unicode and sc.glyphs.get("half") == "▀"
            self.show(runner.rows(W, H, sc.paint.depth, unicode), status=runner.status())
        self.realtime(stage, steps, draw, stage.rate)

    def play_skirmish(self, clip):
        from . import rts
        from .realtime import Controls
        data = self.data(clip)
        spec = copy.deepcopy(data.skirmishes[clip["skirmish"]])
        for side in spec.get("sides") or []:
            side["control"] = "ai"                        # the computer plays every side
        w = rts.World(spec, clip["skirmish"], data, rts.RATE)
        runner = rts.Runner(w, self.screen)
        runner.ui.paused = False
        if not self.note:
            self.note = w.name
        state = {"tick": 0, "look": 0}

        def steps(n):
            for _ in range(n):
                if w.over:
                    return
                runner.step(Controls(state["tick"], frozenset(), (), ()))
                state["tick"] += 1
            if state["tick"] >= state["look"]:              # the view goes where the fighting is
                state["look"] = state["tick"] + 50
                units = [u for u in w.things.values() if not u.building and u.hp > 0 and not u.inside]
                firing = [u for u in units if u.shot is not None and w.tick - u.shot[2] < 40]
                pick = firing or units
                if pick:
                    u = pick[(state["tick"] // 50) % len(pick)]
                    runner.ui.cursor = [int(u.x), int(u.y)]

        def draw():
            sc = self.screen
            W, H = sc.size()
            unicode = sc.unicode and sc.glyphs.get("half") == "▀"
            self.show(runner.rows(W, H, sc.paint.depth, unicode))
        self.realtime(w, steps, draw, 20)

    # -- models in a showroom --------------------------------------------- #
    def play_models(self, clip):
        from . import model as model_mod
        from .firstperson import FX, View
        from .level import Level, TextConsole
        data = self.data(clip)
        names = clip["models"] if isinstance(clip["models"], list) else [clip["models"]]
        each = float(clip.get("seconds", SECONDS["models"]))
        views = clip.get("views") or ["pixel"]
        for i, name in enumerate(names):
            if name not in data.models:
                continue
            self.ends = self.now() + each
            spec = dict(data.models[name], turning=float(clip.get("turning", 12)))
            probe = model_mod.Model(name, spec)
            extent = max(probe.height, 2 * probe.radius, 0.1)
            spec["scale"] = probe.scale * float(clip.get("size", 1.2)) / extent    # about as big, whatever it is
            mdl = centred(model_mod.Model(name, spec))
            lv = Level(_Showroom(data, name, 2), "_showroom", seed=1)
            lv.console = TextConsole(lambda _t: None, None)
            lv.models[name] = mdl
            lv.player.weapon = None                          # empty hands: nothing in front of the model
            for row in lv.grid:
                for c in row:
                    c.sky = c.sky or c.kind != "wall"
            self.note = "%s%s  %d triangles" % (clip.get("caption", "") + "  " if clip.get("caption") else "",
                                               name.replace("_", " "), len(mdl.faces))
            style = views[i % len(views)]
            sc = self.screen
            start = self.now()
            view, size = None, None
            while self.left() > 0:
                W, H = sc.size()
                if (W, H) != size:
                    size, view = (W, H), View(W, max(6, H - 3), style)
                t = time.perf_counter()
                beats = (self.now() - start) * 4.0
                rows = view.render(lv, FX(tick=beats - int(beats)), int(beats))
                self.ms = (time.perf_counter() - t) * 1000.0
                self.show([list(r) for r in rows], extra=style)
                self.wait(1 / 15.0)

    # -- a text adventure, typed --------------------------------------------- #
    def play_adventure(self, clip):
        import io
        from .audio import Audio
        from .audio.backends import NullBackend
        from .game import Game
        from .term import QuitGame, Term
        game_dir = os.path.join(self.games, clip["adventure"])
        commands = clip.get("commands") or []
        if commands == "walkthrough":
            from .editor import finish
            walks = finish.parse(finish.read(game_dir))
            commands = [c for _n, c in walks[0]["lines"]] if walks else []
        sc = self.screen
        W, H = sc.size()
        out = io.StringIO()
        queue = list(commands)

        def answer(_prompt):                            # the game asks: the answer is typed (and echoed)
            if not queue:
                raise EOFError
            return self.type_out(out, queue.pop(0), W, H)

        term = Term(out=out, inp=answer, width=W - 2, height=H, color=self.term.color_depth,
                    unicode=self.term.unicode, animate=False, env={"TERM": "xterm-256color"},
                    glyphs=self.term.glyph_mode)
        game = Game(game_dir, term=term, audio=Audio(backend=NullBackend(), enabled=False),
                    seed=int(clip.get("seed", 1)))
        game.mode_request = next(iter(game.modes), None)
        if not self.note:
            self.note = game.data.title
        self.adventure_rows(out, W, H)
        try:
            game.begin_story()
            prompt = term.paint(game.ui.theme.ui.get("prompt", "> "), game.ui.theme.color("prompt"))
            while queue and not game.over and self.left() > 0:
                game.show_hud()
                line = self.type_out(out, queue.pop(0), W, H)
                out.write(prompt + line + "\n")
                game.execute(line)
            self.adventure_rows(out, W, H)
            self.wait(min(3.0, max(0.0, self.left())))
        except (EOFError, QuitGame):
            pass

    def adventure_rows(self, out, W, H, typing=None):
        lines = [l for l in out.getvalue().replace("\r", "").split("\n")]
        while lines and not strip_ansi(lines[-1]).strip():
            lines.pop()
        if typing is not None:
            lines.append(self.screen.paint.text([("> ", "prompt"), (typing, "text")], W))
        rows = [" " + l for l in lines[-(H - 3):]]
        self.show(rows)

    def type_out(self, out, command, W, H):
        """A command typed a letter at a time, then the game's answer."""
        if self.left() <= 0:
            raise EOFError
        self.adventure_rows(out, W, H, "")
        self.wait(0.6)
        for i in range(1, len(command) + 1):
            self.adventure_rows(out, W, H, command[:i])
            self.wait(0.06)
        self.wait(0.3)
        return command


SHOWROOM_SKY = {"top": "#0b1022", "horizon": "#c46a44", "stars": 0.012,
                "sun": {"at": 0.5, "height": 0.5, "size": 0.3, "color": "#d9b07a", "glow": 0.35},
                "clouds": {"color": "#3a2c44", "amount": 0.3}}


def centred(mdl, lift=0.15):
    """The model turning about its own middle, its lowest point ``lift`` off the floor (on a stand)."""
    rest = mdl.pose("idle", 0.0)
    xs, ys, zs = [p[0] for p in rest], [p[1] for p in rest], [p[2] for p in rest]
    cx, cy, dz = (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0, min(zs) - lift
    pose = mdl.pose
    mdl.pose = lambda clip="idle", t=0.0: [(x - cx, y - cy, z - dz) for x, y, z in pose(clip, t)]
    mdl.height = max(zs) - dz
    return mdl


class _Showroom:
    """A game's data with one more level: a yard open to the sky, the model on a stand ``ahead`` cells in
    front of the player."""

    def __init__(self, data, model, ahead):
        self._data = data
        item = {"name": model.replace("_", " "), "pickup": {"model": model, "text": ""}}
        self.items = dict(data.items, _showroom_model=item)
        rows = ["#ooooooo#"] * (ahead + 3)
        rows[1] = "#ooomooo#"
        rows[1 + ahead] = "#ooo@ooo#"
        self.levels = dict(data.levels, _showroom={
            "name": "Showroom", "facing": "n", "sky": SHOWROOM_SKY,
            "map": ["#########"] + rows + ["#########"],
            "legend": {"m": "_showroom_model", "o": {"sky": True}}})

    def __getattr__(self, name):
        return getattr(self._data, name)


def level_console(player, bot, clip):
    """A level's console in a demo: the frame console's picture, the bot's commands, the clip's time."""
    from .level import FrameConsole

    class DemoConsole(FrameConsole):
        def __init__(self):
            FrameConsole.__init__(self, player.term, (clip.get("views") or ["pixel"])[0], keys=False,
                                  animate=player.term.animate)
            self.screen = player.screen
            self.views_ = clip.get("views") or ["pixel"]
            self.every = float(clip.get("view_every") or
                               float(clip.get("seconds", SECONDS["level"])) / len(self.views_))
            self.began = player.now()

        def start(self):
            pass

        def stop(self):
            pass

        def hint(self):
            return player.caption(self.style)

        def draw(self, lv, fx=None, prompt="> ", cells=None):
            k = int((player.now() - self.began) / self.every) % len(self.views_)
            if self.views_[k] != self.style:
                self.style, self.size = self.views_[k], None
            t = time.perf_counter()
            rows = self.rows(lv, fx, cells)
            if cells is None:
                player.ms = (time.perf_counter() - t) * 1000.0
            player.show(rows, status=self.status, extra=self.style)

        def read(self, lv):
            self.phase += 1
            self.draw(lv)                                   # with the last command under it
            if player.left() <= 0:
                return None
            player.wait(float(clip.get("beat", 0.16)))
            line = bot.read(lv)
            self.status = "%s %s" % (self.screen.glyphs["run"], line or "")
            return line

        def page(self, lv, lines, automap=False):
            player.show(self.rows(lv, page=lines, automap=automap), extra=self.style)
            player.wait(1.6 if lv.beat == 0 else 2.2)

        def ending(self, lv):
            self.draw(lv, prompt=None)
            player.wait(1.0)

        def busy(self):
            import contextlib
            return contextlib.nullcontext()

    return DemoConsole()


def play(term, spec, loop=False, keys=None, clock=None):
    """Play a playlist on ``term`` (a real terminal's screen); "done", "key", or None when it cannot be
    shown here (no screen to draw on)."""
    if not (term.is_tty and term.ansi) and keys is None:
        return None
    return Player(term, spec, keys=keys, clock=clock, loop=loop).run()


def tech():
    """CLIo's own tech demo."""
    return load(TECH)
