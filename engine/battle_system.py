import random

class BattleSystem:
    def __init__(self, player_stats, enemy_stats):
        self.player_stats = player_stats
        self.enemy_stats = enemy_stats

    def engage_battle(self):
        while self.player_stats["health"] > 0 and self.enemy_stats["health"] > 0:
            self.player_turn()
            if self.enemy_stats["health"] > 0:
                self.enemy_turn()

    def player_turn(self):
        action = input("Do you want to attack or defend? ").lower()
        if action == "attack":
            damage = random.randint(10, 20) + self.player_stats["attack"]
            self.enemy_stats["health"] -= damage
            print(f"You attack and deal {damage} damage to the enemy.")
        elif action == "defend":
            self.player_stats["defense"] += 5
            print("You defend and increase your defense.")
        else:
            print("Invalid action. Try again.")
            self.player_turn()

    def enemy_turn(self):
        damage = random.randint(5, 15) - self.player_stats["defense"]
        self.player_stats["health"] -= damage
        print(f"The enemy attacks and deals {damage} damage to you.")

    def modify_attributes(self, item):
        if item in self.player_stats["inventory"]:
            # Modify player attributes based on the item
            pass
