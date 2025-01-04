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
    
    @classmethod
    def load(cls, style_name: str) -> 'StyleConfig':
        # Remove .json extension if present
        style_name = style_name.replace('.json', '')
        
        # Get the base directory of the game
        base_dir = Path(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        config_path = base_dir / "engine" / "style" / "configs" / f"{style_name}.json"
        
        try:
            with open(config_path) as f:
                data = json.load(f)
            return cls(**data)
        except FileNotFoundError:
            print(f"Style config not found: {config_path}, using defaults")
            return cls()
    
    def save(self, style_name: str):
        style_name = style_name.replace('.json', '')
        base_dir = Path(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        config_path = base_dir / "engine" / "style" / "configs" / f"{style_name}.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(config_path, 'w') as f:
            json.dump(self.__dict__, f, indent=2)
    
    @classmethod
    def load(cls, style_name: str) -> 'StyleConfig':
        config_path = Path(__file__).parent / "configs" / f"{style_name}.json"
        with open(config_path) as f:
            data = json.load(f)
        return cls(**data)
    
    def save(self, style_name: str):
        config_path = Path(__file__).parent / "configs" / f"{style_name}.json"
        with open(config_path, 'w') as f:
            json.dump(self.__dict__, f, indent=2)
            
    def update(self, **kwargs):
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
                
    @property
    def available_styles(self) -> list:
        config_dir = Path(__file__).parent / "configs"
        return [p.stem for p in config_dir.glob("*.json")]

    def get_frame_chars(self, style: str) -> str:
        frames = {
            "single": "─│┌┐└┘",
            "double": "═║╔╗╚╝",
            "rounded": "─│╭╮╰╯",
            "ascii": "-|++++"
        }
        return frames.get(style, frames["ascii"])