class GameEngine:
    def __init__(self, scenes, items, characters):
        self.scenes = scenes
        self.items = items
        self.characters = characters
        self.current_scene = next(scene for scene in self.scenes if scene["id"] == "scene1")
        self.inventory = []

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
        if item_name in self.current_scene["items"]:
            item = self.items[item_name]
            print(item["description"])
            if item["usable"]:
                # Logic to use the item
                pass
        else:
            print("Item not found in this scene.")

    def take_item(self, item_name):
        if item_name in self.current_scene["items"]:
            item = self.items[item_name]
            print(f"You take the {item['name']}.")
            self.inventory.append(item_name)
            self.current_scene["items"].remove(item_name)
        else:
            print("Item not found in this scene.")

    def talk_to_character(self, character_name):
        if character_name in self.current_scene["characters"]:
            character = self.characters[character_name]
            print(character["dialogue"]["greet"])
        else:
            print("Character not found in this scene.")

    def give_item_to_character(self, item_name, character_name):
        if item_name in self.inventory and character_name in self.current_scene["characters"]:
            character = self.characters[character_name]
            if "give_" + item_name in character["interactions"]:
                interaction = character["interactions"]["give_" + item_name]
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
        if item_name in self.inventory:
            item = self.items[item_name]
            print(item["description"])
        else:
            print("Item not found in your inventory.")

    def combine_items(self, item1, item2):
        if item1 in self.inventory and item2 in self.inventory:
            combination = f"{item1} + {item2}"
            if combination in self.items["combinations"]:
                new_item = self.items["combinations"][combination]
                print(f"You combine {item1} and {item2} to create {new_item}.")
                self.inventory.remove(item1)
                self.inventory.remove(item2)
                self.inventory.append(new_item)
            else:
                print("These items cannot be combined.")
        else:
            print("One or both items not found in your inventory.")
