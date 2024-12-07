class Parser:
    def __init__(self):
        self.keywords = {
            "explore": self.explore,
            "look around": self.explore,
            "look at": self.look_at,
            "take": self.take,
            "pick up": self.take,
            "open": self.open,
            "close": self.close,
            "equip": self.equip,
            "unequip": self.unequip,
            "talk to": self.talk_to,
            "give": self.give,
            "fight": self.fight,
            "exit": self.exit_room,
            "go to": self.exit_room,
            "inventory": self.list_inventory,
            "examine": self.examine_item,
            "combine": self.combine_items,
            "examine yourself": self.examine_self,
            "look at yourself": self.examine_self,
            "stats": self.show_stats
        }

    def parse_command(self, command):
        if not command.strip():
            return None
        for keyword, action in self.keywords.items():
            if keyword in command:
                return action(command)
        return "I don't understand that command."

    def explore(self, command):
        return "You explore the area, taking in every detail."

    def look_at(self, command):
        item_name = command.split("at")[-1].strip()
        if not item_name:
            return "Please specify an item to look at."
        return f"You carefully examine the {item_name}."

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
