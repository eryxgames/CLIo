import time
import sys
import pygame

class MediaPlayer:
    def __init__(self):
        pygame.mixer.init()

    def play_music(self, filename, fade_out_time=1000):
        if pygame.mixer.music.get_busy():
            pygame.mixer.music.fadeout(fade_out_time)
            time.sleep(fade_out_time / 1000)  # Wait for the fade out to complete
        pygame.mixer.music.load(filename)
        pygame.mixer.music.play(-1)  # Loop the music

    def play_sound_effect(self, filename):
        sound = pygame.mixer.Sound(filename)
        sound.play()

    def print_with_delay(self, message, delay=0.05):
        for char in message:
            sys.stdout.write(char)
            sys.stdout.flush()
            time.sleep(delay)
        print()
