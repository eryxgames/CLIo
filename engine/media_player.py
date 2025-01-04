import time
import sys
import pygame
import os
from engine.message_handler import message_handler

class MediaPlayer:
    def __init__(self):
        pygame.mixer.init()

    def play_music(self, filename, fade_out_time=1000):
        if os.path.exists(filename):
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.fadeout(fade_out_time)
                time.sleep(fade_out_time / 1000)
            pygame.mixer.music.load(filename)
            pygame.mixer.music.play(-1)
        else:
            message_handler.print_message("The music of silence!", "system")

    def play_sound_effect(self, filename):
        if os.path.exists(filename):
            sound = pygame.mixer.Sound(filename)
            sound.play()
        else:
            message_handler.print_message("The sound of silence!", "system")

    def print_with_delay(self, message, delay=0.05):
        message_handler.print_message(message, "system")