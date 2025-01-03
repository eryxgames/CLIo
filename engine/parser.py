class Parser:
    def __init__(self):
        self.actions = [
            {
                "names": ["look", "explore", "look around"],
                "action": "explore_scene",
                "parameters": []
            },
            {
                "names": ["look at", "examine", "inspect", "study"],
                "action": "look_at",
                "parameters": ["target_name"]
            },
            {
                "names": ["take", "pick up", "grab"],
                "action": "take_item",
                "parameters": ["item_name"]
            },
            {
                "names": ["combine", "merge"],
                "action": "combine_items",
                "parameters": ["item1_name", "item2_name"]
            },
            {
                "names": ["repair"],
                "action": "repair_item",
                "parameters": ["item_name"]
            },
            {
                "names": ["look at yourself", "examine yourself"],
                "action": "examine_self",
                "parameters": []
            },
            {
                "names": ["open"],
                "action": "interact_with_item",
                "parameters": ["item_name"]
            },
            {
                "names": ["close"],
                "action": "interact_with_item",
                "parameters": ["item_name"]
            },
            {
                "names": ["equip"],
                "action": "equip_item",
                "parameters": ["item_name"]
            },
            {
                "names": ["unequip"],
                "action": "unequip_item",
                "parameters": ["item_name"]
            },
            {
                "names": ["talk to", "speak to", "converse with"],
                "action": "talk_to_character",
                "parameters": ["character_name"]
            },
            {
                "names": ["give"],
                "action": "give_item_to_character",
                "parameters": ["item_name", "character_name"]
            },
            {
                "names": ["fight", "attack", "hit"],
                "action": "fight_character",
                "parameters": ["character_name"]
            },
            {
                "names": ["push"],
                "action": "push",
                "parameters": ["target_name"]
            },
            {
                "names": ["pull"],
                "action": "pull",
                "parameters": ["target_name"]
            },
            {
                "names": ["exit", "go to"],
                "action": "exit_room",
                "parameters": []
            },
            {
                "names": ["inventory"],
                "action": "list_inventory",
                "parameters": []
            },
            {
                "names": ["craft"],
                "action": "craft_item",
                "parameters": ["item_name"]
            },
            {
                "names": ["stats"],
                "action": "show_stats",
                "parameters": []
            },
            {
                "names": ["use"],
                "action": "use_item",
                "parameters": ["item_name"]
            },
            {
                "names": ["pick lock", "lockpick"],
                "action": "interact_with_item",
                "parameters": ["item_name"]
            },
            {
                "names": ["read"],
                "action": "read_item",
                "parameters": ["item_name"]
            },
            {
                "names": ["help"],
                "action": "help",
                "parameters": []
            }
        ]

    def parse_command(self, command):
        command = command.lower().strip()

        # Special case for exact matches first
        for action in self.actions:
            if command in action["names"]:
                return {"action": action["action"], "parameters": {}}

        # Handle more complex commands
        for action in self.actions:
            for name in action["names"]:
                # Use startswith only for complete words to avoid 'look' matching 'look at'
                if (name + " ").startswith(command + " "):
                    return {"action": action["action"], "parameters": {}}

                if command.startswith(name + " "):
                    params = {}
                    remaining = command[len(name):].strip()

                    # Handle each parameter type
                    for param in action["parameters"]:
                        if param in ["target_name", "character_name", "item_name"]:
                            params[param] = remaining
                        elif param in ["item1_name", "item2_name"]:
                            items = self.parse_combination(remaining)
                            if not items:
                                return {"action": "invalid", "message": f"Invalid format for combining items."}
                            params["item1_name"] = items[0]
                            params["item2_name"] = items[1]

                    # Only return if we have all required parameters
                    if len(params) == len(action["parameters"]):
                        return {"action": action["action"], "parameters": params}

        return {"action": "invalid", "message": "I don't understand that command. Try to use the exact command."}

    def parse_combination(self, command):
        # Handle various combination formats:
        # "combine item1 and item2"
        # "combine item1 with item2"
        # "combine item1 + item2"
        command = command.replace(" and ", " + ")
        command = command.replace(" with ", " + ")
        items = command.split(" + ")
        return [item.strip() for item in items] if len(items) == 2 else None
