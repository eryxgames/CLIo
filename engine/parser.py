class Parser:
    def __init__(self):
        self.actions = [
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
                "names": ["craft"],
                "action": "craft_item",
                "parameters": ["item_name"]
            },
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
                "names": ["examine", "inspect", "study"],
                "action": "examine",
                "parameters": ["target_name"]
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
                "names": ["look at"],
                "action": "examine",
                "parameters": ["target_name"]
            }
        ]

    def parse_command(self, command):
        words = command.lower().split()
        for action in self.actions:
            for name in action["names"]:
                if name in command.lower():
                    if name == "combine":
                        plus_count = words.count('+')
                        if plus_count != 1:
                            return {"action": "invalid", "message": "Invalid combine command. Use 'combine item1 + item2'."}
                    params = {}
                    for param in action["parameters"]:
                        value = self.extract_parameter(words, name, param)
                        if value is None:
                            return {"action": "invalid", "message": f"Missing {param} for this action."}
                        params[param] = value
                    return {"action": action["action"], "parameters": params}
        return {"action": "invalid", "message": "I don't understand that command. Try to use the exact command."}

    def extract_parameter(self, words, action_name, param):
        if param == "item1_name":
            try:
                index = words.index('combine') + 1
                plus_index = words.index('+')
                return ' '.join(words[index:plus_index]).strip().replace(' ', '_')
            except ValueError:
                return None
        elif param == "item2_name":
            try:
                plus_index = words.index('+') + 1
                return ' '.join(words[plus_index:]).strip().replace(' ', '_')
            except ValueError:
                return None
        elif param == "item_name":
            try:
                index = words.index(action_name) + 1
                return ' '.join(words[index:]).strip().replace(' ', '_')
            except ValueError:
                return None
        elif param == "character_name":
            try:
                index = words.index(action_name) + 1
                return ' '.join(words[index:]).strip().replace(' ', '_')
            except ValueError:
                return None
        elif param == "target_name":
            try:
                if action_name == "look at":
                    look_at_index = words.index('look') + 1
                    return ' '.join(words[look_at_index:]).strip().replace(' ', '_')
                else:
                    return None
            except ValueError:
                return None
        # Add more parameter extraction logic if needed
        return None