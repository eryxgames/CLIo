"""The command parser: turns what the player typed into a verb and its objects.

It is a table of verbs and their synonyms plus a few sentence shapes
("give X to Y", "use X on Y", "combine X with Y").  It knows nothing about the
game world; matching names to actual things happens in the game.
"""
from __future__ import annotations

import difflib

from .automap import DIR_WORDS

# canonical verb -> phrases the player may type (longest phrases are tried first)
VERBS = {
    "look": ["look", "l", "look around", "explore", "scan", "search", "where am i", "survey"],
    "examine": ["look at", "look in", "look inside", "look into", "look under", "look behind",
                "examine", "x", "inspect", "study", "check", "describe", "search", "view"],
    "take": ["take", "get", "pick up", "grab", "collect", "loot", "steal", "pocket"],
    "drop": ["drop", "discard", "put down", "throw away", "toss"],
    "inventory": ["inventory", "i", "inv", "items", "bag", "backpack", "pockets"],
    "use": ["use", "apply", "activate", "eat", "drink", "consume", "swallow", "inject",
            "insert", "install", "operate", "plug in", "plug"],
    "open": ["open"],
    "close": ["close", "shut"],
    "unlock": ["unlock", "pick lock of", "pick lock on", "pick lock", "lockpick", "pick the lock of",
               "pick the lock on", "pick"],
    "read": ["read", "skim", "browse"],
    "equip": ["equip", "wear", "wield", "put on", "hold", "arm", "don"],
    "unequip": ["unequip", "remove", "take off", "unwield", "stow", "doff"],
    "combine": ["combine", "merge", "mix", "join", "attach", "connect"],
    "craft": ["craft", "make", "build", "assemble", "create"],
    "repair": ["repair", "fix", "mend", "patch"],
    "give": ["give", "hand", "offer", "show", "feed", "present"],
    "talk": ["talk to", "talk with", "talk", "speak to", "speak with", "speak", "converse with",
             "chat with", "chat", "ask", "greet", "hail", "question", "t"],
    "fight": ["fight", "attack", "hit", "kill", "strike", "punch", "kick", "shoot", "smash", "destroy"],
    "go": ["go to", "go", "walk to", "walk", "move to", "move", "enter", "head to", "head",
           "travel to", "travel", "run to", "run", "climb", "crawl", "exit", "leave", "exits", "out",
           "descend", "ascend"],
    "buy": ["buy", "purchase"],
    "sell": ["sell"],
    "shop": ["shop", "trade", "barter", "wares", "browse wares"],
    "map": ["map", "m", "automap", "show map"],
    "journal": ["journal", "j", "quests", "quest", "log", "tasks", "objectives", "goals", "missions"],
    "stats": ["stats", "status", "character", "sheet", "me", "health", "score", "st"],
    "wait": ["wait", "z", "rest", "pass", "sleep", "listen"],
    "hint": ["hint", "hints", "clue"],
    "help": ["help", "?", "h", "commands", "verbs"],
    "style": ["style", "theme", "styles", "themes", "skin"],
    "sound": ["sound", "audio", "music", "sfx", "volume", "mute", "unmute"],
    "speed": ["speed", "text speed", "textspeed"],
    "art": ["art", "graphics", "images"],
    "save": ["save", "save game"],
    "load": ["load", "restore", "load game"],
    "quit": ["quit", "q", "bye", "exit game", "quit game"],
    "restart": ["restart", "start over", "new game"],
    "about": ["about", "version", "credits", "info"],
    "again": ["again", "g", "repeat"],
}

# sentence shapes: verb -> prepositions that split "object PREP target"
SPLITTERS = {
    "give": [" to "],
    "use": [" on ", " with ", " in ", " into ", " at ", " to "],
    "combine": [" with ", " and ", " + ", " to ", " onto "],
    "unlock": [" with ", " using "],
    "open": [" with ", " using "],
    "repair": [" with ", " using "],
    "fight": [" with ", " using "],
    "talk": [" about "],
    "take": [" from "],
    "buy": [" from "],
    "sell": [" to "],
}
# "give robot the cells" style is rare; "show X to Y" and "feed X to Y" use give's rule.

ARTICLES = {"the", "a", "an", "some", "my", "that", "this", "those", "these"}
NO_OBJECT = {"inventory", "map", "journal", "stats", "wait", "hint", "quit", "restart",
             "about", "again", "shop"}
SELF_WORDS = {"me", "myself", "self", "yourself", "you"}


class Command:
    __slots__ = ("verb", "obj", "target", "raw", "word", "error")

    def __init__(self, verb=None, obj="", target="", raw="", word="", error=""):
        self.verb = verb
        self.obj = obj
        self.target = target
        self.raw = raw
        self.word = word        # the verb as typed (for custom verbs)
        self.error = error

    def __repr__(self):
        return "Command(%r, obj=%r, target=%r)" % (self.verb, self.obj, self.target)


class Parser:
    def __init__(self, extra_verbs=None):
        self.verbs = {k: list(v) for k, v in VERBS.items()}
        for verb, words in (extra_verbs or {}).items():
            self.verbs.setdefault(verb, [])
            self.verbs[verb].extend(w for w in words if w not in self.verbs[verb])
        self._rebuild()

    def _rebuild(self):
        phrases = []
        for verb, words in self.verbs.items():
            for w in words:
                phrases.append((w, verb))
        # longest phrase first; on a tie the earlier table entry wins
        self._phrases = sorted(phrases, key=lambda p: -len(p[0]))
        self.known_words = sorted({p[0] for p in phrases} | set(DIR_WORDS))

    @staticmethod
    def clean(text):
        text = " ".join(text.strip().lower().replace("\t", " ").split())
        return text.strip(" .!?")

    @staticmethod
    def strip_articles(text):
        words = [w for w in text.split() if w not in ARTICLES]
        return " ".join(words)

    def parse(self, line):
        raw = line
        text = self.clean(line)
        if not text:
            return Command(None, raw=raw)

        # a bare direction: "n", "north", "up"
        if text in DIR_WORDS:
            return Command("go", obj=text, raw=raw, word="go")

        for phrase, verb in self._phrases:
            if text == phrase:
                rest = ""
            elif text.startswith(phrase + " "):
                rest = text[len(phrase) + 1:].strip()
            else:
                continue
            # "look" + object means examine; "search" alone means look
            if verb == "look" and rest:
                verb = "examine"
                for lead in ("at ", "in ", "inside ", "into "):
                    if rest.startswith(lead):
                        rest = rest[len(lead):]
            if verb == "examine" and not rest:
                verb = "look"
            if verb in NO_OBJECT and rest and verb not in ("shop",):
                # e.g. "rest here" / "status report": tolerate trailing words
                if verb in ("wait", "stats", "journal", "inventory", "map", "hint"):
                    rest = ""
                else:
                    continue
            cmd = Command(verb, raw=raw, word=phrase)
            return self._objects(cmd, rest)

        # unknown first word: maybe a game-defined verb ("push crate", "pray")
        parts = text.split(" ", 1)
        word = parts[0]
        rest = self.strip_articles(parts[1]) if len(parts) > 1 else ""
        near = difflib.get_close_matches(word, self.known_words, n=1, cutoff=0.75)
        hint = " Did you mean '%s'?" % near[0] if near and len(word) > 2 else ""
        return Command("custom", obj=rest, raw=raw, word=word,
                       error="I don't know how to '%s'.%s Type 'help' for the list of commands." % (word, hint))

    def _objects(self, cmd, rest):
        verb = cmd.verb
        if verb in ("help", "style", "sound", "speed", "save", "load", "art"):
            cmd.obj = rest                     # free-form argument
            if verb == "sound" and cmd.word not in ("sound", "audio"):
                cmd.obj = (cmd.word + " " + rest).strip()
            return cmd
        if verb == "go":
            for lead in ("to ", "through ", "into ", "in ", "toward ", "towards ", "via "):
                if rest.startswith(lead):
                    rest = rest[len(lead):]
            rest = self.strip_articles(rest)
            if cmd.word in ("descend",) and not rest:
                rest = "down"
            if cmd.word in ("ascend",) and not rest:
                rest = "up"
            cmd.obj = rest
            return cmd
        if verb == "talk":
            for lead in ("to ", "with "):
                if rest.startswith(lead):
                    rest = rest[len(lead):]
        if verb == "take" and rest in ("all", "everything", "all items"):
            cmd.obj = "all"
            return cmd
        obj, target = rest, ""
        for sep in SPLITTERS.get(verb, []):
            padded = " " + rest + " "
            idx = padded.find(sep)
            if idx > 0:
                obj = padded[:idx].strip()
                target = padded[idx + len(sep):].strip()
                break
        if verb == "combine" and not target and " " in obj:
            # "combine wire battery"
            a, b = obj.rsplit(" ", 1)
            obj, target = a, b
        cmd.obj = self.strip_articles(obj)
        cmd.target = self.strip_articles(target)
        if verb == "examine" and cmd.obj in SELF_WORDS:
            cmd.verb, cmd.obj = "stats", ""
        return cmd

    def suggest(self, word):
        return difflib.get_close_matches(word, self.known_words, n=3, cutoff=0.6)
