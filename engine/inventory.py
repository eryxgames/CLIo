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

    def find_item_by_partial_name(self, partial_name, items_data):
        """Find an item in inventory by partial name match."""
        partial_name = partial_name.lower()
#        print(f"DEBUG: Looking for item with partial name: '{partial_name}'")
#        print(f"DEBUG: Current inventory: {self.items}")
        
        # First check if it's a direct ID match
        if partial_name in self.items:
            return partial_name
            
        matches = []
        for item_id in self.items:
            item = items_data[item_id]
            item_name = item['name'].lower()
#            print(f"DEBUG: Checking against item: {item_id} ({item_name})")
            
            # Check exact match
            if partial_name == item_name:
 #               print(f"DEBUG: Found exact match: {item_id}")
                return item_id
                
            # Check last word match
            last_word = item_name.split()[-1]
            if partial_name == last_word:
#                print(f"DEBUG: Found last word match: {item_id}")
                matches.append(item_id)
                
            # Check partial match
            elif partial_name in item_name:
#                print(f"DEBUG: Found partial match: {item_id}")
                matches.append(item_id)
                
        # Handle matches
        if len(matches) == 1:
#            print(f"DEBUG: Returning single match: {matches[0]}")
            return matches[0]
        elif matches:
            # Prefer last word matches
            for item_id in matches:
                if partial_name == items_data[item_id]['name'].lower().split()[-1]:
#                    print(f"DEBUG: Returning preferred last word match: {item_id}")
                    return item_id
#            print(f"DEBUG: Returning first match: {matches[0]}")
            return matches[0]
            
#        print(f"DEBUG: No matches found for {partial_name}")
        return None

    def combine_items(self, item1_name, item2_name, items_data):
        """Combine two items."""
#        print(f"DEBUG: Attempting to combine '{item1_name}' with '{item2_name}'")
        
        # Try to find items by partial name
        item1_id = self.find_item_by_partial_name(item1_name, items_data)
        item2_id = self.find_item_by_partial_name(item2_name, items_data)
        
#        print(f"DEBUG: Found item1_id: {item1_id}, item2_id: {item2_id}")

        if not item1_id or not item2_id:
            print("One or both items not found in your inventory.")
            return None

        # Check all items for a valid combination
#        print(f"DEBUG: Looking for combination with components: {item1_id}, {item2_id}")
        for result_id, result_item in items_data.items():
            if 'components' in result_item:
                components = set(result_item['components'])
#                print(f"DEBUG: Checking result item {result_id} with components {components}")
                if {item1_id, item2_id} == components:
                    print(f"You combine {items_data[item1_id]['name']} and {items_data[item2_id]['name']} to create {result_item['name']}.")
                    self.items.remove(item1_id)
                    self.items.remove(item2_id)
                    self.add_item(result_id, items_data)
                    return result_id

        print("These items cannot be combined.")

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
