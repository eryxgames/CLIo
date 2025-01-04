import os
import sys
import time
import textwrap
import shutil
from enum import Enum
from dataclasses import dataclass
from typing import Optional, Dict, List
from engine.style.config import StyleConfig

class FrameStyle(Enum):
    NONE = ""
    SINGLE = "─│┌┐└┘"
    DOUBLE = "═║╔╗╚╝" 
    ROUNDED = "─│╭╮╰╯"
    ASCII = "-|++++"

    @classmethod
    def from_str(cls, style: str) -> 'FrameStyle':
        try:
            return cls[style.upper()]
        except KeyError:
            return cls.NONE

@dataclass
class TextEffect:
    fade_in: bool = False
    gradient: bool = False
    flash: bool = False
    animate_frame: bool = False
    animation_speed: float = 0.02

@dataclass
class TextConfig:
    speed: float = 0.05
    frame_style: FrameStyle = FrameStyle.NONE
    width: Optional[int] = None
    padding: int = 1
    alignment: str = "left"
    color: Optional[str] = None
    effects: TextEffect = TextEffect()
    character_delay: float = 0
    paragraph_delay: float = 1.0

class TextStyler:
    _instance = None
    _config = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.terminal_size = shutil.get_terminal_size()
            cls._instance.configs = {}
        return cls._instance

    def process_config(self, data):
        if not data or not hasattr(data, 'styles'):
            return
            
        TextStyler._config = data
        
        # Process default style first if present
        if 'default' in data.styles:
            self._process_style('default', data.styles['default'], data)
            
        # Process all other styles
        for style_name, style_data in data.styles.items():
            if style_name != 'default':
                self._process_style(style_name, style_data, data)

    def _process_style(self, style_name: str, style_data: dict, data):
        frame_map = {
            "rounded": "ROUNDED",
            "single": "SINGLE",
            "double": "DOUBLE",
            "ascii": "ASCII",
            "none": "NONE"
        }
        frame_type = frame_map.get(style_data.get("frame", "none").lower(), "NONE")
        frame_style = FrameStyle[frame_type]
        
        config = TextConfig(
            speed=style_data.get("speed", data.text_speed),
            frame_style=frame_style,
            padding=style_data.get("padding", data.horizontal_padding),
            alignment=style_data.get("alignment", "left"),
            color=data.colors.get(style_name),
            effects=TextEffect(
                fade_in=style_data.get("fade_in", False),
                gradient=style_data.get("gradient", False),
                flash=style_data.get("flash", False),
                animate_frame=style_data.get("animate_frame", False),
                animation_speed=style_data.get("animation_speed", 0.02)
            ),
            character_delay=style_data.get("character_delay", 0),
            paragraph_delay=style_data.get("paragraph_delay", 1.0)
        )
        self.configs[style_name] = config

    def update_config(self, new_config):
        self.process_config(new_config)

    def update_terminal_size(self):
        self.terminal_size = shutil.get_terminal_size()
        
    def get_wrap_width(self, config: TextConfig) -> int:
        if config.width:
            return min(config.width, self.terminal_size.columns)
        return self.terminal_size.columns - (config.padding * 2)

    def apply_gradient(self, text: str, start_color: int = 196, end_color: int = 201) -> List[str]:
        lines = text.split('\n')
        gradient_lines = []
        
        if len(lines) > 1:
            color_step = (end_color - start_color) / (len(lines) - 1)
            for i, line in enumerate(lines):
                color = int(start_color + (i * color_step))
                gradient_lines.append(f"\033[38;5;{color}m{line}\033[0m")
        else:
            gradient_lines.append(f"\033[38;5;{start_color}m{text}\033[0m")
            
        return gradient_lines

    def animate_frame(self, frame_lines: List[str], speed: float = 0.02):
        if not frame_lines:
            return
            
        for i in range(len(frame_lines)):
            partial_frame = frame_lines[:i+1]
            print('\n'.join(partial_frame))
            time.sleep(speed)
            if i < len(frame_lines) - 1:
                for _ in range(len(partial_frame)):
                    sys.stdout.write('\033[F')
                sys.stdout.flush()

    def create_frame(self, text: str, style: TextConfig) -> List[str]:
        if not text.strip():
            return []
                
        chars = style.frame_style.value
        if not chars:  # Handle NONE case
            return textwrap.wrap(text, self.get_wrap_width(style))
            
        width = self.get_wrap_width(style)
        wrapped = textwrap.wrap(text, width - 4)
        
        if not wrapped:
            return []

        color_start = f"\033[{style.color}m" if style.color and style.color.strip() else ""
        color_end = "\033[0m" if color_start else ""
        
        # Build frame with color applied to each line
        frame = [
            f"{color_start}{chars[2]}{chars[0] * (width-2)}{chars[3]}{color_end}"
        ]
        
        for line in wrapped:
            padding_left = ' ' * style.padding
            padding_right = ' ' * (width - 2 - len(line) - style.padding)
            frame.append(f"{color_start}{chars[1]}{padding_left}{line}{padding_right}{chars[1]}{color_end}")
        
        frame.append(f"{color_start}{chars[4]}{chars[0] * (width-2)}{chars[5]}{color_end}")
        
        return frame

    def print_text(self, text: str, style_name: str = "default"):
        if not text.strip():
            return
            
        config = self.configs.get(style_name, self.configs.get("default", TextConfig()))
        self.update_terminal_size()

        # Apply effects in order: color, frame, animation
        if config.color and config.color.strip():
            colored_text = f"\033[{config.color}m{text}\033[0m"
        else:
            colored_text = text

        if config.effects.gradient:
            lines = self.apply_gradient(colored_text)
            print('\n'.join(lines))
        elif config.frame_style != FrameStyle.NONE:
            frame_lines = self.create_frame(colored_text, config)
            if frame_lines:
                if config.effects.animate_frame:
                    self.animate_frame(frame_lines, config.effects.animation_speed)
                else:
                    print('\n'.join(frame_lines))
        else:
            wrapped = textwrap.wrap(colored_text, self.get_wrap_width(config))
            if config.alignment == "center":
                wrapped = [line.center(self.get_wrap_width(config)) for line in wrapped]
            if wrapped:
                print('\n'.join(wrapped))

        if config.effects.flash:
            self.flash_effect(text)
        elif config.effects.fade_in:
            self.fade_in_text(text)

    def flash_effect(self, text: str, flashes: int = 3, speed: float = 0.1):
        for _ in range(flashes):
            print('\033[?5h')  # Enable inverse
            time.sleep(speed)
            print('\033[?5l')  # Disable inverse
            time.sleep(speed)

    def fade_in_text(self, text: str, delay: float = 0.05):
        lines = text.split('\n')
        for line in lines:
            if line.strip():
                print(line)
                time.sleep(delay)