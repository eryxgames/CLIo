class Parser:
    def __init__(self):
        self.keywords = {
            "explore": self.explore,
            "look around": self.explore,
            "look at": self.look_at,
            "look": self.look,
            "take": self.take,
            "pick up": self.take,
            "grab": self.take,
            "open": self.open,
            "close": self.close,
            "equip": self.equip,
            "unequip": self.unequip,
            "talk to": self.talk_to,
            "speak to": self.talk_to,
            "converse with": self.talk_to,
            "give": self.give,
            "fight": self.fight,
            "exit": self.exit_room,
            "go to": self.exit_room,
            "inventory": self.list_inventory,
            "examine": self.examine_item,
            "inspect": self.examine_item,
            "study": self.examine_item,
            "combine": self.combine_items,
            "merge": self.combine_items,
            "examine yourself": self.examine_self,
            "look at yourself": self.examine_self,
            "stats": self.show_stats,
            "use": self.use,
            "pick lock": self.pick_lock,
            "lockpick": self.pick_lock,
            "help": self.help
        }

    def parse_command(self, command):
        if not command.strip():
            return None
        for keyword, action in self.keywords.items():
            if keyword in command:
                return action(command)
        return "I don't understand that command. Try to use the exact command."

    def explore(self, command):
        return "You explore the area, taking in every detail."

    def look_at(self, command):
        item_name = command.split("at")[-1].strip()
        if not item_name:
            return "Please specify an item to look at."
        return f"You carefully examine the {item_name}."

    def look(self, command):
        return "You look around the area, taking in every detail."

    def take(self, command):
        item_name = command.split()[-1].strip()
        if not item_name:
            return "Please specify an item to take."
        return f"You reach out and take the {item_name}."

    def open(self, command):
        item_name = command.split()[-1].strip()
        if not item_name:
            return "Please specify an item to open."
        return f"You cautiously open the {item_name}."

    def close(self, command):
        item_name = command.split()[-1].strip()
        if not item_name:
            return "Please specify an item to close."
        return f"You firmly close the {item_name}."

    def equip(self, command):
        item_name = command.split()[-1].strip()
        if not item_name:
            return "Please specify an item to equip."
        return f"You equip the {item_name}, feeling more prepared."

    def unequip(self, command):
        item_name = command.split()[-1].strip()
        if not item_name:
            return "Please specify an item to unequip."
        return f"You unequip the {item_name}, feeling a bit lighter."

    def talk_to(self, command):
        character_name = command.split("to")[-1].strip()
        if not character_name:
            return "Please specify a character to talk to."
        return f"You approach {character_name} and start a conversation."

    def give(self, command):
        parts = command.split()
        if "give" in parts and "to" in parts:
            item_name = parts[parts.index("give") + 1]
            character_name = parts[parts.index("to") + 1]
            if not item_name or not character_name:
                return "Please specify an item to give and a character to give it to."
            return f"You hand the {item_name} to {character_name}."
        return "Please specify an item to give and a character to give it to."

    def fight(self, command):
        character_name = command.split("fight")[-1].strip()
        if not character_name:
            return "Please specify a character to fight."
        return f"You prepare to fight {character_name}, your heart racing."

    def exit_room(self, command):
        return "You look for a way out of the room."

    def list_inventory(self, command):
        return "You check your inventory."

    def examine_item(self, command):
        item_name = command.split("examine")[-1].strip()
        if not item_name:
            return "Please specify an item to examine."
        return f"You examine the {item_name} closely."

    def combine_items(self, command):
        parts = command.split()
        if "combine" in parts and "with" in parts:
            item1 = parts[parts.index("combine") + 1]
            item2 = parts[parts.index("with") + 1]
            if not item1 or not item2:
                return "Please specify two items to combine."
            return f"You attempt to combine {item1} with {item2}."
        return "Please specify two items to combine."

    def examine_self(self, command):
        return "You examine yourself closely."

    def show_stats(self, command):
        return "Your stats:"

    def use(self, command):
        item_name = command.split("use")[-1].strip()
        if not item_name:
            return "Please specify an item to use."
        return f"You use the {item_name}."

    def pick_lock(self, command):
        item_name = command.split("lock of")[-1].strip()
        if not item_name:
            return "Please specify an item to pick the lock of."
        return f"You attempt to pick the lock of the {item_name}."

    def help(self, command):
        return (
            "Available commands:\n"
            "explore - Look around the area.\n"
            "look at [item] - Examine a specific item.\n"
            "look - Look around the area.\n"
            "take [item] - Pick up an item.\n"
            "open [item] - Open an item.\n"
            "close [item] - Close an item.\n"
            "equip [item] - Equip an item.\n"
            "unequip [item] - Unequip an item.\n"
            "talk to [character] - Talk to a character.\n"
            "give [item] to [character] - Give an item to a character.\n"
            "fight [character] - Fight a character.\n"
            "exit - Look for a way out of the room.\n"
            "go to [exit] - Go to a specific exit.\n"
            "inventory - Check your inventory.\n"
            "examine [item] - Examine an item closely.\n"
            "combine [item1] with [item2] - Combine two items.\n"
            "examine yourself - Examine yourself closely.\n"
            "look at yourself - Examine yourself closely.\n"
            "stats - Show your stats.\n"
            "use [item] - Use an item.\n"
            "pick lock of [item] - Pick the lock of an item.\n"
            "help - Show this help message."
        )