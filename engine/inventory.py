class Inventory:
    def __init__(self):
        self.items = []
        self.equipped_items = []

    def add_item(self, item_id, items_data):
        item = items_data[item_id]
        self.items.append(item_id)
        print(f"{item['name']} added to inventory.")

    def remove_item(self, item_id):
        if item_id in self.items:
            self.items.remove(item_id)
            print(f"Item removed from inventory.")
        else:
            print(f"Item not found in inventory.")

    def equip_item(self, item_id, items_data):
        item = items_data[item_id]
        if item_id in self.items and item.get("equippable", False):
            self.items.remove(item_id)
            self.equipped_items.append(item_id)
            print(f"You equipped the {item['name']}.")
            return item.get("effect", {})
        else:
            print("Item not found in inventory or cannot be equipped.")
            return {}

    def unequip_item(self, item_id, items_data):
        item = items_data[item_id]
        if item_id in self.equipped_items:
            self.equipped_items.remove(item_id)
            self.items.append(item_id)
            print(f"You unequipped the {item['name']}.")
            return item.get("effect", {})
        else:
            print("Item not found in equipment.")
            return {}

    def list_inventory(self, items_data):
        if self.items:
            print("You have the following items in your inventory:")
            for item_id in self.items:
                print(f"- {items_data[item_id]['name']}")
        else:
            print("Your inventory is empty.")

    def list_equipped_items(self, items_data):
        if self.equipped_items:
            print("You have the following items equipped:")
            for item_id in self.equipped_items:
                print(f"- {items_data[item_id]['name']}")
        else:
            print("You are not equipped with any items.")

    def craft_item(self, item_name, items_data):
        item = items_data.get(item_name.lower())
        if item:
            components = item.get("components", [])
            if all(component in self.items for component in components):
                for component in components:
                    self.remove_item(component)
                self.add_item(item_name, items_data)
                print(f"You have crafted a {item['name']}.")
            else:
                print("You don't have the required components to craft this item.")
        else:
            print("Item not found in the game data.")

    def combine_items(self, item1_id, item2_id, items_data):
        item1 = items_data[item1_id]
        item2 = items_data[item2_id]
        if item1_id in self.items and item2_id in self.items:
            combination = f"{item1_id} + {item2_id}"
            if combination in items_data.get("combinations", {}):
                new_item_id = items_data["combinations"][combination]
                new_item = items_data[new_item_id]
                print(f"You combine {item1['name']} and {item2['name']} to create {new_item['name']}.")
                self.items.remove(item1_id)
                self.items.remove(item2_id)
                self.add_item(new_item_id, items_data)
                return new_item_id
            else:
                print("These items cannot be combined.")
        else:
            print("One or both items not found in your inventory.")
        return None

    def examine_item(self, item_name, items_data):
        item = items_data.get(item_name.lower())
        if item:
            print(item["description"])
        else:
            print("Item not found in the game data.")
