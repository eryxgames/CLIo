import json
import os
import re
import random
import time
from engine.parser import Parser
from engine.inventory import Inventory
from engine.battle_system import BattleSystem
from engine.media_player import MediaPlayer
from engine.save_load import SaveLoad

class GameEngine:
    def __init__(self, config_file, media_player, parser):
        self.config = self.load_config(config_file)
        self.scenes = self.load_data(self.config["scenes_file"])
        self.items = self.load_data(self.config["items_file"])
        self.characters = self.load_data(self.config["characters_file"])
        self.story_texts = self.load_data(self.config["story_texts_file"])
        self.current_scene = next(scene for scene in self.scenes if scene["id"] == self.config["initial_scene"])
        self.inventory = Inventory()
        self.player_stats = self.config["player_stats"]
        self.story_progress = {}
        self.hints_used = 0
        self.max_hints = self.config["max_hints"]
        self.item_not_found_messages = [
            "No such item in sight.",
            "Such item is not within reach.",
            "No can do.",
            "You can't see that item here.",
            "That item is not available.",
            "You can't reach that item.",
            "That item is out of your reach."
        ]
        self.unclear_command_messages = [
            "Be more clear than that.",
            "Be more specific.",
            "I don't understand that command.",
            "Please provide more details.",
            "That command is unclear.",
            "I need more information to proceed."
        ]
        self.media_player = media_player
        self.parser = parser  # Initialize the Parser

        # Ensure that all possible stats are present in player_stats
        for item_id, item in self.items.items():
            if "effect" in item:
                for stat in item["effect"]:
                    if stat not in self.player_stats:
                        self.player_stats[stat] = 0

    def process_command(self, command):
        if not command.strip():
            return
        if command == "quit":
            confirm = input("Are you sure you want to quit your adventure? (yes/no): ").lower()
            if confirm == "yes":
                print("Thank you for playing! Goodbye!")
                exit()
            else:
                print("Continuing the adventure...")
        elif command == "save":
            save_game_state = {
                "current_scene": self.current_scene["id"],
                "inventory": self.inventory.items,
                "player_stats": self.player_stats,
                "story_progress": self.story_progress
            }
            SaveLoad().save_game(save_game_state, "savegame.json")
        elif command == "load":
            saved_state = SaveLoad().load_game("savegame.json")
            self.load_game_state(saved_state)
        else:
            parsed = self.parser.parse_command(command)
            action = parsed.get("action")
            if action == "invalid":
                print(parsed.get("message"))
            else:
                handler = getattr(self, action, None)
                if handler:
                    params = parsed.get("parameters", {})
                    handler(**params)
                else:
                    print("Unknown action.")

        if self.check_game_over():
            return

        self.check_conditions()

    def load_config(self, filename):
        with open(filename, 'r') as f:
            return json.load(f)

    def load_data(self, filename):
        with open(filename, 'r') as f:
            return json.load(f)

    def change_scene(self, scene_id):
        next_scene = next((scene for scene in self.scenes if scene["id"] == scene_id), None)
        if next_scene:
            self.current_scene = next_scene
            music_file = next_scene.get("music", "")
            if music_file and os.path.exists(music_file):
                MediaPlayer.play_music(music_file)
            else:
                print("The sound of silence!")
            if "sound_effects" in next_scene and "enter" in next_scene["sound_effects"]:
                sound_effect_file = next_scene["sound_effects"]["enter"]
                if sound_effect_file and os.path.exists(sound_effect_file):
                    MediaPlayer.play_sound_effect(sound_effect_file)
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
        if "characters" in self.current_scene and self.current_scene["characters"]:
            print("You notice the following characters in the scene:")
            for character_id in self.current_scene["characters"]:
                character = self.characters[character_id]
                greeting = character.get("greeting", character["dialogue"].get("greet", "No greeting available."))
                print(f"- {character['name']}: {greeting}")
                random_text = self.get_random_character_text(character_id)
                if random_text:
                    print(f"  {random_text}")

    def get_random_character_text(self, character_id):
        character = self.characters[character_id]
        random_events = character.get("random_events", [])
        if random_events:
            return random.choice(random_events)
        return ""

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
                            if "contents" in passive_item and passive_item["current_state"] == "open":
                                for content_item in passive_item["contents"]:
                                    self.current_scene["items"].append(content_item)
                                    print(f"You find a {self.items[content_item]['name']} inside.")
                    elif action == "unlock":
                        if passive_item.get("unlock_required_item") == "passcode":
                            passcode = input("Enter the passcode to unlock the item: ")
                            if passcode == passive_item.get("passcode"):
                                print(f"You enter the correct passcode and unlock the {passive_item['name']}.")
                                passive_item["locked"] = False
                                passive_item["current_state"] = state_data.get("next_state", "closed")
                            else:
                                print("Incorrect passcode. The item remains locked.")
                        elif "bent_wire" in self.inventory.items:
                            print(f"You use the bent wire to pick the lock of the {passive_item['name']}.")
                            passive_item["locked"] = False
                            passive_item["current_state"] = state_data.get("next_state", "closed")
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
                print(random.choice(self.item_not_found_messages))
        else:
            print(random.choice(self.item_not_found_messages))

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
                if item["unlock_required_item"] == "passcode":
                    passcode = input("Enter the passcode to unlock the item: ")
                    if passcode == "321":
                        print(f"You enter the correct passcode and unlock the {item['name']}.")
                        item["locked"] = False
                        item["current_state"] = next_state
                    else:
                        print("Incorrect passcode. The item remains locked.")
                elif "bent_wire" in self.inventory.items:
                    print(f"You use the bent wire to pick the lock of the {item['name']}.")
                    item["locked"] = False
                    item["current_state"] = next_state
                else:
                    print(f"You need a tool to pick the lock of the {item['name']}.")
            elif action == "take":
                print(f"You take the item from the {item['name']}.")
                item["current_state"] = next_state

    def reveal_item_from_interactive(self, item):
        if "contents" in item:
            for content_item in item["contents"]:
                self.current_scene["items"].append(content_item)
                print(f"You find a {self.items[content_item]['name']} inside.")

    def take_item(self, item_name):
        if not item_name:
            print(random.choice(self.unclear_command_messages))
            return
        item = self.find_item_by_name(item_name)
        if item and item["id"] in self.current_scene["items"]:
            item_id = item["id"]
            print(f"You take the {item['name']}.")
            self.inventory.add_item(item_id, self.items)
            self.current_scene["items"].remove(item_id)
            # Ensure the item does not reappear in lockers or other interactive items
            for passive_item in self.current_scene.get("passive_items", []):
                passive_item_data = self.items[passive_item]
                if "states" in passive_item_data:
                    for state in passive_item_data["states"].values():
                        if state["action"] == "take" and state["next_state"] == "empty":
                            passive_item_data["current_state"] = "empty"
        else:
            print(random.choice(self.item_not_found_messages))

    def talk_to_character(self, character_name):
        if not character_name:
            print("Who do you want to talk to?")
            return

        # Normalize the character name for comparison
        character_name = character_name.lower()

        # First try exact matches, then partial matches
        matching_characters = []
        for char_id in self.current_scene.get("characters", []):
            char = self.characters[char_id]
            if char["name"].lower() == character_name:
                matching_characters = [char_id]
                break
            elif character_name in char["name"].lower():
                matching_characters.append(char_id)

        if not matching_characters:
            print("Character not found in this scene.")
        elif len(matching_characters) == 1:
            character_id = matching_characters[0]
            character = self.characters[character_id]
            self.start_dialogue(character)
        else:
            print("Multiple characters match your query. Please be more specific:")
            for char_id in matching_characters:
                print(f"- {self.characters[char_id]['name']}")

    def start_dialogue(self, character):
        greeting = character["dialogue"].get("greet", character.get("greeting", "The character does not have a greeting."))
        print(greeting)
        options = character.get("dialogue_options", {})
        if options:
            print("Choose an option:")
            for i, (option, response) in enumerate(options.items(), start=1):
                print(f"{i}. {option}")
            choice = int(input("Enter the number of your choice: ")) - 1
            if 0 <= choice < len(options):
                selected_option = list(options.keys())[choice]
                print(options[selected_option])
                # Handle specific interactions based on the selected option
                if selected_option == "repair_communicator":
                    self.repair_item("broken_communicator")
                elif selected_option == "calm_down":
                    self.update_story_progress("hostile_droid_defeated", True)
                    character["type"] = "neutral"
            else:
                print("Invalid choice.")
        else:
            print("No dialogue options available.")

    def give_item_to_character(self, item_name, character_name):
        item = self.find_item_by_name(item_name)
        if item and item["id"] in self.inventory.items:
            matching_characters = [char for char in self.current_scene["characters"] if character_name.lower() in self.characters[char]["name"].lower()]
            if len(matching_characters) == 1:
                character_id = matching_characters[0]
                character = self.characters[character_id]
                if f"give_{item['id']}" in character["interactions"]:
                    interaction = character["interactions"][f"give_{item['id']}"]
                    print(interaction)
                    # Logic to handle the interaction
                    if interaction == "friendly_robot_repair":
                        self.repair_item("broken_communicator")
                    elif interaction == "hostile_droid_calm_down":
                        self.update_story_progress("hostile_droid_defeated", True)
                else:
                    print("This character doesn't want that item.")
            else:
                print("Character not found in scene or multiple characters match your query.")
        else:
            print("Item not in inventory.")

    def fight_character(self, character_name):
        if not character_name:
            print("Who do you want to fight?")
            return

        # Normalize the character name for comparison
        character_name = character_name.lower()

        # First try exact matches, then partial matches
        matching_characters = []
        for char_id in self.current_scene.get("characters", []):
            char = self.characters[char_id]
            if char["name"].lower() == character_name:
                matching_characters = [char_id]
                break
            elif character_name in char["name"].lower():
                matching_characters.append(char_id)

        if not matching_characters:
            print("Character not found in this scene.")
        elif len(matching_characters) == 1:
            character_id = matching_characters[0]
            character = self.characters[character_id]
            if character["type"] in ["hostile", "neutral", "aggressive"]:
                enemy_stats = character["stats"]
                battle = BattleSystem(self.player_stats, enemy_stats)
                battle.start_battle()
                if self.player_stats["health"] > 0:
                    self.update_story_progress(f"{character_id}_defeated", True)
                    self.remove_enemy_from_scene(character_id)
                    self.drop_items_from_character(character_id)
            else:
                print("This character is not hostile.")
        else:
            print("Multiple characters match your query. Please be more specific:")
            for char_id in matching_characters:
                print(f"- {self.characters[char_id]['name']}")

    def remove_enemy_from_scene(self, character_id):
        self.current_scene["characters"].remove(character_id)
        print(f"The {self.characters[character_id]['name']} has been defeated and removed from the scene.")
        print("There are signs of recent fight all over the place.")

    def drop_items_from_character(self, character_id):
        character = self.characters[character_id]
        if "inventory" in character:
            for item_id in character["inventory"]:
                item = self.items[item_id]
                self.current_scene["items"].append(item_id)
                print(f"The {character['name']} drops a {item['name']}.")

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
        if exit.get("blocked", False):
            required_condition = exit.get("required_condition")
            required_stat = exit.get("required_stat")
            required_value = exit.get("required_value")
            if required_condition and self.get_story_progress(required_condition):
                print(exit["unblock_text"])
                exit["blocked"] = False  # Ensure the door stays unblocked
                self.change_scene(exit["scene_id"])
            elif required_stat and self.player_stats.get(required_stat, 0) >= required_value:
                print(exit["unblock_text"])
                exit["blocked"] = False  # Ensure the door stays unblocked
                self.change_scene(exit["scene_id"])
            else:
                print(exit["block_text"])
        elif exit.get("locked", False):
            required_item = exit.get("required_item")
            if required_item == "passcode":
                passcode = input("Enter the passcode to unlock the door: ")
                if passcode == exit.get("passcode"):
                    print(exit["unlock_text"])
                    exit["locked"] = False  # Ensure the door stays unlocked
                    self.change_scene(exit["scene_id"])
                else:
                    print("Incorrect passcode. The door remains locked.")
            elif required_item in self.inventory.items:
                print(exit["unlock_text"])
                if self.items[required_item].get("consumable", False):
                    self.inventory.remove_item(required_item)
                exit["locked"] = False  # Ensure the door stays unlocked
                self.change_scene(exit["scene_id"])
            else:
                print(exit["lock_text"])
        else:
            self.change_scene(exit["scene_id"])

    def list_inventory(self):
        self.inventory.list_inventory(self.items)

    def examine_item(self, item_name):
        if not item_name:
            print(random.choice(self.unclear_command_messages))
            return
        item = self.find_item_by_name(item_name)
        if item and item["id"] in self.inventory.items:
            print(item["description"])
        else:
            print(random.choice(self.item_not_found_messages))

    def craft_item(self, item_name):
        item = self.find_item_by_name(item_name)
        if item:
            self.inventory.craft_item(item["id"], self.items)
        else:
            print("Item not found in the game data.")

    def combine_items(self, item1_name, item2_name):
        item1 = self.find_item_by_name(item1_name)
        item2 = self.find_item_by_name(item2_name)
        if item1 and item2:
            self.inventory.combine_items(item1["id"], item2["id"], self.items)
        else:
            print("One or both items not found in your inventory.")

    def examine_self(self):
        print("You examine yourself closely.")
        print("Your stats:")
        print(f"Health: {self.player_stats['health']}")
        print(f"Strength: {self.player_stats['strength']}")
        print(f"Defense: {self.player_stats['defense']}")
        print(f"Attack: {self.player_stats['attack']}")
        self.inventory.list_equipped_items(self.items)
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
        print(f"Attack: {self.player_stats['attack']}")
        self.inventory.list_equipped_items(self.items)

    def find_item_by_name(self, item_name):
        for item_id, item in self.items.items():
            if item_name.lower() in item.get("name", "").lower():
                return {
                    "id": item_id,
                    "name": item.get("name", "Unknown Item"),
                    "description": item.get("description", "No description available."),
                    "usable": item.get("usable", False),
                    "interactive": item.get("interactive", False),
                    "states": item.get("states", {}),
                    "readable_item": item.get("readable_item", None),
                    "read_speed": item.get("read_speed", 0.05)
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
                if condition == "item_in_inventory" and item_name in self.inventory.items:
                    self.display_story_text(text_info["text"])
                elif condition == "enemy_defeated" and self.check_enemy_defeated(item_name):
                    self.display_story_text(text_info["text"])

    def check_enemy_defeated(self, enemy_name):
        # Implement logic to check if the enemy is defeated
        return True

    def use_item(self, item_name):
        item = self.find_item_by_name(item_name)
        if item and item["id"] in self.inventory.items and item["usable"]:
            if "effect" in item:
                effect = item["effect"]
                if "health" in effect:
                    self.player_stats["health"] += effect["health"]
                    print(f"You used the {item['name']} and regained {effect['health']} health.")
                    self.inventory.remove_item(item["id"])
                # Add more effects as needed
            else:
                print("This item cannot be used.")
        else:
            print("Item not found in inventory or cannot be used.")

    def equip_item(self, item_name):
        item = self.find_item_by_name(item_name)
        if item:
            effect = self.inventory.equip_item(item["id"], self.items)
            for stat, value in effect.items():
                self.player_stats[stat] += value
        else:
            print("Item not found in inventory or cannot be equipped.")

    def unequip_item(self, item_name):
        item = self.find_item_by_name(item_name)
        if item:
            effect = self.inventory.unequip_item(item["id"], self.items)
            for stat, value in effect.items():
                self.player_stats[stat] -= value
        else:
            print("Item not found in equipment.")

    def get_random_event(self):
        random_events = self.current_scene.get("random_events", [])
        if random_events:
            return random.choice(random_events)
        return ""

    # In GameEngine class:
    def repair_item(self, item_name):
        """
        Repair an item using the appropriate repair tool.

        Args:
            item_name (str): Name of the item to repair
        """
        item = self.find_item_by_name(item_name)
        if not item:
            print("Item not found.")
            return

        if item["id"] not in self.inventory.items:
            print("Item not found in your inventory.")
            return

        self.inventory.repair_item(item["id"], self.items)

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
                greeting = character.get("greeting", character["dialogue"].get("greet", "No greeting available."))
                print(f"- {character['name']}: {greeting}")

    def read_item(self, item_name):
        item = self.find_item_by_name(item_name)
        if item and "readable_item" in item:
            text = item["readable_item"]
            print(f"You start reading the {item['name']}:")
            self.print_with_delay(text, item.get("read_speed", 0.05))
        else:
            print(random.choice(self.item_not_found_messages))


    def look_at(self, target_name):
        if not target_name:
            print("What do you want to look at?")
            return

        # Normalize the target name for comparison
        target_name = target_name.lower()

        # Check characters first
        if "characters" in self.current_scene:
            for char_id in self.current_scene["characters"]:
                char = self.characters[char_id]
                if target_name in char["name"].lower():
                    print(char["description"])
                    return

        # Then check items in the current scene
        for item_id in self.current_scene.get("items", []):
            item = self.items[item_id]
            if target_name in item["name"].lower():
                print(item["description"])
                return

        # Check interactive items in the current scene
        for item_id in self.current_scene.get("passive_items", []):
            item = self.items[item_id]
            if target_name in item["name"].lower():
                current_state = item.get("current_state", "default")
                state_data = item["states"].get(current_state, {})
                print(state_data.get("description", "No description available."))
                return

        # Finally check items in inventory
        for item_id in self.inventory.items:
            item = self.items[item_id]
            if target_name in item["name"].lower():
                print(item["description"])
                return

        print("You don't see that here.")


    def print_with_delay(self, text, delay=0.05):
        paragraphs = text.split("\n\n")
        for paragraph in paragraphs:
            for char in paragraph:
                print(char, end='', flush=True)
                time.sleep(delay)
            print("\n")
            time.sleep(1)  # Pause between paragraphs


    def repair_communicator(self):
        if "energy_cells" in self.inventory.items:
            self.inventory.remove_item("energy_cells")
            print("Your communicator has been repaired.")
        else:
            print("You don't have energy cells to repair the communicator.")

    def load_game_state(self, saved_state):
        self.current_scene = next(scene for scene in self.scenes if scene["id"] == saved_state["current_scene"])
        self.inventory.items = saved_state["inventory"]
        self.player_stats = saved_state["player_stats"]
        self.story_progress = saved_state["story_progress"]
        MediaPlayer.print_with_delay(self.current_scene["description"])
