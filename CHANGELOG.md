# Changelog

Notable changes to CLIo. Versions follow [semantic versioning](https://semver.org).

## Unreleased

### Added

- **Realms: strategy by turns** (`engine/realm.py`, `realms.json`, a scene's `"realm"`): a hold
  and its people, a season at a time. Stocks; people who eat, grow while there is room and leave
  when they go hungry; works that are built, staffed by the hand and yield by formulas; findings
  learned once; one order to build and one to find a season; a calendar and a sky ("tides") that
  is the same for a seed whoever asks and is told seasons ahead; events with choices; threats
  that are sighted before they come, shown with their strength, the defence as it stands and the
  odds in words. Every number may be a formula (the simulators' formulas) over the stocks, the
  works and their hands, the season's and the tide's names, flags and the realm's own values.
- A realm is played at the prompt (`end`, `build`, `find`, `put 3 fields`, `works`, `sky`,
  `news`, `save`, `load`), fits 24 columns, and is saved with the game: a load goes on from its
  season, and the title screen names it. A season is a turn of the game (triggers and quests are
  looked at after each); a realm's effects can run the game's own (`{"game": [...]}`); its end
  runs the scene's `on_realm_won`, `on_realm_lost`, `on_realm_quit`, or ends the game.
- **The steward** (`python -m engine.realm GAME [REALM] [SEEDS]`, and `steward N` at the
  prompt): a player that tries hands and orders on copies whose luck is not the luck to come, a
  year ahead, for the realm's `score`; it says how a realm stands over some seeds.
- `--check` checks realms (formulas and what they read, stocks and works named, effects, events,
  threats, names used twice); `--level ID` starts a game in the scene that plays realm ID; the
  editor lists `realms.json`.
- **`templates/realm`**: a realm starter to copy - a village at a ford through sixteen seasons.
- **Vector displays** (`engine/vector.py`): things in three dimensions drawn in lines, as the
  terminals of old films drew them - as a wire frame (every line) or solid (hidden lines removed:
  faces are filled into a depth buffer and a line shows only where nothing is in front of it, so
  one thing hides another and ground hides what lies behind a hill). Shapes: box, grid, ring,
  gate, tube and cone, globe, ground from heights (a net, or profiles one behind another), orbit,
  any polyline, and CLIo's own 3D models as outlines (`from_model`). A camera with a field of
  view and roll; lines cut at the eye and at the display's rim. The display (`Scope`) draws in
  braille dots, or in strokes (`─ │ ╱ ╲ ┼`, in ASCII `- | / \ +`) for a terminal without braille;
  a colour a line, brighter where lines cross, dimmer with distance, an afterglow that fades over
  the next frames, a faint glow behind lit characters; lines and circles on the glass, words over
  the picture and words that follow a point in space. `python -m engine.vector` plays a reel (a
  hauler, an approach corridor, an orbit, a surface scan); `python -m engine.vector scan 3.5`
  prints one picture.
- **Cues: screens that move with the sound** (`engine/cues.py`). A cue sheet says what happens
  when in a track - named actions with a time, a length, an amount and a shape - and a screen
  asks it for their levels at the sound's own time; nothing is listened to while a game runs.
  The sheet is [Playhead](https://github.com/eigensoundlab/playhead)'s (`playhead-cues`): made
  by Playhead from a recording when the game is built and put beside the file
  (`bridge.cues.json`), or made here from a song's own notes (its kicks, snares, hats, beats,
  bars and parts) by the same kind of rules - a song's `"cues"`, or the usual ones. The track
  that is playing has a clock and a sheet: `audio.clock()`, `audio.cues()` (`cue_offset` evens
  out a slow player). The vector reel ends with "signals", which moves to its track. `--check`
  checks a song's cue rules.
- **Menus** (`engine/menu.py`): a menu is said once - things to do, other menus, and values
  (on or off, a slider, one of a few, a typed line, a key), each with a hint, a note, a key of
  its own, a condition to be there and a reason it cannot be chosen now - and shown in a
  **look**: `bar` (a lit line that moves, in the theme's frame), `tabs` (pages across the top),
  `find` (a long list narrowed by typing), or `lines` (numbered lines answered by typing, which
  every terminal, a pipe and a reader can take and the others fall back to). In a game that
  scrolls it is a few lines redrawn in place; over a frame kind's picture it is a box, the
  picture dark behind it, with clicks, taps and the wheel (not on Windows yet).
- Every game has **`options`** (sound and screen as pages of values, heard and seen as they
  change) and **`menu`** (resume, options, save, load, help, leaving - which asks first). In a
  first-person level `Esc` opens it over the picture; a realm has both at its prompt.
- A game's own menus are data: **`menus.json`**, opened by the effect `{"menu": "camp"}`. Items
  run effects, are there `when` a condition holds, are `locked` with a `why`, ask first with
  `confirm`, come back with `again`, and keep values in a `var` or a `flag`. `--check` checks it.
- Lists of choices (dialogue, shops, "which do you mean?") stay typed numbers unless asked:
  `"menus": "bar"` in `game.json`, `--menus bar`, a theme's `ui.menus`, or the player's choice
  in `options`. `python -m engine.menu [THEME] [--over]` shows the looks on a terminal.
- **Menu frames**: thirteen of them - `single`, `rounded`, `double`, `dos`, `heavy`, `block`,
  `cut`, `dots`, `ascii`, `corners`, `brackets`, `rule`, `none` - each with `shadow`, `center`
  and `caps` if asked (`"border": "double shadow"`). A menu names its own, an item the frame of
  the items under it, a game its house frame (`"menu_border"`), a theme its usual one
  (`ui.menu_frame`), and the player may pick one in `options`. A font without the characters
  gets the nearest. `python -m engine.menu --borders` shows them all.
- **Three more looks**: `line` (the title in letters of heavy lines, rules, a rail with an arm to
  the cursor), `terminal` (a console's functions with how each stands - READY, RUNNING, LOCKED,
  ARMED - and soft keys F1... on a strip) and `cards` (tiles in rows, a picture on each if it
  has one, the arrows going four ways). `"menu_look"` in `game.json` gives a game's own menu and
  its lists of choices one of them.
- **Held to be done** (`"hold": true`): the first Enter arms a thing, holding Enter fills a bar
  and does it, Esc lets go - for what cannot be taken back. Where answers are typed it asks.
- A banner style **`line`**: letters of heavy lines, three rows high (the alphabet of the line
  look). Heavy joints and line ends are drawn double in the Windows console's font, as heavy
  lines are.
- **Panels** (`engine/panels.py`): a screen of instruments - the bridge of a ship, an
  engineering console. Panels stand side by side or one over another, each in a frame (the
  menus' frames) with a title and a phosphor colour, each with widgets that show values by
  name: `gauge` (with parts of the way where it turns amber and red), `center`, `control`
  (with its keys), `number` (`big`: in letters of lines), `compass`, `lamps` (lit while a
  formula holds), `text` with values in it, `plot` (lines over time, in dots), `scope` (a
  vector display: a scene, or one of the game's 3D models turning in lines, drawn from the
  ground up as far as a value says and solid when whole), `map`, `rule`, `space`. A frame can
  brighten with a cue of the music (`"pulse": "bar"`).
- **A simulator's own screen**: `"panels"` in a sim lays its screen out this way where there is
  room (60 columns), and as ever where there is not; the word in the middle (ready, paused,
  how it ended) lies over the panels. `--check` checks the layout and the names in it.
- **`templates/station`**: a station starter to copy - a bridge with three consoles, each a
  simulator with its own screen: the helm (a hopper flown to a pad, with its map), the reactor
  (a core brought to power) and the scan (a beam held on a drifting target while a mast comes
  into the scope). The autopilot wins all three.
- **Views** (`engine/viewer.py`): one thing seen several ways. A 3D model: `shaded` (its
  materials under a light), `wire`, `solid` (hidden lines removed), `structure` (what is
  inside: each group of parts in its own colour, the hull faint, and a `cut` that takes the
  near part away along an axis), `plan` (from above, as a map; floor by floor with `levels`
  and `level`) and `heat` (each group in the colour of a value, the hull seen through). A
  **planet** (`planets.json`: a field of ground from pole to pole, a legend, a tilt, a sun,
  sites): `surface` (lit, with its night side), `heat`, `grid`. A panel's scope takes a
  `view`, and there is a `planet` widget; values, the cut and the level can be names, so a
  screen shows a ship's heat or its decks as they are.
- **`clio.py GAME --view-model [NAME]`**: a viewer for a game's models and planets (arrows,
  `+` `-`, `V` for the view, `C` to cut, `L` for levels, Tab for the next);
  `python -m engine.viewer FILE.glb` looks at a glTF file; `--print VIEW` writes a picture.
- The station starter has a hauler with decks, a hold, a reactor, a bridge and engines, and a
  moon: the reactor console shows the ship by its heat, the scan console the moon below and a
  deck plan. A panel's solid scope now hides the lines behind (it drew them all).
- **Functions** (a simulator's `"functions"`): what a console does when asked, each at a key
  of its own - at once (vent the steam), when the key has been held for `hold` seconds (a
  scram, a beacon deployed: the line fills as it is held and falls back when it is let go), or
  switched on and off (`toggle`). A function can be locked until a formula holds (`if`, with
  `why`), stay on for `lasts` seconds, need a `cooldown`, and run out (`uses`). Done, it sets
  and adds to controls, stocks, fuel and damage (`set`, `add`), keeps them where it wants them
  while it is on (`keeps`), says a line and plays a sound; formulas read it (`scram`: 1 while
  on, `scram_done`, `scram_left`, `scram_wait`, `scram_charge`). It works off the keys of a
  tick alone, so a run still plays back the same.
- A panel lists them with **`{"functions": true}`** (or some, by name): key, name and state -
  READY, LOCKED, held so far as a bar, ON with the seconds left, WAIT, SPENT, or words of the
  function's own - in its `tone`, the line lit for a moment when it is done. Without panels
  they are in the column of instruments; typed, a function is asked for by its name
  (`scram`), held as long as it takes. The key line names them.
- After a simulator, what was done at its console is the game's: the flag `<sim>_<function>`,
  the function's own `effects`, and the counts in the variable `sims`.
- The autopilot tries a systems simulator's functions ahead with its controls (one at a time),
  and does one marked `"pilot": true` as soon as it can - so a simulator that is only done by
  a function is still proved. `--check` checks functions: keys taken twice or by the vehicle,
  a control or the simulator; names that are values already; formulas and what they read;
  what `set`, `add` and `keeps` may change; a hold a tap would do.
- A panel's planet takes `"sites"` of the screen's own, each shown while its `if` holds (a
  beacon, once it is down); a site at a planet's edge has its name before its mark, not cut
  off. While a simulator with panels has not begun or is paused, its screen is dark behind the
  words.
- **The ring look** (`"look": "ring"`): two to eight things round a dial drawn in dots, a
  needle that swings to the one the cursor is on (0.18 s, the short way round), its part of the
  rim lit; left and right go round. A slider, a switch and a thing held to be done fill a
  circle inside the rim; what is locked has a dotted rim, and the reason is shown while the
  cursor is on it. In the text and over a picture; a click on a name chooses it. Where there
  is no braille (the Windows console's own fonts, the Linux console, safe glyphs, ASCII), no
  room, more than eight things, or typed answers, it is a bar. The station starter has one:
  `bay` on the bridge (`menus.json`). `python -m engine.menu` has a Launch bay to try.
- In the terminal look, a thing that is locked says `LOCKED` whatever its `state` (it kept
  saying `READY`).
- The station starter's consoles do things: the reactor vents steam and scrams (hold `X`); the
  scan narrows its beam (faster, and less forgiving) and is done by deploying a beacon (hold
  `B`) once the picture is whole - it descends, and is named on the moon below; the helm
  flushes its coolant.

## 3.5.2 - 2026-11-23

### Added

- On a phone the browser page plays with taps, as Termux does: the picture's left and right thirds
  turn, its bottom corners strafe, the top of the middle steps, the centre fires, the bottom uses,
  a swipe up or down steps forward or back (the page reports a finger's drag as the wheel, which
  xterm does not), the status line readies the next weapon (`--touch on` on touch screens).

### Fixed

- On a phone the keyboard no longer opens with every key under the picture: the terminal's input
  field keeps no focus there unless *abc* asked for the keyboard (or a real keyboard is typed on).
  A phone opened its keyboard whenever that field had the focus, which xterm takes on every touch,
  whatever `inputmode` said; and *hide* gave it the focus back.

## 3.5.1 - 2026-11-22

### Fixed

- On a phone (the web page, itch.io's too) the keys under the picture work while letters are left in
  the command line - a phone's keyboard can leave them there, and the game took no moves while a line
  was half typed: moving and firing clear it first (Ctrl+U). An arrow held down walks on, a step at
  a time as the game takes them. A tap on the picture no longer opens the phone's keyboard, which
  covered those keys; *abc* opens it, *hide* closes it.
- The page's terminal says how often it changed size, and the next frame is drawn whole: a phone's
  keyboard or address bar shrinks the terminal and gives the size back, and the rows that moved
  showed as stripes and stray blocks in the picture, the status line and the messages until the
  next key. Its WebGL glyph cache is cleared then too, a lost WebGL context (a phone taking its GPU
  back) leaves the plain renderer drawing, and `?renderer=dom` plays without WebGL, to compare.

## 3.5.0 - 2026-11-22

### Added

- **The mesh view** (`engine/mesh.py`; `--render mesh`, `"render": "mesh"` in a level or in
  game.json's `first_person`): rooms in a true perspective, as open land is drawn - walls,
  floors, ceilings, steps and lintels as faces filled pixel by pixel, each pixel keeping its
  distance so that monsters, items and models are hidden by what stands in front of them.
  About 11 ms a picture in Python at 110 columns (30 in braille).
- **Floors and ceilings at heights** in rooms: `"height"`, `"ceiling_height"` and `"step"` (the
  risers' tile; the engine's own `step`) in a map's legend; a level's `"climb"` (0.55) is the
  highest step walked up, by the player and by monsters, whose ways go round a ledge by the
  stairs. The eye rises smoothly up a stair. `--check` checks them; the editor's cell form
  has them.
- **CLIo Picture 0.7** draws the mesh view when it is installed (`clio_frame_rooms`): at 150 x 34,
  E1M1 in 3.2 ms (21.7 in Python), 5.0 in braille (52.2). Every face and floor kind is compared
  with the Python's picture, to the pixel (`tests/test_mesh.py`'s features room).
- **Looking up and down, and turning, in the mesh view**: Shift+Up and Shift+Down (or Ctrl, Alt;
  `look up`, `look down`, `look`), two steps each way, free as turning is; a turn is drawn at
  angles between the two facings instead of sliding. CLIo Picture 0.7 draws both.
- **RØØTLESS SIM-12 Stairwell** (`--level sim12`): a hall with a skylight, stairs up to a
  mezzanine, a pump pit, a low passage and a ramp down, drawn as a mesh; in both demos, with a
  "MESH VIEW" card and E1M1 as a mesh in CLIo's (a clip's `"render"`).
- The level bot goes round steps it cannot climb.
- The mesh view, finished for CLIo Picture 0.7: bullet holes on its walls; `"detail": "low"`
  draws its floors and ceilings at half width; magboots up a wall turn the whole view (drawn
  bigger and cut to size, so the rooms fill the corners); heights count for line of sight (a
  ledge, a block as high as the chest or a low ceiling hides; from a gallery one sees over);
  the editor's look from a cell shows classic rooms or the mesh view.
- Terraces on open land: a map cell with `"height"` on a level with `"land"` stands that much
  over the pad - steps, platforms - walked up within `"climb"` (the Python draws them).
- **RØØTLESS E1M6: Kernel Space**, after E1M5: a hall of many floors in the mesh view - a
  gallery a storey up, the scheduler's dais in tiers with your crontab on top, the interrupt
  well, a crawlway under a low ceiling. In the RØØTLESS demo and the tech demo.
- **Magboots on the ceiling**: plating up to the ceiling (`"mag_ceiling"`) takes the player on to
  a plated ceiling (`"ceiling_mag"`), and the world is drawn turned half round - exact and as
  cheap as any picture, in the classic and the mesh view. Up there he walks over acid, fire,
  drops and monsters (out of reach of bites in a tall room); switches, exits, lockers and panels
  marked `"high"` are reached only from up there; hatches (`"hatch"`) lead up to the deck above
  and down again; letting go (F3) drops him on to what is below; an event can cut a ceiling's
  power (`"mag_off_on"`, `"mag_delay"`). Keys follow the screen. The level bot walks it too.
- **RØØTLESS E1M7: The Stack**, after E1M6: the overflow hall crossed on its ceiling (hornets
  come up there), a switch reached only from it, a drop to a door, a corridor whose plating dies
  behind you, and a hatch up to the return address - and a first look at Aspiration Central.
- **RØØTLESS E1M8: Aspiration Central**, the episode's end: a street at night in the rain, the
  Metacron's glass face climbed in magboots while glass falls from its broken windows, the broken
  lift shaft inside (the stuck car passed on the far wall, a counterweight dropping), and the
  spire's top, where the Metacron - the scheduler of schedulers - waits under a broken dome.
- **Walls walked as floors**: map cells can say which way the world's up is (`"world_up"`) - a
  building's face, a lift shaft walked on magboots. The sky is drawn all round (the city far
  below one way, the sky the other, the horizon between), and shows past the face's edges;
  things fall the world's way down (`"falls"`: glass, a counterweight that fills a shaft),
  dropped by cells that `"sheds"` them; the boots stay on; rain blows across.
- **Light and weather**: a level's `"lights"` (ambient light and its tint, changes by events with
  an alarm's pulse, a day going round with a sun and a moon) and lamps on map cells (colour,
  reach, power, flicker, switched by events); its `"weather"` (clear, rain, storm with lightning
  and thunder, snow, fog, dust; a cycle by beats, changes by events). The mesh view and open land
  light each pixel by its place and fog it by its distance; rain and snow fall only under open
  sky; the classic picture is lit as a whole. Fog shortens sight both ways; in the dark a monster
  further than two cells is not seen without the goggles. In RØØTLESS: E1M6 and E1M7 lit, rain
  through SIM-12's skylight, weather and a day on SIM-1's fens.
- **Surfaces lit by their materials** (`engine/surface.py`), where a level has light or weather
  (or `"surfaces": true`): a tile's `"material"` in tiles.json - `"metal"`, `"rough"` (glTF's
  metallic-roughness, as the models'), `"reflect"` for floors, `"glow"` for its palette's letters
  that give light. The mesh view keeps a G-buffer - what each pixel shows, its material, its
  distance - and lights it: ambient by the player's view, lamps by how far across and how the
  surface is turned to them, GGX highlights (a metal's in its own colour; the player's own light's
  sheen on metal ahead); glowing texels, shots, flames and glowing model materials keep their
  light in the dark; floors mirror what stands on them, dimly (Fresnel, smeared on rough floors);
  rain wets floors under the open sky (they mirror more, trembling) and splashes on the ground,
  open land too. `"wet"` wets a whole level. RØØTLESS's tiles have their materials (lit windows
  on Aspiration Central, the plating's strips, the racks' lights, water and wet paving). Models
  are lit by the level's lamps too, each triangle by its own normal.
- **CLIo Picture 0.8** does all of it in C, to the same pixels as the Python: the G-buffer, things
  marking it, the lighting, reflections and splashes (`clio_frame_more`, `clio_frame_surface`) -
  E1M8 at 160 x 45 in 8.5 ms (46 in Python), E1M6 in 6.8 (42) - and the mesh view's low detail,
  terraces on open land (`clio_land_terraced`), the picture turned over on the ceiling
  (`clio_frame_flip`) and turned up a wall (`clio_tilt`). An older library leaves lit levels and
  terraces to the Python.
- **Slopes**: a cell's `"slope"` (the way it rises) and `"rise"` tilt its floor, `"ceiling_slope"` and
  `"ceiling_rise"` its ceiling - ramps, a sewer tube's sides. Steps are measured where cells meet
  (a ramp's foot is level, its sides are steps), a slope rising more than 1 is too steep, the eye
  follows the plane, monsters walk ramps. The mesh view draws sloped floors, ceilings and the
  sloped edges of the faces beside them - CLIo Picture 0.9 too, to the same pixels
  (`clio_frame_rooms2`; SIM-13 at 160 x 45: 62.8 ms in Python, 18.4 with it; an older library leaves
  slopes to the Python). The editor's cell form has them.
- `--get-picture` (and the launcher's Downloads) installs **CLIo Picture 0.9.0** - it was 0.6.0 -
  checked by its SHA-256, for Linux, macOS, Windows and Android (Termux).
- **Wet slopes**: a `"wet"`, slick or oiled slope - or one out in the rain - slides whoever steps on
  it down to its foot (up it: back down; off an edge: a fall). Magboots grip.
- **Jumps**: where a level says `"jump"` (`high`, `far`, `double`), `jump` (F7, `+`) leaps up on to a
  ledge or over a gap, `jj` (F8) jumps again in the air - twice as high, a cell further. A beat each;
  an arc under the ceiling; a hard landing hurts. Not in a suit, a machine, water, on the jetpack or
  the ceiling.
- **Gaits**: the view moves with each step - a pressure suit (`"power": "suit"`) treads heavily (the
  eye rises and falls, sways to the foot coming down, the hands with it); a walking machine
  (`"gait": "mech"`, its own `"climb"` and `"eye"`) shakes as each foot lands; `"headbob": true`
  bobs an ordinary walk. Cells with `"vacuum"` hurt without a suit or a `"sealed"` machine, and no
  rain falls in them. The loader and the hopper keep their ways.
- **RØØTLESS SIM-13: Proving Ground** (`--level sim13`, a free program): a ramp to a gallery, a sewer
  tube, a wet slope into a yard in the rain, pits and a ledge to jump (and jump twice), a pressure
  suit for a vacuum deck, the mechwalker (a new model) up on to its platform.
- **Play in the browser** (`engine/editor/web/play.html`, `engine/web.py`): every game and the
  tech demo in a web page, the engine unchanged in Python made for the web (Pyodide) - a
  terminal on the page (xterm.js), keys shared with the game's worker, sound through WebAudio,
  saves kept in the browser, keys for phones under the picture. The site's first page (and
  itch.io's) offers the games and the editor. Needs a cross-origin isolated page: itch.io's
  *SharedArrayBuffer support*; on GitHub Pages a service worker (`coi.js`) does it.
- **Play from the editor**: on the web, *Play* (beside *Save*) plays the game you are making, as
  last saved, in a tab of its own while the editor stays open - save again and *Restart* there
  plays the new version. Inside itch.io's frame it plays in the frame, and *Back to the editor*
  opens the game in the editor again. With `--edit`, *Play* gives the command for a terminal.
  *CLIo's games* leads from the editor to the games, and the editor's first screen offers them.

### Fixed

- Run natively on Windows (as the tests do), the web page's saves and libraries stay in the page's own
  data folder - they went to the player's `%APPDATA%\clio`, as Windows has no XDG folders. The test
  of the terminal's glyphs no longer assumes it isn't Windows' own console.
- Ctrl+C while CLIo's menu waits (or between demo clips, or over the logo) ends CLIo cleanly - the
  terminal as it was, exit code 130 - instead of leaving a Python traceback (seen in Termux).

## 3.0.0 - 2026-11-21

CLIo 3: from text adventures to a first-person shooter, in the same terminal.

**What's new, for players**

- **RØØTLESS**, a third game: a first-person shooter drawn in pixel blocks (or braille), a
  beat at a time - five levels and a secret one, monsters with brains that take cover and
  work in squads, vehicles to ride and fly, open land to the horizon, 3D-modelled drones,
  lockers and supply crates, force fields, and a boss on a crontab.
- **A simulatron of other kinds of game**, all in RØØTLESS: a platformer, an arcade shooter,
  real-time strategy against the computer, a flight simulator, a reactor to keep in bounds,
  card duels, levels without end, and a test course for magboots, jetpacks and submarines.
- **Demos that play themselves**: CLIo's tech demo from the launcher, each game's own from its
  title screen - or left alone for a while.
- **Phones**: tap and swipe in RØØTLESS, a row of game keys for Termux, and optional
  downloads from the launcher that make the picture several times faster.
- **Windows**: the old console's fonts are drawn for, so no more question marks.
- **Saves inside levels**, real time if you want it (`--realtime`), and physically modelled
  sound for shots and blasts (`--sounds ballistic`).
- **For game makers**: the editor paints first-person levels and monsters, grows monsters on a
  body plan, imports 3D models from Blender, and checks that a level can be finished.

The details follow.

### Added

- **First-person levels** (`levels.json`, a scene's `"level"`). A map of characters with a
  legend: walls in four textures, doors, doors that need the r, w or x key, toxic floor,
  secrets that open to a punch or a shot, an exit switch. **Events** tie a level together:
  stepping on a cell or taking an item opens walls and doors, slams doors shut and wakes
  monsters (closets, traps, sealed arenas). `on_level_exit` in the scene says what follows.
  Health, armour, weapons and ammunition go on to the next level; each level's kills,
  items, secrets and beats are kept in the variable `levels`.
- **Monsters for levels** (`monsters.json`): `hitscan` (takes aim a beat, then fires),
  `projectile` (fire that flies and can be side-stepped), `melee`, `spawner`, `barrel`,
  and `cron`, a boss that works to a crontab - fire raining on patterns of the floor,
  marked a beat ahead, and monsters forked - that turns faster when hurt and can escape
  instead of dying (`escape`, which sets off an event). Monsters wake on sight, on
  gunfire they hear, when hurt or on an event, and fight each other when one hurts another.
- **Pick-ups and weapons**: items with a `pickup` block (health, armour, ammunition, keys,
  weapons, `sudo` - nothing hurts for a while, `boots` - toxic floor does not hurt for a
  number of beats spent on it), and `first_person` in game.json for the
  weapons (fist, pistol, shotgun with pellets, chaingun with bursts) and the player's start.
- **The picture**: walls in perspective with textures, a floor and ceiling that stay put
  as the player moves, sprites drawn smaller with distance and hidden behind walls, the
  gun in the player's hands, muzzle flashes, fire, blood, hits that shake the picture,
  an automap (Tab). Three styles: `pixel` (half blocks), `dots` and `dots-fill` (braille).
- **Frame mode** (`engine/frame.py`, `engine/keys.py`): on a real terminal a level has its
  own screen, redrawn in place, with the prompt on the last lines. Keys act at once while
  nothing is typed: arrow keys step and turn, Ctrl/Alt/Shift+arrows or `,` `.` strafe,
  Space fires, Enter uses, Tab shows the map, 1-7 choose a weapon, the numpad works with
  NumLock off; `"keymap"` changes them. Anything else is typed as a command. The picture is
  drawn again as soon as the window changes size, on Windows as on Linux and macOS.
  Piped, with `--scroll` or on a screen under 40 x 18 a level is played in scrolling text.
- **Commands joined as in a shell**: `a; b`, `a && b`, `a || b`, `!!`, `!3`, `alias`; a
  surprise stops the rest of a line. `ps`, `man`, `kill -9`, `history`, `whoami`.
- **Far versions of sprites** (`lod`, `keep`): far away a sprite is drawn from a smaller
  drawing that keeps the pixels that matter (the letters in `keep`, then the rarest
  colours). The engine makes them when a level starts; a sprite can have its own.
- **Monsters grown on a body plan**: `sprite.monster(seed, body, size)` - biped, beast,
  floater, crawler, brute - with eyes kept in the far versions.
- **Things that move**: crates to push (cover from shots; pushed into acid they sink and
  make a step), pressure plates that hold doors and walls open while something heavy
  stands on them, teleporter pads (the picture dissolves into braille dots and back),
  lifts between two places (a ride in dots, the shaft going by) and a level ending in a
  lift (`exit_ride`), secret areas counted when entered. A barrel's blast throws crates
  and monsters a cell away; the shotgun at point blank throws its target back; monsters
  burn on toxic floor. In the picture only, drawn from dice of their own: debris, gibs,
  sparks, acid splashing, spent cases, items bouncing out. TTY goggles (`power:
  "goggles"`): the level in green braille dots, secret walls showing. `push`, `plate` and
  `lift` sounds.
- **Floors and fire**: slick floor (`;`, `"slick"`) - the player, a pushed crate or a
  rolled barrel slides on until something stops it, picking up what it passes; oil (`:`,
  `"oil"`), slick and burning - fire runs along it a cell a beat and leaves it scorched;
  fire that stays a few beats on a cell and hurts what stands in it (`fire_damage`), set
  off by blasts, flamethrowers and monsters whose tanks burst; belts (`"conveyor": "e"`)
  that move the player, crates, barrels, monsters and items a cell a beat. Barrels roll
  when walked into. Monsters take teleporters, and count a pad as a step on their way.
- **New kinds of attack**: `flame` (levels its nozzle, then sprays fire three cells along
  a row or a column), `spinup` (a minigun that spins up for beats, then fires every beat
  while it sees you), `move_every` (heavy monsters that move every other beat), `dodge`
  (a chance to sidestep a shot seen coming) and `burst_fire` (a death that burns).
- **A secret exit**: `{"exit": "secret"}` runs the scene's `on_secret_exit` instead of
  `on_level_exit`.
- **Monsters that walk and aim**: while a monster moves it shows its steps - made by the
  engine from its standing picture, or drawn (`"walk"`); while it takes aim and fires,
  its `"attack"` picture; its shots flash at its `"muzzle"`.
- **Melee weapons**: one key can hold several weapons (`"key"`; pressed again, the next
  on it; a weapon can also be typed by its id). Melee options `accuracy`, `shove` (throws
  the target back) and `stagger` (a bitten monster loses its turn); `ready_sound`.
- **An end screen** (`"end_screen"` in game.json): a won game of levels ends on a screen
  of its own - banner, pictures (side by side, or taking turns: `picture_every`; as big as
  `picture_lines`), the totals counting up, the ending, what comes next, credits and a
  crontab line still ticking. In the editor it is part of the Game form, drawn as the
  game draws it.
- **Sheets of pictures**: the monsters with their steps and attack, every sprite, or the
  tiles, on one PNG with an atlas (JSON, the form many engines read) - from the editor
  (*A sheet of pictures…*) or `--sheet monsters|sprites|tiles` (`--scale`, `--export`).
  The PNG is written with the standard library.
- **The way back**: an edited sheet is taken back in (the sheet panel, or
  `--import-sheet FILE.png`): only the pictures painted over, checked against the atlas,
  with new colours added to the palettes - a monster's steps and attack too, an engine
  tile becoming the game's own. **From a picture** in the sprite and tile editors makes a
  drawing of any picture file: a pixel picture drawn bigger back to its own pixels, made
  smaller, its colours fewer, its background cleared (the commonest edge colour, or a
  click), dust swept away, an outline if wanted. PNG files are read with the standard
  library (every colour type and depth; not interlaced).
- **Tiles** (`tiles.json`): the walls, floors and ceilings of levels drawn from a game's own
  pictures, in the sprites' format and of any size; a tile named like one of the engine's
  takes its place; `frames` change a beat at a time; clear pixels show what is behind a
  wall. A level's `"floor"` and `"ceiling"`, and a legend entry's, lay them.
- **Weapons** in their own file, `weapons.json` (over `first_person` in game.json).
- **The editor**: *Levels* opens a map painter - the map in its tiles with the monsters
  and items drawn, a palette of the level's characters and the engine's, what each one
  means made with a form (walls and their tiles, doors and keys, secrets, monsters,
  items, events), the level seen from any cell and walked through, and the level bot
  playing it five times. *Tiles* are painted like sprites, from the engine's own if you
  like, and seen in a small room on walls, floor or ceiling. *Weapons* have a form and
  are shown in the player's hands, firing. Under Sprites, *Grow a monster* grows one on a
  body plan, and *Far away, in a first-person level* shows the sprite one to six cells
  away, keeps its far versions to paint over them pixel by pixel, makes them again, or
  leaves them to the game.
- **RØØTLESS** (`games/rootless`), the third demo game: E1M1 *Boot Sector*, a first-person
  level with zombie processes, orphans, daemons, a spawner, barrels, five secrets (hazmat
  boots behind a vent, TTY goggles behind a door a crate must hold open), an acid vat with
  ring-0 armour on an island and a teleporter back, a lift from the boots down to the vat,
  a locked arena and Cron, who rains fire on a schedule and escapes to be the final boss
  of the whole game (the flag `cron_escaped`); the exit is a lift down. A secret exit in
  the goggles' closet leads to E1M9 *Swap Partition*: a belt hall running into acid, an
  oil depot guarded by flamethrowers, a coolant room of slick floor with a crate puzzle,
  and a minigun holding the exit. Five new enemies - shred (flamethrower), kworker
  (dodging gunner), kswapd (heavy gunner), crawler (fast, three red eyes), spinlock
  (minigun) - drawn in the game's own style; the recruit, the game's hero; and two helmet
  portraits (his, and a hazmat mask) taking turns on the end screen. A shovel (E1M1) and a chainsaw (E1M9's closet) share key 1 with the fist. The
  story is framed: a recruit of the Terran Ascendancy Mandate in a simulator pod, his
  first battle simulation. Two riffs, sounds (chip and Ballistic), 41 sprites, a tile.
- `--view STYLE`, `--lines` (every command typed, no single keys), `--scroll`.
  `--check` also counts levels and monsters, and checks their maps and references.
- `engine/levelbot.py`: a simple player that walks a level by its `"bot"` goals - if it can
  finish, a person can (`python tests/levelbot.py`, and in the editor). It plans slides,
  keeps off fire, steps out of a flamethrower's line and ducks a spun-up minigun. 94 more
  tests.
- **Sound sets** (`sounds.NAME.json`): other sets of sound effects over a game's own, chosen
  with `--sounds NAME`, `CLIO_SOUNDS`, `"sound_set"` in game.json, or `sound set NAME` while
  playing (in levels too).
- **Sounds from Ballistic Foley Lab** (`engine/audio/ballistic`): a sound can be one of
  Ballistic's physical models - shots, ricochets, blasts, impacts, arcs, energy fields - with
  its parameters, its finishing for games (`"action": "game"`) and several takes that shots
  in a row take turns with. Node.js renders them in the background into the audio cache;
  `--bake-sounds SET` writes them into the game as WAV files that play without Node; with
  neither, the game's own sound plays. `--check` knows Ballistic's presets and parameters.
- Levels play `hit_body` (a shot or blow lands; a monster's own `sounds.hit` first),
  `hit_wall` (a shot meets a wall, or misses) and `fly_by` (a monster's shot goes wide),
  silent unless a game gives them. RØØTLESS has a Ballistic set for its weapons, hits,
  fire, souls, explosions and Cron: `python clio.py rootless --sounds ballistic`. 17 more tests.
- **Ballistic's C engine** ([Ballistic Engine](https://github.com/eigensoundlab/ballistic-engine)): where its library
  is found (`CLIO_BALLISTIC_LIB`, or `engine/audio/ballistic/lib/`; download it from its releases), Ballistic sounds
  of the kinds it has ported (since its 0.4.0, every weapon, blast and energy kind) render through it,
  in the game's process, without Node.js; Node renders the rest. A field's hum stays a seamless loop. `sound` says
  which renders what. 5 more tests, run when the library is there.
- **Ballistic's game sounds**: `engine.js` follows Ballistic 3603078, which adds liquids, mechanisms (doors, locks,
  switches, turrets), heat, fire, footsteps, creature and robot voices, and handling (pickups, coins, potions). Its C
  engine 0.5.0 follows the same commit; it renders RØØTLESS's weapons and Node renders these until they are ported.
  A level plays `footstep` at every step, silent unless the game or its sound set has one; a step into acid plays
  `wade`, and acid that burns `acid_burn`. RØØTLESS's Ballistic set
  gains 29 sounds: footsteps, wading through acid and acid burning, its doors, secret walls, locks, switches,
  alarm and computer, pickups, coins, healing and boots put on, the player's pain, and the sight, attack and
  death calls of its zombies, orphan, daemon and spawner.

- **TTY goggles on and off**: F2, or `goggles [on|off]` typed (`nv` for short), puts them
  on or takes them off, free as turning is. Their battery runs down only while they are on;
  the line under the picture says `goggles: 12` or `goggles off: 12`, and warns at 5.
- **`detail`** (`--detail auto|high|low`, or `"detail"` in game.json's `first_person`):
  `low` draws a level's floor and ceiling at half width - half their work, which is most of a
  frame - and `auto`, the default, does so only for a very big picture (the goggles' dots in
  a wide window).
- **Rockets and grenades** (weapon kinds `rocket` and `grenade`): a rocket flies the line to
  its target and bursts on what it meets; a grenade is thrown a few cells ahead, bounces back
  off walls, slides on slick floor, rides belts and goes off a beat later. Their **blast** is
  a barrel's - everything within a cell, the player too, thrown back, oil set alight - and
  leaves the floor scorched; grenades next to a blast go off with it. Running out of bullets
  never puts an explosive in the player's hands.
- **Bullet holes**: a shot into a wall, and a shot that misses and goes on into the wall
  behind, leaves a hole in that wall's face, kept in place as the player walks round (the
  last 60 of a level).
- **Vehicles**: a monster with a `"vehicle"` block can be ridden - walk into it to climb in,
  Enter or `out` to climb down. It takes the hits instead of the player, treads on monsters,
  has a claw for a weapon, shoves heavy **containers** (`{"crate": "heavy"}`) that the
  player alone cannot move, wades through acid, fits through no door, and bursts when it is
  wrecked. The picture shows its cage and claws. The level bot can `board` and get `out`.
- **3D models in levels** (`models.json`, `engine/model.py`): a monster, vehicle or item with
  `"model"` is drawn as a low-poly model instead of a sprite - made of parts (box, wedge,
  cylinder, cone, sphere, ring: placed, sized, turned) or a mesh, with glTF's physically
  based materials (colour, metal, rough, glow) lit by a Cook-Torrance light, flat or smooth,
  in the level's fog, with a depth buffer; it faces where it went or whom it aims at, bobs,
  turns, spins groups of parts, plays imported frames (`idle`, `walk`, `attack`), and when
  destroyed breaks into shards that fly, fall and fade. About 1 ms for 200 triangles.
- **The sky over open cells** (`"sky": true` on a cell, the level's `"sky"`): a gradient,
  a sun or a banded planet, drifting clouds, stars and ridges along the horizon - the near
  ones move as the player steps sideways. Drawn once per facing and beat, behind everything.
- **Switches** (`{"switch": event, "label": "GATE"}`): a panel in a wall; Enter throws it
  and sets off the event. Thrown, its lever is up and its lamps green.
- **Balls** (monsters of `"kind": "ball"`): shoved, they roll `speed` cells a beat for
  `roll` cells, crushing what they meet (`crush`), knocking other balls on, setting barrels
  off, breaking hollow walls and rolling through, sinking in acid to make a step, holding
  plates down; shots ping off them and blasts set them rolling. Held by an event, one
  rumbles for a beat and then rolls on its cell's `"roll"` way - a cell a beat behind a
  player who must not stop. Their models turn as they roll. The level bot gets out of
  their way.
- **Machines that fly on fuel**: a vehicle with `"fly"` crosses acid and water; with
  `"fuel"` it needs fuel cells (`"pickup": {"fuel": 12}`), burns a beat of it every beat
  once it lifts, and when it runs dry comes down - `"on_empty": "exit"` ends the level. Its
  `"gun"` fires with Space and never runs dry; `"canopy"` draws a canopy frame and a
  dashboard with a fuel gauge. The status line shows the fuel.
- **`--check`** also checks balls, vehicles' fuel, guns and `on_empty`, fuel items, switches
  (something must listen to their event), `roll` on map cells and a level's `sky`; a ride
  that ends the level counts as its exit. The editor lists **3D models** (models.json),
  draws monsters and items that have a model as a small picture of it, and its map painter
  knows switches, the sky and a ball's roll.
- **A model builder in the editor** (3D models): the model in a small room as a level draws
  it, turned, broken and playing its frames, with its triangles and size; its materials
  and parts as rows to edit (shape, material, group, size, place, turn; copy, mirror, add,
  remove), and *From Blender* to take a `.glb` in. The picture follows every change.
- **Models break into their parts** (`"break": "parts"`, or `"groups"`): a drone's gun and
  plates fly off whole. An imported mesh comes apart where it is not joined.
- **A flying machine's eye is higher** (`"eye"`, 0.74 of a wall's height): more of the
  ground below, a little sway; it rises as the machine lifts off and sinks as it lands.
- **RØØTLESS's Ballistic set** has the sounds E1M3 brought: drones, the hornet swarm, the
  warden, the hopper's cannon, fans, start and stop, fuel, the rolling core, balls and
  the switch.
- **`--import-model FILE`**: glTF 2.0 (`.glb`, `.gltf`) from Blender into `models.json` -
  meshes with their placing, PBR materials, PNG textures and vertex colours as colours per
  triangle, object and skinned animations as frames (`--model-name`, `--model-scale`).
  `--check` checks models and what names them.
- **`python clio.py --get-ballistic`**: installs Ballistic's C engine for this machine - the release CLIo
  follows (0.5.0: Linux x64/arm64, macOS, Windows x64/arm64, Android), checked against the SHA-256 CLIo keeps,
  only the library with its LICENSE and NOTICE, in the user's data folder (`~/.local/share/clio/ballistic/`,
  `%APPDATA%\clio\ballistic\`, or `CLIO_DATA`) rather than CLIo's or a game's. CLIo looks for it after
  `CLIO_BALLISTIC_LIB` and `engine/audio/ballistic/lib/`; `sound` suggests it when no engine is found.
- **Saving in levels**: `save [name]` (F5), `load [name]` (F9) and `saves` in a first-person
  level. A save is the world as the level began and every line played since; loading
  builds the level again and plays them back unseen (a whole level in about a tenth of a
  second), so everything in it comes back as it was. A save notes what the level was made
  of and says when it has changed; one that no longer plays through starts the level
  again. `first_person` `"saves"` limits saves per level and `"autosave"` saves as each
  level begins (what the death menu's "Load your last save" goes back to); a cell with
  `{"savepoint": true}` is a checkpoint. The title screen names a level's save by its level
  and beat. The key reader knows F9.
- **Trying levels out**: `--level ID` starts a new game in the scene that plays a level;
  with `--dev` (or `CLIO_DEV=1`) `*ID` typed in a level goes on to that level as you are,
  `*` lists the levels, and saves are not counted.
- **RØØTLESS E1M2 *Dynamic Loader***: the cargo dock where everything the facility runs is
  loaded first - containers, a belt of crates feeding an acid channel, the w key across it,
  and a cargo loader in its bay; three secrets; the rocket launcher and grenades; its own
  music. E1M1's exit leads there, and so does the secret level's.
- **RØØTLESS E1M3 *Drone Refit Assembly***: where the facility's drones are pressed again
  out of recycled Xantrium. Balls of it to roll into the acid trough (or on to a plate that
  holds a store open), the x key at the top of an ore chute whose hatch lets a Xantrium core
  roll after you, drones in three sizes (scout, hornet swarm, warden) drawn as 3D models,
  three fuel cells, the launch controls - and the X-47B Swamp Hopper, flown out of the
  launch gate over a swamp under an alien dusk until its fuel runs out. Its own music, and
  sounds for drones, balls and the hopper. E1M2's exit leads there.
- **Open land** (`engine/land.py`, a level's `"land"`): hills, lakes and coasts made from a
  seed, drawn in true perspective to the horizon, with the level's map (a camp, a compound)
  set down on flattened ground. The ground is worked out from the coordinates, so it goes on
  past the level as far as the picture reaches. Biomes by height colour it and grow props
  (sprites or models; solid ones are in the way), landmarks stand far off and show on the
  map, `things` and `scatter` put monsters and items about it the same way every time, and
  far things fade into the haze. Deep water and cliffs stop a walker but not a drone that
  floats or a machine that flies; hills hide what is behind them; a flying machine that runs
  dry glides down to firm ground. `--check` checks a land, and the level bot crosses it.
- **RØØTLESS E1M4 *Xantrium Fens***: open country past the refit plant. Fens and lakes of
  toxic water, Xantrium crystals on the hills, a survey camp with a spare hopper and fuel
  cells, a secret on the rocks, and a relay mast to the north-east whose compound holds the
  switch that ends the simulation. Its own music. E1M3's ending leads there; it ends the demo.
- **Levels without end** (`engine/chunks.py`, a level's `"world"`): made a chunk at a time
  round the player. Monsters and items wake near him and sleep where they stand when he goes;
  what changed in a chunk is kept for when he comes back, untouched chunks are forgotten and
  made again the same, and far cells are let go, so a long way keeps little. Two kinds: open
  land without end, with sites (small maps) at fixed places and by chance, and spawns per
  chunk by biome and distance; and dungeons without end, a room to a chunk, deeper the
  further one goes. The same seed makes the same world, `"seed": "run"` a new one each game,
  and saves play back the same.
- **Dungeon floors from a seed** (`engine/levelgen.py`, a level's `"generate"`): rooms,
  corridors, doors, the exit in the room furthest from the start, behind a locked door with
  its key where one can reach it, a secret closet, acid pools, rooms in their own walls, and
  monsters and items by depth - from a game variable, so a scene can go down a floor at a time.
- RØØTLESS: three free programs of the simulatron, made new each run - **SIM-1 Long Fens**
  (the fens without end: camps, ruins, hopper pads and shrines by chance, the relay mast 230
  cells off), **SIM-2 Deep Swap** (floor after floor, each worse) and **SIM-3 Swap Sprawl**
  (rooms without end). `--level sim1`, `sim2`, `sim3`; the demo's last page says so.
- The level bot plans its way in a window round itself in a world without end, keeps out of
  acid unless booted, and picks up what helps on a long way.
- **Saves hold the level's state** (`engine/snapshot.py`). Loading puts it back on the level
  built afresh instead of playing every line again: 0.05 s rather than seconds for a long
  game. The snapshot's digest is checked on loading, and the level plays on exactly as
  before. Nothing is listed as "to save": every part of a level is kept unless it is made
  again when the level is built. Tests snapshot every kind of level half way through,
  play the rest on both copies and compare, and compare the digest across processes, so
  two machines can check they agree (the ground for multiplayer).
- Lines are kept with the beat they were played on. A save asked for during a line is made
  when the line is done (whole beats). Saves keep the last 20000 lines, and old saves
  still load.
- Saves are written whole (flushed to the disk, then put in place) and the one before is
  kept as `.bak`, which loading falls back on if a save is damaged. A rogue run's death
  removes both.
- **Brains** (`engine/ai/brain.py`, a monster's `"brain"`): a monster that weighs, each beat,
  coming at the player, keeping its distance, taking cover and leaning out to shoot, working
  round to his side, falling back when hurt, holding, or searching where he was last seen -
  by how hurt it is, whether he sees it, how far he is and how many friends are near. It only
  knows where he is while it sees or hears him, and only shoots what it sees. Five presets
  (`brute`, `skirmisher`, `soldier`, `heavy`, `coward`) and weights of one's own; `ps` shows
  what each is doing and the manual page how it fights. Monsters without a brain play as before.
- **Squads** (`engine/ai/squad.py`, a level's `"squads"`, `"squad"` in the legend): monsters
  that share what they see, wake each other, follow the strongest, and take parts by the
  squad's tactic - `pincer`, `fire_team`, `hold` (guards by their posts until he comes near)
  and `rush`. `"auto"` squads the brainy monsters that stand near each other; in a world
  without end squads are made a chunk at a time, and spawns can come in packs.
- **A search for games of moves** (`engine/ai/search.py`): minimax with alpha-beta and Monte
  Carlo tree search, stopped by a budget of positions, not by time, and rounding the same on
  every machine - for duels and cards to come.
- RØØTLESS's monsters have brains (kworkers take cover, scouts and orphans flank, wardens and
  minigunners hold their lines, crawlers come at you); its levels make squads of those that
  stand together, E1M4's two relay wardens guard their compound, and SIM-1's scouts and
  kworkers come in pairs.
- The level bot steps out of the line of a gun that takes aim when it is hurt or the gun is
  far, keeps further from acid the more hurt it is, and looks further round when a lake is
  in its way.
- **Tactics that pay.** Cover: a shot at someone beside a wall, crate or closed door that the
  line of fire grazes hits the cover half the time - the player's shots and the monsters' alike;
  walls along a corridor are no cover, the corner one leans out from is. Crossfire: a squad's
  gun is surer for each other gun of the squad on him from another side. Monsters can carry
  `"grenades"` (thrown at one in cover or out of sight, never on their own, three beats to get
  out) and `"mines"` (laid unseen in doorways and by the cover they hold; a mine is an item with
  `"pickup": {"mine": ...}`, seen only within 3 cells, never counted as an item found, set off
  by blasts).
- **Squads that fight as squads**: `assault` (the short guns and claws go in together while the
  long guns pin him down), `sweep` (bounding overwatch: half move, half cover, by turns),
  `ambush` (awake, still and silent until he comes close, then all fire at once) and `swarm` (a
  pack circles until enough of it is near, comes in from every side, bites harder together, and
  scatters when halved). Two more brains, `assault` and `swarm`. A monster's `"squad_tactic"`
  says how it fights in a squad, and `"auto"` squads chain only monsters that fight alike.
  Rooms of dungeons without end and of floors from a seed can hold packs.
- RØØTLESS: **bugrats** (swarm bots: weak alone, a pack is another matter), **gc sweepers**
  (sweep squad soldiers who mine what they hold) and **sigkill commandos** (assault, shotguns
  and grenades); a training program, **SIM-4 Kill House** (`--level sim4`): a room for each kind
  of squad. Bugrat packs roam SIM-1's fens; packs of all three come with depth in SIM-2 and SIM-3.
- The level bot steps out of a grenade's blast, never steps on a mine it has seen, and leaves
  alone items dropped where it cannot stand or under a parked machine.
- **Card battles** (`engine/cards.py`, `cards.json`): a fight played with a deck - energy and
  a hand each turn, a draw and a discard pile, block, strength, weak, exposed, poison, burn,
  bleed, stun, cards that exhaust. Enemies keep their moves and show them with numbers (a
  heavy blow a turn ahead). `"battle": "cards"` in game.json, a mode or a character; decks
  per class; a card to take after each win (the enemy's `card_rewards`, else by rarity and
  class); effects `add_card` and `remove_card`; the `deck` command; `--check` checks cards,
  decks and battles; the editor has a Cards page and its odds play card battles.
- **Duellists**: a character with a `"deck"` plays cards as the player does, choosing each
  one by Monte Carlo tree search over guesses of the hand it cannot see (the visits of a few
  guesses added up). MCTS now asks a state whose move it is (`to_play`), so one side may make
  several moves in a row, and gives its visit counts (`search.mcts_visits`).
- The Hollow: a **Deck** mode - every fight a card battle, a starting deck for each class,
  18 cards of its own, and the Bone Warden and the Hollow King fight with decks of their own.
  `python tests/bot.py 30 cards` plays it.
- **Real time** (`engine/realtime.py`): a fixed-rate clock that runs the ticks it owes (a few at
  most, so a slow machine slows the game rather than making it jump), `Controls` for each tick
  (keys held, pressed, let go), a journal of the keys by tick that plays back the same, and a
  loop for games stepped tick by tick.
- **Key events** (`engine/keys.py`): presses, repeats and releases, from the kitty keyboard
  protocol (asked for, and turned on only when the terminal speaks it; Ctrl-C still stops),
  from the Windows console, or - anywhere else - held keys guessed from their repeats, in
  ticks, so even the guess plays back the same. `--keys` shows what a terminal reports.
- **First-person levels in real time**: `"realtime"` (seconds a beat lasts) on a level or in
  `first_person`, `--realtime [SECONDS]`, and the `realtime [off|SECONDS]` command. A beat
  passes when no key acts in time; typing a line holds the clock; the beats that pass are
  journaled (`.`), so saves play back the same. The footer says REAL TIME.
- **Arcade stages** (`stages.json`, a scene's `"stage"`, `engine/arcade.py`): platformers and
  top-down stages in real time, built from a map of characters - walls, platforms that are
  jumped through from below and dropped through, ladders, spikes, pits, doors and keys,
  checkpoints, chips, hearts, the exit - with runs that speed up and slow down, jumps that are
  lower when let go early, a moment after an edge to still jump and a jump pressed just before
  landing kept. Enemies walk, hop, fly, chase and shoot; jumped on, they are beaten. Goals:
  the exit (with chips), all the chips, every enemy, or lasting out the time; lives, health
  and a time limit. Drawn in half-block pixels with a camera that follows, or a character a
  tile in plain text; piped, a stage is played a typed line at a time. Whole numbers only, so
  a stage's keys play it back the same. `"arcade"` in game.json for a game's own enemies,
  colours, physics and sounds; `on_stage_clear`, `on_stage_fail`, `on_stage_quit` in the scene.
- **The stage bot** (`engine/stagebot.py`, `python -m engine.stagebot GAME`): finds a way
  through a stage without losing a life, and the keys that play its run back.
- RØØTLESS: two arcade sims - **SIM-5: Bus Run**, side on (`--level sim5`), and **SIM-6:
  Purge**, from above with a gun (`--level sim6`).
- **Skirmishes: real-time strategy** (`skirmishes.json`, a scene's `"skirmish"`,
  `engine/rts.py`). A map of ground, rock, water, trees and crystal with up to four sides; workers
  gather crystal and build, buildings train units (queues, paid back when cancelled, rally
  points), units move on flow fields shared by everyone sent to one place, fight what comes
  near, attack on the way, hold, and splash; towers shoot; fog of war. The computer player keeps
  its workers busy, builds barracks, towers and a factory, trains an army in its mix, defends,
  and attacks in growing waves. Kinds and factions as data (game.json `"rts"`). On the screen:
  a cursor, choosing by box, a build menu, a panel with a map of the whole field; the mouse where
  the terminal reports it. Piped, typed commands (`select workers; gather; wait 20`). Ten ticks
  a second in whole numbers: the orders kept by tick play a game back the same.
  `python -m engine.rts GAME` lets the computer play every side.
- **Skirmishes, the rest**: gas, a second resource (`&`, a second cost); **upgrades** made at
  buildings (`"upgrades"`: what they add to which kinds or roles; hit points to those there
  already) and **tech** (`needs`: a building or an upgrade first); **fliers** (`air`: straight
  over anything; `hits` ground, air or both) and **transports** (`carries`: board, ride, set
  down, lost with it); **repair** (workers, for crystal) and **patrol**; **control groups**
  (`G` and a digit; the digit again; twice to go there); groups that keep their shape and the
  slowest one's pace. The computer player puts workers on gas, researches, builds an airfield
  for an air mix, mends its buildings and attacks with what it has when its crystal is gone.
- **Card duels in first-person levels**: a terminal (a switch with `"duel"`) is hacked by a card
  duel before it opens; a monster with `"duel"` is a challenger that waits to be faced. The
  player duels with his health in the level; a lost duel hurts (`feedback`). The duel is
  fought off the level's screen and its outcome is kept in the level's journal, so loads play
  it back without fighting again.
- **Better cards**: `id+` in the deck - a card's own `"upgrade"`, else more of its first
  effect, else cheaper; the effect `upgrade_card` (choose, random, or a card).
- **Card shops**: a shop's card counter - `"cards"` for sale (priced by rarity or `"price"`),
  `"upgrade"` and `"remove"` services. The Hollow's merchant has one.
- **Simulators** (`sims.json`, a scene's `"sim"`, `engine/sim.py`): a vehicle over a map in real
  time - a car (grip, drift, terrain that slows, walls that hurt), a boat, a hover craft (thrust,
  lift, gentle sinking, soft or hard landings, falling when dry) and a plane (throttle, stalls,
  runways) - with fuel and fuel pads, checkpoints in order, landing pads, time limits, and
  instruments as data (bars, centred bars, numbers, a compass strip). **Systems** as data:
  stocks that change by formulas each tick (a small, safe formula language), harming the vehicle
  above a limit, and `win_if` / `fail_if`. **Systems sims** without a vehicle: controls on keys,
  gauges, charts - an economy, an ecology, a reactor. Sines and cosines from a table made with
  whole numbers. Piped, typed keys for seconds. `python -m engine.sim GAME`: the autopilot does
  each one, and its keys play the run back.
- **Mouse reports** (`engine/keys.py`): an SGR mouse report is read as `mouse:B:X:Y` (and
  `mouseup:...`), and the real-time `Controls` carry each tick's events as they came.
- RØØTLESS: **SIM-7: Xantrium Rush** (`--level sim7`), the TAM against the root process - mining
  rigs, troopers, drum gunners and cargo loaders against kworkers, daemons, drones and spinlocks,
  across a toxic channel with three crossings; Xantrium and plasma, hoppers and landers from the
  TAM's hangar, hornets from the root's hive, four upgrades a side.
- RØØTLESS: **SIM-8: Fen Hopper** (`--level sim8`), the hopper flown over the fens through five
  checkpoints to a landing, minding fuel and engine heat; **SIM-9: Coolant Loop** (`--level
  sim9`), a reactor through a shift - rods and pumps against a changing demand.
- RØØTLESS: a hacking deck (ping, firewall, traceroute, fork bomb, kill -9, sudo, grep,
  nohup, chmod 000, fsck, rm -rf, overclock), Black ICE and the Kernel Sentinel, and
  **SIM-10: Root Shell** (`--level sim10`): hack a terminal, then out-deal a sentinel.
- RØØTLESS: **E1M5: User Space**, after the Fens (they lead to it now; it ends the demo): the
  uplink bay behind a one-way door, the barracks (bunks, his own locker six, an alarm locker
  that wakes the sleepers, a locker the r key opens, a hollow wall), the quartermaster's heap
  (supply crates, the r key in one, the armoury behind bars), the syscall gate (a force field
  across the hall, its two MMU emitters shot through it) and the scheduler's time slice (a
  switch opens the door to the kernel lift for 14 beats; thrown again if it shuts). New: the
  emitter, the r key, tiles field (moving), bunk and pod, sprites emitter, supply,
  supply_open, key_r, four chip sounds, music `user_space`, two clips in RØØTLESS's demo and
  one in the tech demo. The level bot finishes it (10 of 10 seeds); it throws a timed door's
  switch again when the door shut before it got through.
- RØØTLESS: a new **shovel**, after the owner's sketch - a pointed spade with a ridge and
  rust, held in a gloved hand, the sleeve from the lower left - and its pickup, the spade
  standing in the floor. Kept for later levels: `w_gauntlet` (an armoured fist), `w_knuckles`
  (taped knuckles) and `w_etool` (an entrenching tool). A sprite's `"scale"` draws a weapon
  in hand with smaller (or bigger) pixels: more detail at the same size.
- **Doors and gates**: lockers in the walls (`"locker": [items]`, opened by walking into them
  or Enter; `"key"`, `"on_open"`), supply crates that open and still stand (`"supply": [items]`;
  pushed, thrown and carried with what is in them), bars seen and shot through (`"gate": true`),
  force fields that throw back whoever walks in (`"field": true`, `"zap"`; off on an event or
  when their emitter dies - a monster cell's `"on_death"`), timed doors that shut again after
  `"open_for"` beats (their switch can be thrown again) and one-way doors (`"from"`). The
  engine's own tiles for them (`locker`, `bars`, `field`, `door_timed`, `door_oneway`, ...),
  the supply crate's pictures, the automap, saves, `--check`, the editor's painter and the
  level bot know them all. Monster attack kind `"none"` (it only stands there).
- **Downloads** in the launcher (`engine/downloads.py`): CLIo Picture and Ballistic's C engine
  for this machine, each with its size and source, asked about first and fetched only on a
  yes (as `--get-picture` and `--get-ballistic`), and how to get Node.js (`pkg install
  nodejs` on Termux). Shown while one of them is not here yet. The `sound set` and `sound`
  commands say how many of a set's Ballistic sounds the C engine makes and what the rest need;
  sounds baked into the game need nothing.
- **CLIo Picture** (`engine/picture/`, `--get-picture`): a C library, found and installed as
  Ballistic's is, for the inner loops of the pictures; `--get-picture` installs release 0.6.0
  for Linux, macOS, Windows or Android (Termux), checked by its SHA-256. It draws the open
  land's ground (the caster, `Land.cast`) and the sky over open cells (all but the sun's disc
  and glow, which stay in Python), from release 0.3 the rooms' floor and ceiling (all but
  the teleporters' rings), and from 0.4 it keeps the whole picture from the floor to the
  cells (`engine/picture/frame.py`: walls, pictures, shadows, models' triangles, colour
  changes, hurt, shaking, the cockpit; what has no call there - a glow, a blast - is drawn
  through rows that read and write the frame), and from 0.5 it projects and shades the models
  (with the `pow` and `exp` of the Python running CLIo, handed over by ctypes and checked
  against `model.pbr` before models are drawn there), and from 0.6 it keeps each model's
  faces (`clio_mesh_new`) and is handed only the posed corners and where the model stands
  (`clio_frame_mesh_draw`, used when the library has it): with 100 drones in sight on E1M4 a
  frame takes 15 ms instead of 32; it works out the land's heights a chunk
  at a time and makes the braille of the dots and dots-fill views. Along the bot's games at
  150 x 34, a room frame takes 4-5 ms instead of 10-12 (dots: 6-7 instead of 40), E1M3, E1M4
  and SIM-1 7-8 ms instead of 35-80 (dots: 10-15 instead of 95-140). It gives exactly the Python's
  results, to the last bit, and is checked against the Python before it is used; an older
  release does what it can and leaves the rest to the Python; without it everything is drawn
  in Python as before.

- **Taps and swipes in first-person levels** (on by default in Termux, `--touch on|off`
  elsewhere): the picture in thirds - the sides turn, their bottom corners strafe, the
  middle's top steps forward, its centre fires, its bottom uses; a swipe up or down steps
  forward or back (one step per 0.3 s of swiping); the status line changes weapon, the lines
  under the picture show the map; a tap closes a page. `help` lists them. `next` (key `]`)
  readies the next weapon. `--termux-keys` prints a row of extra keys for Termux's keyboard
  (fire, strafe, use, map, goggles, save and load) and how to install it.

- **Demos** (`engine/demo.py`, a game's `demo.json`): playlists of clips that play
  themselves with a caption line - levels played by their bot, sims flown by the
  autopilot, stages and skirmishes played by the computer (on every side), models turning
  in a showroom, a text adventure typed out, title cards between them. **CLIo's tech demo**
  (`engine/demos/clio.json`: physics, models, pictures in three views, six kinds of game) is
  on the launcher's menu, and **RØØTLESS's** (`games/rootless/demo.json`: the action of
  every level, the sims, the arcade, the skirmish) on its title screen (`d`). Either plays
  by itself after 45 seconds with no key (`CLIO_DEMO_IDLE`, 0: never), and any key goes
  back. `--demo` plays one once, `--attract` over and over; `--check` checks demo.json. The
  caption says how long each picture took, with CLIo Picture or in Python.

- **Getting about in first-person levels**: **stairs** (`"stairs"`, walked into: to the other
  end of the same name, the view climbing past), **magnetic plating** (`"mag"`, walked up in
  **magboots** while the world tips on its side; magboots also stop a slide on slick floor and
  hold the player on a belt; F3), **drops** (`"pit"`: fliers only), the **jetpack** (F4: in the
  air with the gun in hand over drops, acid, water and fire, a beat of fuel a beat, gliding to
  an edge when it runs dry), **swimming and diving** (`"swim": true` on a level: deep water is
  swum, F6 dives - the bottom below, the surface above, the picture in the water's colour,
  `"breath"` beats of air - and a diver passes under a `"bulkhead"`), and **submarines**
  (vehicles with `"swim"` and `"dive"`: through the water and under bulkheads, torpedoes as a
  rocket gun). The level bot knows them all (goals `jet`, `land`, `dive`, `surface`, `mag`,
  `unmag`; stairs and plating by their map characters); the editor's map painter has them;
  `--check` wants stairs and plating in pairs. RØØTLESS: **SIM-11: Deep Works**
  (`--level sim11`): a coolant deck of slick floor and a belt into acid, stairs, a magnetic
  shaft, a drop crossed by jetpack under hornets, a flooded vault with a bulkhead to dive under,
  and the DS-9 Bathyscaphe through a hall of sea mines; magboots, a jetpack, jet fuel, the
  bathyscaphe and sea mines as 3D models, tiles for water, the bottom, the surface, drops,
  stairs, plating, bulkheads and docks, and 12 sounds. The bot finishes it in 138-156 beats.

### Changed

- **Crowds think faster**, and exactly as before: a monster's way to its goal is worked out
  only as far as it is asked (`Level.ways`; if the map changes halfway through a beat, the
  ways asked for before are finished on the map as it was), the flood fill and the line of
  sight over open land do less per cell. 100 awake monsters on E1M4: 49 -> 25 ms a beat
  (kworkers), 71 -> 35 ms (scouts).
- RØØTLESS's first episode is called **Roasted in the Shell**.
- The banner font has `Ø`, `ø`, `Æ`, `æ`; in plain ASCII they become `0`, `o`, `AE`, `ae`.
- **The far end of a room**: walls are drawn 10 cells ahead (monsters and items are still
  seen, aimed at and shot at within 7), and wide rooms are drawn to the edges of the
  picture, so a far wall no longer shows the floor through it. The walls beside and behind
  the player are drawn from the cells they are, each with its own tile, so a panel beside
  him (the shooting target, the exit switch) is no longer drawn three times. Beyond the
  walls is a dark haze.
- **Faster frames**: the floor and ceiling work out what depends on a cell once per cell
  and each colour's fog once per row; walls, the dots of the braille view and whole-picture
  tints (the goggles' green, root's inverse) work each colour out once - the dots view
  draws in about half the time. The screen writes only what changed since the last frame
  (in an animation, often a small part), with colour codes that set only the colour that
  changed: a whole frame is about a quarter smaller. An animation keeps its time: a slow
  frame shortens the wait after it, and one that comes too late is left out (never the last).

### Fixed

- **Symbols the font lacks** no longer show as `?` or empty boxes. Windows' own console
  window draws with Consolas or Lucida Console, which have only the old Windows glyph list:
  there the hopper's diagonal heading arrows and the reactor's chart bars were question
  marks. CLIo now finds what draws it and swaps what the font lacks for the nearest it has:
  in the console window (and the Linux console) the new symbol set `console` (fine bars as
  `_▄█`, diagonal arrows as `/` and `\`, the dots as shades, rounded corners as square), in
  Windows Terminal the few symbols its Cascadia Mono lacks (the heading arrows become eight
  triangles). `--glyphs full` turns it off; `--test-display` has a row for these shapes. A
  test checks that every symbol the engine and its games show has a stand-in in both fonts
  and in ASCII.
- A first-person view no longer shows the floor and ceiling of the level before when the
  next one starts at the same place, facing the same way.
- E1M3's title page showed its intro a letter to a line (a level's `intro` may now be one
  line or a list), and dying there named a text that is not one; `--check` now says when
  a level's `death_text` is not in texts.json.

## 2.2.2 - 2026-11-18

Music with more colours: instruments that can be overdriven, detuned, filtered and put in
a room, and generated music whose sound and length a game's designer chooses.

### Added

- **Overdrive in songs.** An instrument can have `"drive"` (0 to 1): its track is
  flattened as by a guitar amplifier, so a root and its fifth on a `saw` wave sound as a
  power chord, and a kit can be made to crack. With `lowpass` after it, the fizz goes.
  Songs without it sound exactly as they did. `docs/AUTHORING.md` now also names the
  other things an instrument can have: `gate`, `lowpass`, `echo`.
- **Three more settings for instruments**, for strings, brass, pads and acid lines:
  `detune` (two more oscillators a few cents above and below), `filter` (a resonant
  low-pass whose cutoff moves over every note: `[from Hz, to Hz, resonance, seconds]`)
  and `room` (a cluster of early echoes). Songs without them sound exactly as they did.
- **Generated music: a sound and a form to choose.** `"sound": "rich"` plays the same
  generated tune on other instruments - strings, a horn or a trumpet, a clarinet, plucked
  strings, an overdriven guitar, as the mood has them - each as loud as its chip
  counterpart; `"chip"`, the default, is CLIo as it has always sounded. `"form"` lays the
  tune's two halves out: `(A)` without the tune, `A-` quietly, `A+` a tone higher;
  `"long"` is `(A) A A B A B- A A+`, more than twice as long before it comes round. Both
  can be said in a track, or once with `music_sound` and `music_form` for the game, a
  scene or a dungeon floor - also in the editor - so a game keeps one sound.
- `synth.render_tracks(song)`: a song track by track, for a player that lets voices be
  switched on and off.

### Changed

- Rendered music and sounds are cached anew once, so that a song written with the new
  instrument settings is not played from an older, plainer render.

## 2.2.1 - 2026-11-17

New names in the demo games, and saved games that cope with a renamed conversation.

### Changed

- Derelict: the cargo hauler has a new name, the CH Erebus, and so has its ship's mind,
  EREBUS (`talk to erebus`). Ask it what the name stands for.
- The Hollow: the boss of the deeper Court is now the Remains of the Hollow King, and the
  quest down the endless floors is The Long Slumber.

### Fixed

- A save keeps each character's dialogue tree by name, so when a game renamed a tree the
  conversation stopped at the greeting. It now falls back to the tree the game names for
  that character. A Derelict game saved in 2.2.0 loads and plays on, under the old names
  until you start a new game.

## 2.2.0 - 2026-11-17

CLIo 2.2 is about how games look. A game can set its title in a graphic style without
drawing a thing, draw pictures and animations in the same styles, and bring any art to
life; the editor shows all of it as the game will draw it. CLIo itself has a new logo.
Games made for 2.1 run unchanged.

### Added

- **Banners.** Any text in one of nine graphic styles - `pixel`, `shadow`, `chrome`,
  `glitch`, `reflect`, `synthwave`, `led`, `dots`, `plain` - and thirteen palettes, or
  colours of your own. A game draws its title this way with `"title_banner"` in game.json,
  puts one up in the story with the `banner` effect (`{"banner": "Chapter II", "style":
  "led"}`), and ends with `"win_banner"` / `"lose_banner"`. Banners wrap and shrink to fit,
  down to a 24-column phone; lower case is drawn as small capitals. Each theme has a style
  of its own for banners that name none. `clio.py --banner TEXT` shows one; `--export FILE`
  writes it as an `.art` file to draw over.
- **A game's own palettes and house style.** `"palettes"` in game.json names colours of the
  game's own, used like the built-in ones; `"banner_defaults"` sets what every banner uses
  unless it says otherwise.
- **Pictures in the styles.** A sprite can be drawn as half blocks (as before), big square
  `blocks`, fine braille `dots`, an `led` panel or `ascii` letters, and can hold more
  drawings that play in turn (`"frames"`, `"fps"`, `"loops"`) or any animation
  (`"effect"`). Every sprite is a picture too: `"art": "torch"` in a scene, a portrait, the
  story's `art` effect and a sprite called `title` all find it when there is no `.art` file
  of that name. Enemies fight in their sprite's style.
- **Animated art.** Effects that play over any art once it is shown: `glitch`, `flicker`,
  `shine`, `twinkle`, `pulse`, `cycle`, `type`, and `frames`, which plays the `@frame`
  drawings an `.art` file has always been able to hold (they were read but never shown).
  Named in the file (`@effect glitch`, `@fps 12`), in game.json (`"title_effect"`) or in
  an effect (`{"art": "door", "effect": "flicker"}`). Only on a real terminal, never with
  `--fast`; Ctrl-C skips.
- **A new CLIo logo**: a little terminal window that types its own name at the prompt. It
  shows in the launcher and on the title screen of games without title art, keeps its window
  without Unicode and fits a 24-column screen in one line.
- **Fourteen more CLIo logos** in `engine/art/logos/`, most with an animation of their own,
  the old logo among them as `classic`. A game picks one with `"logo"`; the launcher with
  `--logo NAME` or `CLIO_LOGO`. `--looks` lists the logos, styles, palettes and animations.
- **The editor draws it all.** Banner fields of game.json are drawn by the engine as you
  type - on a desktop, a phone or a 24-column screen, with a note when a style has to fall
  back to plain letters. The sprite editor has drawings (add, copy, remove, with the one
  before showing faintly underneath), boards up to 64 x 64, a style and an animation, and
  the picture as the game draws it, with *Play the animation*. Palettes are edited as forms;
  the `banner` effect is in the list of effects.
- **`@ascii`** in `.art` files: a hand-made version for terminals without Unicode.

### Changed

- Games without title art, and the launcher, show the new logo. `"logo": "classic"` in
  game.json (or `--logo classic`) brings back the old one.

### Fixed

- In an `.art` palette, `a = #ff8800` read as a comment and gave no colour. A comment now
  needs a space after the `#` (or anything that is not a hex colour).
- Without Unicode, accented letters became the letter and a `?` (`ř` -> `r?`), which also
  pushed lines one column wider per accent. They now just lose the accent.
- Without Unicode, braille dots became `?`; they now become `. ' : #` by how many dots are
  set. The quadrant blocks `▖▗▘▝▚▞` got ASCII stand-ins too.

## 2.1.0 - 2026-11-14

### Added

- **Slides and levels in songs.** A note can slide (`c3>c5:16`), be played at a level
  (`c4@5`, from `@0` to `@9`), or change level as it sounds (`c4@2>9:16`); together they
  make risers, falls and swells. Levels also work on chords and drum hits, slides on the
  `noise` wave. Songs written for 2.0 sound exactly as before.
- `synth.tone(..., glide=True)` slides evenly in pitch over the held part of a note.
- **An editor in the browser.** `python clio.py mygame --edit` opens the game as a page
  served by CLIo itself: forms for scenes, items, characters, quests and texts, built from
  a description of the data files (`engine/schema.py`); the engine's own check as you
  type; saving that changes only the lines you changed; a list of where each thing is
  used, and renaming that carries those places along. Standard library only. It is the
  first step towards replacing the tkinter entity editor in `utils/`, which still edits
  CLIo 1 games only.
- **All the text at once.** In the editor: find and replace across everything a player
  reads, and export of every such line to a CSV file - for a spreadsheet, a proofreader
  or a translator - with import to put it back. Ids, conditions and structure are never
  touched; rows that no longer match anything are reported. Also from the command line:
  `--export-text FILE`, `--import-text FILE`.
- **Making an enemy, and trying it.** In the editor: a new enemy of a chosen strength -
  measured as the dungeon generator measures it, against a floor and a rank - started
  from an existing character or a plain one, leaning tough or sharp. *Try in a fight*,
  for a new enemy or any character with stats, runs the engine's own battle code forty
  times per class and shows wins, health left and turns.
- **Pictures.** The editor shows the sprite a character will be drawn with, can grow a
  different creature for it, and has a pixel editor for sprites: paint with mouse or
  keyboard, mirrored or not, change colours and size, or grow one from any words. *Draw
  over it* turns a grown creature into a drawing of your own.
- **Forms for the parts of things.** Exits, stats, moves, quest stages, dialogue nodes and
  choices, item states and effects are edited as forms - add, remove, reorder - instead
  of JSON. Described, like everything else, in `engine/schema.py` (`group`, `rows`, `map`).
- **The map and the conversations.** The editor draws the rooms where the player's own map
  puts them (`automap.layout`), level by level, with locked ways, one-way ways and stairs
  marked; drag a room to pin it elsewhere. A dialogue is drawn as it runs: nodes in the
  order they are reached, choices and automatic jumps as arrows, unreachable nodes and
  jumps to nowhere pointed out.
- **Can it be finished?** A game can keep its way through in `walkthrough.txt` - commands
  as a player types them, `== name` for each further way. The editor plays them on the
  real engine, on the game as it is in the page, and says how each ends, where it stops,
  which lines were refused, and what no walkthrough reaches. `python clio.py mygame
  --walkthrough` does the same for scripts. Derelict has one for each of its three endings.
- **Effects and conditions as forms.** In the editor, what happens (`do`, `on_enter`,
  `on_complete`, what an item answers to being used, what a character does when given
  something...) is a list of lines - an effect chosen from all the engine knows, and its
  target chosen from the game's own things - and a condition (`if`, `when`, `done_when`...)
  is a question chosen the same way, with a tick for *not*. What is richer than a line
  (branches, several questions at once) stays as written and is edited as JSON. The two
  vocabularies are data in `engine/schema.py`, held equal to `engine/conditions.py` by a
  test. Parts only some things have wait under *Add…* instead of lengthening every form.
- **The editor on the web.** The repository is its own site: opened from a web address
  (GitHub Pages; nothing is built), the editor's page runs the engine in the browser
  (Pyodide) and asks it the same questions it asks the local server
  (`engine/editor/service.py`). Open a game folder, a zip, a new game from the starter, or
  a demo game. In Chrome and Edge it saves straight into the opened folder; elsewhere
  a game is kept by the browser on every save and offered again on the next visit
  (*Carry on with*). The game never leaves the computer. `python -m engine.editor.hosted
  --pack FILE.zip` writes the site as one zip for hosts that take an upload (itch.io);
  shown inside another site's page the editor says so and works without folder access.
- Editor: *Check-up* lists rooms that cannot be reached and things nothing refers to.
- Editor: a light / dark / system theme switch, and *Download game* (the folder as a zip).
  The editor now opens at the same address each time (port 8420) when that is free.

### Changed

- The dungeon demo is now called *The Hollow* (it was *The Hollow Depths*). Its folder is
  still `games/depths`, so saves, records and commands are unchanged.

### Fixed

- The condition `talked:<character>` never held: the conversation was recorded, but the
  question was read as an unknown kind and answered no. So a conversation never opened
  with its "we have met" line a second time, and hints that should move on after a talk
  stayed. It is a condition of its own now (`"talked:robot"`, `{"talked": "robot"}`). In
  the demo games Bolt, the ship's mind, the replicator and Maren now greet you differently the
  second time, as they were written to.

## 2.0.0 - 2026-11-13

A rebuild of the engine. Games written for CLIo 1 still load.

### Added

- **Sound.** A built-in chiptune synthesizer: music and sound effects are written as
  JSON, with no audio files and no third-party packages. A composer writes a track from
  a mood and a seed. Ordinary audio files can still be used. Playback goes through
  whatever the machine has (PipeWire, PulseAudio, ALSA, `afplay`, `mpv`, `ffplay`,
  Termux `play-audio`, Windows multimedia) and stays silent when nothing is found.
- **ASCII art** files with colour masks and a narrow variant for small screens.
- **Pixel sprites** drawn with half-block characters, hand-made or generated from a name.
- **Auto-map** of the explored world (`map`).
- **Status bar** and working text effects: typewriter, fade, glitch, flash, wipes,
  animated title screens.
- **Dialogue trees** with conditions, effects and one-time choices.
- **Quests** with stages that track themselves, a journal, and triggers.
- **Conditions and effects**: a small JSON vocabulary for game logic, so games stay data.
- **Tactical combat**: enemies telegraph their next move; guard, focus, heavy blows,
  skills, status effects, items, fleeing.
- **Fights against groups**: every hostile in the room joins in and shows its own intent;
  targets are picked by number (`strike 2`); skills and items can hit everyone (`area`)
  or spill over onto the rest (`splash`).
- **RPG systems**: levels, experience, gold, character classes, a character generator, shops.
- **Spawning** of characters and a **maze generator** for procedural dungeons, with
  monster packs and **endless dungeons** whose floors are scaled to get harder with depth.
- **Game modes** chosen at the start or with `--mode`, **permadeath** (the run is saved as
  it goes, there is no loading back, the save is erased at the end), **scores** and a
  **records table** (`records`).
- **Saves of the whole world** (opened containers, moved characters, unlocked doors) in
  named slots.
- Parser: directions, `use X on Y`, game-defined verbs, typo suggestions, `again`.
- Two demo games, *Derelict* and *The Hollow Depths* (with a story mode and a rogue mode),
  and a starter template to copy.
- A launcher (`clio.py`) with `--style`, `--no-sound`, `--ascii`, `--width`, `--seed`,
  `--check` and more.
- `--test-display`, a page for checking frames, symbols, colours and sprites on a given
  terminal, and `--glyphs safe` for fonts that lack some symbols.
- An authoring guide (`docs/AUTHORING.md`) and 71 automated tests.
- Apache-2.0 licence for the engine and everything it ships for games to use.

### Changed

- Runs on the Python standard library alone (3.8+). pygame is no longer required.
- Layout adapts from 36 columns (a phone in Termux) to wide terminals, and degrades from
  truecolor to monochrome and from Unicode to plain ASCII.
- The seven themes keep their names and file schema; colours and timings were retuned,
  and not every message is framed any more.
- Conversations in the original `dialogue_options` format continue until the player leaves.
- Unlocking a container also opens it. Repair tools are kept unless marked consumable.
- Saves moved to the user data folder and are not compatible with CLIo 1.

### Removed

- The CLIo 1 engine modules. Early prototypes moved to `legacy/prototypes/`.
- Hard-coded demo behaviour (the `bent_wire` lockpick, fixed passcodes); these are now data.
- Built-in `push` / `pull`: define verbs per item with `actions`.

### Known limitations

- Tested on Linux and on Windows (with and without pygame), with layouts from 24
  columns up. Not yet run on a phone.
- The Tkinter data editor still edits only the CLIo 1 layout in `game_files/`.
- Combat is one enemy at a time.

## 1.0.0-pre - 2025-01-08

The original experimental framework, kept as a reference point before the rebuild.

- JSON-driven scenes, items and characters with a verb parser.
- Inventory, combining, crafting and repairing; characters that craft from given items.
- Simple dialogues, item interactions (trade, information, quest, replicate), wandering
  and following characters.
- A basic attack / defend battle and simple RPG stats.
- Seven console styles with framed, coloured text.
- A Tkinter entity data editor (alpha).
- Requires pygame.
