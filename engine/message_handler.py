# engine/message_handler.py
import time
import sys
from engine.text_styler import TextStyler

class MessageHandler:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.text_styler = TextStyler()
        return cls._instance

    def print_message(self, message: str, style: str = "default"):
        config = self.text_styler.configs.get(style, self.text_styler.configs["default"])
        if config.effects.fade_in:
            self.fade_in_text(message, config)
        elif config.character_delay > 0:
            self.print_with_delay(message, config.character_delay, config.paragraph_delay)
        else:
            self.text_styler.print_text(message, style)

    def print_with_delay(self, text: str, char_delay: float, para_delay: float = 1.0):
        paragraphs = text.split("\n\n")
        for i, paragraph in enumerate(paragraphs):
            for char in paragraph:
                sys.stdout.write(char)
                sys.stdout.flush()
                if char not in {' ', '\n'}:
                    time.sleep(char_delay)
            if i < len(paragraphs) - 1:
                print("\n")
                time.sleep(para_delay)

message_handler = MessageHandler()