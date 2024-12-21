class Parser:
    def __init__(self):
        self.actions = [
            {
                "names": ["look", "explore", "look around"],
                "action": "explore_scene",
                "parameters": []
            },
            {
                "names": ["take", "pick up", "grab"],
                "action": "take_item",
                "parameters": ["item_name"]
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
                "names": ["examine", "inspect", "study", "look at"],
                "action": "examine_item",
                "parameters": ["item_name"]
            },
            {
                "names": ["combine", "merge"],
                "action": "combine_items",
                "parameters": ["item1_name", "item2_name"]
            },
            {
                "names": ["craft"],
                "action": "craft_item",
                "parameters": ["item_name"]
            },
            {
                "names": ["examine yourself", "look at yourself"],
                "action": "examine_self",
                "parameters": []
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
            },
            {
                "names": ["repair"],
                "action": "repair_item",
                "parameters": ["item_name"]
            }
        ]

    def parse_command(self, command):
        command = command.lower()
        for action in self.actions:
            for name in action["names"]:
                if command.startswith(name):
                    params = {}
                    for param in action["parameters"]:
                        value = self.extract_parameter(command, name, param)
                        if value is None:
                            return {"action": "invalid", "message": f"Missing {param} for this action."}
                        params[param] = value
                    return {"action": action["action"], "parameters": params}
        return {"action": "invalid", "message": "I don't understand that command. Try to use the exact command."}

    def extract_parameter(self, command, action_name, param):
        # Remove the action name from the command
        remaining_command = command[len(action_name):].strip()
        if param == "item_name":
            return remaining_command
        elif param == "character_name":
            return remaining_command
        elif param == "item1_name":
            # Assuming item1 name is the first item mentioned
            items = remaining_command.split(',')
            if items:
                return items[0].strip()
            else:
                return None
        elif param == "item2_name":
            # Assuming item2 name is the second item mentioned
            items = remaining_command.split(',')
            if len(items) > 1:
                return items[1].strip()
            else:
                return None
        # Add more parameter extraction logic if needed
        return None
