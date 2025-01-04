from dataclasses import dataclass
from typing import Dict, Optional
from pathlib import Path
import json
import os

@dataclass
class StyleConfig:
    text_speed: float = 0.05
    dialogue_frame: str = "rounded"
    scene_frame: str = "single" 
    intro_frame: str = "double"
    horizontal_padding: int = 2
    vertical_padding: int = 1
    colors: Optional[Dict[str, str]] = None
    styles: Optional[Dict[str, Dict]] = None
    
    @staticmethod
    def get_config_dir() -> Path:
        return Path(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))) / "engine" / "style" / "configs"
    
    @classmethod
    def load(cls, style_name: str) -> 'StyleConfig':
            # Debug print
        print(f"Loading style: {style_name}")
        style_name = style_name.replace('.json', '')
        config_path = cls.get_config_dir() / f"{style_name}.json"

        print(f"Looking for config at: {config_path}")  # Debug path     
        
        try:
            with open(config_path) as f:
                data = json.load(f)
            return cls(**data)
        except FileNotFoundError:
            print(f"Style config file not found: {config_path}")  # Debug print
            return cls()
    
    def save(self, style_name: str):
        style_name = style_name.replace('.json', '')
        config_path = self.get_config_dir() / f"{style_name}.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(config_path, 'w') as f:
            json.dump(self.__dict__, f, indent=2)
            
    def update(self, **kwargs):
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
                
    @property
    def available_styles(self) -> list:
        return [p.stem for p in self.get_config_dir().glob("*.json")]

    def get_frame_chars(self, style: str) -> str:
        frames = {
            "single": "─│┌┐└┘",
            "double": "═║╔╗╚╝",
            "rounded": "─│╭╮╰╯",
            "ascii": "-|++++"
        }
        return frames.get(style, frames["ascii"])