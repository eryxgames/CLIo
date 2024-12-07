import json
import os
from os import environ
environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
from engine.parser import Parser
from engine.game_engine import GameEngine
from engine.inventory import Inventory
from engine.battle_system import BattleSystem
from engine.media_player import MediaPlayer
from utils.save_load import SaveLoad

def load_data(filename):
    with open(filename, 'r') as f:
        data = json.load(f)
    return data

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def main():
    # Clear the screen and display the game name and version
    clear_screen()
    print("================================")
    print("CLIo - Text-Based CLI Game Maker")
    print("Version 1.0")
    print("================================")
    print("                                ")

    # Initialize game components
    parser = Parser()
    inventory = Inventory()
    media_player = MediaPlayer()
    save_load = SaveLoad()

    # Initialize game engine with the configuration file
    game_engine = GameEngine('game_files/config.json')

    # Start the game
    media_player.print_with_delay(game_engine.current_scene["description"])
    game_engine.display_story_text("intro")

    try:
        while True:
            command = input(">> ").lower()
            if not command.strip():
                continue
            if command == "quit":
                confirm = input("Are you sure you want to quit your adventure? (yes/no): ").lower()
                if confirm == "yes":
                    print("Thank you for playing! Goodbye!")
                    break
                else:
                    print("Continuing the adventure...")
                    continue
            elif command == "save":
                save_game_state = {
                    "current_scene": game_engine.current_scene["id"],
                    "inventory": inventory.items,
                    "player_stats": game_engine.player_stats,
                    "story_progress": game_engine.story_progress
                    # Add more game state as needed
                }
                save_load.save_game(save_game_state, "savegame.json")
            elif command == "load":
                saved_state = save_load.load_game("savegame.json")
                game_engine.current_scene = next(scene for scene in game_engine.scenes if scene["id"] == saved_state["current_scene"])
                inventory.items = saved_state["inventory"]
                game_engine.player_stats = saved_state["player_stats"]
                game_engine.story_progress = saved_state["story_progress"]
                media_player.print_with_delay(game_engine.current_scene["description"])
            elif command.startswith("use "):
                item_name = command.split("use")[-1].strip()
                game_engine.use_item(item_name)
            elif command.startswith("equip "):
                item_name = command.split("equip")[-1].strip()
                game_engine.equip_item(item_name)
            elif command.startswith("unequip "):
                item_name = command.split("unequip")[-1].strip()
                game_engine.unequip_item(item_name)
            elif command.startswith("open "):
                item_name = command.split("open")[-1].strip()
                game_engine.interact_with_item(item_name)
            elif command.startswith("pick lock of "):
                item_name = command.split("lock of")[-1].strip()
                game_engine.interact_with_item(item_name)
            elif command == "hint":
                game_engine.provide_hint()
            else:
                response = parser.parse_command(command)
                if response and response != "I don't understand that command. Try to use the exact command.":
                    media_player.print_with_delay(response)

                # Further logic based on parsed command
                if "explore" in command or "look around" in command:
                    game_engine.explore_scene()
                elif "look at" in command and "yourself" not in command:
                    item_name = command.split("at")[-1].strip()
                    game_engine.interact_with_item(item_name)
                elif "look" in command:
                    game_engine.explore_scene()
                elif "take" in command or "pick up" in command or "grab" in command:
                    item_name = command.split()[-1].strip()
                    game_engine.take_item(item_name)
                elif "talk to" in command or "speak to" in command or "converse with" in command:
                    character_name = command.split("to")[-1].strip()
                    game_engine.talk_to_character(character_name)
                elif "give" in command:
                    parts = command.split()
                    item_name = parts[parts.index("give") + 1]
                    character_name = parts[parts.index("to") + 1]
                    game_engine.give_item_to_character(item_name, character_name)
                elif "fight" in command:
                    character_name = command.split("fight")[-1].strip()
                    game_engine.fight_character(character_name)
                elif "exit" in command or "go to" in command:
                    game_engine.exit_room()
                elif "inventory" in command:
                    game_engine.list_inventory()
                elif "examine" in command and "yourself" not in command or "inspect" in command or "study" in command:
                    item_name = command.split("examine")[-1].strip()
                    game_engine.examine_item(item_name)
                elif "combine" in command or "merge" in command:
                    parts = command.split()
                    item1 = parts[parts.index("combine") + 1]
                    item2 = parts[parts.index("with") + 1]
                    game_engine.combine_items(item1, item2)
                elif "examine yourself" in command or "look at yourself" in command:
                    game_engine.examine_self()
                elif "stats" in command:
                    game_engine.show_stats()

                # Check if the game is over
                if game_engine.check_game_over():
                    break

                # Check conditions for displaying story texts
                game_engine.check_conditions()
    except KeyboardInterrupt:
        print("\nGame interrupted. Thank you for playing! Goodbye!")

if __name__ == "__main__":
    main()
