import json
import os
from os import environ
environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
from engine.game_engine import GameEngine
from engine.save_load import SaveLoad
from engine.media_player import MediaPlayer
from engine.parser import Parser

def load_data(filename):
    with open(filename, 'r') as f:
        return json.load(f)

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def main():
    clear_screen()
    print("================================")
    print("CLIo - Text-Based CLI Game Maker")
    print("Version 1.0")
    print("================================")
    print("                                ")

    media_player = MediaPlayer()
    save_load = SaveLoad()
    parser = Parser()  # Initialize the Parser
    game_engine = GameEngine('game_files/config.json', media_player, parser)  # Pass the parser to GameEngine
    media_player.print_with_delay(game_engine.current_scene["description"])
    game_engine.display_story_text("intro")

    try:
        while True:
            command = input(">> ").lower()
            if not command.strip():
                continue
            game_engine.process_command(command)

            if game_engine.check_game_over():
                break

            game_engine.check_conditions()
    except KeyboardInterrupt:
        print("\nGame interrupted. Thank you for playing! Goodbye!")

if __name__ == "__main__":
    main()
