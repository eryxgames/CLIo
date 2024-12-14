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

def display_menu():
    print("1. Start New Game")
    print("2. Continue (Load Game)")
    print("3. Options")
    print("4. Hall of Fame")
    print("5. Quit")

def main():
    clear_screen()
    print("================================")
    print("CLIo - Text-Based CLI Game Maker")
    print("Version 1.0")
    print("================================")
    print("                                ")

    media_player = MediaPlayer()  # Create an instance of MediaPlayer
    parser = Parser()  # Create an instance of Parser

    while True:
        display_menu()
        choice = input("Enter your choice: ")

        if choice == "1":
            # Start New Game
            game_engine = GameEngine('game_files/config.json', media_player, parser)
            media_player.print_with_delay(game_engine.current_scene["description"])
            game_engine.display_story_text("intro")
            game_loop(game_engine)
        elif choice == "2":
            # Continue (Load Game)
            saved_state = SaveLoad.load_game("savegame.json")
            if saved_state:
                game_engine = GameEngine('game_files/config.json', media_player, parser)
                game_engine.load_game_state(saved_state)
                game_loop(game_engine)
            else:
                print("No saved game found.")
        elif choice == "3":
            # Options
            print("Options not implemented yet.")
        elif choice == "4":
            # Hall of Fame
            print("Hall of Fame not implemented yet.")
        elif choice == "5":
            # Quit
            print("Thank you for playing! Goodbye!")
            break
        else:
            print("Invalid choice. Please select again.")

def game_loop(game_engine):
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