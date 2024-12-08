import random
import time

class BattleSystem:
    def __init__(self, player_stats, enemy_stats):
        self.player_stats = player_stats
        self.enemy_stats = enemy_stats
        self.player_critical_hit_chance = player_stats.get("critical_hit_chance", 0)
        self.enemy_critical_hit_chance = enemy_stats.get("critical_hit_chance", 0)

    def start_battle(self):
        print("A battle has started!")
        self.engage_battle()

    def engage_battle(self):
        while self.player_stats["health"] > 0 and self.enemy_stats["health"] > 0:
            self.player_turn()
            if self.enemy_stats["health"] > 0:
                self.enemy_turn()

        if self.player_stats["health"] <= 0:
            print("You have been defeated.")
        else:
            print("You have defeated the enemy!")

    def player_turn(self):
        action = input("Do you want to attack or defend? ").lower()
        if action == "attack":
            damage = random.randint(10, 20) + self.player_stats["attack"]
            if random.random() < self.player_critical_hit_chance:
                damage *= 2
                print("Critical hit!")
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
        if random.random() < self.enemy_critical_hit_chance:
            damage *= 2
            print("Enemy critical hit!")
        if damage > 0:
            self.player_stats["health"] -= damage
            print(f"The enemy attacks and deals {damage} damage to you.")
        else:
            print("Your defense blocks the enemy's attack.")
