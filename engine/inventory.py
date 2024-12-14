# engine/inventory.py

class Inventory:
    def __init__(self, items_data):
        self.items = []
        self.equipped_items = []
        self.items_data = items_data

    def add_item(self, item_id):
        item = self.items_data[item_id]
        self.items.append(item_id)
        print(f"{item['name']} added to inventory.")

    def remove_item(self, item_id):
        if item_id in self.items:
            self.items.remove(item_id)
            print(f"Item removed from inventory.")
        else:
            print(f"Item not found in inventory.")

    def find_item_by_name(self, item_name):
        for item_id, item in self.items_data.items():
            if item_name.lower().replace('_', ' ') in item.get("name", "").lower():
                return {
                    "id": item_id,
                    "name": item.get("name", "Unknown Item"),
                    "description": item.get("description", "No description available."),
                    "usable": item.get("usable", False),
                    "interactive": item.get("interactive", False),
                    "states": item.get("states", {})
                }
        return None

    def combine_items(self, item1_name, item2_name):
        item1 = self.find_item_by_name(item1_name)
        item2 = self.find_item_by_name(item2_name)

        if item1 and item2:
            item1_id = item1["id"]
            item2_id = item2["id"]
            if item1_id in self.items and item2_id in self.items:
                sorted_ids = sorted([item1_id, item2_id])
                combination = f"{sorted_ids[0]} + {sorted_ids[1]}"
                if combination in self.items_data.get("combinations", {}):
                    new_item_id = self.items_data["combinations"][combination]
                    new_item = self.items_data[new_item_id]
                    print(f"You combine {item1['name']} and {item2['name']} to create {new_item['name']}.")
                    self.items.remove(item1_id)
                    self.items.remove(item2_id)
                    self.add_item(new_item_id)
                    return new_item_id
                else:
                    print("These items cannot be combined.")
            else:
                print("One or both items not found in your inventory.")
        else:
            print("One or both items not found in your inventory.")
        return None

    def craft_item(self, item_name):
        item = self.items_data.get(item_name.lower().replace('_', ' '))
        if item:
            components = item.get("components", [])
            if all(component in self.items for component in components):
                for component in components:
                    self.remove_item(component)
                self.add_item(item_name)
                print(f"You have crafted a {item['name']}.")
            else:
                print("You don't have the required components to craft this item.")
        else:
            print("Item not found in the game data.")

    def repair_item(self, item_name):
        item = self.items_data.get(item_name.lower().replace('_', ' '))
        if item and item.get("repairable", False):
            repair_items = item.get("repair_items", [])
            for repair_item_id in repair_items:
                repair_item = self.items_data.get(repair_item_id)
                if repair_item_id in self.items:
                    self.remove_item(repair_item_id)
                    new_item_id = item.get("repaired_item_id")
                    new_item = self.items_data[new_item_id]
                    print(f"You repair the {item['name']} using the {repair_item['name']} and create a {new_item['name']}.")
                    self.add_item(new_item_id)
                    self.remove_item(item["id"])  # Remove the original item
                    return
            print(f"You don't have any valid repair items to repair the {item['name']}.")
        else:
            print("Item not found in the game data or cannot be repaired.")

    def equip_item(self, item_name):
        item = self.find_item_by_name(item_name)
        if item:
            item_id = item["id"]
            if item_id in self.items and item.get("equippable", False):
                self.items.remove(item_id)
                self.equipped_items.append(item_id)
                print(f"You equipped the {item['name']}.")
                return item.get("effect", {})
            else:
                print("Item not found in inventory or cannot be equipped.")
        else:
            print("Item not found in inventory or cannot be equipped.")
        return {}

    def unequip_item(self, item_name):
        item = self.find_item_by_name(item_name)
        if item:
            item_id = item["id"]
            if item_id in self.equipped_items:
                self.equipped_items.remove(item_id)
                self.items.append(item_id)
                print(f"You unequipped the {item['name']}.")
                return item.get("effect", {})
            else:
                print("Item not found in equipment.")
        else:
            print("Item not found in equipment.")
        return {}

    def list_inventory(self):
        if self.items:
            print("You have the following items in your inventory:")
            for item_id in self.items:
                print(f"- {self.items_data[item_id]['name']}")
        else:
            print("Your inventory is empty.")

    def list_equipped_items(self):
        if self.equipped_items:
            print("You have the following items equipped:")
            for item_id in self.equipped_items:
                print(f"- {self.items_data[item_id]['name']}")
        else:
            print("You are not equipped with any items.")

    def contains_item(self, item_id):
        return item_id in self.items
