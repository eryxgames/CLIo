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
    # Load data files
    scenes = load_data('game_files/scenes/scenes.json')
    items = load_data('game_files/items.json')
    characters = load_data('game_files/characters.json')

    # Initialize game components
    parser = Parser()
    inventory = Inventory()
    media_player = MediaPlayer()
    save_load = SaveLoad()

    # Initialize game engine
    game_engine = GameEngine(scenes, items, characters)

    # Start the game
    media_player.print_with_delay(game_engine.current_scene["description"])

    while True:
        command = input(">> ").lower()
        if command == "quit":
            break
        elif command == "save":
            save_game_state = {
                "current_scene": game_engine.current_scene["id"],
                "inventory": inventory.items
                # Add more game state as needed
            }
            save_load.save_game(save_game_state, "savegame.json")
        elif command == "load":
            saved_state = save_load.load_game("savegame.json")
            game_engine.current_scene = next(scene for scene in scenes if scene["id"] == saved_state["current_scene"])
            inventory.items = saved_state["inventory"]
            media_player.print_with_delay(game_engine.current_scene["description"])
        else:
            response = parser.parse_command(command)
            media_player.print_with_delay(response)

            # Further logic based on parsed command
            if "explore" in command:
                media_player.print_with_delay(game_engine.current_scene["description"])
            elif "look at" in command:
                item_name = command.split("at")[-1].strip()
                game_engine.interact_with_item(item_name)
            elif "take" in command:
                item_name = command.split("take")[-1].strip()
                game_engine.interact_with_item(item_name)
                inventory.add_item(item_name)
            elif "talk to" in command:
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

if __name__ == "__main__":
    main()
