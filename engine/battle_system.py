import random
import time
import os
from engine.text_styler import TextStyler
from engine.style.config import StyleConfig
from engine.message_handler import message_handler

class BattleSystem:
    def __init__(self, player_stats, enemy_stats):
        self.player_stats = player_stats
        self.enemy_stats = enemy_stats
        self.player_critical_hit_chance = player_stats.get("critical_hit_chance", 0)
        self.enemy_critical_hit_chance = enemy_stats.get("critical_hit_chance", 0)

    def start_battle(self):
        message_handler.print_message("A battle has started!", "combat")
        self.engage_battle()

    def engage_battle(self):
        while self.player_stats["health"] > 0 and self.enemy_stats["health"] > 0:
            self.player_turn()
            if self.enemy_stats["health"] > 0:
                self.enemy_turn()

        if self.player_stats["health"] <= 0:
            message_handler.print_message("You have been defeated.")
        else:
            message_handler.print_message("You have defeated the enemy!")

    def player_turn(self):
        action = input("Do you want to attack or defend? ").lower()
        if action == "attack":
            damage = random.randint(10, 20) + self.player_stats["attack"]
            if random.random() < self.player_critical_hit_chance:
                damage *= 2
                message_handler.print_message("Critical hit!")
            self.enemy_stats["health"] -= damage
            message_handler.print_message(f"You attack and deal {damage} damage to the enemy.")
        elif action == "defend":
            self.player_stats["defense"] += 5
            message_handler.print_message("You defend and increase your defense.")
        else:
            message_handler.print_message("Invalid action. Try again.")
            self.player_turn()

    def enemy_turn(self):
        damage = random.randint(5, 15) - self.player_stats["defense"]
        if random.random() < self.enemy_critical_hit_chance:
            damage *= 2
            message_handler.print_message("Enemy critical hit!")
        if damage > 0:
            self.player_stats["health"] -= damage
            message_handler.print_message(f"The enemy attacks and deals {damage} damage to you.")
        else:
            message_handler.print_message("Your defense blocks the enemy's attack.")
