import json

class SaveLoad:
    def save_game(self, game_state, filename):
        with open(filename, 'w') as f:
            json.dump(game_state, f)
        print("Game saved.")

    def load_game(self, filename):
        with open(filename, 'r') as f:
            game_state = json.load(f)
        return game_state