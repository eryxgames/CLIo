# engine/style_manager.py
from typing import Dict, Optional
from engine.style.config import StyleConfig
import copy

class StyleManager:
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
        
    def __init__(self):
        if not self._initialized:
            self.current_style = None
            self.style_cache: Dict[str, StyleConfig] = {}
            self._initialized = True
    
    def get_style(self, style_name: str) -> StyleConfig:
        if style_name not in self.style_cache:
            self.style_cache[style_name] = StyleConfig.load(style_name)
        return copy.deepcopy(self.style_cache[style_name])
        
    def clear_cache(self):
        self.style_cache.clear()