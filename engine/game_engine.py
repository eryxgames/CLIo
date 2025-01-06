import json
import os
import re
import random
import time
import shutil
import textwrap
from engine.parser import Parser
from engine.inventory import Inventory
from engine.battle_system import BattleSystem
from engine.media_player import MediaPlayer
from engine.save_load import SaveLoad
from engine.text_styler import TextStyler
from engine.style.config import StyleConfig
from engine.message_handler import message_handler

class GameEngine:
    def __init__(self, config_file, media_player, parser):
        self.config = self.load_config(config_file)
        
        # Initialize text styling singleton
        self.text_styler = TextStyler()
        self.message_handler = message_handler
        
        # Load and apply style config with proper path
        style_name = self.config.get("style_config", "default")
        style_config = StyleConfig.load(style_name)
        
        # Process the style configuration
        self.text_styler.process_config(style_config)
        
        # Apply the style configuration to message handler
        self.message_handler.text_styler.process_config(style_config)
        
        # Load game data
        self.scenes = self.load_data(self.config["scenes_file"]) 
        self.items = self.load_data(self.config["items_file"])
        self.characters = self.load_data(self.config["characters_file"])
        self.story_texts = self.load_data(self.config["story_texts_file"])
        self.current_scene = next(scene for scene in self.scenes if scene["id"] == self.config["initial_scene"])


        # Initialize game state
        self.inventory = Inventory()
        self.character_crafting_inventories = {}
        self.player_stats = self.config["player_stats"].copy()
        self.story_progress = {}
        self.hints_used = 0
        self.max_hints = self.config["max_hints"]

        # Add missing stats from items
        for item_id, item in self.items.items():
            if "effect" in item:
                for stat in item["effect"]:
                    if stat not in self.player_stats:
                        self.player_stats[stat] = 0

        # Initialize messages
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

        # Setup components
        self.media_player = media_player
        self.parser = parser

        # Initialize character movement
        self.commands_since_last_move = 0
        self.characters_last_move = {}
        self.initialize_movable_characters()

        message_handler.print_message("Game initialized", "system")

    def initialize_movable_characters(self):
        """Initialize tracking for characters that can move between scenes"""
        for char_id, char in self.characters.items():
            if char.get("movable", False):
                self.characters_last_move[char_id] = 0
                # Set initial scene for movable characters
                initial_scene = char.get("initial_scene", "scene1")
                # Find the scene and add the character if not already there
                for scene in self.scenes:
                    if scene["id"] == initial_scene:
                        if "characters" not in scene:
                            scene["characters"] = []
                        if char_id not in scene["characters"]:
                            scene["characters"].append(char_id)

    def clear_screen(self):
        os.system('cls' if os.name == 'nt' else 'clear')

    def display_styled_text(self, text_obj, default_style="default"):
        """Display text with implicit or explicit styling."""
        if isinstance(text_obj, dict):
            text = text_obj.get("text", "")
            style = text_obj.get("style", default_style)
        else:
            text = str(text_obj)
            style = default_style
            
        message_handler.print_message(text, style)

    def explore_scene(self):
        """Explore the current scene with implicit styling."""
        self.display_styled_text(self.current_scene["description"], "description")
        
        random_event = self.get_random_event()
        if random_event:
            self.display_styled_text(random_event, "ambient")
        
        if "items" in self.current_scene and self.current_scene["items"]:
            self.display_styled_text("You see:", "default")
            for item in self.current_scene["items"]:
                self.display_styled_text(f"- {self.items[item]['name']}", "item")
        
        if "passive_items" in self.current_scene and self.current_scene["passive_items"]:
            self.display_styled_text("You notice:", "default")
            for item in self.current_scene["passive_items"]:
                self.display_styled_text(f"- {self.items[item]['name']}", "item")
        
        if "characters" in self.current_scene:
            for char_id in self.current_scene["characters"]:
                character = self.characters[char_id]
                self.display_styled_text(character.get("greeting"), "greeting")
                
                random_text = self.get_random_character_text(char_id)
                if random_text:
                    self.display_styled_text(random_text, "ambient")

    def display_scene_description(self, scene):
        self.text_styler.print_text(
            scene["description"],
            style_name="scene"
        )

    def display_dialogue(self, text, character=None):
        if character:
            header = f"{character['name']} says:"
            self.text_styler.print_text(header, style_name="dialogue_header")
        self.text_styler.print_text(text, style_name="dialogue")

    def display_combat_message(self, message):
        self.text_styler.print_text(message, style_name="combat")

    def change_style_config(self, style_name):
        self.style_config = StyleConfig.load(f"engine/style_configs/{style_name}.json")
        self.text_styler.update_config(self.style_config)

    def process_command(self, command):
        if not command.strip():
            return
        if command == "quit":
            confirm = input("Are you sure you want to quit your adventure? (yes/no): ").lower()
            if confirm == "yes":
                message_handler.print_message("Thank you for playing! Goodbye!", "system")
                exit()
            else:
                message_handler.print_message("Continuing the adventure...", "system")
        elif command == "save":
            save_game_state = {
                "current_scene_id": self.current_scene["id"],
                "inventory_items": self.inventory.items,
                "equipped_items": self.inventory.equipped_items,
                "player_stats": self.player_stats,
                "story_progress": self.story_progress,
                "hints_used": self.hints_used,
                "character_crafting_inventories": self.character_crafting_inventories,
                "commands_since_last_move": self.commands_since_last_move,
                "characters_last_move": self.characters_last_move
            }
            SaveLoad().save_game(save_game_state, "savegame.json")
            message_handler.print_message("Game saved successfully!", "success")
        elif command == "load":
            try:
                saved_state = SaveLoad().load_game("savegame.json")
                self.load_game_state(saved_state)
                message_handler.print_message("Game loaded successfully!", "success")
                self.explore_scene()
            except FileNotFoundError:
                message_handler.print_message("No saved game found.", "error")
            except Exception as e:
                message_handler.print_message(f"Error loading game: {str(e)}", "error")
        else:
            parsed = self.parser.parse_command(command)
            action = parsed.get("action")
            if action == "invalid":
                message_handler.print_message(parsed.get("message"))
            else:
                handler = getattr(self, action, None)
                if handler:
                    params = parsed.get("parameters", {})
                    handler(**params)
                else:
                    message_handler.print_message("Unknown action.")



        if self.check_game_over():
            return

        self.check_conditions()

        # After processing any command, increment counter and check for character movement
        self.commands_since_last_move += 1
        self.check_character_movements()

    def check_character_movements(self):
        """Check and process any pending character movements"""
        for char_id, char in self.characters.items():
            if not char.get("movable", False):
                continue

            moves_after = char.get("moves_after_commands", 5)
            moves_on_scene_change = char.get("moves_on_scene_change", False)
            follow_player = char.get("follow_player", False)

            if follow_player:
                self.move_character_to_player_scene(char_id)
            elif self.commands_since_last_move >= moves_after:
                self.move_character(char_id)
            elif moves_on_scene_change:
                self.move_character(char_id)

    def move_character_to_player_scene(self, char_id):
        """Move a character to the player's current scene"""
        character = self.characters[char_id]
        current_scene = self.current_scene["id"]

        # Find the current scene of the character
        for scene in self.scenes:
            if "characters" in scene and char_id in scene["characters"]:
                scene["characters"].remove(char_id)
                break

        # Add the character to the player's current scene
        for scene in self.scenes:
            if scene["id"] == current_scene:
                if "characters" not in scene:
                    scene["characters"] = []
                if char_id not in scene["characters"]:
                    scene["characters"].append(char_id)
                    message_handler.print_message(f"\n{character['name']} follows you into the room.")
                break

    def move_character(self, char_id):
        """Move a character to an adjacent scene"""
        # Find current scene containing the character
        current_scene = None
        for scene in self.scenes:
            if "characters" in scene and char_id in scene["characters"]:
                current_scene = scene
                break

        if not current_scene:
            return

        # Get possible destinations from current scene's exits
        possible_destinations = []
        for exit in current_scene.get("exits", []):
            if not exit.get("locked", False) and not exit.get("blocked", False):
                possible_destinations.append(exit["scene_id"])

        if possible_destinations:
            # Choose random destination
            new_scene_id = random.choice(possible_destinations)

            # Remove character from current scene
            current_scene["characters"].remove(char_id)

            # Add character to new scene
            for scene in self.scenes:
                if scene["id"] == new_scene_id:
                    if "characters" not in scene:
                        scene["characters"] = []
                    scene["characters"].append(char_id)
                    break

            # Reset movement counter if this was triggered by command count
            if self.commands_since_last_move >= self.characters[char_id].get("moves_after_commands", 5):
                self.commands_since_last_move = 0

            # Update last move time
            self.characters_last_move[char_id] = time.time()

            # Only notify if character moves into or out of current scene
            if current_scene["id"] == self.current_scene["id"] or new_scene_id == self.current_scene["id"]:
                char_name = self.characters[char_id]["name"]
                if new_scene_id == self.current_scene["id"]:
                    message_handler.print_message(f"\n{char_name} enters the room.")
                else:
                    message_handler.print_message(f"\n{char_name} leaves the room.")

    def change_scene(self, scene_id):
        next_scene = next((scene for scene in self.scenes if scene["id"] == scene_id), None)
        if next_scene:
            self.current_scene = next_scene
            music_file = next_scene.get("music", "")
            if music_file and os.path.exists(music_file):
                MediaPlayer.play_music(music_file)
            else:
                message_handler.print_message("The sound of silence!")
            if "sound_effects" in next_scene and "enter" in next_scene["sound_effects"]:
                sound_effect_file = next_scene["sound_effects"]["enter"]
                if sound_effect_file and os.path.exists(sound_effect_file):
                    MediaPlayer.play_sound_effect(sound_effect_file)
                else:
                    message_handler.print_message("The sound of silence!")
            message_handler.print_message(self.current_scene["description"])
            self.report_characters_in_scene()
        else:
            message_handler.print_message("Invalid scene ID.")

        # After changing scene, check for character movements
        self.check_character_movements()

    def report_characters_in_scene(self):
        """Report characters present in the current scene"""
        if "characters" in self.current_scene and self.current_scene["characters"]:
            message_handler.print_message("\nYou notice the following characters in the scene:")
            for character_id in self.current_scene["characters"]:
                character = self.characters[character_id]
                # For movable characters, add movement-specific greeting
                if character.get("movable", False):
                    movement_text = " (moving between rooms)" if character.get("movable") else ""
                    message_handler.print_message(f"- {character['name']}{movement_text}: {character.get('greeting', 'No greeting available.')}")
                else:
                    message_handler.print_message(f"- {character['name']}: {character.get('greeting', 'No greeting available.')}")

    def load_config(self, filename):
        with open(filename, 'r') as f:
            return json.load(f)

    def load_data(self, filename):
        with open(filename, 'r') as f:
            return json.load(f)

    def explore_scene(self):
        message_handler.print_message(self.current_scene["description"])
        random_event = self.get_random_event()
        if random_event:
            message_handler.print_message(random_event)
        if "items" in self.current_scene and self.current_scene["items"]:
            message_handler.print_message("You see the following items:")
            for item in self.current_scene["items"]:
                message_handler.print_message(f"- {self.items[item]['name']}")
        if "passive_items" in self.current_scene and self.current_scene["passive_items"]:
            message_handler.print_message("You notice the following interactive items:")
            for item in self.current_scene["passive_items"]:
                message_handler.print_message(f"- {self.items[item]['name']}")
        if "characters" in self.current_scene and self.current_scene["characters"]:
            message_handler.print_message("You notice the following characters in the scene:")
            for character_id in self.current_scene["characters"]:
                character = self.characters[character_id]
                greeting = character.get("greeting", character["dialogue"].get("greet", "No greeting available."))
                message_handler.print_message(f"- {character['name']}: {greeting}")
                random_text = self.get_random_character_text(character_id)
                if random_text:
                    message_handler.print_message(f"  {random_text}")

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
                message_handler.print_message(item["description"])
                if item["usable"]:
                    # Logic to use the item
                    pass
                elif item.get("interactive"):
                    self.handle_interactive_item(item)
            elif item_id in self.current_scene.get("passive_items", []):
                passive_item = self.items[item_id]
                current_state = passive_item.get("current_state", "default")
                state_data = passive_item.get("states", {}).get(current_state, {})
                message_handler.print_message(state_data.get("description", "No description available."))
                action = state_data.get("action")
                if action:
                    if action == "open":
                        if "locked" in passive_item and passive_item["locked"]:
                            message_handler.print_message("The item is locked. You need to unlock it first.")
                        else:
                            message_handler.print_message(f"You open the {passive_item['name']}.")
                            passive_item["current_state"] = state_data.get("next_state", "open")
                            if "contents" in passive_item and passive_item["current_state"] == "open":
                                for content_item in passive_item["contents"]:
                                    self.current_scene["items"].append(content_item)
                                    message_handler.print_message(f"You find a {self.items[content_item]['name']} inside.")
                    elif action == "unlock":
                        if passive_item.get("unlock_required_item") == "passcode":
                            passcode = input("Enter the passcode to unlock the item: ")
                            if passcode == passive_item.get("passcode"):
                                message_handler.print_message(f"You enter the correct passcode and unlock the {passive_item['name']}.")
                                passive_item["locked"] = False
                                passive_item["current_state"] = state_data.get("next_state", "closed")
                            else:
                                message_handler.print_message("Incorrect passcode. The item remains locked.")
                        elif "bent_wire" in self.inventory.items:
                            message_handler.print_message(f"You use the bent wire to pick the lock of the {passive_item['name']}.")
                            passive_item["locked"] = False
                            passive_item["current_state"] = state_data.get("next_state", "closed")
                        else:
                            message_handler.print_message("You need a tool to pick the lock.")
                    elif action == "take":
                        reward_item = state_data.get("reward")
                        if reward_item:
                            if reward_item in self.current_scene["items"]:
                                self.take_item(reward_item)
                                passive_item["current_state"] = state_data.get("next_state", "empty")
                            else:
                                message_handler.print_message("There is nothing left to take.")
                        else:
                            message_handler.print_message("There is nothing to take.")
            else:
                message_handler.print_message(random.choice(self.item_not_found_messages))
        else:
            message_handler.print_message(random.choice(self.item_not_found_messages))

    def handle_interactive_item(self, item):
        current_state_key = item.get("current_state", "default")
        if current_state_key not in item["states"]:
            message_handler.print_message("Invalid state for this item.")
            return
        current_state = item["states"][current_state_key]
        message_handler.print_message(current_state["description"])
        action = current_state["action"]
        if action:
            next_state = current_state["next_state"]
            if action == "open":
                message_handler.print_message(f"You open the {item['name']}.")
                item["current_state"] = next_state
                if next_state == "open":
                    self.reveal_item_from_interactive(item)
            elif action == "unlock":
                if item["unlock_required_item"] == "passcode":
                    passcode = input("Enter the passcode to unlock the item: ")
                    if passcode == "321":
                        message_handler.print_message(f"You enter the correct passcode and unlock the {item['name']}.")
                        item["locked"] = False
                        item["current_state"] = next_state
                    else:
                        message_handler.print_message("Incorrect passcode. The item remains locked.")
                elif "bent_wire" in self.inventory.items:
                    message_handler.print_message(f"You use the bent wire to pick the lock of the {item['name']}.")
                    item["locked"] = False
                    item["current_state"] = next_state
                else:
                    message_handler.print_message(f"You need a tool to pick the lock of the {item['name']}.")
            elif action == "take":
                message_handler.print_message(f"You take the item from the {item['name']}.")
                item["current_state"] = next_state

    def reveal_item_from_interactive(self, item):
        if "contents" in item:
            for content_item in item["contents"]:
                self.current_scene["items"].append(content_item)
                message_handler.print_message(f"You find a {self.items[content_item]['name']} inside.")

    def take_item(self, item_name):
        if not item_name:
            message_handler.print_message(random.choice(self.unclear_command_messages))
            return
        item = self.find_item_by_name(item_name)
        if item and item["id"] in self.current_scene["items"]:
            item_id = item["id"]
            message_handler.print_message(f"You take the {item['name']}.")
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
            message_handler.print_message(random.choice(self.item_not_found_messages))

    def talk_to_character(self, character_name):
        if not character_name:
            message_handler.print_message("Who do you want to talk to?")
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
            message_handler.print_message("Character not found in this scene.")
        elif len(matching_characters) == 1:
            character_id = matching_characters[0]
            character = self.characters[character_id]
            self.start_dialogue(character)
        else:
            message_handler.print_message("Multiple characters match your query. Please be more specific:")
            for char_id in matching_characters:
                message_handler.print_message(f"- {self.characters[char_id]['name']}")

    def start_dialogue(self, character):
        """Start a dialogue with a character using implicit styling."""
        greeting = character.get("dialogue", {}).get("greet", character.get("greeting"))
        self.display_styled_text(greeting, "dialogue")
        
        options = character.get("dialogue_options", {})
        if options:
            self.display_styled_text("Choose an option:", "menu")
            for i, (option, response) in enumerate(options.items(), start=1):
                self.display_styled_text(f"{i}. {option}", "menu")
                
            while True:
                choice = input("Enter the number of your choice (or 'exit' to leave): ").lower().strip()
                
                # Check for exit command
                if choice in ['exit', 'quit', 'leave', 'back']:
                    self.display_styled_text("You end the conversation.", "dialogue")
                    return
                    
                # Try to convert input to number
                try:
                    choice_num = int(choice) - 1
                    if 0 <= choice_num < len(options):
                        selected_option = list(options.keys())[choice_num]
                        response = options[selected_option]
                        self.display_styled_text(response, "dialogue")
                        self.handle_dialogue_option(character, selected_option)
                        return
                    else:
                        self.display_styled_text(f"Please enter a number between 1 and {len(options)}.", "error")
                except ValueError:
                    self.display_styled_text("Please enter a valid number or 'exit' to leave the conversation.", "error")
        else:
            self.display_styled_text("No dialogue options available.", "dialogue")

    def give_item_to_character(self, item_name, character_name):
        """Enhanced give item handler with multiple interaction types."""
        item = self.find_item_by_name(item_name)
        if not item:
            self.display_styled_text("Item not found in the game data.", "error")
            return
            
        if item["id"] not in self.inventory.items:
            self.display_styled_text(f"{item['name']} not in your inventory.", "error")
            return

        # Find the character in the current scene
        matching_characters = [
            char_id for char_id in self.current_scene.get("characters", [])
            if character_name.lower() in self.characters[char_id]["name"].lower()
        ]

        if not matching_characters:
            message_handler.print_message("That character isn't here.")
            return

        character_id = matching_characters[0]
        character = self.characters[character_id]

        # Initialize crafting inventory if needed
        if character_id not in self.character_crafting_inventories:
            self.character_crafting_inventories[character_id] = set()

        # Check for crafting requirements first
        required_items_for_character = set()
        for craftable_id, craftable_item in self.items.items():
            if "npc_craftable" in craftable_item:
                craft_data = craftable_item["npc_craftable"]
                if craft_data["crafter"] == character_id:
                    required_items_for_character.update(craft_data["required_items"])

        # Check for item interactions defined in character
        if "item_interactions" in character:
            if item["id"] in character["item_interactions"]:
                interaction = character["item_interactions"][item["id"]]
                
                # Handle different types of interactions
                if interaction["type"] == "passage":
                    # Item required to pass/leave
                    message_handler.print_message(interaction["response"])
                    if interaction.get("consume_item", False):
                        self.inventory.remove_item(item["id"])
                    if "unlock_scene" in interaction:
                        self.current_scene["exits"][interaction["unlock_scene"]]["blocked"] = False
                    if "story_flag" in interaction:
                        self.update_story_progress(interaction["story_flag"], True)
                    return

                elif interaction["type"] == "information":
                    # Character provides information about the item
                    message_handler.print_message(interaction["response"])
                    if "story_flag" in interaction:
                        self.update_story_progress(interaction["story_flag"], True)
                    return

                elif interaction["type"] == "trade":
                    # Trade item for another item
                    message_handler.print_message(interaction["response"])
                    if interaction.get("consume_item", False):
                        self.inventory.remove_item(item["id"])
                    if "reward_item" in interaction:
                        self.inventory.add_item(interaction["reward_item"], self.items)
                    return

                elif interaction["type"] == "quest":
                    # Quest-related item interaction
                    message_handler.print_message(interaction["response"])
                    if interaction.get("consume_item", False):
                        self.inventory.remove_item(item["id"])
                    if "quest_flag" in interaction:
                        self.update_story_progress(interaction["quest_flag"], True)
                    if "reward_item" in interaction:
                        self.inventory.add_item(interaction["reward_item"], self.items)
                    return
                
                elif interaction["type"] == "replicate":
                    # Replicate item with comical errors
                    message_handler.print_message(interaction["response"])
                    if "reward_item" in interaction:
                        self.inventory.add_item(interaction["reward_item"], self.items)
                    return
                                
        # If no special interaction found, check if it's a crafting item
        if item["id"] in required_items_for_character:
            # Handle crafting (existing crafting logic)
            self.character_crafting_inventories[character_id].add(item["id"])
            self.inventory.remove_item(item["id"])
            message_handler.print_message(f"{character['name']} takes the {item['name']}.")

            # Check if we can craft anything
            for craftable_id, craftable_item in self.items.items():
                if "npc_craftable" in craftable_item:
                    craft_data = craftable_item["npc_craftable"]
                    if craft_data["crafter"] == character_id:
                        required_items = set(craft_data["required_items"])
                        if required_items.issubset(self.character_crafting_inventories[character_id]):
                            message_handler.print_message(craft_data["success_message"])
                            self.character_crafting_inventories[character_id].clear()
                            self.inventory.add_item(craftable_id, self.items)
                            message_handler.print_message(craft_data["dialogue_response"])
                        else:
                            remaining_items = required_items - self.character_crafting_inventories[character_id]
                            remaining_names = [self.items[item_id]["name"] for item_id in remaining_items]
                            if remaining_names:
                                message_handler.print_message(f"The {character['name']} still needs: {', '.join(remaining_names)}")
        else:
            message_handler.print_message(f"{character['name']} has no use for this item.")

    def handle_dialogue_option(self, character, option):
        """Handle dialogue options with proper styling."""
        character_id = character["id"]
        
        # Handle dialogue rewards
        if "dialogue_rewards" in character and option in character["dialogue_rewards"]:
            reward_data = character["dialogue_rewards"][option]
            if "required_progress" in reward_data:
                if not self.story_progress.get(reward_data["required_progress"]):
                    self.display_styled_text(reward_data.get("failure_message"), "error")
                    return
                
                # Give the reward item
                item_id = reward_data["item"]
                self.display_styled_text(reward_data.get("success_message"), "success")
                self.inventory.add_item(item_id, self.items)
                
    def fight_character(self, character_name):
        if not character_name:
            message_handler.print_message("Who do you want to fight?")
            return

        # Normalize the character name for comparison
        character_name = character_name.lower()

        # First try exact matches, then partial matches
        matching_characters = []
        for char_id, char in self.characters.items():
            if char["name"].lower() == character_name:
                matching_characters = [char_id]
                break
            elif character_name in char["name"].lower():
                matching_characters.append(char_id)

        if not matching_characters:
            message_handler.print_message("Character not found in this scene.")
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
                message_handler.print_message("This character is not hostile.")
        else:
            message_handler.print_message("Multiple characters match your query. Please be more specific:")
            for char_id in matching_characters:
                message_handler.print_message(f"- {self.characters[char_id]['name']}")

    def remove_enemy_from_scene(self, character_id):
        self.current_scene["characters"].remove(character_id)
        message_handler.print_message(f"The {self.characters[character_id]['name']} has been defeated and removed from the scene.")
        message_handler.print_message("There are signs of recent fight all over the place.")

    def drop_items_from_character(self, character_id):
        character = self.characters[character_id]
        if "inventory" in character:
            for item_id in character["inventory"]:
                item = self.items[item_id]
                self.current_scene["items"].append(item_id)
                message_handler.print_message(f"The {character['name']} drops a {item['name']}.")

    def exit_room(self, direction=None):
        """Handle room exit with proper input validation."""
        exits = self.current_scene.get("exits", [])
        if not exits:
            self.display_styled_text("There are no exits in this scene.", "error")
            return

        if len(exits) == 1:
            self.display_styled_text("There is just one exit from here. Do you want to leave?", "menu")
            while True:
                choice = input("Enter 'yes' to leave or 'no' to stay (or 'exit' to cancel): ").lower().strip()
                if choice in ['yes', 'y']:
                    self.attempt_to_exit(exits[0])
                    break
                elif choice in ['no', 'n', 'exit', 'cancel']:
                    self.display_styled_text("You decide to stay.", "dialogue")
                    break
                else:
                    self.display_styled_text("Please enter 'yes' or 'no'.", "error")
        else:
            self.display_styled_text("There are multiple exits. Where do you want to go?", "menu")
            for i, exit in enumerate(exits):
                self.display_styled_text(f"{i + 1}. {exit['door_name']}", "menu")
            
            while True:
                choice = input("Enter the number of your choice (or 'exit' to cancel): ").lower().strip()
                
                if choice in ['exit', 'cancel', 'back']:
                    self.display_styled_text("You decide to stay.", "dialogue")
                    return
                    
                try:
                    choice_num = int(choice) - 1
                    if 0 <= choice_num < len(exits):
                        self.attempt_to_exit(exits[choice_num])
                        break
                    else:
                        self.display_styled_text(f"Please enter a number between 1 and {len(exits)}.", "error")
                except ValueError:
                    if not choice:  # Empty input
                        self.display_styled_text("You decide to stay.", "dialogue")
                        return
                    self.display_styled_text("Please enter a valid number or 'exit' to cancel.", "error")

    def attempt_to_exit(self, exit):
        """Handle exit attempt with proper input validation."""
        if exit.get("blocked", False):
            required_condition = exit.get("required_condition")
            required_stat = exit.get("required_stat")
            required_value = exit.get("required_value")
            if required_condition and self.get_story_progress(required_condition):
                self.display_styled_text(exit["unblock_text"], "success")
                exit["blocked"] = False
                self.change_scene(exit["scene_id"])
            elif required_stat and self.player_stats.get(required_stat, 0) >= required_value:
                self.display_styled_text(exit["unblock_text"], "success")
                exit["blocked"] = False
                self.change_scene(exit["scene_id"])
            else:
                self.display_styled_text(exit["block_text"], "error")
        elif exit.get("locked", False):
            required_item = exit.get("required_item")
            if required_item == "passcode":
                while True:
                    passcode = input("Enter the passcode to unlock the door (or 'exit' to cancel): ").strip()
                    if passcode.lower() in ['exit', 'cancel', 'back']:
                        self.display_styled_text("You decide not to enter a passcode.", "dialogue")
                        return
                    if passcode == exit.get("passcode"):
                        self.display_styled_text(exit["unlock_text"], "success")
                        exit["locked"] = False
                        self.change_scene(exit["scene_id"])
                        break
                    elif not passcode:  # Empty input
                        return
                    else:
                        self.display_styled_text("Incorrect passcode. The door remains locked.", "error")
            elif required_item in self.inventory.items:
                self.display_styled_text(exit["unlock_text"], "success")
                if self.items[required_item].get("consumable", False):
                    self.inventory.remove_item(required_item)
                exit["locked"] = False
                self.change_scene(exit["scene_id"])
            else:
                self.display_styled_text(exit["lock_text"], "error")
        else:
            self.change_scene(exit["scene_id"])

    def list_inventory(self):
        items_text = "Inventory:\n" + "\n".join(
            f"- {self.items[item_id]['name']}"
            for item_id in self.inventory.items
        )
        self.text_styler.print_text(items_text, style_name="inventory")

    def examine_item(self, item_name):
        if not item_name:
            message_handler.print_message(random.choice(self.unclear_command_messages))
            return
        item = self.find_item_by_name(item_name)
        if item and item["id"] in self.inventory.items:
            message_handler.print_message(item["description"])
        else:
            message_handler.print_message(random.choice(self.item_not_found_messages))

    def craft_item(self, item_name):
        item = self.find_item_by_name(item_name)
        if item:
            self.inventory.craft_item(item["id"], self.items)
        else:
            message_handler.print_message("Item not found in the game data.")

    def combine_items(self, item1_name, item2_name):
        item1 = self.find_item_by_name(item1_name)
        item2 = self.find_item_by_name(item2_name)
        if item1 and item2:
            self.inventory.combine_items(item1["id"], item2["id"], self.items)
        else:
            message_handler.print_message("One or both items not found in your inventory.")

    def examine_self(self):
        message_handler.print_message("You examine yourself closely.")
        message_handler.print_message("Your stats:")
        message_handler.print_message(f"Health: {self.player_stats['health']}")
        message_handler.print_message(f"Strength: {self.player_stats['strength']}")
        message_handler.print_message(f"Defense: {self.player_stats['defense']}")
        message_handler.print_message(f"Attack: {self.player_stats['attack']}")
        self.inventory.list_equipped_items(self.items)
        self.list_inventory()
        self.describe_health_status()

    def describe_health_status(self):
        health = self.player_stats["health"]
        if health >= 75:
            message_handler.print_message("You are feeling great.")
        elif 50 <= health < 75:
            message_handler.print_message("You are slightly injured.")
        elif 25 <= health < 50:
            message_handler.print_message("You are moderately injured.")
        elif 10 <= health < 25:
            message_handler.print_message("You are heavily injured.")
        else:
            message_handler.print_message("You are critically injured.")

    def show_stats(self):
        message_handler.print_message("Your stats:")
        message_handler.print_message(f"Health: {self.player_stats['health']}")
        message_handler.print_message(f"Strength: {self.player_stats['strength']}")
        message_handler.print_message(f"Defense: {self.player_stats['defense']}")
        message_handler.print_message(f"Attack: {self.player_stats['attack']}")
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
                    message_handler.print_message(text_info["text"])
                    self.story_progress[text_key] = True
            else:
                message_handler.print_message(text_info["text"])
        else:
            message_handler.print_message("")  # when there is no key defined

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
                    message_handler.print_message(f"You used the {item['name']} and regained {effect['health']} health.")
                    self.inventory.remove_item(item["id"])
                # Add more effects as needed
            else:
                message_handler.print_message("This item cannot be used.", "story")
        else:
            message_handler.print_message("Item not found in inventory or cannot be used.")

    def equip_item(self, item_name):
        item = self.find_item_by_name(item_name)
        if item:
            effect = self.inventory.equip_item(item["id"], self.items)
            for stat, value in effect.items():
                self.player_stats[stat] += value
        else:
            message_handler.print_message("Item not found in inventory or cannot be equipped.")

    def unequip_item(self, item_name):
        item = self.find_item_by_name(item_name)
        if item:
            effect = self.inventory.unequip_item(item["id"], self.items)
            for stat, value in effect.items():
                self.player_stats[stat] -= value
        else:
            message_handler.print_message("Item not found in equipment.")

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
            message_handler.print_message("Item not found.")
            return

        if item["id"] not in self.inventory.items:
            message_handler.print_message("Item not found in your inventory.")
            return

        self.inventory.repair_item(item["id"], self.items)

    def provide_hint(self):
        if self.hints_used < self.max_hints:
            hint = self.current_scene.get("hint", "No hint available.")
            message_handler.print_message(hint)
            self.hints_used += 1
        else:
            message_handler.print_message("You have used all your hints.")

    def report_characters_in_scene(self):
        if "characters" in self.current_scene and self.current_scene["characters"]:
            message_handler.print_message("\nYou notice the following characters in the scene:")
            for character_id in self.current_scene["characters"]:
                character = self.characters[character_id]
                greeting = character.get("greeting", character["dialogue"].get("greet", "No greeting available."))
                message_handler.print_message(f"- {character['name']}: {greeting}")

    def read_item(self, item_name):
        """Read a readable item with proper delay and styling."""
        item = self.find_item_by_name(item_name)
        if item and "readable_item" in item:
            text = item["readable_item"]
            self.display_styled_text(f"You start reading the {item['name']}:", "default")
            message_handler.print_with_delay(text, item.get("read_speed", 0.05), "reading")
        else:
            self.display_styled_text(random.choice(self.item_not_found_messages), "error")

    def look_at(self, target_name):
        if not target_name:
            message_handler.print_message("What do you want to look at?")
            return

        # Normalize the target name for comparison
        target_name = target_name.lower()

        # Check characters first
        if "characters" in self.current_scene:
            for char_id in self.current_scene["characters"]:
                char = self.characters[char_id]
                if target_name in char["name"].lower():
                    message_handler.print_message(char["description"])
                    return

        # Then check items in the current scene
        for item_id in self.current_scene.get("items", []):
            item = self.items[item_id]
            if target_name in item["name"].lower():
                message_handler.print_message(item["description"])
                return

        # Check interactive items in the current scene
        for item_id in self.current_scene.get("passive_items", []):
            item = self.items[item_id]
            if target_name in item["name"].lower():
                current_state = item.get("current_state", "default")
                state_data = item["states"].get(current_state, {})
                message_handler.print_message(state_data.get("description", "No description available."))
                return

        # Finally check items in inventory
        for item_id in self.inventory.items:
            item = self.items[item_id]
            if target_name in item["name"].lower():
                message_handler.print_message(item["description"])
                return

        message_handler.print_message("You don't see that here.")

    def get_available_styles(self):
        """Get list of available style configurations."""
        style_dir = os.path.join("engine", "style", "configs")
        style_files = [f for f in os.listdir(style_dir) if f.endswith('.json')]
        return [os.path.splitext(f)[0] for f in style_files]

    def change_style(self, style_name=None):
        """Change the game's style configuration.
        
        Args:
            style_name: Name of style to change to, or None to rotate to next style
        """
        available_styles = self.get_available_styles()
        
        if not available_styles:
            message_handler.print_message("No style configurations found.", "error")
            return
            
        if style_name is None:
            # Rotate to next style
            current_style = self.config.get("style_config", "default")
            try:
                current_index = available_styles.index(current_style)
                next_index = (current_index + 1) % len(available_styles)
                style_name = available_styles[next_index]
            except ValueError:
                style_name = available_styles[0]
        elif style_name not in available_styles:
            message_handler.print_message(f"Style '{style_name}' not found. Available styles:", "error")
            for style in available_styles:
                message_handler.print_message(f"- {style}", "system")
            return
        
        try:
            # Load and apply the new style
            style_config = StyleConfig.load(style_name)
            self.text_styler.process_config(style_config)
            self.message_handler.text_styler.process_config(style_config)
            self.config["style_config"] = style_name
            
            # Announce the style change
            message_handler.print_message(f"Style changed to: {style_name}", "success")
            
        except Exception as e:
            message_handler.print_message(f"Error loading style '{style_name}': {str(e)}", "error")


    def repair_communicator(self):
        if "energy_cells" in self.inventory.items:
            self.inventory.remove_item("energy_cells")
            message_handler.print_message("Your communicator has been repaired.")
        else:
            message_handler.print_message("You don't have energy cells to repair the communicator.")

    def display_grouped_text(self, title, items, style="list_content"):
        """Display a group of related text items within a single frame."""
        if not items:
            return
        
        try:
            # Get terminal width with fallback
            term_width = shutil.get_terminal_size().columns - 4  # Account for frame
        except:
            term_width = 76  # Fallback width if can't detect terminal size
        
        # Format the title
        text = f"{title}\n\n"
        
        # Format each item with proper wrapping
        for item in items:
            wrapped = textwrap.fill(str(item), width=term_width, subsequent_indent='  ')
            text += f"- {wrapped}\n"
        
        self.display_styled_text(text.rstrip(), style)

    def help(self, topic=None):
        """Display help information about game commands and features.
        
        Args:
            topic: Optional specific topic to get help about
        """
        if topic:
            self.display_topic_help(topic)
            return

        # General help categories
        help_categories = {
            "Basic Commands": {
                "look/explore": "Look around the current scene",
                "inventory": "Check your inventory",
                "stats": "Show your character stats",
                "exit": "Exit current room (if possible)",
                "style": "Change game visual style",
                "save/load": "Save or load game progress",
                "quit": "Exit the game"
            },
            "Interaction Commands": {
                "look at [item/character]": "Examine something specific",
                "take [item]": "Pick up an item",
                "use [item]": "Use an item from your inventory",
                "read [item]": "Read a readable item",
                "combine [item1] with [item2]": "Combine two items",
                "equip/unequip [item]": "Equip or unequip items"
            },
            "Character Interaction": {
                "talk to [character]": "Start a conversation",
                "give [item] to [character]": "Give an item to a character",
                "fight [character]": "Engage in combat (careful!)"
            },
            "Special Commands": {
                "repair [item]": "Repair a broken item",
                "hint": f"Get a hint ({self.max_hints - self.hints_used} remaining)"
            }
        }

        # Display title
        self.display_styled_text("GAME HELP", "list_title")

        # Display scene-specific help if available
        scene_specific = []
        current_scene = self.current_scene
        
        if current_scene.get("items"):
            scene_specific.append("There are items you can interact with here")
        if current_scene.get("characters"):
            scene_specific.append("There are characters you can talk to here")
        if current_scene.get("exits"):
            scene_specific.append("There are exits you can use here")
        if current_scene.get("passive_items"):
            scene_specific.append("There are interactive objects in this scene")

        if scene_specific:
            self.display_grouped_text("In This Scene", scene_specific, "list_category")

        # Display command categories
        for category, commands in help_categories.items():
            formatted_commands = [f"{cmd}: {desc}" for cmd, desc in commands.items()]
            self.display_grouped_text(category, formatted_commands, "list_category")

        # Display tips
        tips = [
            "Type 'help [command]' for more details about a specific command",
            "Most commands support multiple variations (e.g., 'look' or 'explore')",
            "You can exit most interactions by typing 'exit' or pressing Enter",
            f"You have {self.max_hints - self.hints_used} hints remaining"
        ]
        self.display_grouped_text("Tips", tips, "list_content")

    def display_topic_help(self, topic):
        """Display help for a specific topic or command."""
        detailed_help = {
            "look": {
                "title": "Looking Around",
                "description": "Examine your surroundings or specific things",
                "usage": [
                    "look - View current scene",
                    "look at [item/character] - Examine something specific",
                    "explore - Same as 'look'"
                ],
                "tips": [
                    "Use 'look' whenever you enter a new area",
                    "Examining specific items might reveal important details"
                ]
            },
            "inventory": {
                "title": "Inventory Management",
                "description": "Check and manage your items",
                "usage": [
                    "inventory - Show all items",
                    "equip [item] - Equip an item",
                    "unequip [item] - Unequip an item"
                ],
                "tips": [
                    "Equipped items may affect your stats",
                    "Some items can be combined or repaired"
                ]
            },
            "combine": {
                "title": "Combining Items",
                "description": "Create new items by combining others",
                "usage": [
                    "combine [item1] with [item2]",
                    "combine [item1] and [item2]"
                ],
                "tips": [
                    "Not all items can be combined",
                    "Try combining related items",
                    "Some characters might give hints about combinations"
                ]
            }
            # Add more detailed help topics as needed
        }

        topic_lower = topic.lower()
        found_topic = next((v for k, v in detailed_help.items() 
                        if topic_lower in k.lower()), None)

        if found_topic:
            self.display_styled_text(found_topic['title'], "list_title")
            self.display_styled_text(found_topic['description'], "list_content")
            
            self.display_grouped_text("Usage", found_topic['usage'], "list_category")
            self.display_grouped_text("Tips", found_topic['tips'], "list_content")
        else:
            self.display_styled_text(
                f"No detailed help available for '{topic}'. Try 'help' for general commands.", 
                "error"
            )

    def load_game_state(self, saved_state):
        """Load a saved game state."""
        # Load current scene
        self.current_scene = next(
            scene for scene in self.scenes 
            if scene["id"] == saved_state["current_scene_id"]
        )
        
        # Load inventory
        self.inventory.items = saved_state["inventory_items"]
        self.inventory.equipped_items = saved_state.get("equipped_items", [])
        
        # Load player stats and progress
        self.player_stats = saved_state["player_stats"]
        self.story_progress = saved_state["story_progress"]
        self.hints_used = saved_state.get("hints_used", 0)
        
        # Load character states
        self.character_crafting_inventories = saved_state.get("character_crafting_inventories", {})
        self.commands_since_last_move = saved_state.get("commands_since_last_move", 0)
        self.characters_last_move = saved_state.get("characters_last_move", {})
        
        # Initial scene description
        message_handler.print_message("\nGame loaded. Current location:", "system")
