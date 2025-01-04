from engine.message_handler import message_handler

class Inventory:
    def __init__(self):
        self.items = []
        self.equipped_items = []

    def add_item(self, item_id, items_data):
        item = items_data[item_id]
        self.items.append(item_id)
        message_handler.print_message(f"{item['name']} added to inventory.")

    def remove_item(self, item_id):
        if item_id in self.items:
            self.items.remove(item_id)
            message_handler.print_message(f"Item removed from inventory.")
        else:
            message_handler.print_message(f"Item not found in inventory.")

    def equip_item(self, item_id, items_data):
        item = items_data[item_id]
        if item_id in self.items and item.get("equippable", False):
            self.items.remove(item_id)
            self.equipped_items.append(item_id)
            message_handler.print_message(f"You equipped the {item['name']}.")
            return item.get("effect", {})
        else:
            message_handler.print_message("Item not found in inventory or cannot be equipped.")
            return {}

    def unequip_item(self, item_id, items_data):
        item = items_data[item_id]
        if item_id in self.equipped_items:
            self.equipped_items.remove(item_id)
            self.items.append(item_id)
            message_handler.print_message(f"You unequipped the {item['name']}.")
            return item.get("effect", {})
        else:
            message_handler.print_message("Item not found in equipment.")
            return {}

    def list_inventory(self, items_data):
        if self.items:
            message_handler.print_message("You have the following items in your inventory:")
            for item_id in self.items:
                message_handler.print_message(f"- {items_data[item_id]['name']}")
        else:
            message_handler.print_message("Your inventory is empty.")

    def list_equipped_items(self, items_data):
        if self.equipped_items:
            message_handler.print_message("You have the following items equipped:")
            for item_id in self.equipped_items:
                message_handler.print_message(f"- {items_data[item_id]['name']}")
        else:
            message_handler.print_message("You are not equipped with any items.")

    def craft_item(self, item_name, items_data):
        item = items_data.get(item_name.lower())
        if item:
            components = item.get("components", [])
            if all(component in self.items for component in components):
                for component in components:
                    self.remove_item(component)
                self.add_item(item_name, items_data)
                message_handler.print_message(f"You have crafted a {item['name']}.")
            else:
                message_handler.print_message("You don't have the required components to craft this item.")
        else:
            message_handler.print_message("Item not found in the game data.")

    def combine_items(self, item1_id, item2_id, items_data):
        item1 = items_data[item1_id]
        item2 = items_data[item2_id]
        if item1_id in self.items and item2_id in self.items:
            combination = f"{item1_id} + {item2_id}"
            if combination in items_data.get("combinations", {}):
                new_item_id = items_data["combinations"][combination]
                new_item = items_data[new_item_id]
                message_handler.print_message(f"You combine {items_data[item1_id]['name']} and {items_data[item2_id]['name']} to create {new_item['name']}.")
                self.items.remove(item1_id)
                self.items.remove(item2_id)
                self.add_item(new_item_id, items_data)
                return new_item_id
            else:
                message_handler.print_message("These items cannot be combined.")
        else:
            message_handler.print_message("One or both items not found in your inventory.")
        return None

    def examine_item(self, item_name, items_data):
        item = items_data.get(item_name.lower())
        if item:
            message_handler.print_message(item["description"])
        else:
            message_handler.print_message("Item not found in the game data.")

    # In Inventory class:
    def repair_item(self, item_id, items_data):
        """
        Repair an item using the required repair item.

        Args:
            item_id (str): ID of the item to repair
            items_data (dict): Game items data
        """
        if item_id not in self.items:
            message_handler.print_message("Item not found in your inventory.")
            return

        item = items_data[item_id]
        if not item.get("repairable", False):
            message_handler.print_message("This item cannot be repaired.")
            return

        repair_item_id = item.get("repair_item")
        if not repair_item_id:
            message_handler.print_message("This item doesn't have a specified repair item.")
            return

        if repair_item_id not in self.items:
            message_handler.print_message(f"You need a {items_data[repair_item_id]['name']} to repair this item.")
            return

        # Get the repaired version's name from the components list of items
        repaired_item_id = None
        for potential_item_id, potential_item in items_data.items():
            if potential_item.get("components") == [item_id]:
                repaired_item_id = potential_item_id
                break

        if not repaired_item_id:
            message_handler.print_message("Cannot find the repaired version of this item.")
            return

        # Remove both the broken item and the repair tool
        self.remove_item(item_id)
        self.remove_item(repair_item_id)

        # Add the repaired item
        self.add_item(repaired_item_id, items_data)
        message_handler.print_message(f"You successfully repaired the {item['name']} using the {items_data[repair_item_id]['name']}.")
