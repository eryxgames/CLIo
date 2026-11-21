# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""What a game's data files hold, described as data.

The editor builds its forms from this list, so the description of a field is
written once, here.  It is deliberately incomplete: a field that is not listed
is still loaded, kept and shown (as JSON) - nothing is lost by not knowing it.

A kind has a ``shape``:

``map``     the file is ``{id: thing, ...}``
``list``    the file is ``[thing, ...]`` and each thing carries its own ``id``
``object``  the whole file is one thing (``game.json``, ``dungeon.json``)

A field has a ``type``: ``text``, ``long`` (several lines), ``number``,
``bool``, ``choice`` (one of ``options``), ``tags`` (a list of words), ``ref``
(the id of a thing of kind ``of``), ``refs`` (a list of such ids), ``sprite``
(the name of a pixel sprite, or ``auto``), ``range`` (two numbers, least and
most: a weapon's damage).  Four types hold fields of their
own, in ``fields``: ``group`` (an object: stats), ``banner`` (a group that is
also drawn, as the game would draw it: title banners), ``rows`` (a list of
objects: exits, moves, quest stages) and ``map`` (objects by name: dialogue
nodes, item states).  ``effects`` is what happens (the lists under ``do``) and
``condition`` what is asked (``if``), built from the vocabularies ``EFFECTS``
and ``CONDITIONS`` below.  Anything else is edited as JSON.  A kind with ``"editor"`` gets a
tool of its own in the page (``sprite``: the pixel editor; ``level``: the map painter).
"""

from . import banner as _banner, fx as _fx, pixels as _pixels
from .art import logo_names as _logo_names


def R(key, type, label, **more):
    """A field few things have: shown where it is present, otherwise offered under "Add…"."""
    return F(key, type, label, rare=True, **more)


def F(key, type="text", label=None, **more):
    return dict({"key": key, "type": type, "label": label or key.replace("_", " ").capitalize()}, **more)


# The small language of the data: what can happen (effects, under "do") and what can be asked (conditions,
# under "if").  ``arg`` says what an entry takes:
#   "text", "long", "number", "flag", "none" (the entry is just ``true``), "json" (anything; edited as written)
#   {"ref": kind}                     the id of a thing
#   {"words": [...]}                  text, with these as suggestions
#   {"choice": [...]}                 one of these
#   {"pair": [first, second]}         a list of two, each part one of the above
#   {"way": True}                     an exit: "to", or ["from", "to"]
#   {"measure": [...], "ops": [...]}  a comparison or a change: [op, number], or with a name first: [name, op, number]
# ``short`` entries are other spellings of an entry above them; the editor shows them where a game uses them and does
# not offer them.  engine/conditions.py is the authority; a test keeps these two lists level with it.
def V(key, label, arg="text", **more):
    return dict({"key": key, "label": label, "arg": arg}, **more)


COMPARE = [">=", "<=", ">", "<", "==", "!="]
CHANGE = ["=", "+=", "-="]
QUEST_AT = ["active", "done", "failed", "inactive", "started"]
SCENE_OF = {"pair": [{"ref": "characters"}, {"ref": "scenes"}]}

EFFECTS = [
    V("say", "Say", "long"), V("narrate", "Narrate", "long"), V("story", "Show the text", {"ref": "texts"}),
    V("set", "Set the flag", "flag"), V("clear", "Clear the flag", "flag"),
    V("var", "Change a number", {"measure": ["text"], "ops": CHANGE}),
    V("give", "Give the player", {"ref": "items"}), V("take", "Take from the player", {"ref": "items"}),
    V("add_item", "Put an item in a scene", {"pair": [{"ref": "items"}, {"ref": "scenes"}]}),
    V("remove_item", "Remove from the world", {"ref": "items"}),
    V("item_state", "Put an item in the state", {"pair": [{"ref": "items"}, "text"]}), V("item_set", "Change an item", "json"),
    V("stat", "Change the player's stats", "json"), V("heal", "Heal by", "number"), V("damage", "Hurt by", "number"),
    V("gold", "Give or take money", "number"), V("xp", "Give experience", "number"), V("learn", "Teach the skill"),
    V("goto", "Move the player to", {"ref": "scenes"}), V("look", "Describe the room again", "none"),
    V("unlock", "Unlock the way", {"way": True}), V("lock", "Lock the way", {"way": True}),
    V("reveal", "Reveal the way", {"way": True}), V("hide", "Hide the way", {"way": True}),
    V("block", "Block the way", {"way": True}),
    V("spawn", "Bring a character to", SCENE_OF), V("move_char", "Move a character to", SCENE_OF),
    V("remove_char", "Remove the character", {"ref": "characters"}), V("char_set", "Change a character", "json"),
    V("quest", "Quest", {"pair": [{"ref": "quests"}, {"choice": ["start", "advance", "complete", "fail"]}]}),
    V("fight", "Start a fight with", {"ref": "characters"}), V("dialogue", "Start a conversation with", {"ref": "characters"}),
    V("end_dialogue", "End the conversation", "none"), V("shop", "Open a shop", "json"),
    V("sfx", "Play the sound"), V("music", "Play the music", {"ref": "music"}), V("art", "Show the picture"),
    V("banner", "Show a banner (big styled text)", "text"),
    V("pause", "Pause, in seconds", "number"), V("transition", "Wipe the screen", "none"),
    V("turns", "Let turns pass", "number"), V("save", "Save the game", "none"), V("deepen", "Add a dungeon floor", "none"),
    V("win", "Win, with the text", {"ref": "texts"}), V("lose", "Lose, with the text", {"ref": "texts"}),
    V("random", "One of these at random", "json"), V("do", "A group of effects", "json"),
    V("add_card", "Put a card in the player's deck", {"ref": "cards"}),
    V("remove_card", "Take a card out of the player's deck", {"ref": "cards"}),
    V("upgrade_card", "Make a card in the deck better: choose, random, or a card's id", "text"),
]

CONDITIONS = [
    V("flag", "the flag is set", "flag"), V("not_flag", "the flag is not set", "flag", short=True),
    V("has", "the player has", {"ref": "items"}), V("lacks", "the player lacks", {"ref": "items"}),
    V("equipped", "the player wears or wields", {"ref": "items"}), V("visited", "the player has been to", {"ref": "scenes"}),
    V("in_scene", "the player is in", {"ref": "scenes"}), V("in", "the player is in", {"ref": "scenes"}, short=True),
    V("talked", "the player has talked to", {"ref": "characters"}),
    V("here", "in this room is", {"ref": "characters"}), V("item_here", "in this room lies", {"ref": "items"}),
    V("defeated", "was defeated", {"ref": "characters"}), V("alive", "is alive", {"ref": "characters"}),
    V("class", "the player's class is"),
    V("quest", "a quest is", {"pair": [{"ref": "quests"}, {"words": QUEST_AT}]}),
    V("item_state", "an item is in the state", {"pair": [{"ref": "items"}, "text"]}),
    V("state", "an item is in the state", {"pair": [{"ref": "items"}, "text"]}, short=True),
    V("item_in", "an item lies in", {"pair": [{"ref": "items"}, {"ref": "scenes"}]}), V("char_in", "a character is in", SCENE_OF),
    V("stat", "a stat of the player", {"measure": [{"words": ["health", "max_health", "attack", "defense"]}], "ops": COMPARE}),
    V("var", "a number", {"measure": ["text"], "ops": COMPARE}),
    V("gold", "the player's money", {"measure": [], "ops": COMPARE}), V("level", "the player's level", {"measure": [], "ops": COMPARE}),
    V("turns", "the turns played", {"measure": [], "ops": COMPARE}), V("chance", "by chance (0 to 1)", "number"),
    V("all", "all of these hold", "json"), V("any", "any of these holds", "json"), V("not", "this does not hold", "json"),
]

STATS = [F("health", "number"), F("max_health", "number"), F("attack", "number"), F("defense", "number"),
         F("critical_hit_chance", "number", "Critical hit chance (0 to 1)")]

EXIT = [F("door_name", label="Called"), F("dir", label="Direction (n, s, e, w, u, d)"), F("scene_id", "ref", "Leads to", of="scenes"),
        F("locked", "bool"), F("required_item", "ref", "Opened with", of="items"), F("lock_text", "long", "Said while locked"),
        F("unlock_text", "long", "Said on unlocking"), F("blocked", "bool"), F("block_text", "long", "Said while blocked"),
        R("unblock_if", "condition", "Unblocked when"), F("unblock_text", "long", "Said on unblocking"),
        F("guard", "ref", "Guarded by", of="characters"), F("guard_text", "long", "Said while guarded"),
        R("leave_if", "condition", "May be used when"), F("leave_text", "long", "Said when it may not"),
        R("on_unlock", "effects", "When it is unlocked"), R("do", "effects", "When it is used")]

MOVE = [F("type", "choice", options=["attack", "heavy", "guard", "status", "drain", "heal"]), F("name"),
        F("weight", "number", "How often (weight)"), F("mult", "number", "Damage multiplier"),
        F("tell", "long", "Warning shown the turn before"), F("status"), F("turns", "number"), F("power", "number"),
        F("amount", "number"), F("below", "number", "Only below this share of health"),
        R("if", "condition", "Only when")]

CHOICE = [F("text", label="The player says"), F("say", "long", "The answer"), F("goto", label="Then go to node"),
          F("once", "bool"), F("if", "condition", "Offered when"), F("do", "effects", "And then"), F("tag")]
HINT = [F("if", "condition", "When"), F("text", "long", "The hint")]
# What a thing answers when something is done with it: used on its own, used on another thing, given to someone.
ANSWER = [F("if", "condition", "Works when"), F("else", "long", "Said when it does not"), F("text", "long", "What is said"),
          F("do", "effects", "And then"), R("consume", "bool", "Uses the item up"), R("next_state", "text", "Its state becomes"),
          R("sfx", "text", "Sound")]
GIVEN = [F("if", "condition", "Accepted when"), F("else", "long", "Said when it is not"), F("text", "long", "What is said"),
         F("do", "effects", "And then"), R("consume", "bool", "Keeps the item"), R("reward_item", "ref", "Gives in return", of="items"),
         R("flag", "text", "Sets the flag"), R("sfx", "text", "Sound")]

# A banner: text drawn in one of the graphic styles of engine/banner.py.  The editor shows a
# field of type "banner" as a group of these fields with a live picture of the result.
BANNER = [F("text", label="Text (the game's title if left empty)"),
          F("style", "choice", options=list(_banner.STYLES)),
          F("palette", "choice", "Colours (the game's own palettes come first)", options=list(_banner.PALETTES)),
          F("effect", "choice", "Animation", options=list(_fx.NAMES)),
          F("scale", "number", "Scale (1 or 2)")]
END_SCREEN = [F("heading", label="Heading (THE END if left empty)"),
              F("picture", "refs", "Pictures (sprites)", of="sprites"),
              F("picture_every", "number", "Seconds each picture is shown (0: side by side)"),
              F("picture_lines", "number", "Lines high a picture may be (14)"),
              F("next", label="What comes next"), F("credits", "lines", "Credits, a line each"),
              F("tick", label="A line at the bottom that keeps ticking (a crontab line, say)")]
PALETTE = [F("colors", "tags", "Colours, top to bottom (#rrggbb, #rrggbb, ...)"),
           F("accent", "tags", "Colours for lower-case letters (optional)")]

KINDS = [
    {"key": "game", "file": "game", "label": "Game", "one": "game", "shape": "object", "title": "title", "fields": [
        F("title"), F("subtitle"), F("description", "long"), F("author"), F("version"),
        F("initial_scene", "ref", "First scene", of="scenes"), F("style"), F("currency"),
        F("max_hints", "number"), F("player_stats", "group", "The player's stats", fields=STATS),
        R("title_banner", "banner", "The title drawn in a graphic style", fields=BANNER),
        R("title_effect", "choice", "Animation of the title picture", options=list(_fx.NAMES)),
        R("music_sound", "choice", "Generated music is played on", options=["chip", "rich"]),
        R("music_form", "text", "Form of generated music (long, or as (A) A B- A+)"),
        R("sound_set", "text", "Sound effects from another set (sounds.NAME.json), unless the player picks one"),
        R("logo", "choice", "CLIo logo on the title screen", options=_logo_names()),
        R("win_banner", "banner", "Banner when the player wins", fields=BANNER),
        R("lose_banner", "banner", "Banner when the player loses", fields=BANNER),
        R("banner_defaults", "banner", "The game's banner style (for every banner)", fields=BANNER),
        R("palettes", "map", "The game's own colour palettes", one="palette", fields=PALETTE),
        R("on_start", "effects", "When a new game starts"),
        R("end_screen", "endscreen", "The end screen of a game of levels", fields=END_SCREEN)]},
    {"key": "scenes", "file": "scenes", "label": "Scenes", "one": "scene", "shape": "list", "title": "name", "fields": [
        F("name"), F("area"), F("description", "long"), F("first_visit", "long"), F("art"),
        F("music", "ref", of="music"), F("enter_sfx", label="Sound on entering"),
        F("items", "refs", of="items"), F("passive_items", "refs", "Scenery (items that cannot be taken)", of="items"),
        F("characters", "refs", of="characters"), F("exits", "rows", fields=EXIT, one="exit"),
        R("hint", "rows", "Hints", fields=HINT, one="hint"),
        R("extra", "rows", "More to the description", one="line", fields=[F("if", "condition", "When"), F("text", "long")]),
        R("music_sound", "choice", "Generated music is played on", options=["chip", "rich"]),
        R("music_form", "text", "Form of generated music (long, or as (A) A B- A+)"),
        R("on_first_enter", "effects", "On entering for the first time"), R("on_enter", "effects", "On entering"),
        R("level", "ref", "A first-person level played here", of="levels"),
        R("on_level_exit", "effects", "When its level is finished"),
        R("on_secret_exit", "effects", "When its level is left by the secret exit"),
        R("stage", "ref", "An arcade stage played here (in real time)", of="stages"),
        R("on_stage_clear", "effects", "When its stage is cleared"),
        R("on_stage_fail", "effects", "When its stage is failed (none: the game is lost)"),
        R("on_stage_quit", "effects", "When its stage is left (none: the game ends)"),
        R("skirmish", "ref", "A skirmish played here (real-time strategy)", of="skirmishes"),
        R("on_skirmish_win", "effects", "When its skirmish is won"),
        R("on_skirmish_lose", "effects", "When its skirmish is lost (none: the game is lost)"),
        R("on_skirmish_quit", "effects", "When its skirmish is left (none: the game ends)"),
        R("sim", "ref", "A simulator played here (a vehicle, or systems)", of="sims"),
        R("on_sim_done", "effects", "When its sim is done"),
        R("on_sim_fail", "effects", "When its sim is failed (none: the game is lost)"),
        R("on_sim_quit", "effects", "When its sim is left (none: the game ends)")]},
    {"key": "items", "file": "items", "label": "Items", "one": "item", "shape": "map", "title": "name", "fields": [
        F("name"), F("short", label="Short name"), F("description", "long"), F("aliases", "tags"),
        F("value", "number"), F("takeable", "bool"), F("usable", "bool"), F("use_text", "long"),
        F("equippable", "bool"), F("slot"), F("interactive", "bool"), F("current_state"),
        F("tool", "bool"), F("lockpick", "bool"), F("contents", "refs", of="items"),
        F("components", "refs", "Made from", of="items"),
        F("effect", "group", "Effect when used or worn", fields=STATS),
        F("states", "map", one="state", fields=[F("description", "long"), F("action", label="Changed by the word"),
                                                F("next_state", label="Becomes"),
                                                R("do", "effects", "When the word is used"),
                                                R("on_enter", "effects", "On coming to this state")]),
        R("on_use", "group", "When used", fields=ANSWER),
        R("use_with", "map", "When used on another thing", one="thing it is used on", fields=ANSWER),
        R("take_if", "condition", "May be taken when"), R("on_take", "effects", "When taken"),
        R("on_examine", "effects", "When examined"), R("on_read", "effects", "When read"),
        R("on_repair", "effects", "When repaired")]},
    {"key": "characters", "file": "characters", "label": "Characters", "one": "character", "shape": "map",
     "title": "name", "fields": [
        F("name"), F("aliases", "tags"),
        F("type", "choice", "Attitude", options=["friendly", "neutral", "hostile", "aggressive"]),
        F("description", "long"), F("greeting", "long"), F("dialogue_tree", "ref", "Dialogue", of="dialogues"),
        F("sprite", "sprite", "Sprite"), F("sprite_seed", label="Sprite grown from"), F("sprite_size", "number"),
        F("portrait"), F("tags", "tags"), F("inventory", "refs", of="items"),
        F("xp", "number"), F("show_hostile", "bool"), F("battle_intro", "long"), F("defeat_text", "long"),
        F("refuse_text", "long"), F("no_fight_text", "long"), F("immune", "tags"),
        F("stats", "group", fields=STATS), F("moves", "rows", "Moves in a fight", fields=MOVE, one="move"),
        R("gives", "map", "When given something", one="item it is given", fields=GIVEN),
        R("ambush_if", "condition", "Attacks first when"), R("on_defeat", "effects", "When defeated"),
        R("battle", "choice", "Fights with", options=["cards", "classic"]),
        R("deck", "refs", "Its own deck in a card battle (a duellist)", of="cards"),
        R("energy", "number", "A duellist's energy a turn"), R("hand", "number", "Cards a duellist draws a turn"),
        R("card_rewards", "refs", "Cards offered when it is beaten", of="cards")]},
    {"key": "dialogues", "file": "dialogues", "label": "Dialogues", "one": "dialogue", "shape": "map", "fields": [
        F("start", label="Starts at node"),
        F("nodes", "map", one="node", fields=[F("text", "long", "What is said"), F("speaker"), F("goto", label="Then go to node"),
                                              R("do", "effects", "And then"), R("on_exit", "effects", "On leaving it"),
                                              R("variants", "rows", "Other lines", one="line",
                                                fields=[F("if", "condition", "When"), F("text", "long", "What is said")]),
                                              F("choices", "rows", fields=CHOICE, one="choice")])]},
    {"key": "quests", "file": "quests", "label": "Quests", "one": "quest", "shape": "map", "title": "title", "fields": [
        F("title"), F("description", "long"), F("complete_on_win", "bool"),
        F("stages", "rows", one="stage", fields=[F("id"), F("text", "long", "Shown in the journal"),
                                                 F("done_when", "condition", "Done when"),
                                                 R("do", "effects", "And then")]),
        R("fail_when", "condition", "Fails when"), R("on_complete", "effects", "When it is completed"),
        R("on_fail", "effects", "When it fails")]},
    {"key": "triggers", "file": "triggers", "label": "Triggers", "one": "trigger", "shape": "list", "fields": [
        F("once", "bool"), F("every", "number", "Every N turns"), F("when", "condition", "When"),
        F("do", "effects", "Then")]},
    {"key": "texts", "file": "texts", "label": "Texts", "one": "text", "shape": "map", "fields": [
        F("text", "long"), F("show_once", "bool")]},
    {"key": "music", "file": "music", "label": "Music", "one": "song", "shape": "map", "title": "title", "fields": [
        F("title"), F("tempo", "number"), F("steps_per_beat", "number"), F("volume", "number")]},
    {"key": "sounds", "file": "sounds", "label": "Sounds", "one": "sound", "shape": "map", "fields": []},
    {"key": "sprites", "file": "sprites", "label": "Sprites", "one": "sprite", "shape": "map", "editor": "sprite",
     "fields": [F("style", "choice", "Drawn as", options=list(_pixels.STYLES)),
                F("effect", "choice", "Animation when it is shown", options=list(_fx.NAMES)),
                F("fps", "number", "Drawings a second"), F("loops", "number", "Times the drawings play")]},
    {"key": "dungeon", "file": "dungeon", "label": "Dungeon", "one": "dungeon", "shape": "object", "fields": []},
    {"key": "levels", "file": "levels", "label": "Levels", "one": "level", "shape": "map", "title": "name",
     "editor": "level", "fields": [
        F("name"), F("title", label="Title shown when it starts"), F("par", "number", "Par (beats)"),
        F("music", "ref", of="music"), F("facing", "choice", "The player starts facing", options=["n", "e", "s", "w"]),
        R("death_text", "ref", "Text when the player dies", of="texts"),
        R("realtime", "number", "Real time: seconds a beat lasts when no key is pressed (0: it waits)"),
        R("render", "choice", "How its rooms are drawn (a player's --render wins)", options=["classic", "mesh"]),
        R("climb", "number", "Rooms with heights: the highest step walked up, in walls' heights (0.55)")]},
    {"key": "tiles", "file": "tiles", "label": "Tiles", "one": "tile", "shape": "map", "editor": "sprite", "fields": []},
    {"key": "weapons", "file": "weapons", "label": "Weapons", "one": "weapon", "shape": "map", "title": "name",
     "editor": "weapon", "fields": [
        F("name"), F("kind", "choice", "Kind", options=["gun", "melee"]),
        F("ammo", label="Ammunition it uses (bullets, shells...; none for a fist)"),
        F("damage", "range", "Damage, least to most"), F("sprite", "sprite", "Sprite in the player's hands"),
        F("sound", label="Sound of a shot"), F("text", label="A shot in words (BANG.)"),
        R("pellets", "number", "Pellets a shot (a shotgun: 7)"),
        R("spread", "number", "How far the pellets spread to monsters beside (0 to 1)"),
        R("burst", "number", "Rounds fired a beat (a chaingun: 2)"),
        R("key", "text", "The key that picks it, 1-9 (one key can hold several: pressed again, the next)"),
        R("accuracy", "number", "Melee: the chance a blow lands (0 to 1; 0.85 if not said)"),
        R("shove", "bool", "Melee: a blow throws the target a cell back"),
        R("stagger", "number", "Melee: beats a bitten monster loses (no aim, no step)"),
        R("ready_sound", "text", "Sound when it is taken in hand")]},
    {"key": "monsters", "file": "monsters", "label": "Monsters", "one": "monster", "shape": "map", "title": "name",
     "fields": [
        F("name"), F("role"), F("tag", label="Tag letter (z: z1, z2...)"), F("sprite", "sprite", "Sprite"),
        F("hp", "number", "Health"), F("size", "number", "Size (1: a person)"),
        F("float", "number", "Floats above the floor (0..1)"), F("sight", "number", "Sees this many cells"),
        F("awake", "bool", "Awake from the start"), F("boss", "bool"), F("drops", "ref", "Drops", of="items"),
        F("death", label="When it dies (%s: its tag)"),
        R("model", "ref", "A 3D model drawn instead of the sprite", of="models"),
        R("brain", "choice", "Its brain (how it fights)",
          options=["brute", "skirmisher", "soldier", "heavy", "coward", "assault", "swarm"]),
        R("squad_tactic", "choice", "In a squad it fights as",
          options=["pincer", "fire_team", "hold", "rush", "assault", "sweep", "ambush", "swarm"]),
        R("grenades", "group", "Grenades it carries", fields=[F("count", "number"), F("range", "number"),
                                                                F("fuse", "number", "Fuse (beats)"),
                                                                F("blast", "number"), F("every", "number", "At most every (beats)")]),
        R("mines", "group", "Mines it lays", fields=[F("count", "number"), F("item", "ref", "The mine (an item)", of="items")])]},
    {"key": "cards", "file": "cards", "label": "Cards", "one": "card", "shape": "map", "title": "name", "fields": [
        F("name"), F("cost", "number", "Cost (energy)"), F("type", "choice", options=["attack", "skill", "power"]),
        F("target", "choice", "Played at", options=["enemy", "all", "self"]),
        F("rarity", "choice", options=["starter", "common", "uncommon", "rare"]),
        F("effects", "rows", "What it does, in order", one="effect", fields=[
            F("damage", "number"), F("times", "number", "Hits (damage this many times)"), F("block", "number"),
            F("draw", "number", "Draw cards"), F("energy", "number", "Energy"), F("heal", "number"),
            F("strength", "number", "Strength (more damage a hit, for the fight)"),
            F("status", "choice", "Status on the target", options=["weak", "exposed", "poison", "burn", "bleed", "stun", "blind"]),
            F("turns", "number"), F("power", "number", "Power (a turn)")]),
        F("exhaust", "bool", "Gone for the rest of the fight once played"),
        R("reward", "bool", "Offered after a win (false: an enemy's card)"),
        R("classes", "tags", "Offered only to these classes"), R("text", "long", "What it says it does"),
        R("say", "text", "Said when it is played"), R("sfx", "text", "Sound when it is played")]},
    {"key": "stages", "file": "stages", "label": "Arcade stages", "one": "stage", "shape": "map", "title": "name",
     "fields": [
        F("name"), F("title", label="Title shown when it starts"),
        F("mode", "choice", "Played as", options=["platformer", "topdown"]),
        F("goal", "choice", "Won by", options=["exit", "chips", "clear", "survive"]),
        F("intro", "long", "Shown before it starts"), F("music", "ref", of="music"),
        F("lives", "number"), F("health", "number", "Health (hits a life takes)"),
        F("gun", "bool", "The fire key shoots"),
        R("need", "number", "Chips needed at the exit"), R("time", "number", "Seconds (a limit; survive: to last)"),
        R("physics", "group", "How things move", fields=[
            F("speed", "number", "Running speed (tiles a second)"), F("jump", "number", "Jump (tiles high)"),
            F("gravity", "number", "Gravity (1: as the engine has it)"), F("fall", "number", "Falling at most (tiles a second)"),
            F("climb", "number", "Climbing (tiles a second)"), F("shot", "number", "Shots (tiles a second)"),
            F("range", "number", "Shots fly (tiles)"), F("every", "number", "Seconds between shots")]),
        R("on_clear", "effects", "When it is cleared"), R("on_fail", "effects", "When it is failed"),
        R("death_text", "ref", "Text when it is failed (and nothing else is said)", of="texts")]},
    {"key": "skirmishes", "file": "skirmishes", "label": "Skirmishes (strategy)", "one": "skirmish", "shape": "map",
     "title": "name", "fields": [
        F("name"), F("title", label="Title shown"), F("intro", "long", "Shown before it starts"),
        F("music", "ref", of="music"),
        F("goal", "choice", "Won by", options=["destroy", "survive"]),
        R("time", "number", "Seconds to hold out (survive)"), R("limit", "number", "Units a side may have"),
        R("crystal", "number", "Crystal in each crystal tile"),
        R("on_win", "effects", "When it is won"), R("on_lose", "effects", "When it is lost"),
        R("death_text", "ref", "Text when it is lost (and nothing else is said)", of="texts")]},
    {"key": "sims", "file": "sims", "label": "Simulators", "one": "sim", "shape": "map", "title": "name",
     "fields": [
        F("name"), F("title", label="Title shown"), F("intro", "long", "Shown before it starts"),
        F("music", "ref", of="music"), F("mode", "choice", "What it is", options=["vehicle", "systems"]),
        F("goal", "choice", "Done by", options=["checkpoints", "land", "survive"]),
        F("land", "bool", "Land on a pad at the end"), R("time", "number", "Seconds (a limit; survive: to last)"),
        F("win_if", label="Done when (a formula)"), F("fail_if", label="Failed when (a formula)"),
        F("score", label="Better when higher (a formula, for the autopilot)"),
        R("on_done", "effects", "When it is done"), R("on_fail", "effects", "When it is failed"),
        R("death_text", "ref", "Text when it is failed (and nothing else is said)", of="texts")]},
    {"key": "models", "file": "models", "label": "3D models", "one": "model", "shape": "map", "editor": "model", "fields": [
        F("smooth", "bool", "Smooth (lit at the corners: round things)"), F("scale", "number", "Scale (1: as built)"),
        F("break", "choice", "Destroyed, it breaks into", options=["shards", "parts", "groups"]),
        F("turning", "number", "Turns this many degrees a beat (a pickup)"), F("fps", "number", "Frames a beat")]},
]

BY_FILE = {k["file"]: k for k in KINDS}
