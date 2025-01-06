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
                "names": ["help", "?"],
                "action": "help",
                "parameters": ["topic"]
            },
            {
                "names": ["hint"],
                "action": "provide_hint",
                "parameters": []
            },            
            {
                "names": ["style"],
                "action": "change_style",
                "parameters": ["style_name"]
            }
        ]

    def parse_combination(self, command):
        """Parse combination command formats."""
        # Handle various combination formats:
        # "item1 with item2"
        # "item1 and item2"
        command = command.replace(" with ", " + ")
        command = command.replace(" and ", " + ")
        items = command.split(" + ")
        return [item.strip() for item in items] if len(items) == 2 else None

    def parse_command(self, command):
        command = command.lower().strip()

        # Special case for "give" command
        if command.startswith("give "):
            remaining = command[5:].strip()
            parts = remaining.split(" to ")
            if len(parts) == 2:
                item_name = parts[0].strip()
                character_name = parts[1].strip()
                return {
                    "action": "give_item_to_character",
                    "parameters": {"item_name": item_name, "character_name": character_name}
                }
            else:
                return {
                    "action": "invalid",
                    "message": "Invalid give command. Use 'give [item_name] to [character_name]'."
                }

        # Special case for help command
        if command.startswith("help "):
            parts = command.split(None, 1)  # Split into max 2 parts
            if len(parts) > 1:
                return {
                    "action": "help",
                    "parameters": {"topic": parts[1].strip()}  # Changed from topic_name to topic
                }
        elif command == "help":
            return {
                "action": "help",
                "parameters": {"topic": None}  # Changed from topic_name to topic
            }
        

        # Special case for style command
        if command.startswith("style"):
            parts = command.split(None, 1)
            style_name = parts[1] if len(parts) > 1 else None
            return {
                "action": "change_style",
                "parameters": {"style_name": style_name}
            }            

        # Handle combine command specially
        if command.startswith("combine "):
            remaining = command[8:].strip()  # Length of "combine " is 8
            items = self.parse_combination(remaining)
            if items:
                return {
                    "action": "combine_items",
                    "parameters": {
                        "item1_name": items[0],
                        "item2_name": items[1]
                    }
                }
            else:
                return {
                    "action": "invalid",
                    "message": "Invalid combination format. Use 'combine [item1] with [item2]' or 'combine [item1] and [item2]'."
                }

        # Process multi-word commands
        for action in self.actions:
            for name in action["names"]:
                if " " in name:  # Multi-word command
                    if command.startswith(name + " "):
                        remaining = command[len(name):].strip()
                        if remaining:
                            # Check if this is a combination command
                            if action["action"] == "combine_items":
                                items = self.parse_combination(remaining)
                                if items:
                                    return {
                                        "action": action["action"],
                                        "parameters": {
                                            "item1_name": items[0],
                                            "item2_name": items[1]
                                        }
                                    }
                            else:
                                return {
                                    "action": action["action"],
                                    "parameters": {action["parameters"][0]: remaining}
                                }
                    elif command == name:
                        if not action["parameters"]:
                            return {"action": action["action"], "parameters": {}}
                        else:
                            return {
                                "action": "invalid",
                                "message": f"The command '{name}' needs a target. Try '{name} [target]'."
                            }

        # Process single-word commands
        for action in self.actions:
            for name in action["names"]:
                if not " " in name:
                    if command == name:
                        return {"action": action["action"], "parameters": {}}
                    elif command.startswith(name + " "):
                        remaining = command[len(name):].strip()
                        if remaining and action["parameters"]:
                            return {
                                "action": action["action"],
                                "parameters": {action["parameters"][0]: remaining}
                            }

        return {"action": "invalid", "message": "I don't understand that command. Try 'help' for a list of commands."}
