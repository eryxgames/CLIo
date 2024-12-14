import json
import os

class SaveLoad:
    def __init__(self):
        self.save_file = "savegame.json"

    def save_game(self, game_state, filename=None):
        if filename is None:
            filename = self.save_file
        with open(filename, 'w') as f:
            json.dump(game_state, f, indent=2)
        print(f"Game saved to {filename}")

    def load_game(self, filename=None):
        if filename is None:
            filename = self.save_file
        if os.path.exists(filename):
            with open(filename, 'r') as f:
                return json.load(f)
        else:
            print(f"Save file {filename} not found.")
            return None
