# Developing CLIo

For people working on the engine itself. Making a game needs none of this: see
[AUTHORING.md](AUTHORING.md). Playing needs even less: see the [README](../README.md).

## What the engine does

- [x] Core engine: scenes, exits (locked, blocked, guarded, hidden), items, fixtures with state machines
- [x] Parser with synonyms, directions, `use X on Y`, `give X to Y`, game-defined verbs, typo suggestions
- [x] Inventory, equipment slots, crafting, combining, repairing
- [x] Simple dialogues (original format) **and** branching dialogue trees with conditions and effects
- [x] Character interaction: giving, trading, NPC crafting, shops
- [x] Character movement, followers, ambushes, guards
- [x] Character/enemy spawning (`spawn` effect, generated dungeons)
- [x] Quests with stages that track themselves, a journal, triggers
- [x] RPG features: stats, levels, experience, gold, classes
- [x] Tactical combat: telegraphed enemy moves, guard/focus/heavy, skills, status effects, items, fleeing
- [x] Fights against groups: every enemy shows its intent, targets by number, area skills and items
- [x] Character generator (name and class at the start of a game)
- [x] Sounds and music: synthesizer, generative composer, optional audio files
- [x] Sound sets, and physically modelled shots, ricochets and blasts from
      [Ballistic Foley Lab](https://github.com/eigensoundlab/ballistic)'s engine (Node.js, its C
      engine, or baked)
- [x] Styling: seven themes, frames, typewriter / fade / glitch effects, HUD
- [x] ASCII art with colour masks, half-block pixel sprites, procedural sprites
- [x] Banners: a game's title (or any text) in nine graphic styles and thirteen palettes, with
      animation - glitch, flicker, shine, twinkle, pulse, colour cycle, typing, hand-drawn frames
- [x] A game's own palettes and house style for banners, drawn live in the editor
- [x] Pictures in the same styles - half blocks, square blocks, braille dots, LED, ASCII -
      with drawings that play in turn, drawn and played in the editor
- [x] Fifteen CLIo logos to choose from, most of them animated
- [x] Auto-map
- [x] Generative maze, monster packs, endless dungeons that scale with depth
- [x] Game modes (for example story and rogue), permadeath, scores and a records table
- [x] Card battles: decks, hands and energy, enemies that show what they will do, duellists with
      decks of their own that choose by search, card rewards; a mode or a character turns them on
- [x] First-person levels: a map drawn in perspective and redrawn in place (frame mode),
      textured walls, sprites that shrink with distance and keep their eyes, 3D models, monsters
      that aim, throw fire, charge, spawn and fight each other, keys, doors, lockers, supply
      crates, bars, force fields, timed and one-way doors, secrets, events, a boss on a
      schedule, an automap; arrow keys or typed commands, any window size; a game's own tiles;
      crates, pressure plates, teleporters, lifts, stairs, magnetic walls, a jetpack, water to
      swim and dive in; debris and gibs; an end screen; a map painter in the editor
- [x] Monsters with brains that take cover, flank, hold and fall back, throw grenades and lay
      mines, in squads that share what they see - packs that swarm, sweeps, ambushes, assaults;
      open land and dungeons without end; saves that hold a level's state
- [x] Arcade stages in real time: platformers (jumps, platforms, ladders, doors and keys,
      checkpoints) and top-down chases, enemies that walk, hop, fly, hunt and shoot, drawn in
      half-block pixels; a bot that proves each stage can be cleared
- [x] Real-time strategy: skirmishes with workers, two resources, buildings, training, upgrades
      and tech, armies on flow fields, fliers and transports, control groups, fog of war, a
      computer player that builds, researches and attacks in waves; keys and the mouse; orders
      kept by tick, so a game plays back (the base for lockstep multiplayer)
- [x] Simulators: cars, boats, a hopper and planes in fixed steps over a map, instruments,
      fuel and systems as data (formulas), checkpoints and landings; systems sims with controls
      and charts; an autopilot that proves each one can be done
- [x] Realms: strategy by turns as data - stocks, people set to works, orders, a calendar whose
      tides are told ahead, events with choices, threats that show themselves a season before
      they come; saved with the game; a steward that plays each one over seeds
- [x] Save / load of the *whole* world, named slots
- [x] Optional C libraries, exactly as fast as the Python is right: CLIo Picture (the
      first-person picture; models kept as meshes for crowds) and Ballistic's C engine (sound)
- [x] Demos that play by themselves: CLIo's tech demo and a game's own
- [x] Vector displays: 3D in lines, wire frame or solid with hidden lines, in braille dots or
      strokes, with afterglow - a hauler, a corridor, an orbit and a surface scan as a reel
- [x] Cues: screens that move with the sound, from Playhead's cue sheets or a song's own notes
- [x] Menus: one menu in several looks, options and a game menu in every game, a game's own as data
- [x] Panels: a simulator's own screen of instruments (a bridge, an engineering console)
- [x] Three demo games and a terminals demo, three starter templates, over a thousand automated tests
- [x] Game editor in the browser: `python clio.py mygame --edit`, or
      [on the web](https://eryxgames.github.io/CLIo/) with nothing installed - forms for
      everything a game is made of, the map, conversations as graphs, all text as a
      table, an enemy workshop, a sprite editor, and a check that the game can be finished
- [ ] The older entity data editor (`utils/entity_editor.py`, Tkinter, desktop only - still alpha and
      still edits the CLIo 1 file layout in `game_files/`; its Project Map needs
      `pip install graphviz pillow` plus the Graphviz program)

## Project layout

```
clio.py              launcher
engine/
  term.py            terminal detection, colour, markup, wrapping
  ui.py              frames, panels, menus, HUD, text effects
  theme.py           themes (files in engine/style/configs/)
  art.py             ASCII art files          sprite.py   pixel sprites
  banner.py          text in graphic styles   fx.py       art animation
  automap.py         auto-map                 maze.py     dungeon generator
  audio/             synth, composer, sound effects, playback backends
    ballistic/       Ballistic Foley Lab's sound engine (Node.js, or its C engine: --get-ballistic)
  picture/           CLIo Picture: the first-person picture in C, when installed (--get-picture)
  downloads.py       the launcher's optional downloads
  data.py            loading and normalising game files
  world.py           game state, save/load
  parser.py          command parser           actions.py  the verbs
  conditions.py      conditions and effects   quests.py   dialogue.py   combat.py
  game.py            the turn loop
  level.py           first-person levels      firstperson.py  the view
  levelbot.py        a player that proves a level can be finished
  model.py           3D models in levels      gltf.py     glTF from Blender
  motion/            models moved by CLIo Motion: the glue, and the library's Python package carried (clio_motion/)
  frame.py  keys.py  the redrawn screen and single keys
  realm.py           realms: strategy by turns (seasons, stocks, works, threats), and its steward
  vector.py          vector displays: 3D in lines (wire and hidden-line), dots or strokes, afterglow
  cues.py            cue sheets (Playhead's): what a screen does with the sound, from a file or a song's notes
  menu.py            menus: items and values, looks (bar, tabs, find, line, terminal, cards, ring, wheel, lines), frames
  panels.py          screens of instruments: panels in frames, gauges, big numbers, lamps, plots, scopes
  ahead.py           what is ahead, in lines: the view forward over a simulator's map, as ground or as space; rocks
  viewer.py          views of a model (shaded, lines, cut open, a plan, by heat) and of a planet; --view-model
  shots.py           --shots: a game's consoles, menus and models as a page of pictures, without playing it
  recipes.py         --add: a working console, menu or model pasted into a game
  jsonschema.py      --schema: JSON Schemas of the data files, from schema.py, for editors that complete
  demo.py            the demos (engine/demos/clio.json, a game's demo.json)
  editor/            the editor (a page in the browser, also served as a web site)
games/               derelict/  depths/  rootless/
templates/starter/   a tiny complete game to copy (Apache-2.0)
templates/realm/     a tiny complete realm to copy (Apache-2.0)
templates/station/   three simulators with screens of panels to copy: helm, reactor, scan; a wheel menu (Apache-2.0)
game_files/          the original CLIo 1 sandbox
tests/               python -m unittest discover -s tests
utils/               Tkinter data editor (desktop, alpha)
index.html, .nojekyll   the editor as a web site (GitHub Pages serves the repository as it is)
legacy/prototypes/   early dialogue / crafting experiments from CLIo 1
```

`python main.py` still works, as in CLIo 1. Games written for CLIo 1 (`config.json` + scenes /
items / characters / story texts) load as they are; see "Coming from CLIo 1" in the authoring
guide.

## Tests

```
python -m unittest discover -s tests     # 1137 tests, a few minutes
python -m engine.vector                  # the vector display's reel (Ctrl-C ends)
python -m engine.realm templates/realm 8 # a steward plays the realm starter over eight seeds
python tests/bot.py 30                   # an automatic player runs the dungeon 30x per class
python tests/bot.py 30 rogue             # the same in rogue mode: how deep does it get
python tests/bot.py 30 cards             # the same with card battles (the Deck mode)
python tests/levelbot.py 10              # an automatic player walks Rootless's E1M1 ten times
python tests/levelbot.py 10 rootless e1m9  # ...and its secret level
python tests/levelbot.py 10 rootless e1m2  # ...and E1M2, the loader and all
python tests/levelbot.py 10 rootless e1m3  # ...and E1M3, out over the swamp
python tests/levelbot.py 10 rootless e1m4  # ...and E1M4, across the fens to the mast
python tests/levelbot.py 10 rootless e1m5  # ...and E1M5, lockers, fields and the time slice
python tests/levelbot.py 10 rootless e1m6  # ...and E1M6, up the dais and the gallery stairs (the mesh view)
python tests/levelbot.py 10 rootless e1m7  # ...and E1M7, on the ceiling over the overflow
python tests/levelbot.py 10 rootless e1m8  # ...and E1M8, up the face and the shaft to the Metacron
python tests/levelbot.py 10 rootless sim1  # ...and the Simulatron's fens without end (also sim2, sim3)
python tests/levelbot.py 10 rootless sim4  # ...and the Kill House, a room for each kind of squad
```

The tests play the adventure and the dungeon to every ending from scripts, walk Rootless's
levels to their exits (key presses in a redrawn screen and typed commands), check that every
screen fits 40 columns in both Unicode and ASCII (and down to 24), fight packs, run rogue mode
until the bot falls, round-trip saves, and render every sound effect. They write nothing into
the repository: saves and audio go to temporary folders. With `CLIO_PICTURE_LIB` set to a build
of CLIo Picture (and `CLIO_PICTURE_REQUIRE=1`), the picture tests compare it with the Python -
`tests/test_vector.py`'s `LibraryTests` the vector display (library 0.10 and later), scene by
scene and dot for dot. `engine.vector.backend()` says what draws the display here.

## Releasing

Raise `__version__` in `engine/__init__.py`, add a `## x.y.z - date` section to
`CHANGELOG.md`, then push a tag: `git tag -a vx.y.z -m "CLIo x.y.z" && git push origin vx.y.z`.
The release workflow (`.github/workflows/release.yml`) runs the tests, makes the GitHub release
with those notes (each paragraph joined onto one line, as GitHub keeps line breaks in release
notes), the engine as a zip and the editor's web pack, and pushes both to itch.io
(channels `win-linux-mac` and `html5`). It needs the repository secret `BUTLER_API_KEY`
(itch.io → Settings → API keys, the key whose source is wharf); without it the itch.io step is
skipped.

**itch.io's page** plays the `html5` upload in a frame: tick *SharedArrayBuffer support* in its
embed options once - playing needs it (below).

### In the browser

`engine/editor/web/play.html` plays CLIo in a web page: `play.html?game=rootless` (or `depths`,
`derelict`; none: CLIo's own menu; `?demo`: the tech demo; `?edited=ID`: the game the editor's
*Play* handed over - the whole game under its id in IndexedDB `clio-editor-play`, written under
`/edited/ID` and run by its path, without fetching CLIo's own games). Its worker (`play.js`) runs Python
compiled for the web (Pyodide, from jsDelivr), writes the engine, `clio.py` and the games into
it (the manifest's `engine` and `play` lists) and runs `engine/web.py`, which gives the engine
what a terminal gives it on a desktop: standard input and output that are a terminal, a stand-in
`termios`, `select` and `os.read` on the keys, `time.sleep`, the terminal's size, a sound backend
(WAVs to the page's WebAudio, each sent once) and the data folder's writes reported (the page
keeps saves in IndexedDB and hands them back next visit). The page shows the terminal with
xterm.js (jsDelivr; its WebGL renderer draws blocks and braille exactly).

The keys go through memory the page and the worker share (SharedArrayBuffer), so a game waits
for a key as in a terminal (32 bytes of counters - bytes written, bytes read, columns, rows, and
how often the terminal changed size, which makes the next frame whole: a phone's keyboard shrinks
it and gives the size back, and its rows have moved all the same - then the keys' ring). That
needs a cross-origin isolated page: itch.io's
*SharedArrayBuffer support*, or the headers `Cross-Origin-Opener-Policy: same-origin` and
`Cross-Origin-Embedder-Policy: require-corp` from the server; on a host that cannot send them
(GitHub Pages) `coi.js`, a service worker, adds them and the page reloads once. In a frame that
is not isolated the page offers a tab of its own. `?pyodide=` and `?npm=` take Python and
xterm.js from elsewhere (a local copy); `?renderer=dom` leaves WebGL out (to compare, where a
phone's GPU garbles the glyph cache: each colour pair of a picture's cell is a glyph there). `tests/test_web.py` runs the games on a page made of a
script; in a real browser:

```
python3 -m http.server     # plus the two headers, or try GitHub Pages' way: coi.js does it
```

The optional libraries are released from their own repositories; CLIo follows one release of
each (`RELEASE` and `SHA256` in `engine/picture/fetch.py` and `engine/audio/ballistic/fetch.py`,
sizes in `engine/downloads.py`).

CLIo Motion is carried, not downloaded: `engine/motion/clio_motion/` is a copy of its Python
package (pure Python, the characters and their rigs as JSON beside it), which the engine does
not change. A newer one is brought in from a checkout of
[clio-motion](https://github.com/eryxgames/clio-motion) with
`python tools/clio/carry.py PATH/TO/CLIo` (`--check` says whether the copy here is that
version), then `python -m engine.editor.hosted` and the tests here.

Its C core is optional, as CLIo Picture is: `engine/motion/clio_motion/native.py` loads
`clio_motion.dll` / `libclio_motion.so` / `.dylib` from `CLIO_MOTION_LIB`, `engine/motion/lib/`,
the folder `--get-motion` fills or the system, checks it against the Python, and bodies run live (`engine/motion`'s `Actor`)
are then stepped in it. With `CLIO_MOTION_LIB` set, `tests/test_motion.py`'s `TheCCore` compares
the two; without it those tests are passed over. `--get-motion` (`engine/motion/fetch.py`) is
`--get-picture` again: the zip for this machine from the release CLIo follows, its SHA-256
against the one noted in `fetch.py`, the library and its LICENSE and NOTICE into the data
folder, then the same check against the Python. (With `SHA256` there empty CLIo would follow
no release: `--get-motion` then says how to build the library and the launcher's Downloads
leaves it out.)

**Following a release** of CLIo Picture or CLIo Motion is one command, once the release has
its files:

```
python -m engine.follow motion 0.25.0    # or: picture 0.10.0; --check only says what would change
```

It reads the release's `checksums.txt`, downloads every zip, checks each against that list and
that the library is where `--get-...` looks for it, and writes `RELEASE`, `SHA256` and the
sizes the launcher quotes (`engine/downloads.py`) - or nothing, if any zip is not right. Then
the tests, and commit. `tests/test_follow.py` fails if the committed tables are not as the
script writes them (the sizes were once left from an earlier release).
