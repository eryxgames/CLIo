from dialogue_manager import DialogueManager
from player import Player


def main():
    player = Player()
    dialogue_manager = DialogueManager(player)
    # Load the dialogue file
    dialogue_manager.load_dialogue('dialogue.json')
    # Start the dialogue from node 1
    dialogue_manager.start('1')
    while True:
        dialogue_manager.display_current_node()
        responses = dialogue_manager.get_available_responses()
        if not responses:
            print("Dialogue complete.")
            break
        for i, response in enumerate(responses):
            print(f"{i+1}. {response['text']}")
        choice = int(input("Enter your choice: ")) - 1
        if 0 <= choice < len(responses):
            dialogue_manager.choose_response(choice)
            if not dialogue_manager.handle_events():
                print("Cannot proceed due to missing requirements.")
        else:
            print("Invalid choice.")

if __name__ == "__main__":
    main()