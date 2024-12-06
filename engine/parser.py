class Parser:
    def __init__(self):
        self.keywords = {
            "explore": self.explore,
            "look at": self.look_at,
            "take": self.take,
            "talk to": self.talk_to,
            "give": self.give,
            "fight": self.fight
        }

    def parse_command(self, command):
        for keyword, action in self.keywords.items():
            if keyword in command:
                return action(command)
        return "I don't understand that command."

    def explore(self, command):
        return "You explore the area."

    def look_at(self, command):
        item_name = command.split("at")[-1].strip()
        return f"You look at the {item_name}."

    def take(self, command):
        item_name = command.split("take")[-1].strip()
        return f"You take the {item_name}."

    def talk_to(self, command):
        character_name = command.split("to")[-1].strip()
        return f"You talk to {character_name}."

    def give(self, command):
        parts = command.split()
        item_name = parts[parts.index("give") + 1]
        character_name = parts[parts.index("to") + 1]
        return f"You give the {item_name} to {character_name}."

    def fight(self, command):
        character_name = command.split("fight")[-1].strip()
        return f"You fight {character_name}."
