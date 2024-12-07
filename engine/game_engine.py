import json
import os
import random
from engine import media_player
from engine.battle_system import BattleSystem

class GameEngine:
    def __init__(self, scenes, items, characters, story_texts_filename):
        self.scenes = scenes
        self.items = items
        self.characters = characters
        self.story_texts = self.load_story_texts(story_texts_filename)
        self.current_scene = next(scene for scene in self.scenes if scene["id"] == "scene1")
        self.inventory = []
        self.player_stats = {
            "health": 100,
            "strength": 10,
            "defense": 5,
            "equipment": []
        }
        self.story_progress = {}
        self.hints_used = 0
        self.max_hints = 5

    def load_story_texts(self, filename):
        try:
            with open(filename, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"Error: The file {filename} was not found.")
            return {}
        except json.JSONDecodeError:
            print(f"Error: The file {filename} is not a valid JSON file.")
            return {}

    def change_scene(self, scene_id):
        next_scene = next((scene for scene in self.scenes if scene["id"] == scene_id), None)
        if next_scene:
            self.current_scene = next_scene
            music_file = next_scene.get("music", "")
            if music_file and os.path.exists(music_file):
                media_player.play_music(music_file)
            else:
                print("The sound of silence!")
            if "sound_effects" in next_scene and "enter" in next_scene["sound_effects"]:
                sound_effect_file = next_scene["sound_effects"]["enter"]
                if sound_effect_file and os.path.exists(sound_effect_file):
                    media_player.play_sound_effect(sound_effect_file)
                else:
                    print("The sound of silence!")
            print(self.current_scene["description"])
            self.report_characters_in_scene()
        else:
            print("Invalid scene ID.")

    def explore_scene(self):
        print(self.current_scene["description"])
        random_event = self.get_random_event()
        if random_event:
            print(random_event)
        if "items" in self.current_scene and self.current_scene["items"]:
            print("You see the following items:")
            for item in self.current_scene["items"]:
                print(f"- {self.items[item]['name']}")
        if "passive_items" in self.current_scene and self.current_scene["passive_items"]:
            print("You notice the following interactive items:")
            for item in self.current_scene["passive_items"]:
                print(f"- {self.items[item]['name']}")

    def interact_with_item(self, item_name):
        item = self.find_item_by_name(item_name)
        if item:
            item_id = item["id"]
            if item_id in self.current_scene["items"]:
                print(item["description"])
                if item["usable"]:
                    # Logic to use the item
                    pass
                elif item.get("interactive"):
                    self.handle_interactive_item(item)
            elif item_id in self.current_scene.get("passive_items", []):
                passive_item = self.items[item_id]
                current_state = passive_item.get("current_state", "default")
                state_data = passive_item.get("states", {}).get(current_state, {})
                print(state_data.get("description", "No description available."))
                action = state_data.get("action")
                if action:
                    if action == "open":
                        if "locked" in passive_item and passive_item["locked"]:
                            print("The item is locked. You need to unlock it first.")
                        else:
                            print(f"You open the {passive_item['name']}.")
                            passive_item["current_state"] = state_data.get("next_state", "open")
                            if "contents" in passive_item:
                                for content_item in passive_item["contents"]:
                                    self.current_scene["items"].append(content_item)
                                    print(f"You find a {self.items[content_item]['name']} inside.")
                    elif action == "unlock":
                        if "bent_wire" in self.inventory:
                            print(f"You use the bent wire to pick the lock of the {passive_item['name']}.")
                            passive_item["locked"] = False
                            passive_item["current_state"] = state_data.get("next_state", "unlocked")
                        else:
                            print("You need a tool to pick the lock.")
                    elif action == "take":
                        reward_item = state_data.get("reward")
                        if reward_item:
                            if reward_item in self.current_scene["items"]:
                                self.take_item(reward_item)
                                passive_item["current_state"] = state_data.get("next_state", "empty")
                            else:
                                print("There is nothing left to take.")
                        else:
                            print("There is nothing to take.")
            else:
                print("Item not found in this scene.")
        else:
            print("Item not found in this scene. Try to use the exact command.")

    def handle_interactive_item(self, item):
        current_state_key = item.get("current_state", "default")
        if current_state_key not in item["states"]:
            print("Invalid state for this item.")
            return
        current_state = item["states"][current_state_key]
        print(current_state["description"])
        action = current_state["action"]
        if action:
            next_state = current_state["next_state"]
            if action == "open":
                print(f"You open the {item['name']}.")
                item["current_state"] = next_state
                if next_state == "open":
                    self.reveal_item_from_interactive(item)
            elif action == "unlock":
                if "bent_wire" in self.inventory:
                    print(f"You use the bent wire to pick the lock of the {item['name']}.")
                    item["current_state"] = next_state
                    if next_state == "open":
                        self.reveal_item_from_interactive(item)
                else:
                    print(f"You need a tool to pick the lock of the {item['name']}.")
            elif action == "take":
                print(f"You take the item from the {item['name']}.")
                item["current_state"] = next_state

    def reveal_item_from_interactive(self, item):
        if item["id"] == "metal_locker":
            self.current_scene["items"].append("storage_room_key")
            print("You find a Storage Room Key inside the locker.")
        elif item["id"] == "rusty_metal_locker":
            self.current_scene["items"].append("chx_cargo_hauler_manual")
            print("You find a CHX Cargo Hauler Manual inside the locker.")

    def take_item(self, item_name):
        item = self.find_item_by_name(item_name)
        if item:
            item_id = item["id"]
            print(f"You take the {item['name']}.")
            self.inventory.append(item_id)
            self.current_scene["items"].remove(item_id)
            # Ensure the item does not reappear in lockers or other interactive items
            for passive_item in self.current_scene.get("passive_items", []):
                passive_item_data = self.items[passive_item]
                if "states" in passive_item_data:
                    for state in passive_item_data["states"].values():
                        if state["action"] == "take" and state["next_state"] == "empty":
                            passive_item_data["current_state"] = "empty"
        else:
            print("Item not found in this scene.")

    def talk_to_character(self, character_name):
        if character_name in self.current_scene["characters"]:
            character = self.characters[character_name]
            if "conditions" in character:
                for condition, data in character["conditions"].items():
                    if condition == "has_energy_cells" and "energy_cells" in self.inventory:
                        print(data["text"])
                        if data["action"] == "repair_communicator":
                            self.repair_communicator()
                        return
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
                enemy_stats = character["stats"]
                battle = BattleSystem(self.player_stats, enemy_stats)
                battle.engage_battle()
            else:
                print("This character is not hostile.")
        else:
            print("Character not found in this scene.")

    def exit_room(self, direction=None):
        exits = self.current_scene.get("exits", [])
        if not exits:
            print("There are no exits in this scene.")
            return

        if len(exits) == 1:
            print("There is just one exit from here. Do you want to leave?")
            choice = input("Enter 'yes' to leave or 'no' to stay: ").lower()
            if choice == "yes":
                self.attempt_to_exit(exits[0])
            else:
                print("You decide to stay.")
        else:
            print("There are multiple exits. Where do you want to go?")
            for i, exit in enumerate(exits):
                print(f"{i + 1}. {exit['door_name']}")
            choice = int(input("Enter the number of your choice: ")) - 1
            if 0 <= choice < len(exits):
                self.attempt_to_exit(exits[choice])
            else:
                print("Invalid choice.")

    def attempt_to_exit(self, exit):
        if exit["locked"]:
            required_item = exit["required_item"]
            if required_item in self.inventory:
                print(exit["unlock_text"])
                if self.items[required_item].get("consumable", False):
                    self.inventory.remove(required_item)
                exit["locked"] = False  # Ensure the door stays unlocked
                self.change_scene(exit["scene_id"])
            else:
                print(exit["lock_text"])
        else:
            self.change_scene(exit["scene_id"])

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
        print("You examine yourself closely.")
        print("Your stats:")
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
        print("Your stats:")
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
            if item_name.lower() in item.get("name", "").lower():
                return {
                    "id": item_id,
                    "name": item.get("name", "Unknown Item"),
                    "description": item.get("description", "No description available."),
                    "usable": item.get("usable", False),
                    "interactive": item.get("interactive", False),
                    "states": item.get("states", {})
                }
        return None

    def display_story_text(self, text_key):
        text_info = self.story_texts.get(text_key, None)
        if text_info:
            show_once = text_info.get("show_once", False)
            if show_once:
                if text_key not in self.story_progress:
                    print(text_info["text"])
                    self.story_progress[text_key] = True
            else:
                print(text_info["text"])
        else:
            print("")  # when there is no key defined

    def check_game_over(self):
        if self.player_stats["health"] <= 0:
            self.display_story_text("outro_lose")
            return True
        return False

    def update_story_progress(self, event, value):
        self.story_progress[event] = value

    def get_story_progress(self, event):
        return self.story_progress.get(event, None)

    def check_conditions(self):
        for condition, items in self.story_texts["conditions"].items():
            for item_name, text_info in items.items():
                if condition == "item_in_inventory" and item_name in self.inventory:
                    self.display_story_text(text_info["text"])
                elif condition == "enemy_defeated" and self.check_enemy_defeated(item_name):
                    self.display_story_text(text_info["text"])

    def check_enemy_defeated(self, enemy_name):
        # Implement logic to check if the enemy is defeated
        return True

    def use_item(self, item_name):
        item = self.find_item_by_name(item_name)
        if item and item["id"] in self.inventory and item["usable"]:
            if "effect" in item:
                effect = item["effect"]
                if "health" in effect:
                    self.player_stats["health"] += effect["health"]
                    print(f"You used the {item['name']} and regained {effect['health']} health.")
                    self.inventory.remove(item["id"])
                # Add more effects as needed
            else:
                print("This item cannot be used.")
        else:
            print("Item not found in inventory or cannot be used.")

    def equip_item(self, item_name):
        item = self.find_item_by_name(item_name)
        if item and item["id"] in self.inventory and item.get("equippable", False):
            self.player_stats["equipment"].append(item["id"])
            self.inventory.remove(item["id"])
            if "effect" in item:
                for stat, value in item["effect"].items():
                    self.player_stats[stat] += value
            print(f"You equipped the {item['name']}.")
        else:
            print("Item not found in inventory or cannot be equipped.")

    def unequip_item(self, item_name):
        item = self.find_item_by_name(item_name)
        if item and item["id"] in self.player_stats["equipment"]:
            self.player_stats["equipment"].remove(item["id"])
            self.inventory.append(item["id"])
            if "effect" in item:
                for stat, value in item["effect"].items():
                    self.player_stats[stat] -= value
            print(f"You unequipped the {item['name']}.")
        else:
            print("Item not found in equipment.")

    def get_random_event(self):
        random_events = self.current_scene.get("random_events", [])
        if random_events:
            return random.choice(random_events)
        return ""

    def repair_communicator(self):
        if "energy_cells" in self.inventory:
            self.inventory.remove("energy_cells")
            print("Your communicator has been repaired.")
        else:
            print("You don't have energy cells to repair the communicator.")

    def provide_hint(self):
        if self.hints_used < self.max_hints:
            hint = self.current_scene.get("hint", "No hint available.")
            print(hint)
            self.hints_used += 1
        else:
            print("You have used all your hints.")

    def report_characters_in_scene(self):
        if "characters" in self.current_scene and self.current_scene["characters"]:
            print("You notice the following characters in the scene:")
            for character_id in self.current_scene["characters"]:
                character = self.characters[character_id]
                greeting = character.get("greeting", character["dialogue"]["greet"])
                print(f"- {character['name']}: {greeting}")