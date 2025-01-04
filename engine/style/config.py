from dataclasses import dataclass, field
from typing import Dict, Optional
from pathlib import Path
import json
import os
import copy

@dataclass
class StyleConfig:
   text_speed: float = 0.05
   dialogue_frame: str = "rounded"  
   scene_frame: str = "single"
   intro_frame: str = "double"
   horizontal_padding: int = 2
   vertical_padding: int = 1
   colors: Dict[str, str] = field(default_factory=lambda: {})
   styles: Dict[str, Dict] = field(default_factory=lambda: {})
   
   @staticmethod
   def get_config_dir() -> Path:
       return Path(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))) / "engine" / "style" / "configs"
   
   @classmethod
   def load(cls, style_name: str) -> 'StyleConfig':
       config_path = cls.get_config_dir() / f"{style_name.replace('.json', '')}.json"
       try:
           with open(config_path) as f:
               data = json.load(f)
           return cls(
               text_speed=data.get('text_speed', 0.05),
               dialogue_frame=data.get('dialogue_frame', 'rounded'),
               scene_frame=data.get('scene_frame', 'single'),
               intro_frame=data.get('intro_frame', 'double'),
               horizontal_padding=data.get('horizontal_padding', 2),
               vertical_padding=data.get('vertical_padding', 1),
               colors=copy.deepcopy(data.get('colors', {})),
               styles=copy.deepcopy(data.get('styles', {}))
           )
       except FileNotFoundError:
           return cls()
   
   def save(self, style_name: str):
       config_path = self.get_config_dir() / f"{style_name.replace('.json', '')}.json"
       config_path.parent.mkdir(parents=True, exist_ok=True)
       
       with open(config_path, 'w') as f:
           json.dump({
               'text_speed': self.text_speed,
               'dialogue_frame': self.dialogue_frame,
               'scene_frame': self.scene_frame,
               'intro_frame': self.intro_frame,
               'horizontal_padding': self.horizontal_padding, 
               'vertical_padding': self.vertical_padding,
               'colors': self.colors,
               'styles': self.styles
           }, f, indent=2)
           
   def update(self, **kwargs):
       valid_fields = {f.name for f in self.__dataclass_fields__}
       for key, value in kwargs.items():
           if key in valid_fields:
               if key in ['colors', 'styles']:
                   setattr(self, key, copy.deepcopy(value))
               else:
                   setattr(self, key, value)
               
   @property
   def available_styles(self) -> list:
       return [p.stem for p in self.get_config_dir().glob("*.json")]

   def get_frame_chars(self, style: str) -> str:
       frames = {
           'single': "─│┌┐└┘",
           'double': "═║╔╗╚╝",
           'rounded': "─│╭╮╰╯",
           'ascii': "-|++++"
       }
       return frames.get(style, frames['ascii'])

   def __post_init__(self):
       self.colors = copy.deepcopy(self.colors)
       self.styles = copy.deepcopy(self.styles)