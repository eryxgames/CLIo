import os
import sys
import time
import textwrap
import shutil
import json
from enum import Enum
from dataclasses import dataclass
from typing import Optional, Dict, List
from engine.style.config import StyleConfig

class FrameStyle(Enum):
    SINGLE = "─│┌┐└┘"
    DOUBLE = "═║╔╗╚╝" 
    ROUNDED = "─│╭╮╰╯"
    ASCII = "-|++++"

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

class TextStyler:
    def __init__(self, config_file: str = None):
        self.configs: Dict[str, TextConfig] = {}
        self.terminal_size = shutil.get_terminal_size()
        if config_file:
            self.load_config(config_file)
        else:
            self.set_default_configs()

    def load_config(self, config_file: str):
        with open(config_file) as f:
            data = json.load(f)
            self.process_config(data)

    def process_config(self, data: StyleConfig):
        self.configs = {}
        
        if not data.styles:
            self.set_default_configs()
            return
            
        for style_name, style_data in data.styles.items():
            frame_style = FrameStyle[style_data.get("frame", "SINGLE").upper()]
            effects = TextEffect(
                fade_in=style_data.get("fade_in", False),
                gradient=style_data.get("gradient", False),
                flash=style_data.get("flash_effect", False),
                animate_frame=style_data.get("animate_frame", False)
            )
            
            self.configs[style_name] = TextConfig(
                speed=style_data.get("speed", data.text_speed),
                frame_style=frame_style,
                padding=style_data.get("padding", data.horizontal_padding),
                alignment=style_data.get("alignment", "left"),
                color=data.colors.get(style_name) if data.colors else None,
                effects=effects
            )

    def update_terminal_size(self):
        self.terminal_size = shutil.get_terminal_size()
        
    def get_wrap_width(self, config: TextConfig) -> int:
        if config.width:
            return min(config.width, self.terminal_size.columns)
        return self.terminal_size.columns - (config.padding * 2)

    def apply_gradient(self, text: str, start_color: int = 196, end_color: int = 201) -> List[str]:
        lines = text.split('\n')
        gradient_lines = []
        color_step = (end_color - start_color) / len(lines)
        
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
        
        frame_lines = self.create_frame(text, config) if config.frame_style else [text]
        
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

    def flash_effect(self, text: str, flashes: int = 3, speed: float = 0.1):
        for _ in range(flashes):
            print('\033[?5h')  # Enable reverse video
            time.sleep(speed)
            print('\033[?5l')  # Disable reverse video
            time.sleep(speed)

    def set_default_configs(self):
        self.configs = {
            "default": TextConfig(),
            "dialogue": TextConfig(
                speed=0.08,
                frame_style=FrameStyle.ROUNDED,
                effects=TextEffect(animate_frame=True)
            ),
            "scene": TextConfig(
                speed=0.03,
                padding=2,
                effects=TextEffect(fade_in=True)
            ),
            "intro": TextConfig(
                speed=0.1,
                frame_style=FrameStyle.DOUBLE,
                effects=TextEffect(gradient=True)
            ),
            "combat": TextConfig(
                speed=0.02,
                frame_style=FrameStyle.DOUBLE,
                effects=TextEffect(flash=True)
            )
        }

    def update_config(self, new_config: dict):
        self.process_config(new_config)