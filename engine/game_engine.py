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

    def interact_with_item(self, item_name):
        if item_name in self.current_scene["items"]:
            item = self.items[item_name]
            print(item["description"])
            if item["usable"]:
                # Logic to use the item
                pass
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
