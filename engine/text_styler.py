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
    frame_style: FrameStyle = FrameStyle.SINGLE
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
        for style_name, style_data in data.styles.items():
            frame_type = style_data.get("frame", "SINGLE").upper()
            frame_style = FrameStyle[frame_type] if frame_type != "NONE" else FrameStyle.NONE
            
            config = TextConfig(
                speed=style_data.get("speed", data.text_speed),
                frame_style=frame_style,
                padding=style_data.get("padding", data.horizontal_padding),
                alignment=style_data.get("alignment", "left"),
                color=data.colors.get(style_name),
                effects=TextEffect(**{k: style_data.get(k, False) for k in TextEffect.__annotations__}),
                character_delay=style_data.get("character_delay", 0),
                paragraph_delay=style_data.get("paragraph_delay", 1.0)
            )
            self.configs[style_name] = config
            
        if "default" not in self.configs:
            self.configs["default"] = TextConfig()

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
        color_step = (end_color - start_color) / max(len(lines), 1)
        
        for i, line in enumerate(lines):
            color = int(start_color + (i * color_step))
            gradient_lines.append(f"\033[38;5;{color}m{line}\033[0m")
            
        return gradient_lines

    def animate_frame(self, frame_lines: List[str], speed: float = 0.02):
        for i in range(len(frame_lines)):
            partial_frame = frame_lines[:i+1]
            print('\n'.join(partial_frame), end='\r')
            time.sleep(speed)
            if i < len(frame_lines) - 1:
                print('\033[F' * len(partial_frame))

    def create_frame(self, text: str, style: TextConfig) -> List[str]:
        chars = style.frame_style.value
        width = self.get_wrap_width(style)
        wrapped = textwrap.wrap(text, width - 4)
        
        frame = [
            f"{chars[2]}{chars[0] * (width-2)}{chars[3]}",
            *[f"{chars[1]}{' ' * (width-2)}{chars[1]}" for _ in wrapped],
            f"{chars[4]}{chars[0] * (width-2)}{chars[5]}"
        ]
        
        for i, line in enumerate(wrapped, 1):
            padding = ' ' * ((width - 2 - len(line)) // 2) if style.alignment == "center" else ' '
            frame[i] = f"{chars[1]}{padding}{line}{' ' * (width-2-len(line)-len(padding))}{chars[1]}"
            
        return frame

    def print_text(self, text: str, style_name: str = "default", delay_override: Optional[float] = None):
        config = self.configs.get(style_name, self.configs["default"])
        self.update_terminal_size()
        
        if config.frame_style != FrameStyle.NONE:
            frame_lines = self.create_frame(text, config)
        else:
            frame_lines = [text]
        
        if config.effects.gradient:
            frame_lines = self.apply_gradient('\n'.join(frame_lines))
        elif config.color:
            frame_lines = [f"\033[{config.color}m{line}\033[0m" for line in frame_lines]

        if config.effects.animate_frame:
            self.animate_frame(frame_lines, config.effects.animation_speed)
        else:
            print('\n'.join(frame_lines))

        if config.effects.flash:
            self.flash_effect('\n'.join(frame_lines))

    def fade_in_text(self, text: str, delay: float = 0.05):
        lines = text.split('\n')
        for line in lines:
            print(line)
            time.sleep(delay)

    def flash_effect(self, text: str, flashes: int = 3, speed: float = 0.1):
        for _ in range(flashes):
            print('\033[?5h')
            time.sleep(speed)
            print('\033[?5l')
            time.sleep(speed)