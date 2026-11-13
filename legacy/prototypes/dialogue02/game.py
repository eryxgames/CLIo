import json
import os

# Load inventory from file
def load_inventory():
    if os.path.exists('inventory.json'):
        with open('inventory.json', 'r') as file:
            return json.load(file)
    else:
        return {}

# Save inventory to file
def save_inventory(inventory):
    with open('inventory.json', 'w') as file:
        json.dump(inventory, file)

# Add item to inventory
def add_item(inventory, item, quantity=1):
    if item in inventory:
        inventory[item] += quantity
    else:
        inventory[item] = quantity
    print(f"You have received {quantity} {item}.")

# Remove item from inventory
def remove_item(inventory, item, quantity=1):
    if item in inventory and inventory[item] >= quantity:
        inventory[item] -= quantity
        if inventory[item] == 0:
            del inventory[item]
        print(f"You have given {quantity} {item}.")
        return True
    else:
        print("You don't have enough of that item.")
        return False

# Display current inventory
def display_inventory(inventory):
    print("Current inventory:")
    for item, quantity in inventory.items():
        print(f"- {item}: {quantity}")

# Conversation loop
def conversation_loop(dialogue, current_node, inventory):
    while True:
        node = dialogue[current_node]
        print(f"{node['character']}: {node['text']}")
        responses = node['responses']
        for i, response in enumerate(responses, 1):
            print(f"{i}. {response['text']}")
        print("0. Exit Conversation")
        choice = input("Enter your choice: ")
        if choice == "0":
            break  # Exit the conversation
        else:
            try:
                chosen_response = responses[int(choice)-1]
                if "give_item" in chosen_response:
                    item = chosen_response["give_item"]
                    if remove_item(inventory, item):
                        current_node = chosen_response["node_id"]
                    else:
                        continue  # Prompt again
                else:
                    current_node = chosen_response["node_id"]
                # Handle any events in the new node
                for event in node.get("events", []):
                    if event["type"] == "give_item":
                        add_item(inventory, event["item"])
                # Display updated inventory if items were added or removed
                display_inventory(inventory)
            except (IndexError, ValueError):
                print("Invalid choice. Please try again.")

def main():
    inventory = load_inventory()
    while True:
        print("\nWhat would you like to do?")
        print("1. Talk to Captain")
        print("2. Talk to Engineer")
        print("3. Talk to Scientist")
        print("4. Check inventory")
        print("5. Save game and quit")
        choice = input("Enter your choice: ")
        if choice == "1":
            with open('captain_dialogue.json', 'r') as file:
                dialogue = json.load(file)
            current_node = "1"
            conversation_loop(dialogue, current_node, inventory)
        elif choice == "2":
            with open('engineer_dialogue.json', 'r') as file:
                dialogue = json.load(file)
            current_node = "1"
            conversation_loop(dialogue, current_node, inventory)
        elif choice == "3":
            with open('scientist_dialogue.json', 'r') as file:
                dialogue = json.load(file)
            current_node = "1"
            conversation_loop(dialogue, current_node, inventory)
        elif choice == "4":
            display_inventory(inventory)
        elif choice == "5":
            save_inventory(inventory)
            print("Game saved. Goodbye!")
            break
        else:
            print("Invalid choice. Please try again.")

if __name__ == "__main__":
    main()