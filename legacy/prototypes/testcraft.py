# game.py
import json
import os
import re

class InventoryGame:
    def __init__(self, recipes_file='recipes.json'):
        """
        Initialize the game with player inventory and load recipes
        
        Args:
            recipes_file (str): Path to the JSON file containing crafting and combining recipes
        """
        self.inventory = []
        self.recipes_file = recipes_file
        self.recipes = self.load_recipes()

    def load_recipes(self):
        """
        Load recipes from external JSON file
        
        Returns:
            dict: Parsed recipes for crafting and combining
        """
        try:
            with open(self.recipes_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"Recipes file {self.recipes_file} not found. Creating default.")
            default_recipes = {
                "crafting": {},
                "combining": {}
            }
            with open(self.recipes_file, 'w') as f:
                json.dump(default_recipes, f, indent=2)
            return default_recipes

    def add_to_inventory(self, item):
        """
        Add an item to player's inventory
        
        Args:
            item (str): Name of the item to add
        """
        self.inventory.append(item)
        print(f"Added {item} to inventory.")

    def remove_from_inventory(self, item):
        """
        Remove an item from player's inventory
        
        Args:
            item (str): Name of the item to remove
        
        Returns:
            bool: True if item was removed, False otherwise
        """
        if item in self.inventory:
            self.inventory.remove(item)
            return True
        return False

    def craft(self, final_item):
        """
        Craft an item using known recipe
        
        Args:
            final_item (str): Name of the item to craft
        
        Returns:
            bool: True if crafting was successful, False otherwise
        """
        # Check if the final item exists in crafting recipes
        if final_item not in self.recipes.get('crafting', {}):
            print(f"No known recipe for {final_item}.")
            return False
        
        # Get required ingredients for the item
        recipe = self.recipes['crafting'][final_item]
        ingredients = recipe.get('ingredients', [])
        
        # Check if player has all required ingredients
        can_craft = all(ingredient in self.inventory for ingredient in ingredients)
        
        if can_craft:
            # Remove ingredients from inventory
            for ingredient in ingredients:
                self.remove_from_inventory(ingredient)
            
            # Add crafted item to inventory
            self.add_to_inventory(final_item)
            print(f"Successfully crafted {final_item}!")
            return True
        else:
            print(f"Missing ingredients to craft {final_item}.")
            return False

    def combine(self, item1, item2):
        """
        Combine two items from inventory
        
        Args:
            item1 (str): First item to combine
            item2 (str): Second item to combine
        
        Returns:
            bool: True if combination was successful, False otherwise
        """
        # Check if either item is not in inventory
        if item1 not in self.inventory or item2 not in self.inventory:
            print("Both items must be in your inventory.")
            return False
        
        # Try combinations in both directions
        combine_key = f"{item1}+{item2}"
        reverse_key = f"{item2}+{item1}"
        
        combining_recipes = self.recipes.get('combining', {})
        
        if combine_key in combining_recipes:
            result = combining_recipes[combine_key]
        elif reverse_key in combining_recipes:
            result = combining_recipes[reverse_key]
        else:
            print(f"No known recipe for combining {item1} and {item2}.")
            return False
        
        # Remove original items and add result
        self.remove_from_inventory(item1)
        self.remove_from_inventory(item2)
        self.add_to_inventory(result)
        
        print(f"Successfully combined {item1} and {item2} to create {result}!")
        return True

    def show_inventory(self):
        """
        Display current inventory
        """
        print("Inventory:", ', '.join(self.inventory) if self.inventory else "Empty")

def main():
    game = InventoryGame()
    
    # Example interactions
    game.add_to_inventory('stick')
    game.add_to_inventory('stone')
    game.add_to_inventory('rope')
    
    while True:
        game.show_inventory()
        command = input("Enter command (craft/combine/add/quit): ").strip().lower()
        
        if command == 'quit':
            break
        elif command.startswith('add '):
            item = command.split(' ', 1)[1]
            game.add_to_inventory(item)
        elif command.startswith('craft '):
            item = command.split(' ', 1)[1]
            game.craft(item)
        elif command.startswith('combine '):
            # Improved parsing for combine command
            match = re.match(r'^combine\s+(\w+)\s*(?:and|with)?\s*(\w+)$', command)
            if match:
                item1, item2 = match.groups()
                game.combine(item1, item2)
            else:
                print("Invalid combine syntax. Use 'combine item1 and/with item2'")

if __name__ == "__main__":
    main()