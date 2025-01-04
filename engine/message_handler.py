import sys
import time
from engine.text_styler import TextStyler

class MessageHandler:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.text_styler = TextStyler()
        return cls._instance

    def print_message(self, message: str, style: str = "default"):
        if not message.strip():
            return
            
        self.text_styler.print_text(message, style)

    def print_with_delay(self, text: str, char_delay: float = 0.05):
        if not text.strip():
            return

        paragraphs = text.split("\n\n")
        for i, paragraph in enumerate(paragraphs):
            for char in paragraph:
                sys.stdout.write(char)
                sys.stdout.flush()
                if char not in {' ', '\n'}:
                    time.sleep(char_delay)
            if i < len(paragraphs) - 1:
                print("\n")

message_handler = MessageHandler()