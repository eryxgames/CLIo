# Making games with CLIo

A game is a folder of JSON files. Nothing in it is code. Put the folder under
`games/` and it appears in the launcher; run `python clio.py yourgame --check`
to have the engine look for broken references.

- [A complete tiny game](#a-complete-tiny-game)
- [game.json](#gamejson)
- [Scenes and exits](#scenes-and-exits)
- [Items](#items)
- [Characters](#characters)
- [Conditions and effects](#conditions-and-effects)
- [Dialogue trees](#dialogue-trees)
- [Quests and triggers](#quests-and-triggers)
- [Combat](#combat)
- [Text, colour and themes](#text-colour-and-themes)
- [ASCII art](#ascii-art)
- [Pixel sprites](#pixel-sprites)
- [The map](#the-map)
- [Sound and music](#sound-and-music)
- [Generated dungeons](#generated-dungeons)
- [Coming from CLIo 1](#coming-from-clio-1)

## A complete tiny game

`games/cellar/game.json`

```json
{
  "title": "The Cellar",
  "initial_scene": "cellar",
  "player_stats": {"health": 30, "attack": 3, "defense": 1},
  "intro": "You came down for a bottle of wine. The door has swung shut."
}
```

`games/cellar/scenes.json`

```json
[
  {
    "id": "cellar", "name": "Wine Cellar",
    "description": "Racks of dusty bottles. Stone steps lead up to a heavy door.",
    "items": ["corkscrew"], "passive_items": ["barrel"],
    "exits": [{"door_name": "Cellar Door", "dir": "u", "scene_id": "kitchen",
               "locked": true, "required_item": "iron_key",
               "lock_text": "Locked. Of course it is."}]
  },
  {
    "id": "kitchen", "name": "Kitchen",
    "description": "Daylight, and the smell of bread.",
    "on_enter": [{"win": "You are out, and you still have the corkscrew."}]
  }
]
```

`games/cellar/items.json`

```json
{
  "corkscrew": {"name": "Corkscrew", "description": "Sturdy. Pointed."},
  "iron_key": {"name": "Iron Key", "description": "Cold and heavy."},
  "barrel": {
    "name": "Barrel", "description": "A barrel with a loose bung.", "takeable": false,
    "use_with": {"corkscrew": {"text": "You work the bung out. Something clinks inside.",
                               "do": [{"give": "iron_key"}]}}
  }
}
```

That is a finished game: `take corkscrew`, `use corkscrew on barrel`, `up`. It ships as
`templates/starter/` (run it with `python clio.py templates/starter`); copy that folder to
`games/yourgame/` to begin. It is Apache-2.0 like the engine, so it is yours to change.

## game.json

| Key | Meaning |
| --- | --- |
| `title`, `subtitle`, `author`, `version`, `description` | Shown on the title screen and in the launcher. |
| `initial_scene` | Where the player starts. |
| `player_stats` | `health`, `max_health`, `attack`, `defense`, `critical_hit_chance`, `evasion`, plus any stat of your own. |
| `style` | Theme name (see [themes](#text-colour-and-themes)). |
| `intro` | Key of a text in `texts.json` (or the text itself) shown at the start. |
| `music`, `title_music` | Default track and title-screen track. |
| `max_hints`, `default_hint` | Hint budget and fallback hint. |
| `rpg` | `true` to show levels, experience and gold. |
| `starting_items`, `starting_gold`, `currency` | Inventory and money at the start. |
| `character_creation` | Name prompt and classes; see `games/depths/game.json`. |
| `abilities`, `verbs`, `actions` | Extra combat skills, extra verb synonyms, verbs that work everywhere. |
| `generator` | Turns on the [dungeon generator](#generated-dungeons). |
| `files` | Override file names: `{"scenes": "world/rooms.json"}`. |

Files are looked up by these default names: `scenes.json`, `items.json`,
`characters.json`, `texts.json`, `dialogues.json`, `quests.json`, `triggers.json`,
`music.json`, `sounds.json`, `sprites.json`, `dungeon.json`, and the folder `art/`.
Only scenes and items are required.

## Scenes and exits

```json
{
  "id": "corridor", "name": "Main Corridor", "area": "Deck B",
  "description": "The spine of Deck B.",
  "first_visit": "A longer text shown the first time only.",
  "extra": [{"if": "reactor_online", "text": "The lights are back."}],
  "art": "corridor", "art_if": [{"if": "reactor_online", "art": "corridor_lit"}],
  "music": "lower_deck", "music_if": [{"if": "reactor_online", "music": "powered"}],
  "items": ["wrench"], "passive_items": ["panel"], "characters": ["robot"],
  "exits": [ ... ],
  "random_events": ["A panel rattles."],
  "hint": [{"if": "!has:key", "text": "Find the key."}, "Head south."],
  "on_first_enter": [ ...effects... ], "on_enter": [ ...effects... ],
  "actions": {"shout": "Your voice echoes."},
  "map": [1, 0, 0], "map_icon": "$"
}
```

`items` can be picked up; `passive_items` are fixtures (give them `"takeable": false`
or simply leave them as fixtures; add `"scenery": true` to keep one out of the "You
notice" line).

An **exit**:

| Key | Meaning |
| --- | --- |
| `door_name`, `scene_id` | What it is called and where it leads. |
| `dir` | `n s e w u d ne nw se sw` (or the words). Optional; the map invents one if missing. |
| `locked` + `required_item` | Needs that item (`"passcode"` + `passcode` asks for a code). `lock_text`, `unlock_text`. |
| `blocked` + `unblock_if` | Opens when a condition holds. `block_text`, `unblock_text`. (CLIo 1's `required_condition` / `required_stat` + `required_value` also work.) |
| `guard` | A character id; nobody passes while that character is alive and present. `guard_text`. |
| `leave_if`, `leave_text` | A condition checked every time. |
| `hidden`, `show_if` | Invisible until revealed by an effect or a condition. |
| `do`, `on_unlock` | Effects when passing / when first unlocked. |

## Items

```json
"plasma_cutter": {
  "name": "Plasma Cutter", "aliases": ["cutter"],
  "description": "A heavy cutting tool.",
  "equippable": true, "slot": "weapon", "effect": {"attack": 8},
  "abilities": ["overcharge"], "value": 60
}
```

| Key | Meaning |
| --- | --- |
| `usable` + `effect` | `use` applies the stat changes and consumes it (`"consumable": false` keeps it). |
| `equippable`, `slot`, `effect` | Worn or wielded; one item per slot. |
| `readable_item` | Text shown by `read`. `on_read` runs effects. |
| `components` | Two ids: `combine a with b` makes this item. One id: this is the repaired form. `"tool": true` on a component keeps it. |
| `repairable`, `repair_item`, `repaired_item` | `repair x` turns it into its fixed form if the tool is carried. |
| `lockpick` | Opens any lock that has no particular key. |
| `on_use` | `{"text", "do", "if", "else", "consume"}` for `use x`. |
| `use_on` / `use_with` | `use x on y`: keyed by the other item's id, same shape as `on_use` plus `next_state`. |
| `actions` | Game-defined verbs: `{"push": {"text": "...", "do": [...]}}`. A list of variants picks the first whose `if` holds. |
| `on_take`, `on_examine`, `take_if`, `takeable` | Hooks and restrictions. |
| `combat` | Usable in a fight: `{"damage", "heal", "status", "cure", "focus", "text"}`. |
| `art` | Art shown when examined. |

**State machines** (the CLIo 1 format, extended) make containers, switches and machines:

```json
"locker": {
  "name": "Locker", "current_state": "locked", "contents": ["screwdriver"],
  "unlock_required_item": "locker_key",
  "states": {
    "locked": {"description": "It is locked.", "action": "unlock", "next_state": "closed"},
    "closed": {"description": "It is closed.", "action": "open", "next_state": "open",
               "do": [{"set": "locker_opened"}]},
    "open":   {"description": "It stands open.", "action": "take", "next_state": "empty"},
    "empty":  {"description": "It is empty.", "action": null}
  }
}
```

`unlock_required_item` may be an item id, `"passcode"` (with `passcode`), or absent (any
lockpick works). A state's `action` can be any verb - `"push"`, `"pull"`, `"press"` - and
a state may also carry its own `actions` map.

## Characters

```json
"robot": {
  "name": "Bolt", "aliases": ["robot"], "type": "friendly",
  "description": "A boxy maintenance robot.", "greeting": "It beeps.",
  "portrait": "robot", "voice": {"pitch": 330, "wave": "square"},
  "dialogue_tree": "bolt",
  "gives": {"orange": {"text": "Citric acid!", "consume": true, "do": [{"set": "has_orange"}]}},
  "refuse_text": "It hands the thing back."
}
```

`type` is `friendly`, `neutral`, `hostile` or `aggressive`. Enemies add `stats`, `moves`,
`sprite`, `xp`, `gold`, `inventory` (dropped on defeat), `loot` (`[[item, chance], ...]`),
`tags`, `immune`, `ambush`, `no_flee`, `on_defeat`.

Wanderers: `"movable": true, "moves_after_commands": 4, "roam": ["a", "b"]`, or
`"follow_player": true`. Shops: `"shop": {"sells": [...], "buy_rate": 0.5}`.

`gives` (CLIo 1: `item_interactions`) says what happens when the player gives an item.
The CLIo 1 keys `response`, `consume_item`, `reward_item`, `story_flag` still work.

## Conditions and effects

Anywhere you see `"if"` it takes a **condition**; anywhere you see `"do"` it takes
**effects**.

Conditions:

| Form | True when |
| --- | --- |
| `"flag"` / `"!flag"` | the flag is set / not set |
| `"has:item"`, `"visited:scene"`, `"defeated:char"`, `"here:char"`, `"quest:id:done"` | shorthand |
| `{"has": "x"}`, `{"lacks": "x"}`, `{"equipped": "x"}` | inventory |
| `{"stat": ["attack", ">=", 15]}`, `{"var": ["n", ">=", 3]}`, `{"gold": 20}`, `{"level": 3}`, `{"turns": [">=", 40]}` | numbers |
| `{"in_scene": "x"}`, `{"item_state": ["locker", "open"]}`, `{"class": "rogue"}`, `{"chance": 0.3}` | world |
| `{"all": [...]}`, `{"any": [...]}`, `{"not": ...}`; a list or several keys mean *all* | logic |

Effects (one dict may hold several; they run in order):

| Effect | Does |
| --- | --- |
| `{"say": "text", "style": "story"}` | prints (styles are theme roles; add `"effect": "glitch"`) |
| `{"set": "flag"}`, `{"clear": "flag"}`, `{"var": ["n", "+=", 1]}` | state |
| `{"give": "item"}`, `{"take": "item"}`, `{"add_item": ["item", "scene"]}`, `{"remove_item": "item"}` | things |
| `{"item_state": ["item", "state"]}`, `{"item_set": ["item", "key", value]}` | item state |
| `{"stat": {"attack": 1}}`, `{"heal": 20}` / `"full"`, `{"damage": 5}`, `{"gold": 10}`, `{"xp": 25}`, `{"learn": "cleave"}` | the player |
| `{"goto": "scene"}`, `{"unlock": "scene"}`, `{"lock": ...}`, `{"reveal": ["from", "to"]}`, `{"block": ...}` | movement |
| `{"spawn": ["char", "scene"]}` (add `"copy": true` for a fresh instance), `{"remove_char": "id"}`, `{"move_char": ["id", "scene"]}`, `{"char_set": ["id", "key", value]}` | characters |
| `{"quest": ["id", "start"]}` (`advance`, `complete`, `fail`) | quests |
| `{"fight": "char"}`, `{"dialogue": "char"}`, `{"shop": "char"}` | encounters |
| `{"sfx": "name"}`, `{"music": "track"}`, `{"art": "name"}`, `{"pause": 0.5}` | presentation |
| `{"save": "save"}`, `{"win": "text or key"}`, `{"lose": "text or key"}` | the game |
| `{"if": cond, "then": [...], "else": [...]}`, `{"random": [[...], [...]]}` | control |

`$player` in any text is replaced by the player's name.

## Dialogue trees

```json
"bolt": {
  "start": [{"if": "remote_built", "node": "after"}, "hello"],
  "nodes": {
    "hello": {"text": "BEEP! A human!", "goto": "menu"},
    "after": {"text": "The remote suits you.", "goto": "menu"},
    "menu": {"choices": [
      {"text": "Where is everybody?", "say": "Evacuated.", "once": true},
      {"text": "About that droid...", "if": "!droid_calmed", "goto": "droid"},
      {"text": "Take this.", "if": "has:orange", "do": [{"take": "orange"}], "goto": "end"}
    ]},
    "droid": {"text": "It runs hot and angry.", "do": [{"quest": ["remote", "start"]}], "goto": "menu"}
  }
}
```

A choice answers inline with `say` (and stays put), or jumps with `goto` (a node, `"end"`
or `"back"`). `if` hides it, `once` removes it after use, `do` runs effects. A node may
offer `variants` (`[{"if", "text"}]`) for its line. The flag `talked:<character id>` is
set after any conversation.

The original flat format still works and is turned into a one-node tree:

```json
"dialogue": {"greet": "Hello."},
"dialogue_options": {"Ask about the ship": "It is old.", "Ask for help": "No."}
```

## Quests and triggers

```json
"main": {
  "title": "Abandon Ship", "description": "Time you left.",
  "auto_start": true,
  "stages": [
    {"text": "Restore main power", "done_when": "reactor_online"},
    {"text": "Reach the bridge", "done_when": "visited:bridge", "do": [{"xp": 20}]}
  ],
  "on_complete": [{"say": "Done."}], "complete_on_win": true
}
```

After every turn each active quest checks its current stage. `auto_start` may be `true`
or a condition; otherwise start a quest with the `quest` effect.

`triggers.json` is a list of `{"id", "when": condition, "do": effects}`; each fires once
(`"once": false` and `"every": 5` make a repeating one).

## Combat

Damage is `(6 + attack) x multiplier, +/-15%, minus half the target's defense`. Each round
the enemy picks a move and *shows it* before the player acts.

```json
"moves": [
  {"type": "attack", "name": "its shock baton", "weight": 3},
  {"type": "heavy",  "name": "The overload discharge", "mult": 2.3, "weight": 2,
   "tell": "Its capacitors whine."},
  {"type": "guard",  "name": "plates locked"},
  {"type": "status", "name": "a venomous bite", "status": "poison", "turns": 3, "power": 3},
  {"type": "heal",   "name": "self-repair", "amount": 15, "below": 0.5},
  {"type": "drain",  "name": "latch on"}
]
```

A `heavy` move takes two rounds: a wind-up (a free round for the player) and the blow.
Statuses: `poison`, `burn`, `bleed` (damage per round), `stun`, `blind`, `weak`, `exposed`.

Skills live in `engine/combat.py` (`ABILITIES`) and can be added in `game.json`:

```json
"abilities": {"headbutt": {"name": "Headbutt", "cost": 1, "kind": "attack", "mult": 1.2,
                           "status": {"name": "stun", "turns": 1}, "text": "You lower your head."}}
```

The player gets a skill from a class, from an item's `abilities`, or from the `learn` effect.

## Text, colour and themes

Inline markup works in every text:

```
You take the {item}Bent Wire{/}.   {b red}Danger!{/}   {#ff8800}orange{/}   {on_blue}boxed{/}
```

A tag is a theme role (`item`, `character`, `exit`, `key`, `hint`, `quest`, `error` ...), a
colour name, `#rrggbb`, a 256-colour number, or an attribute (`b`, `dim`, `i`, `u`, `inv`).
`{{` prints a brace.

Themes live in `engine/style/configs/` (a game may add its own in `themes/`). The CLIo 1
schema is unchanged - `colors` per role, `styles` per role - with a few additions:

```json
"styles": {
  "description": {"frame": "ROUNDED", "padding": 2, "character_delay": 0.012, "fade_in": true},
  "list_title":  {"frame": "DOUBLE", "alignment": "center", "gradient": true}
},
"ui": {"prompt": "> ", "max_width": 78, "transition": "wipe", "frame_color": "38;5;61",
       "title_gradient": [39, 45, 51, 87, 123]}
```

Frames: `NONE SINGLE DOUBLE ROUNDED HEAVY ASCII DOTS`. Effects: `character_delay`
(typewriter), `fade_in`, `glitch`, `flash`, `gradient`. Effects only play on a real
terminal and never when output is piped.

## ASCII art

`art/corridor.art`:

```
# comment
@color steel
@palette
y = amber
@art
 |   |   _______   |   |
 | ' |  |   |   |  | ' |
@mask

   y                 y
@small
 [corridor]
```

The mask has the same shape as the art; each letter picks a palette colour, blanks use
`@color`. `@small` is used when the main drawing is too wide; if nothing fits, the art is
left out. Keep art within about 34 columns so it fits beside the text on a desktop and
above it on a phone. Reference art from scenes (`"art"`), items (`"art"`) and characters
(`"portrait"`); `title`, `win` and `lose` are picked up automatically.

## Pixel sprites

`sprites.json`:

```json
"bugrat": {
  "palette": {"b": "#3a2a22", "B": "#8b5a3c", "r": "#ff3030"},
  "pixels": ["..bBBb..", ".BrBBrB.", "..BBBB.."]
}
```

Two pixel rows share one text row (`▀` with a foreground and a background colour), so
pixels are square. `.` is transparent. Give a character `"sprite": "bugrat"` - or
`"sprite": "auto"` to have one grown from its name (`"sprite_size": 14` to change the size).

## The map

`map` draws explored rooms from the exits. Give exits a `dir` and the layout follows it;
give scenes `"map": [x, y, level]` for full control. `"map_icon": "$"` marks a room once
visited. Set `"map": false` in `game.json` to disable it.

## Sound and music

Reference a track from a scene (`"music"`), from `game.json`, or with the `music` effect.
A track is:

- a name from `music.json`,
- an audio file relative to the game folder (`"music/theme.ogg"`) - played if the machine
  has a player for that format, otherwise the default track is used,
- or generated: `{"generate": {"mood": "dark", "seed": 7}}`.
  Moods: `calm mystery dark tense battle heroic shop space victory defeat`.

A written song (`music.json`):

```json
"theme": {
  "tempo": 84, "steps_per_beat": 4,
  "instruments": {
    "lead": {"wave": "square", "duty": 0.25, "attack": 0.02, "decay": 0.15, "sustain": 0.5,
             "release": 0.3, "vibrato": [5, 0.006], "volume": 0.3, "echo": [0.36, 0.35]},
    "arp":  {"wave": "triangle", "volume": 0.22, "arp": 2},
    "bass": {"wave": "triangle", "volume": 0.5},
    "kit":  {"wave": "drums"}
  },
  "patterns": {
    "A": {"lead": "e5:4 .:2 c5:2 d5:2 e5:4 .:2 | f5:4 .:2 e5:2 d5:2 c5:4 .:2",
          "arp":  "[a3 c4 e4 c4]:16 | [f3 a3 c4 a3]:16",
          "bass": "a1:8 a1:4 e2:4 | f1:8 f1:4 c2:4",
          "kit":  "k . h . s . h . k k h . s . h h | k . h . s . h . k k h . s . s s"}
  },
  "sequence": ["A", "A"]
}
```

Notes: `c4`, `d#4`, `eb3`; `:4` lasts four steps; `.` rests; `-` holds; `[c4 e4 g4]:8` is a
chord (arpeggiated if the instrument has `arp`); `|` is ignored. Waves: `square` (with
`duty`), `triangle`, `saw`, `sine`, `soft`, `organ`, `noise`, `drums` (`k s h o t c`).

Sound effects are played by name (`{"sfx": "unlock"}`). Built in: `select back error save
step door airlock locked unlock pickup drop open use craft read computer power teleport
secret coin quest quest_done levelup heal trap alarm encounter hit crit miss hurt guard
focus special flee enemy_down win lose explosion`. Add or replace them in `sounds.json`:

```json
"zap": {"wave": "saw", "freq": [900, 120], "dur": 0.2, "vol": 0.4},
"fanfare": {"notes": "c5 e5 g5 c6:3", "tempo": 480, "wave": "square"},
"door": "sounds/my_door.wav"
```

Rendered audio is cached in `~/.cache/clio/audio` (override with `CLIO_CACHE`).

## Generated dungeons

```json
"generator": {"type": "maze", "entry": "camp", "loops": 0.22}
```

`entry` is a hand-written scene with an exit whose `scene_id` starts with `@`; the
generator connects it to the first floor. Floors are described in `dungeon.json`: size
(`w`, `h`), `monsters` (weighted), `elite` (guards the stair down), `boss` (last floor),
`merchant`, `treasure`, `shrine`, `wanderer`, loot tables, room texts per kind and
`trap_damage`. `games/depths/dungeon.json` is a complete example. The world seed decides
everything, so `--seed` replays a dungeon exactly.

## Coming from CLIo 1

CLIo 1 game folders load unchanged. What behaves differently:

- **Conversations** from `dialogue_options` continue until the player leaves, instead of
  ending after one reply. `dialogue_rewards` options now appear in the menu.
- **Unlocking** a container also opens it.
- **Lock picking** used to be hard-wired to the item `bent_wire`. It is now the item flag
  `"lockpick": true` (set automatically on `bent_wire` when no item declares it).
- **Repairing** keeps the tool unless the tool is `"consumable": true`. A broken item
  named `broken_x` finds `fixed_x` / `repaired_x` on its own.
- **Combat** is the new tactical system; typing `attack` and `defend` still works.
- **`push`, `pull`** and friends are no longer built in: define them with `actions`.
- **Saves** hold the entire world (opened containers, moved characters, unlocked doors),
  live in the user data folder (`CLIO_SAVES` to override) and are not compatible with
  CLIo 1's `savegame.json`.
- **Framing**: not every message gets its own frame; the theme decides per role.
- **`story_texts.json` conditions** match item and enemy names or ids, and
  `enemy_defeated` is actually checked.
- **Missing audio files** no longer print "The sound of silence!"; a generated track
  plays instead.
