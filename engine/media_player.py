import time
import sys
import pygame

class MediaPlayer:
    def __init__(self):
        pygame.mixer.init()

    def play_music(self, filename):
        pygame.mixer.music.load(filename)
        pygame.mixer.music.play()

    def play_sound_effect(self, filename):
        sound = pygame.mixer.Sound(filename)
        sound.play()

    def print_with_delay(self, message, delay=0.05):
        for char in message:
            sys.stdout.write(char)
            sys.stdout.flush()
            time.sleep(delay)
        print()
