class GameEngine:
    def __init__(self, scenes, items, characters):
        self.scenes = scenes
        self.items = items
        self.characters = characters
        self.current_scene = next(scene for scene in self.scenes if scene["id"] == "scene1")
        self.inventory = []
        self.player_stats = {
            "health": 100,
            "strength": 10,
            "defense": 5,
            "equipment": []
        }

    def change_scene(self, scene_id):
        scene = next((scene for scene in self.scenes if scene["id"] == scene_id), None)
        if scene:
            self.current_scene = scene
            print(self.current_scene["description"])
        else:
            print("Invalid scene ID.")

    def explore_scene(self):
        print(self.current_scene["description"])
        if "items" in self.current_scene and self.current_scene["items"]:
            print("You see the following items:")
            for item in self.current_scene["items"]:
                print(f"- {self.items[item]['name']}")

    def interact_with_item(self, item_name):
        item = self.find_item_by_name(item_name)
        if item:
            print(item["description"])
            if item["usable"]:
                # Logic to use the item
                pass
        else:
            print("Item not found in this scene.")

    def take_item(self, item_name):
        item = self.find_item_by_name(item_name)
        if item:
            item_id = item["id"]
            print(f"You take the {item['name']}.")
            self.inventory.append(item_id)
            self.current_scene["items"].remove(item_id)
        else:
            print("Item not found in this scene.")

    def talk_to_character(self, character_name):
        if character_name in self.current_scene["characters"]:
            character = self.characters[character_name]
            print(character["dialogue"]["greet"])
        else:
            print("Character not found in this scene.")

    def give_item_to_character(self, item_name, character_name):
        item = self.find_item_by_name(item_name)
        if item and item["id"] in self.inventory and character_name in self.current_scene["characters"]:
            character = self.characters[character_name]
            if "give_" + item["id"] in character["interactions"]:
                interaction = character["interactions"]["give_" + item["id"]]
                print(interaction)
                # Logic to handle the interaction
            else:
                print("This character doesn't want that item.")
        else:
            print("Item not in inventory or character not in scene.")

    def fight_character(self, character_name):
        if character_name in self.current_scene["characters"]:
            character = self.characters[character_name]
            if character["type"] == "hostile":
                # Engage battle system
                pass
            else:
                print("This character is not hostile.")
        else:
            print("Character not found in this scene.")

    def exit_room(self):
        if "exits" in self.current_scene:
            exits = self.current_scene["exits"]
            if len(exits) == 1:
                next_scene_id = exits[0]["scene_id"]
                self.change_scene(next_scene_id)
            else:
                print("There are multiple exits. Where do you want to go?")
                for i, exit in enumerate(exits):
                    print(f"{i + 1}. {exit['description']}")
                choice = int(input("Enter the number of your choice: ")) - 1
                if 0 <= choice < len(exits):
                    next_scene_id = exits[choice]["scene_id"]
                    self.change_scene(next_scene_id)
                else:
                    print("Invalid choice.")
        else:
            print("There are no exits in this scene.")

    def list_inventory(self):
        if self.inventory:
            print("You have the following items in your inventory:")
            for item in self.inventory:
                print(f"- {self.items[item]['name']}")
        else:
            print("Your inventory is empty.")

    def examine_item(self, item_name):
        if not item_name:
            print("Please specify an item to examine.")
            return
        item = self.find_item_by_name(item_name)
        if item and item["id"] in self.inventory:
            print(item["description"])
        else:
            print("Item not found in your inventory.")

    def combine_items(self, item1, item2):
        item1_id = self.find_item_by_name(item1)["id"]
        item2_id = self.find_item_by_name(item2)["id"]
        if item1_id in self.inventory and item2_id in self.inventory:
            combination = f"{item1_id} + {item2_id}"
            if combination in self.items["combinations"]:
                new_item = self.items["combinations"][combination]
                print(f"You combine {item1} and {item2} to create {new_item}.")
                self.inventory.remove(item1_id)
                self.inventory.remove(item2_id)
                self.inventory.append(new_item)
            else:
                print("These items cannot be combined.")
        else:
            print("One or both items not found in your inventory.")

    def examine_self(self):
        print("You examine yourself:")
        print(f"Health: {self.player_stats['health']}")
        print(f"Strength: {self.player_stats['strength']}")
        print(f"Defense: {self.player_stats['defense']}")
        if self.player_stats["equipment"]:
            print("Equipment:")
            for item in self.player_stats["equipment"]:
                print(f"- {self.items[item]['name']}")
        else:
            print("You are not equipped with any items.")
        self.list_inventory()
        self.describe_health_status()

    def describe_health_status(self):
        health = self.player_stats["health"]
        if health >= 75:
            print("You are feeling great.")
        elif 50 <= health < 75:
            print("You are slightly injured.")
        elif 25 <= health < 50:
            print("You are moderately injured.")
        elif 10 <= health < 25:
            print("You are heavily injured.")
        else:
            print("You are critically injured.")

    def show_stats(self):
        print("You check your stats:")
        print(f"Health: {self.player_stats['health']}")
        print(f"Strength: {self.player_stats['strength']}")
        print(f"Defense: {self.player_stats['defense']}")
        if self.player_stats["equipment"]:
            print("Equipment:")
            for item in self.player_stats["equipment"]:
                print(f"- {self.items[item]['name']}")
        else:
            print("You are not equipped with any items.")

    def find_item_by_name(self, item_name):
        for item_id, item in self.items.items():
            if item_name.lower() in item["name"].lower():
                return {"id": item_id, "name": item["name"], "description": item["description"], "usable": item["usable"]}
        return None
