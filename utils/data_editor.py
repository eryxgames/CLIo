import json
import os

def load_data(filename):
    with open(filename, 'r') as f:
        return json.load(f)

def save_data(data, filename):
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)

def edit_data(filename):
    data = load_data(filename)
    print(json.dumps(data, indent=2))
    print("\nWhat would you like to edit?")
    print("1. Add a new entry")
    print("2. Edit an existing entry")
    print("3. Delete an entry")
    choice = input("Enter the number of your choice: ")

    if choice == "1":
        new_entry = {}
        for key in data[0].keys():
            value = input(f"Enter value for {key}: ")
            new_entry[key] = value
        data.append(new_entry)
    elif choice == "2":
        index = int(input("Enter the index of the entry to edit: "))
        if 0 <= index < len(data):
            entry = data[index]
            for key in entry.keys():
                value = input(f"Enter new value for {key} (current: {entry[key]}): ")
                if value:
                    entry[key] = value
        else:
            print("Invalid index.")
    elif choice == "3":
        index = int(input("Enter the index of the entry to delete: "))
        if 0 <= index < len(data):
            del data[index]
        else:
            print("Invalid index.")
    else:
        print("Invalid choice.")

    save_data(data, filename)
    print("Data saved.")

if __name__ == "__main__":
    filename = input("Enter the filename to edit (e.g., scenes.json): ")
    filepath = os.path.join("game_files", filename)
    if os.path.exists(filepath):
        edit_data(filepath)
    else:
        print(f"File {filepath} not found.")
