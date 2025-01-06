import json

class SaveLoad:
    def save_game(self, game_state, filename):
        """Save game state to a file."""
        try:
            with open(filename, 'w') as f:
                json.dump(game_state, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving game: {str(e)}")
            return False

    def load_game(self, filename):
        """Load game state from a file."""
        try:
            with open(filename, 'r') as f:
                game_state = json.load(f)
            return game_state
        except FileNotFoundError:
            raise FileNotFoundError("No saved game found.")
        except json.JSONDecodeError:
            raise ValueError("Saved game file is corrupted.")
        except Exception as e:
            raise Exception(f"Error loading game: {str(e)}")