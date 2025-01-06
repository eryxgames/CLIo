import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
from ttkthemes import ThemedTk
import json
import shutil
import os
import re
import sys
import copy
import time
import logging
import traceback
import functools
from datetime import datetime
from contextlib import contextmanager
from tkinter.scrolledtext import ScrolledText
from pygments import highlight
from pygments.lexers import get_lexer_by_name
from pygments.formatters import HtmlFormatter
from tkhtmlview import HTMLScrolledText

# Decorator definition
def safe_operation(func):
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except Exception as e:
            self.handle_operation_error(e, func.__name__)
            return None
    return wrapper

class EditorError(Exception):
    """Base class for editor errors"""
    pass

class FileOperationError(EditorError):
    """Error during file operations"""
    pass

class ValidationError(EditorError):
    """Error during data validation"""
    pass

class PlaceholderEntry(ttk.Entry):
    def __init__(self, master=None, placeholder="PLACEHOLDER", color='grey', *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.placeholder = placeholder
        self.placeholder_color = color
        self.default_fg_color = self['foreground']
        self.bind("<FocusIn>", self._clear_placeholder)
        self.bind("<FocusOut>", self._add_placeholder)
        self._add_placeholder()

    def _add_placeholder(self, *args):
        if not self.get():
            self.insert(0, self.placeholder)
            self['foreground'] = self.placeholder_color

    def _clear_placeholder(self, *args):
        if self.get() == self.placeholder:
            self.delete(0, tk.END)
            self['foreground'] = self.default_fg_color

class GameDataEditor:
    def __init__(self, root):
        self.root = root
        self.setup_window()
        self.initialize_data()
        self.setup_ui()
        self.setup_error_handlers()
        self.setup_event_bindings()
        self.load_data()

    def setup_window(self):
        self.root.title("CLIo Game Data Editor")
        self.root.geometry("1400x900")
        self.root.configure(bg='#1e1e1e')
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.configure_dark_theme()

    def initialize_data(self):
        self.undo_stack = []
        self.redo_stack = []
        self.modified = set()
        self.scenes_data = []
        self.items_data = {}
        self.characters_data = {}
        self.story_texts_data = {}
        self.dialogue_data = {}
        self.recipes_data = []
        
        self.search_vars = {
            'scene': tk.StringVar(),
            'item': tk.StringVar(),
            'character': tk.StringVar()
        }

    def setup_ui(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(expand=1, fill="both", padx=10, pady=10)

        self.tabs = {
            'scenes': ttk.Frame(self.notebook),
            'items': ttk.Frame(self.notebook),
            'characters': ttk.Frame(self.notebook),
            'dialogues': ttk.Frame(self.notebook),
            'story_texts': ttk.Frame(self.notebook),
            'crafting': ttk.Frame(self.notebook)
        }

        for name, frame in self.tabs.items():
            self.notebook.add(frame, text=name.title())

        self.create_toolbar()
        self.create_status_bar()
        self.create_scenes_tab()
        self.create_items_tab()
        self.create_characters_tab()
        self.create_dialogues_tab()
        self.create_story_text_editor()
        self.create_crafting_editor()

    def configure_dark_theme(self):
        colors = {
            'bg': '#1e1e1e',
            'fg': '#ffffff',
            'select_bg': '#404040',
            'select_fg': '#ffffff',
            'input_bg': '#2d2d2d',
            'button_bg': '#3d3d3d',
            'button_active': '#4d4d4d'
        }

        style_configs = {
            'TFrame': {'background': colors['bg']},
            'TLabel': {'background': colors['bg'], 'foreground': colors['fg']},
            'TButton': {
                'background': colors['button_bg'],
                'foreground': colors['fg'],
                'borderwidth': 1,
                'focusthickness': 3,
                'focuscolor': 'none'
            },
            'TNotebook': {'background': colors['bg'], 'borderwidth': 0},
            'TNotebook.Tab': {
                'background': colors['button_bg'],
                'foreground': colors['fg'],
                'padding': [10, 2],
                'borderwidth': 1
            }
        }

        for style, config in style_configs.items():
            self.style.configure(style, **config)

        self.style.map('TButton', background=[('active', colors['button_active'])])
        self.style.map('TNotebook.Tab',
                      background=[('selected', colors['select_bg'])],
                      foreground=[('selected', colors['select_fg'])])

        return colors

    def create_custom_listbox(self, parent, height=20, width=40):
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.BOTH, expand=True)

        listbox = tk.Listbox(frame,
                          height=height,
                          width=width,
                          bg='#2d2d2d',
                          fg='#ffffff',
                          selectbackground='#404040',
                          selectforeground='#ffffff',
                          selectmode=tk.SINGLE,
                          relief=tk.FLAT,
                          borderwidth=0,
                          highlightthickness=1,
                          highlightbackground='#404040')
        
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL)
        listbox.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=listbox.yview)
        
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        return listbox

    def create_custom_text(self, parent, height=30, width=80):
        text = ScrolledText(parent,
                         height=height,
                         width=width,
                         bg='#2d2d2d',
                         fg='#ffffff',
                         insertbackground='#ffffff',
                         relief=tk.FLAT,
                         borderwidth=0,
                         highlightthickness=1,
                         highlightbackground='#404040')
        return text

    def create_search_frame(self, parent, search_var, placeholder):
        search_frame = ttk.Frame(parent)
        search_frame.pack(fill=tk.X, pady=(0,5))
        
        PlaceholderEntry(search_frame, 
                        textvariable=search_var,
                        placeholder=placeholder).pack(fill=tk.X, padx=5)
        
        return search_frame

    def create_tab_layout(self, tab_frame, search_var, placeholder):
        paned = ttk.PanedWindow(tab_frame, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        list_frame = ttk.Frame(paned)
        paned.add(list_frame, weight=1)

        self.create_search_frame(list_frame, search_var, placeholder)
        listbox = self.create_custom_listbox(list_frame)
        
        editor_frame = ttk.Frame(paned)
        paned.add(editor_frame, weight=2)
        
        return listbox, editor_frame

    def create_toolbar(self):
        toolbar = ttk.Frame(self.root)
        toolbar.pack(fill=tk.X, padx=5, pady=2)

        buttons = [
            ("Save All", self.save_all),
            ("Reload", self.reload_data),
            ("Undo", self.undo),
            ("Redo", self.redo),
            ("Validate", self.validate_all_data),
            ("Find References", self.find_references)
        ]

        for text, command in buttons:
            ttk.Button(toolbar, text=text, command=command).pack(side=tk.LEFT, padx=2)

    def create_status_bar(self):
        self.status_var = tk.StringVar()
        status_bar = ttk.Label(self.root, textvariable=self.status_var,
                             relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        self.update_status()

    def update_status(self, message=None):
        if message:
            self.status_var.set(message)
        else:
            modified = len(self.modified)
            self.status_var.set(f"Modified files: {', '.join(self.modified)}" if modified else "No modifications")

    # Include all previously defined methods for:
    # - Tab creation (create_scenes_tab, create_items_tab, etc.)
    # - Event handling (setup_event_bindings)
    # - Error handling (setup_error_handlers)
    # - Data validation (validate_all_data, etc.)
    # - File operations (load_data, save_all, etc.)

    def setup_error_handlers(self):
        """Initialize error handling"""
        self.root.report_callback_exception = self.handle_callback_error
        self.setup_logging()

    def setup_logging(self):
        """Configure error logging"""
        os.makedirs('logs', exist_ok=True)
        logging.basicConfig(
            filename='logs/editor.log',
            level=logging.ERROR,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger('GameEditor')

    def handle_callback_error(self, exc_type, exc_value, exc_traceback):
        """Handle Tkinter callback errors"""
        error_msg = self.format_error_message(exc_type, exc_value)
        self.log_error(exc_type, exc_value, exc_traceback)
        self.show_error_dialog(error_msg)

    def format_error_message(self, exc_type, exc_value):
        """Format error message for display"""
        if isinstance(exc_value, FileOperationError):
            return f"File Operation Error: {str(exc_value)}"
        elif isinstance(exc_value, ValidationError):
            return f"Validation Error: {str(exc_value)}"
        else:
            return f"Error: {str(exc_value)}"

    def log_error(self, exc_type, exc_value, exc_traceback):
        """Log error with full traceback"""
        self.logger.error(
            "Exception occurred",
            exc_info=(exc_type, exc_value, exc_traceback)
        )

    def show_error_dialog(self, message, title="Error"):
        """Display error dialog to user"""
        messagebox.showerror(title, message)
        if self.in_transaction:
            self.rollback_transaction()

    @contextmanager
    def error_handling(self, operation_name):
        """Context manager for error handling"""
        try:
            yield
        except Exception as e:
            self.handle_operation_error(e, operation_name)

    def handle_operation_error(self, error, operation_name):
        """Handle operation-specific errors"""
        error_msg = f"Error in {operation_name}: {str(error)}"
        self.logger.error(error_msg, exc_info=True)
        self.show_error_dialog(error_msg)

    def handle_file_error(self, error, filepath):
        """Handle file operation errors"""
        if isinstance(error, FileNotFoundError):
            return self.handle_missing_file(filepath)
        elif isinstance(error, json.JSONDecodeError):
            return self.handle_invalid_json(filepath)
        else:
            raise FileOperationError(f"Error accessing {filepath}: {str(error)}")

    def handle_missing_file(self, filepath):
        """Handle missing file"""
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            return self.create_default_data(filepath)
        except Exception as e:
            raise FileOperationError(f"Could not create default data for {filepath}: {str(e)}")

    def handle_invalid_json(self, filepath):
        """Handle corrupted JSON files"""
        backup_path = f"{filepath}.bak.{int(time.time())}"
        try:
            if os.path.exists(filepath):
                shutil.copy2(filepath, backup_path)
                self.logger.warning(f"Backed up corrupt file to {backup_path}")
            return self.create_default_data(filepath)
        except Exception as e:
            raise FileOperationError(f"Could not handle corrupt file {filepath}: {str(e)}")

    @contextmanager
    def transaction(self):
        """Transaction context for multi-step operations"""
        self.begin_transaction()
        try:
            yield
            self.commit_transaction()
        except Exception as e:
            self.rollback_transaction()
            raise e

    def begin_transaction(self):
        """Start a new transaction"""
        self.transaction_backup = {
            'scenes': copy.deepcopy(self.scenes_data),
            'items': copy.deepcopy(self.items_data),
            'characters': copy.deepcopy(self.characters_data)
        }
        self.in_transaction = True

    def commit_transaction(self):
        """Commit current transaction"""
        self.transaction_backup = None
        self.in_transaction = False

    def rollback_transaction(self):
        """Rollback current transaction"""
        if self.transaction_backup:
            self.scenes_data = self.transaction_backup['scenes']
            self.items_data = self.transaction_backup['items']
            self.characters_data = self.transaction_backup['characters']
            self.refresh_all_lists()
        self.in_transaction = False

    def create_default_data(self, filepath):
        """Create default data based on file type"""
        defaults = {
            'scenes.json': [{'id': 'start', 'name': 'Start', 'description': 'Starting area'}],
            'items.json': {},
            'characters.json': {},
            'story_texts.json': {}
        }
        filename = os.path.basename(filepath)
        return defaults.get(filename, {})

    def safe_save(self, filepath, data):
        """Safely save file with backup"""
        backup_path = f"{filepath}.bak"
        try:
            if os.path.exists(filepath):
                shutil.copy2(filepath, backup_path)
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            if os.path.exists(backup_path):
                shutil.copy2(backup_path, filepath)
            raise FileOperationError(f"Failed to save {filepath}: {str(e)}")

    def setup_event_bindings(self):
        self.root.bind('<Control-s>', lambda e: self.save_all())
        self.root.bind('<Control-z>', lambda e: self.undo())
        self.root.bind('<Control-y>', lambda e: self.redo())
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.notebook.bind('<<NotebookTabChanged>>', self.on_tab_change)

    def on_close(self):
        if self.modified and messagebox.askyesno("Save Changes", "Save changes before closing?"):
            self.save_all()
        self.root.destroy()

    def on_tab_change(self, event=None):
        current = self.notebook.select()
        tab_name = self.notebook.tab(current)["text"].lower()
        self.refresh_tab(tab_name)

    def refresh_tab(self, tab_name):
        refresh_methods = {
            'scenes': self.refresh_scenes_list,
            'items': self.refresh_items_list,
            'characters': self.refresh_characters_list,
            'story_texts': self.refresh_story_texts_list
        }
        if method := refresh_methods.get(tab_name):
            method()

    def on_scene_select(self, event=None):
        if not (selection := self.scenes_listbox.curselection()):
            return
            
        scene = self.scenes_data[selection[0]]
        self.scene_id_var.set(scene['id'])
        self.scene_name_var.set(scene['name'])
        self.scene_desc_text.delete('1.0', tk.END)
        self.scene_desc_text.insert('1.0', scene.get('description', ''))
        self.update_scene_contents(scene)

    def on_item_select(self, event=None):
        if not (selection := self.items_listbox.curselection()):
            return
            
        item_id = list(self.items_data.keys())[selection[0]]
        item = self.items_data[item_id]
        self.update_item_editor(item_id, item)

    def on_character_select(self, event=None):
        if not (selection := self.chars_listbox.curselection()):
            return
            
        char_id = list(self.characters_data.keys())[selection[0]]
        character = self.characters_data[char_id]
        self.update_character_editor(char_id, character)

    @safe_operation
    def undo(self):
        if not self.undo_stack:
            return
            
        action = self.undo_stack.pop()
        self.redo_stack.append(action)
        self._apply_action(action, reverse=True)
        self.update_status(f"Undo: {action['description']}")

    @safe_operation
    def redo(self):
        if not self.redo_stack:
            return
            
        action = self.redo_stack.pop()
        self.undo_stack.append(action)
        self._apply_action(action)
        self.update_status(f"Redo: {action['description']}")

    def _apply_action(self, action, reverse=False):
        data = action['undo_data'] if reverse else action['redo_data']
        target = action['target']
        
        data_map = {
            'scenes': self.scenes_data,
            'items': self.items_data,
            'characters': self.characters_data
        }
        
        if target_data := data_map.get(target):
            if isinstance(target_data, list):
                self._apply_list_action(target_data, data)
            else:
                self._apply_dict_action(target_data, data)
                
        self.refresh_tab(target)

    def _apply_list_action(self, target_data, data):
        for idx, item in enumerate(target_data):
            if item['id'] == data['id']:
                target_data[idx] = data
                break

    def _apply_dict_action(self, target_data, data):
        target_data[data['id']] = data

    def add_undo_action(self, action_type, target, undo_data, redo_data, description):
        self.undo_stack.append({
            'type': action_type,
            'target': target,
            'undo_data': undo_data,
            'redo_data': redo_data,
            'description': description
        })
        self.redo_stack.clear()
        self.modified.add(target)

    def validate_all_data(self):
        """Validate all game data"""
        errors = []
        validators = [
            self.validate_scenes,
            self.validate_items,
            self.validate_characters,
            self.validate_references
        ]
        
        for validator in validators:
            errors.extend(validator())
        
        self.show_validation_results(errors)
        return not errors

    def validate_scenes(self):
        """Validate scenes data"""
        errors = []
        scene_ids = set()
        
        for scene in self.scenes_data:
            # Check required fields
            if not scene.get('id'):
                errors.append("Scene missing ID")
                continue
                
            if scene['id'] in scene_ids:
                errors.append(f"Duplicate scene ID: {scene['id']}")
            scene_ids.add(scene['id'])
            
            if not scene.get('name'):
                errors.append(f"Scene {scene['id']} missing name")
            
            # Validate exits
            for exit in scene.get('exits', []):
                if not exit.get('scene_id'):
                    errors.append(f"Scene {scene['id']} has exit without target")
                elif exit['scene_id'] not in scene_ids:
                    errors.append(f"Scene {scene['id']} has invalid exit to {exit['scene_id']}")
                
                if not exit.get('door_name'):
                    errors.append(f"Scene {scene['id']} has exit without name")
            
            # Validate items and characters
            for item_id in scene.get('items', []):
                if item_id not in self.items_data:
                    errors.append(f"Scene {scene['id']} references invalid item: {item_id}")
                    
            for char_id in scene.get('characters', []):
                if char_id not in self.characters_data:
                    errors.append(f"Scene {scene['id']} references invalid character: {char_id}")
        
        return errors

    def validate_items(self):
        """Validate items data"""
        errors = []
        valid_types = {"Regular", "Quest", "Key", "Tool", "Weapon", "Consumable"}
        
        for item_id, item in self.items_data.items():
            if not item.get('name'):
                errors.append(f"Item {item_id} missing name")
                
            if item_type := item.get('type'):
                if item_type not in valid_types:
                    errors.append(f"Item {item_id} has invalid type: {item_type}")
            else:
                errors.append(f"Item {item_id} missing type")
                
            if item.get('usable') and not item.get('effects'):
                errors.append(f"Usable item {item_id} has no effects")
                
            if item.get('equippable'):
                effects = item.get('effects', {})
                if not any(e in effects for e in ['attack', 'defense', 'speed']):
                    errors.append(f"Equippable item {item_id} missing combat effects")
                    
            # Validate effects structure
            for effect_type, effect in item.get('effects', {}).items():
                if not isinstance(effect, dict):
                    errors.append(f"Item {item_id} has invalid effect structure for {effect_type}")
                    continue
                    
                if 'value' not in effect:
                    errors.append(f"Item {item_id} effect {effect_type} missing value")
                    
                if 'duration' not in effect:
                    errors.append(f"Item {item_id} effect {effect_type} missing duration")
        
        return errors

    def validate_characters(self):
        """Validate characters data"""
        errors = []
        valid_types = {"friendly", "hostile", "neutral", "merchant"}
        
        for char_id, char in self.characters_data.items():
            if not char.get('name'):
                errors.append(f"Character {char_id} missing name")
                
            if char_type := char.get('type'):
                if char_type not in valid_types:
                    errors.append(f"Character {char_id} has invalid type: {char_type}")
            else:
                errors.append(f"Character {char_id} missing type")
                
            # Validate movement rules
            if char.get('movable'):
                if not char.get('initial_scene'):
                    errors.append(f"Movable character {char_id} missing initial scene")
                if char.get('follows_player') and char.get('allowed_scenes'):
                    errors.append(f"Character {char_id} cannot both follow player and have restricted scenes")
                    
            # Validate inventory
            for item_id in char.get('inventory', []):
                if item_id not in self.items_data:
                    errors.append(f"Character {char_id} has invalid item: {item_id}")
                    
            # Validate dialogue
            for dialogue_id, dialogue in char.get('dialogue_options', {}).items():
                if not dialogue.get('response'):
                    errors.append(f"Character {char_id} dialogue {dialogue_id} missing response")
                if dialogue.get('requires_item') and dialogue['requires_item'] not in self.items_data:
                    errors.append(f"Character {char_id} dialogue {dialogue_id} requires invalid item")
        
        return errors

    def validate_references(self):
        """Validate cross-references between data types"""
        errors = []
        
        # Validate scene references in characters
        for char_id, char in self.characters_data.items():
            if initial_scene := char.get('initial_scene'):
                if not any(s['id'] == initial_scene for s in self.scenes_data):
                    errors.append(f"Character {char_id} has invalid initial scene: {initial_scene}")
                    
            for scene_id in char.get('allowed_scenes', []):
                if not any(s['id'] == scene_id for s in self.scenes_data):
                    errors.append(f"Character {char_id} has invalid allowed scene: {scene_id}")
        
        # Validate item references in crafting recipes
        for recipe in self.get_all_recipes():
            if result := recipe.get('result'):
                if result not in self.items_data:
                    errors.append(f"Recipe has invalid result item: {result}")
                    
            for ingredient in recipe.get('ingredients', []):
                if ingredient not in self.items_data:
                    errors.append(f"Recipe has invalid ingredient: {ingredient}")
        
        return errors

    def show_validation_results(self, errors):
        """Display validation results dialog"""
        if not errors:
            messagebox.showinfo("Validation", "No errors found in game data")
            return
            
        error_window = tk.Toplevel(self.root)
        error_window.title("Validation Errors")
        error_window.geometry("600x400")
        
        text = self.create_custom_text(error_window)
        text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        for error in errors:
            text.insert(tk.END, f"• {error}\n")
        text.config(state=tk.DISABLED)
        
        ttk.Button(error_window, text="Close", 
                  command=error_window.destroy).pack(pady=5)

    def get_all_recipes(self):
        """Helper to collect all crafting recipes from characters"""
        recipes = []
        for char in self.characters_data.values():
            recipes.extend(char.get('crafting_recipes', []))
        return recipes

    def load_data(self):
        """Load all game data files"""
        try:
            self.load_scenes()
            self.load_items()
            self.load_characters()
            self.load_story_texts()
            self.load_dialogue_data()
            self.refresh_all_lists()
        except Exception as e:
            self.show_error_dialog(f"Error loading data: {str(e)}")

    def load_dialogue_data(self):
        """Load dialogue data from file"""
        try:
            with open('game_files/dialogues.json', 'r') as f:
                self.dialogue_data = json.load(f)
                self.refresh_dialogue_tree()
        except FileNotFoundError:
            self.dialogue_data = {
                'default': {
                    'name': 'Default Dialogue',
                    'content': 'Default dialogue content',
                    'responses': []
                }
            }
            self.refresh_dialogue_tree()            

    def load_scenes(self):
        try:
            with open('game_files/scenes/scenes.json', 'r') as f:
                self.scenes_data = json.load(f)
        except FileNotFoundError:
            self.scenes_data = []
            self.create_default_scenes()

    def load_items(self):
        try:
            with open('game_files/items.json', 'r') as f:
                self.items_data = json.load(f)
        except FileNotFoundError:
            self.items_data = {}
            self.create_default_items()

    def load_characters(self):
        try:
            with open('game_files/characters.json', 'r') as f:
                self.characters_data = json.load(f)
        except FileNotFoundError:
            self.characters_data = {}
            self.create_default_characters()

    def load_story_texts(self):
        try:
            with open('game_files/story_texts.json', 'r') as f:
                self.story_texts_data = json.load(f)
        except FileNotFoundError:
            self.story_texts_data = {}

    def save_all(self):
        """Save all modified data files"""
        if not self.modified:
            return

        try:
            self.create_backup()
            
            if 'scenes' in self.modified:
                self.save_scenes()
            if 'items' in self.modified:
                self.save_items()
            if 'characters' in self.modified:
                self.save_characters()
            if 'story_texts' in self.modified:
                self.save_story_texts()

            self.modified.clear()
            self.update_status("All changes saved successfully")
        except Exception as e:
            self.show_error_dialog(f"Error saving data: {str(e)}")

    def save_scenes(self):
        os.makedirs('game_files/scenes', exist_ok=True)
        with open('game_files/scenes/scenes.json', 'w') as f:
            json.dump(self.scenes_data, f, indent=4)

    def save_items(self):
        with open('game_files/items.json', 'w') as f:
            json.dump(self.items_data, f, indent=4)

    def save_characters(self):
        with open('game_files/characters.json', 'w') as f:
            json.dump(self.characters_data, f, indent=4)

    def save_story_texts(self):
        with open('game_files/story_texts.json', 'w') as f:
            json.dump(self.story_texts_data, f, indent=4)

    def create_backup(self):
        """Create backup of current data files"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_dir = os.path.join('backups', timestamp)
        os.makedirs(backup_dir, exist_ok=True)

        files_to_backup = {
            'scenes': 'game_files/scenes/scenes.json',
            'items': 'game_files/items.json',
            'characters': 'game_files/characters.json',
            'story_texts': 'game_files/story_texts.json'
        }

        for data_type, filepath in files_to_backup.items():
            if data_type in self.modified and os.path.exists(filepath):
                backup_path = os.path.join(backup_dir, os.path.basename(filepath))
                shutil.copy2(filepath, backup_path)

    def reload_data(self):
        """Reload all data from disk"""
        if self.modified:
            if not messagebox.askyesno("Confirm Reload", 
                "You have unsaved changes. Are you sure you want to reload?"):
                return

        self.load_data()
        self.modified.clear()
        self.update_status("Data reloaded from disk")

    def create_default_scenes(self):
        """Create default scene if none exists"""
        self.scenes_data = [{
            'id': 'start',
            'name': 'Starting Area',
            'description': 'The beginning of your journey.',
            'exits': [],
            'items': [],
            'characters': []
        }]

    def create_default_items(self):
        """Create default item if none exists"""
        self.items_data = {
            'basic_sword': {
                'name': 'Basic Sword',
                'type': 'Weapon',
                'description': 'A simple sword.',
                'equippable': True,
                'effects': {'attack': {'value': 5, 'duration': 'permanent'}}
            }
        }

    def create_default_characters(self):
        """Create default character if none exists"""
        self.characters_data = {
            'guide': {
                'name': 'Guide',
                'type': 'friendly',
                'description': 'A helpful guide.',
                'greeting': 'Welcome, traveler!'
            }
        }

    def export_data(self, data_type):
        """Export specific data type to file"""
        file_types = [('JSON files', '*.json'), ('All files', '*.*')]
        filename = filedialog.asksaveasfilename(
            defaultextension='.json',
            filetypes=file_types,
            title=f'Export {data_type}'
        )
        
        if filename:
            try:
                data = getattr(self, f'{data_type}_data')
                with open(filename, 'w') as f:
                    json.dump(data, f, indent=4)
                messagebox.showinfo('Success', f'{data_type} exported successfully')
            except Exception as e:
                self.show_error_dialog(f'Error exporting {data_type}: {str(e)}')

    def import_data(self, data_type):
        """Import specific data type from file"""
        file_types = [('JSON files', '*.json'), ('All files', '*.*')]
        filename = filedialog.askopenfilename(
            filetypes=file_types,
            title=f'Import {data_type}'
        )
        
        if filename:
            try:
                with open(filename, 'r') as f:
                    data = json.load(f)
                setattr(self, f'{data_type}_data', data)
                self.modified.add(data_type)
                self.refresh_all_lists()
                messagebox.showinfo('Success', f'{data_type} imported successfully')
            except Exception as e:
                self.show_error_dialog(f'Error importing {data_type}: {str(e)}')    

    def create_scenes_tab(self):
        self.scenes_listbox, editor_frame = self.create_tab_layout(
            self.tabs['scenes'], 
            self.search_vars['scene'],
            "Search scenes..."
        )

        # Properties Frame
        props_frame = ttk.LabelFrame(editor_frame, text="Scene Properties")
        props_frame.pack(fill=tk.X, padx=5, pady=5)

        self.scene_id_var = tk.StringVar()
        self.scene_name_var = tk.StringVar()
        
        ttk.Label(props_frame, text="ID:").grid(row=0, column=0, padx=5, pady=2)
        ttk.Entry(props_frame, textvariable=self.scene_id_var, state='readonly').grid(
            row=0, column=1, padx=5, pady=2, sticky='ew')
            
        ttk.Label(props_frame, text="Name:").grid(row=1, column=0, padx=5, pady=2)
        ttk.Entry(props_frame, textvariable=self.scene_name_var).grid(
            row=1, column=1, padx=5, pady=2, sticky='ew')

        # Description Frame
        desc_frame = ttk.LabelFrame(editor_frame, text="Description")
        desc_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.scene_desc_text = self.create_custom_text(desc_frame)
        self.scene_desc_text.pack(fill=tk.BOTH, expand=True)

        # Contents Frame
        contents_frame = ttk.LabelFrame(editor_frame, text="Scene Contents")
        contents_frame.pack(fill=tk.X, padx=5, pady=5)

        # Items List
        items_frame = ttk.Frame(contents_frame)
        items_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(items_frame, text="Items:").pack(anchor=tk.W)
        self.scene_items_list = self.create_custom_listbox(items_frame, height=5)
        self.scene_items_list.pack(fill=tk.X)

        item_buttons = ttk.Frame(items_frame)
        item_buttons.pack(fill=tk.X)
        ttk.Button(item_buttons, text="Add Item", command=self.add_item_to_scene).pack(side=tk.LEFT, padx=2)
        ttk.Button(item_buttons, text="Remove Item", command=self.remove_item_from_scene).pack(side=tk.LEFT, padx=2)

        # Characters List
        chars_frame = ttk.Frame(contents_frame)
        chars_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(chars_frame, text="Characters:").pack(anchor=tk.W)
        self.scene_chars_list = self.create_custom_listbox(chars_frame, height=5)
        self.scene_chars_list.pack(fill=tk.X)

        char_buttons = ttk.Frame(chars_frame)
        char_buttons.pack(fill=tk.X)
        ttk.Button(char_buttons, text="Add Character", command=self.add_character_to_scene).pack(side=tk.LEFT, padx=2)
        ttk.Button(char_buttons, text="Remove Character", command=self.remove_character_from_scene).pack(side=tk.LEFT, padx=2)

        # Exits Frame
        exits_frame = ttk.LabelFrame(editor_frame, text="Exits")
        exits_frame.pack(fill=tk.X, padx=5, pady=5)
        self.scene_exits_list = self.create_custom_listbox(exits_frame, height=5)
        self.scene_exits_list.pack(fill=tk.X)

        exit_buttons = ttk.Frame(exits_frame)
        exit_buttons.pack(fill=tk.X)
        ttk.Button(exit_buttons, text="Add Exit", command=self.add_exit).pack(side=tk.LEFT, padx=2)
        ttk.Button(exit_buttons, text="Edit Exit", command=self.edit_exit).pack(side=tk.LEFT, padx=2)
        ttk.Button(exit_buttons, text="Remove Exit", command=self.remove_exit).pack(side=tk.LEFT, padx=2)

        # Bindings
        self.scenes_listbox.bind('<<ListboxSelect>>', self.on_scene_select)
        self.scene_exits_list.bind('<Double-Button-1>', lambda e: self.edit_exit())

    def create_items_tab(self):
        self.items_listbox, editor_frame = self.create_tab_layout(
            self.tabs['items'],
            self.search_vars['item'],
            "Search items..."
        )

        # Properties Frame
        props_frame = ttk.LabelFrame(editor_frame, text="Item Properties")
        props_frame.pack(fill=tk.X, padx=5, pady=5)

        self.item_id_var = tk.StringVar()
        self.item_name_var = tk.StringVar()
        self.item_type_var = tk.StringVar()

        grid_items = [
            ("ID:", self.item_id_var, 'readonly'),
            ("Name:", self.item_name_var, 'normal'),
            ("Type:", self.item_type_var, 'normal')
        ]

        for i, (label, var, state) in enumerate(grid_items):
            ttk.Label(props_frame, text=label).grid(row=i, column=0, padx=5, pady=2)
            if label == "Type:":
                ttk.Combobox(props_frame, textvariable=var,
                            values=["Regular", "Quest", "Key", "Tool", "Weapon", "Consumable"]).grid(
                    row=i, column=1, padx=5, pady=2, sticky='ew')
            else:
                ttk.Entry(props_frame, textvariable=var, state=state).grid(
                    row=i, column=1, padx=5, pady=2, sticky='ew')

        # Checkboxes Frame
        checks_frame = ttk.Frame(props_frame)
        checks_frame.grid(row=len(grid_items), column=0, columnspan=2, padx=5, pady=2)

        self.item_usable_var = tk.BooleanVar()
        self.item_equippable_var = tk.BooleanVar()
        self.item_consumable_var = tk.BooleanVar()

        check_items = [
            ("Usable", self.item_usable_var),
            ("Equippable", self.item_equippable_var),
            ("Consumable", self.item_consumable_var)
        ]

        for text, var in check_items:
            ttk.Checkbutton(checks_frame, text=text, variable=var).pack(side=tk.LEFT, padx=5)

        # Description Frame
        desc_frame = ttk.LabelFrame(editor_frame, text="Description")
        desc_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.item_desc_text = self.create_custom_text(desc_frame)
        self.item_desc_text.pack(fill=tk.BOTH, expand=True)

        # Effects Frame
        effects_frame = ttk.LabelFrame(editor_frame, text="Effects")
        effects_frame.pack(fill=tk.X, padx=5, pady=5)
        self.effects_list = self.create_custom_listbox(effects_frame, height=5)
        self.effects_list.pack(fill=tk.X)

        effect_buttons = ttk.Frame(effects_frame)
        effect_buttons.pack(fill=tk.X)
        ttk.Button(effect_buttons, text="Add Effect", command=self.add_item_effect).pack(side=tk.LEFT, padx=2)
        ttk.Button(effect_buttons, text="Edit Effect", command=self.edit_item_effect).pack(side=tk.LEFT, padx=2)
        ttk.Button(effect_buttons, text="Remove Effect", command=self.remove_item_effect).pack(side=tk.LEFT, padx=2)

        # Bindings
        self.items_listbox.bind('<<ListboxSelect>>', self.on_item_select)
        self.effects_list.bind('<Double-Button-1>', lambda e: self.edit_item_effect())

    def create_characters_tab(self):
        self.chars_listbox, editor_frame = self.create_tab_layout(
            self.tabs['characters'],
            self.search_vars['character'],
            "Search characters..."
        )

        notebook = ttk.Notebook(editor_frame)
        notebook.pack(fill=tk.BOTH, expand=True)

        self.create_character_basic_info(notebook)
        self.create_character_dialogue(notebook)
        self.create_character_stats(notebook)

        # Main buttons
        button_frame = ttk.Frame(editor_frame)
        button_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(button_frame, text="Save Character", command=self.save_current_character).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Delete Character", command=self.delete_current_character).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Duplicate Character", command=self.duplicate_current_character).pack(side=tk.LEFT, padx=2)

        # Bindings
        self.chars_listbox.bind('<<ListboxSelect>>', self.on_character_select)

    def create_character_basic_info(self, notebook):
        basic_frame = ttk.Frame(notebook)
        notebook.add(basic_frame, text="Basic Info")

        props_frame = ttk.LabelFrame(basic_frame, text="Character Properties")
        props_frame.pack(fill=tk.X, padx=5, pady=5)

        self.char_id_var = tk.StringVar()
        self.char_name_var = tk.StringVar()
        self.char_type_var = tk.StringVar()

        grid_items = [
            ("ID:", self.char_id_var, 'readonly'),
            ("Name:", self.char_name_var, 'normal'),
            ("Type:", self.char_type_var, ['friendly', 'hostile', 'neutral', 'merchant'])
        ]

        for i, (label, var, state_or_values) in enumerate(grid_items):
            ttk.Label(props_frame, text=label).grid(row=i, column=0, padx=5, pady=2)
            if isinstance(state_or_values, list):
                ttk.Combobox(props_frame, textvariable=var, values=state_or_values).grid(
                    row=i, column=1, padx=5, pady=2, sticky='ew')
            else:
                ttk.Entry(props_frame, textvariable=var, state=state_or_values).grid(
                    row=i, column=1, padx=5, pady=2, sticky='ew')

        # Movement Options
        movement_frame = ttk.LabelFrame(basic_frame, text="Movement Options")
        movement_frame.pack(fill=tk.X, padx=5, pady=5)

        self.char_movable_var = tk.BooleanVar()
        self.char_follows_var = tk.BooleanVar()

        ttk.Checkbutton(movement_frame, text="Movable", variable=self.char_movable_var).pack(anchor=tk.W, padx=5)
        ttk.Checkbutton(movement_frame, text="Follows Player", variable=self.char_follows_var).pack(anchor=tk.W, padx=5)

        # Description
        desc_frame = ttk.LabelFrame(basic_frame, text="Description")
        desc_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.char_desc_text = self.create_custom_text(desc_frame)
        self.char_desc_text.pack(fill=tk.BOTH, expand=True)

    def create_character_dialogue(self, notebook):
        dialogue_frame = ttk.Frame(notebook)
        notebook.add(dialogue_frame, text="Dialogue")

        # Greeting
        greet_frame = ttk.LabelFrame(dialogue_frame, text="Greeting")
        greet_frame.pack(fill=tk.X, padx=5, pady=5)
        self.char_greeting_text = self.create_custom_text(greet_frame, height=3)
        self.char_greeting_text.pack(fill=tk.X)

        # Dialogue Options
        options_frame = ttk.LabelFrame(dialogue_frame, text="Dialogue Options")
        options_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.dialogue_options_list = self.create_custom_listbox(options_frame)
        self.dialogue_options_list.pack(fill=tk.BOTH, expand=True)

        button_frame = ttk.Frame(options_frame)
        button_frame.pack(fill=tk.X, pady=5)
        
        buttons = [
            ("Add Option", self.add_dialogue_option),
            ("Edit Option", self.edit_dialogue_option),
            ("Remove Option", self.remove_dialogue_option)
        ]
        
        for text, command in buttons:
            ttk.Button(button_frame, text=text, command=command).pack(side=tk.LEFT, padx=2)

        self.dialogue_options_list.bind('<Double-Button-1>', lambda e: self.edit_dialogue_option())

    def create_character_stats(self, notebook):
        stats_frame = ttk.Frame(notebook)
        notebook.add(stats_frame, text="Stats")

        # Stats Treeview
        self.stats_tree = ttk.Treeview(stats_frame, columns=("value"), show="headings")
        self.stats_tree.heading("value", text="Value")
        self.stats_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        scrollbar = ttk.Scrollbar(stats_frame, orient=tk.VERTICAL, command=self.stats_tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.stats_tree.configure(yscrollcommand=scrollbar.set)

        # Buttons for stat management
        button_frame = ttk.Frame(stats_frame)
        button_frame.pack(fill=tk.X, padx=5, pady=5)
        
        buttons = [
            ("Add Stat", self.add_character_stat),
            ("Edit Stat", self.edit_character_stat),
            ("Remove Stat", self.remove_character_stat)
        ]
        
        for text, command in buttons:
            ttk.Button(button_frame, text=text, command=command).pack(side=tk.LEFT, padx=2)

        self.stats_tree.bind('<Double-Button-1>', lambda e: self.edit_character_stat())

    def create_dialogues_tab(self):
        dialogue_frame = ttk.Frame(self.tabs['dialogues'])
        paned = ttk.PanedWindow(dialogue_frame, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # Tree structure
        self.dialogue_tree = ttk.Treeview(paned, selectmode='browse')
        self.dialogue_tree.heading('#0', text='Dialogue Tree')
        paned.add(self.dialogue_tree, weight=1)

        # Editor frame
        editor_frame = ttk.Frame(paned)
        paned.add(editor_frame, weight=2)

        # Content editor
        content_frame = ttk.LabelFrame(editor_frame, text="Dialogue Content")
        content_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.dialogue_content = self.create_custom_text(content_frame)
        self.dialogue_content.pack(fill=tk.BOTH, expand=True)

        # Response options
        options_frame = ttk.LabelFrame(editor_frame, text="Response Options")
        options_frame.pack(fill=tk.X, padx=5, pady=5)
        self.response_list = self.create_custom_listbox(options_frame, height=5)
        self.response_list.pack(fill=tk.X)

        # Response buttons
        button_frame = ttk.Frame(options_frame)
        button_frame.pack(fill=tk.X, pady=5)
        for text, command in [
            ("Add Response", self.add_dialogue_response),
            ("Edit Response", self.edit_dialogue_response),
            ("Remove Response", self.remove_dialogue_response)
        ]:
            ttk.Button(button_frame, text=text, command=command).pack(side=tk.LEFT, padx=2)

        self.dialogue_tree.bind('<<TreeviewSelect>>', self.on_dialogue_select)

    def create_story_text_editor(self):
        story_frame = ttk.Frame(self.tabs['story_texts'])
        paned = ttk.PanedWindow(story_frame, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Text list panel
        list_frame = ttk.Frame(paned)
        paned.add(list_frame, weight=1)

        # Search
        search_frame = self.create_search_frame(list_frame, tk.StringVar(), "Search texts...")
        self.story_texts_listbox = self.create_custom_listbox(list_frame)

        # Editor panel
        editor_frame = ttk.Frame(paned)
        paned.add(editor_frame, weight=2)

        # Properties
        props_frame = ttk.LabelFrame(editor_frame, text="Properties")
        props_frame.pack(fill=tk.X, pady=5)
        
        self.text_key_var = tk.StringVar()
        ttk.Label(props_frame, text="Key:").grid(row=0, column=0, padx=5, pady=2)
        ttk.Entry(props_frame, textvariable=self.text_key_var).grid(row=0, column=1, sticky='ew')
        
        self.show_once_var = tk.BooleanVar()
        ttk.Checkbutton(props_frame, text="Show Once", variable=self.show_once_var).grid(
            row=1, column=0, columnspan=2, pady=2)

        # Text editor
        self.story_text_editor = self.create_custom_text(editor_frame)
        self.story_text_editor.pack(fill=tk.BOTH, expand=True, pady=5)

        # Control buttons
        controls = ttk.Frame(editor_frame)
        controls.pack(fill=tk.X)
        for text, command in [
            ("New Text", self.add_story_text),
            ("Save Text", self.save_story_text),
            ("Delete Text", self.delete_story_text)
        ]:
            ttk.Button(controls, text=text, command=command).pack(side=tk.LEFT, padx=2)

        self.story_texts_listbox.bind('<<ListboxSelect>>', self.on_story_text_select)

    def create_crafting_editor(self):
        crafting_frame = ttk.Frame(self.tabs['crafting'])
        paned = ttk.PanedWindow(crafting_frame, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Recipe list panel
        list_frame = ttk.Frame(paned)
        paned.add(list_frame, weight=1)

        search_frame = self.create_search_frame(list_frame, tk.StringVar(), "Search recipes...")
        self.recipes_listbox = self.create_custom_listbox(list_frame)

        # Editor panel
        editor_frame = ttk.Frame(paned)
        paned.add(editor_frame, weight=2)

        # Recipe details
        details_frame = ttk.LabelFrame(editor_frame, text="Recipe Details")
        details_frame.pack(fill=tk.X, pady=5)

        ttk.Label(details_frame, text="Result:").grid(row=0, column=0, padx=5, pady=2)
        self.result_item_var = tk.StringVar()
        self.result_combo = ttk.Combobox(details_frame, textvariable=self.result_item_var)
        self.result_combo.grid(row=0, column=1, sticky='ew', padx=5, pady=2)

        # Ingredients
        ingredients_frame = ttk.LabelFrame(editor_frame, text="Ingredients")
        ingredients_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        self.ingredients_list = self.create_custom_listbox(ingredients_frame, height=10)
        self.ingredients_list.pack(fill=tk.BOTH, expand=True)

        # Ingredient controls
        ingredient_buttons = ttk.Frame(ingredients_frame)
        ingredient_buttons.pack(fill=tk.X, pady=5)
        for text, command in [
            ("Add Ingredient", self.add_ingredient),
            ("Edit Ingredient", self.edit_ingredient),
            ("Remove Ingredient", self.remove_ingredient)
        ]:
            ttk.Button(ingredient_buttons, text=text, command=command).pack(side=tk.LEFT, padx=2)

        # Recipe controls
        recipe_buttons = ttk.Frame(editor_frame)
        recipe_buttons.pack(fill=tk.X, pady=5)
        for text, command in [
            ("New Recipe", self.new_recipe),
            ("Save Recipe", self.save_recipe),
            ("Delete Recipe", self.delete_recipe)
        ]:
            ttk.Button(recipe_buttons, text=text, command=command).pack(side=tk.LEFT, padx=2)

        self.recipes_listbox.bind('<<ListboxSelect>>', self.on_recipe_select)

    def find_references(self):
        """Find all references to the selected item/character"""
        current_tab = self.notebook.select()
        tab_name = self.notebook.tab(current_tab)["text"].lower()

        if tab_name == "items":
            if not (selection := self.items_listbox.curselection()):
                return
            item_id = list(self.items_data.keys())[selection[0]]
            self.show_item_references(item_id)
        elif tab_name == "characters":
            if not (selection := self.chars_listbox.curselection()):
                return
            char_id = list(self.characters_data.keys())[selection[0]]
            self.show_character_references(char_id)

    def show_item_references(self, item_id):
        """Show all references to a specific item"""
        references = []
        
        # Check scenes
        for scene in self.scenes_data:
            if item_id in scene.get('items', []):
                references.append(f"Scene: {scene['name']} (inventory)")

        # Check characters
        for char_id, char in self.characters_data.items():
            if item_id in char.get('inventory', []):
                references.append(f"Character: {char['name']} (inventory)")
            if item_id in char.get('crafting_requirements', []):
                references.append(f"Character: {char['name']} (crafting)")

        self.show_references_window("Item References", item_id, references)

    def show_character_references(self, char_id):
        """Show all references to a specific character"""
        references = []
        
        # Check scenes
        for scene in self.scenes_data:
            if char_id in scene.get('characters', []):
                references.append(f"Scene: {scene['name']}")
            for exit in scene.get('exits', []):
                if char_id in exit.get('dialogue_requirements', []):
                    references.append(f"Scene: {scene['name']} (exit requirement)")

        self.show_references_window("Character References", char_id, references)

    def show_references_window(self, title, entity_id, references):
        """Display references in a new window"""
        window = tk.Toplevel(self.root)
        window.title(title)
        window.geometry("400x300")

        ttk.Label(window, text=f"References to: {entity_id}").pack(pady=5)
        
        ref_list = self.create_custom_listbox(window)
        ref_list.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        if references:
            for ref in references:
                ref_list.insert(tk.END, ref)
        else:
            ref_list.insert(tk.END, "No references found")

        ttk.Button(window, text="Close", 
                command=window.destroy).pack(pady=5)   

    def add_item_to_scene(self):
        selection = self.scenes_listbox.curselection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a scene first")
            return

        if not self.items_data:
            messagebox.showwarning("Warning", "No items available")
            return

        scene = self.scenes_data[selection[0]]
        
        dialog = tk.Toplevel(self.root)
        dialog.title("Add Item")
        dialog.geometry("300x200")
        dialog.transient(self.root)
        dialog.grab_set()

        item_list = self.create_custom_listbox(dialog)
        item_list.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        for item_id, item in self.items_data.items():
            item_list.insert(tk.END, f"{item['name']} ({item_id})")

        def add_selected_item():
            if not (sel := item_list.curselection()):
                return
            item_id = list(self.items_data.keys())[sel[0]]
            if 'items' not in scene:
                scene['items'] = []
            scene['items'].append(item_id)
            self.scene_items_list.insert(tk.END, self.items_data[item_id]['name'])
            self.modified.add('scenes')
            dialog.destroy()

        ttk.Button(dialog, text="Add", command=add_selected_item).pack(pady=5)

    def remove_item_from_scene(self):
        scene_sel = self.scenes_listbox.curselection()
        item_sel = self.scene_items_list.curselection()
        
        if not (scene_sel and item_sel):
            messagebox.showwarning("Warning", "Please select a scene and item")
            return

        scene = self.scenes_data[scene_sel[0]]
        item_index = item_sel[0]
        
        if 'items' in scene and item_index < len(scene['items']):
            del scene['items'][item_index]
            self.scene_items_list.delete(item_sel)
            self.modified.add('scenes')

    def add_character_to_scene(self):
        selection = self.scenes_listbox.curselection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a scene first")
            return

        if not self.characters_data:
            messagebox.showwarning("Warning", "No characters available")
            return

        scene = self.scenes_data[selection[0]]
        
        dialog = tk.Toplevel(self.root)
        dialog.title("Add Character")
        dialog.geometry("300x200")
        dialog.transient(self.root)
        dialog.grab_set()

        char_list = self.create_custom_listbox(dialog)
        char_list.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        for char_id, char in self.characters_data.items():
            char_list.insert(tk.END, f"{char['name']} ({char_id})")

        def add_selected_character():
            if not (sel := char_list.curselection()):
                return
            char_id = list(self.characters_data.keys())[sel[0]]
            if 'characters' not in scene:
                scene['characters'] = []
            scene['characters'].append(char_id)
            self.scene_chars_list.insert(tk.END, self.characters_data[char_id]['name'])
            self.modified.add('scenes')
            dialog.destroy()

        ttk.Button(dialog, text="Add", command=add_selected_character).pack(pady=5)

    def remove_character_from_scene(self):
        scene_sel = self.scenes_listbox.curselection()
        char_sel = self.scene_chars_list.curselection()
        
        if not (scene_sel and char_sel):
            messagebox.showwarning("Warning", "Please select a scene and character")
            return

        scene = self.scenes_data[scene_sel[0]]
        char_index = char_sel[0]
        
        if 'characters' in scene and char_index < len(scene['characters']):
            del scene['characters'][char_index]
            self.scene_chars_list.delete(char_sel)
            self.modified.add('scenes')       

    def add_exit(self):
        selection = self.scenes_listbox.curselection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a scene first")
            return

        scene = self.scenes_data[selection[0]]
        
        dialog = tk.Toplevel(self.root)
        dialog.title("Add Exit")
        dialog.geometry("300x200")
        dialog.transient(self.root)
        dialog.grab_set()

        door_frame = ttk.Frame(dialog)
        door_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(door_frame, text="Door Name:").pack(side=tk.LEFT)
        door_var = tk.StringVar()
        ttk.Entry(door_frame, textvariable=door_var).pack(side=tk.LEFT, padx=5)

        target_frame = ttk.Frame(dialog)
        target_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(target_frame, text="Target Scene:").pack(side=tk.LEFT)
        target_var = tk.StringVar()
        target_combo = ttk.Combobox(target_frame, textvariable=target_var,
                                values=[s['name'] for s in self.scenes_data])
        target_combo.pack(side=tk.LEFT, padx=5)

        def add_exit_to_scene():
            door_name = door_var.get().strip()
            target_scene_name = target_var.get()
            if not door_name or not target_scene_name:
                messagebox.showerror("Error", "Door name and target scene required")
                return

            target_scene = next((s for s in self.scenes_data 
                            if s['name'] == target_scene_name), None)
            if not target_scene:
                messagebox.showerror("Error", "Invalid target scene")
                return

            if 'exits' not in scene:
                scene['exits'] = []

            scene['exits'].append({
                'door_name': door_name,
                'scene_id': target_scene['id']
            })

            self.scene_exits_list.insert(tk.END, f"{door_name} → {target_scene_name}")
            self.modified.add('scenes')
            dialog.destroy()

        ttk.Button(dialog, text="Add Exit", command=add_exit_to_scene).pack(pady=10)

    def edit_exit(self):
        scene_sel = self.scenes_listbox.curselection()
        exit_sel = self.scene_exits_list.curselection()
        
        if not (scene_sel and exit_sel):
            messagebox.showwarning("Warning", "Please select a scene and exit")
            return

        scene = self.scenes_data[scene_sel[0]]
        exit_index = exit_sel[0]
        exit_data = scene['exits'][exit_index]

        dialog = tk.Toplevel(self.root)
        dialog.title("Edit Exit")
        dialog.geometry("300x200")
        dialog.transient(self.root)
        dialog.grab_set()

        door_frame = ttk.Frame(dialog)
        door_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(door_frame, text="Door Name:").pack(side=tk.LEFT)
        door_var = tk.StringVar(value=exit_data['door_name'])
        ttk.Entry(door_frame, textvariable=door_var).pack(side=tk.LEFT, padx=5)

        target_frame = ttk.Frame(dialog)
        target_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(target_frame, text="Target Scene:").pack(side=tk.LEFT)
        target_scene = next(s for s in self.scenes_data if s['id'] == exit_data['scene_id'])
        target_var = tk.StringVar(value=target_scene['name'])
        target_combo = ttk.Combobox(target_frame, textvariable=target_var,
                                values=[s['name'] for s in self.scenes_data])
        target_combo.pack(side=tk.LEFT, padx=5)

        def update_exit():
            door_name = door_var.get().strip()
            target_scene_name = target_var.get()
            if not door_name or not target_scene_name:
                messagebox.showerror("Error", "Door name and target scene required")
                return

            new_target = next((s for s in self.scenes_data 
                            if s['name'] == target_scene_name), None)
            if not new_target:
                messagebox.showerror("Error", "Invalid target scene")
                return

            scene['exits'][exit_index].update({
                'door_name': door_name,
                'scene_id': new_target['id']
            })

            self.scene_exits_list.delete(exit_sel)
            self.scene_exits_list.insert(exit_sel, f"{door_name} → {target_scene_name}")
            self.modified.add('scenes')
            dialog.destroy()

        ttk.Button(dialog, text="Update Exit", command=update_exit).pack(pady=10)

    def remove_exit(self):
        scene_sel = self.scenes_listbox.curselection()
        exit_sel = self.scene_exits_list.curselection()
        
        if not (scene_sel and exit_sel):
            messagebox.showwarning("Warning", "Please select a scene and exit")
            return

        if not messagebox.askyesno("Confirm", "Remove this exit?"):
            return

        scene = self.scenes_data[scene_sel[0]]
        exit_index = exit_sel[0]
        
        del scene['exits'][exit_index]
        self.scene_exits_list.delete(exit_sel)
        self.modified.add('scenes')

    def add_item_effect(self):
        if not (selection := self.items_listbox.curselection()):
            messagebox.showwarning("Warning", "Please select an item first")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Add Effect")
        dialog.geometry("300x200")
        dialog.transient(self.root)
        dialog.grab_set()

        type_frame = ttk.Frame(dialog)
        type_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(type_frame, text="Effect Type:").pack(side=tk.LEFT)
        type_var = tk.StringVar(value="health")
        ttk.Combobox(type_frame, textvariable=type_var,
                    values=["health", "attack", "defense", "speed"]).pack(side=tk.LEFT, padx=5)

        value_frame = ttk.Frame(dialog)
        value_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(value_frame, text="Value:").pack(side=tk.LEFT)
        value_var = tk.StringVar()
        ttk.Entry(value_frame, textvariable=value_var).pack(side=tk.LEFT, padx=5)

        duration_frame = ttk.Frame(dialog)
        duration_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(duration_frame, text="Duration:").pack(side=tk.LEFT)
        duration_var = tk.StringVar(value="permanent")
        ttk.Combobox(duration_frame, textvariable=duration_var,
                    values=["permanent", "temporary", "single-use"]).pack(side=tk.LEFT, padx=5)

        def add_effect():
            try:
                value = float(value_var.get())
            except ValueError:
                messagebox.showerror("Error", "Value must be a number")
                return

            item_id = list(self.items_data.keys())[selection[0]]
            item = self.items_data[item_id]
            
            if 'effects' not in item:
                item['effects'] = {}

            effect_type = type_var.get()
            item['effects'][effect_type] = {
                'value': value,
                'duration': duration_var.get()
            }

            self.effects_list.insert(tk.END, f"{effect_type}: {value} ({duration_var.get()})")
            self.modified.add('items')
            dialog.destroy()

        ttk.Button(dialog, text="Add", command=add_effect).pack(pady=10)

    def edit_item_effect(self):
        item_sel = self.items_listbox.curselection()
        effect_sel = self.effects_list.curselection()

        if not (item_sel and effect_sel):
            messagebox.showwarning("Warning", "Please select an item and effect")
            return

        item_id = list(self.items_data.keys())[item_sel[0]]
        item = self.items_data[item_id]
        
        effect_text = self.effects_list.get(effect_sel)
        effect_type = effect_text.split(':')[0].strip()
        effect = item['effects'][effect_type]

        dialog = tk.Toplevel(self.root)
        dialog.title("Edit Effect")
        dialog.geometry("300x200")
        dialog.transient(self.root)
        dialog.grab_set()

        value_frame = ttk.Frame(dialog)
        value_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(value_frame, text="Value:").pack(side=tk.LEFT)
        value_var = tk.StringVar(value=str(effect['value']))
        ttk.Entry(value_frame, textvariable=value_var).pack(side=tk.LEFT, padx=5)

        duration_frame = ttk.Frame(dialog)
        duration_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(duration_frame, text="Duration:").pack(side=tk.LEFT)
        duration_var = tk.StringVar(value=effect['duration'])
        ttk.Combobox(duration_frame, textvariable=duration_var,
                    values=["permanent", "temporary", "single-use"]).pack(side=tk.LEFT, padx=5)

        def update_effect():
            try:
                value = float(value_var.get())
            except ValueError:
                messagebox.showerror("Error", "Value must be a number")
                return

            item['effects'][effect_type].update({
                'value': value,
                'duration': duration_var.get()
            })

            self.effects_list.delete(effect_sel)
            self.effects_list.insert(effect_sel, f"{effect_type}: {value} ({duration_var.get()})")
            self.modified.add('items')
            dialog.destroy()

        ttk.Button(dialog, text="Update", command=update_effect).pack(pady=10)

    def remove_item_effect(self):
        item_sel = self.items_listbox.curselection()
        effect_sel = self.effects_list.curselection()

        if not (item_sel and effect_sel):
            messagebox.showwarning("Warning", "Please select an item and effect")
            return

        if not messagebox.askyesno("Confirm", "Remove this effect?"):
            return

        item_id = list(self.items_data.keys())[item_sel[0]]
        item = self.items_data[item_id]
        
        effect_text = self.effects_list.get(effect_sel)
        effect_type = effect_text.split(':')[0].strip()
        
        del item['effects'][effect_type]
        self.effects_list.delete(effect_sel)
        self.modified.add('items')         

    def add_dialogue_option(self):
        if not (selection := self.chars_listbox.curselection()):
            messagebox.showwarning("Warning", "Please select a character first")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Add Dialogue Option")
        dialog.geometry("500x400")
        dialog.transient(self.root)
        dialog.grab_set()

        # Option text
        option_frame = ttk.Frame(dialog)
        option_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(option_frame, text="Option Text:").pack(anchor=tk.W)
        option_var = tk.StringVar()
        ttk.Entry(option_frame, textvariable=option_var).pack(fill=tk.X)

        # Response
        response_frame = ttk.LabelFrame(dialog, text="Response")
        response_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        response_text = self.create_custom_text(response_frame)
        response_text.pack(fill=tk.BOTH, expand=True)

        # Conditions
        conditions_frame = ttk.LabelFrame(dialog, text="Conditions")
        conditions_frame.pack(fill=tk.X, padx=5, pady=5)
        self.dialog_conditions_list = self.create_custom_listbox(conditions_frame, height=3)
        self.dialog_conditions_list.pack(fill=tk.X)

        condition_buttons = ttk.Frame(conditions_frame)
        condition_buttons.pack(fill=tk.X)
        ttk.Button(condition_buttons, text="Add Condition", 
                command=lambda: self.add_dialogue_condition(self.dialog_conditions_list)).pack(side=tk.LEFT, padx=2)
        ttk.Button(condition_buttons, text="Remove Condition",
                command=lambda: self.remove_dialogue_condition(self.dialog_conditions_list)).pack(side=tk.LEFT, padx=2)

        def add():
            if not (option_text := option_var.get().strip()):
                messagebox.showerror("Error", "Option text required")
                return
            if not (response := response_text.get('1.0', tk.END).strip()):
                messagebox.showerror("Error", "Response text required")
                return

            char_id = list(self.characters_data.keys())[selection[0]]
            char = self.characters_data[char_id]
            
            if 'dialogue_options' not in char:
                char['dialogue_options'] = {}

            conditions = {}
            for i in range(self.dialog_conditions_list.size()):
                cond = self.dialog_conditions_list.get(i)
                type, value = cond.split(': ')
                conditions[type] = value

            char['dialogue_options'][option_text] = {
                'response': response,
                'conditions': conditions
            }

            self.dialogue_options_list.insert(tk.END, option_text)
            self.modified.add('characters')
            dialog.destroy()

        ttk.Button(dialog, text="Add Option", command=add).pack(pady=10)

    def edit_dialogue_option(self):
        char_sel = self.chars_listbox.curselection()
        option_sel = self.dialogue_options_list.curselection()

        if not (char_sel and option_sel):
            messagebox.showwarning("Warning", "Please select a character and dialogue option")
            return

        char_id = list(self.characters_data.keys())[char_sel[0]]
        char = self.characters_data[char_id]
        
        option_text = self.dialogue_options_list.get(option_sel)
        option = char['dialogue_options'][option_text]

        dialog = tk.Toplevel(self.root)
        dialog.title("Edit Dialogue Option")
        dialog.geometry("500x400")
        dialog.transient(self.root)
        dialog.grab_set()

        # Option text
        text_frame = ttk.Frame(dialog)
        text_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(text_frame, text="Option Text:").pack(anchor=tk.W)
        text_var = tk.StringVar(value=option_text)
        ttk.Entry(text_frame, textvariable=text_var).pack(fill=tk.X)

        # Response
        response_frame = ttk.LabelFrame(dialog, text="Response")
        response_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        response_text = self.create_custom_text(response_frame)
        response_text.insert('1.0', option['response'])
        response_text.pack(fill=tk.BOTH, expand=True)

        # Conditions
        conditions_frame = ttk.LabelFrame(dialog, text="Conditions")
        conditions_frame.pack(fill=tk.X, padx=5, pady=5)
        conditions_list = self.create_custom_listbox(conditions_frame, height=3)
        conditions_list.pack(fill=tk.X)

        for cond_type, value in option.get('conditions', {}).items():
            conditions_list.insert(tk.END, f"{cond_type}: {value}")

        condition_buttons = ttk.Frame(conditions_frame)
        condition_buttons.pack(fill=tk.X)
        ttk.Button(condition_buttons, text="Add Condition",
                command=lambda: self.add_dialogue_condition(conditions_list)).pack(side=tk.LEFT, padx=2)
        ttk.Button(condition_buttons, text="Remove Condition",
                command=lambda: self.remove_dialogue_condition(conditions_list)).pack(side=tk.LEFT, padx=2)

        def update():
            if not (new_text := text_var.get().strip()):
                messagebox.showerror("Error", "Option text required")
                return
            if not (response := response_text.get('1.0', tk.END).strip()):
                messagebox.showerror("Error", "Response text required")
                return

            # Create new conditions dict
            new_conditions = {}
            for i in range(conditions_list.size()):
                cond = conditions_list.get(i)
                type, value = cond.split(': ')
                new_conditions[type] = value

            # Remove old option if text changed
            if new_text != option_text:
                del char['dialogue_options'][option_text]
                self.dialogue_options_list.delete(option_sel)

            # Add updated option
            char['dialogue_options'][new_text] = {
                'response': response,
                'conditions': new_conditions
            }

            self.dialogue_options_list.insert(option_sel, new_text)
            self.modified.add('characters')
            dialog.destroy()

        ttk.Button(dialog, text="Update", command=update).pack(pady=10)

    def remove_dialogue_option(self):
        char_sel = self.chars_listbox.curselection()
        option_sel = self.dialogue_options_list.curselection()

        if not (char_sel and option_sel):
            messagebox.showwarning("Warning", "Please select a character and dialogue option")
            return

        if not messagebox.askyesno("Confirm", "Remove this dialogue option?"):
            return

        char_id = list(self.characters_data.keys())[char_sel[0]]
        char = self.characters_data[char_id]
        option_text = self.dialogue_options_list.get(option_sel)

        del char['dialogue_options'][option_text]
        self.dialogue_options_list.delete(option_sel)
        self.modified.add('characters')    

    def add_character_stat(self):
        if not (selection := self.chars_listbox.curselection()):
            messagebox.showwarning("Warning", "Please select a character first")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Add Stat")
        dialog.geometry("300x150")
        dialog.transient(self.root)
        dialog.grab_set()

        name_frame = ttk.Frame(dialog)
        name_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(name_frame, text="Name:").pack(side=tk.LEFT)
        name_var = tk.StringVar()
        ttk.Entry(name_frame, textvariable=name_var).pack(side=tk.LEFT, padx=5)

        value_frame = ttk.Frame(dialog)
        value_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(value_frame, text="Value:").pack(side=tk.LEFT)
        value_var = tk.StringVar()
        ttk.Entry(value_frame, textvariable=value_var).pack(side=tk.LEFT, padx=5)

        def add():
            if not (stat_name := name_var.get().strip()):
                messagebox.showerror("Error", "Stat name required")
                return
                
            try:
                value = float(value_var.get())
            except ValueError:
                messagebox.showerror("Error", "Value must be a number")
                return

            char_id = list(self.characters_data.keys())[selection[0]]
            char = self.characters_data[char_id]
            
            if 'stats' not in char:
                char['stats'] = {}

            char['stats'][stat_name] = value
            self.stats_tree.insert('', 'end', text=stat_name, values=(value,))
            self.modified.add('characters')
            dialog.destroy()

        ttk.Button(dialog, text="Add", command=add).pack(pady=10)

    def edit_character_stat(self):
        char_sel = self.chars_listbox.curselection()
        stat_sel = self.stats_tree.selection()

        if not (char_sel and stat_sel):
            messagebox.showwarning("Warning", "Please select a character and stat")
            return

        char_id = list(self.characters_data.keys())[char_sel[0]]
        char = self.characters_data[char_id]
        
        stat_item = self.stats_tree.item(stat_sel[0])
        stat_name = stat_item['text']
        current_value = char['stats'][stat_name]

        dialog = tk.Toplevel(self.root)
        dialog.title("Edit Stat")
        dialog.geometry("250x100")
        dialog.transient(self.root)
        dialog.grab_set()

        value_frame = ttk.Frame(dialog)
        value_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(value_frame, text=f"{stat_name}:").pack(side=tk.LEFT)
        value_var = tk.StringVar(value=str(current_value))
        ttk.Entry(value_frame, textvariable=value_var).pack(side=tk.LEFT, padx=5)

        def update():
            try:
                value = float(value_var.get())
            except ValueError:
                messagebox.showerror("Error", "Value must be a number")
                return

            char['stats'][stat_name] = value
            self.stats_tree.set(stat_sel[0], column='value', value=value)
            self.modified.add('characters')
            dialog.destroy()

        ttk.Button(dialog, text="Update", command=update).pack(pady=10)

    def remove_character_stat(self):
        char_sel = self.chars_listbox.curselection()
        stat_sel = self.stats_tree.selection()

        if not (char_sel and stat_sel):
            messagebox.showwarning("Warning", "Please select a character and stat")
            return

        if not messagebox.askyesno("Confirm", "Remove this stat?"):
            return

        char_id = list(self.characters_data.keys())[char_sel[0]]
        char = self.characters_data[char_id]
        
        stat_item = self.stats_tree.item(stat_sel[0])
        stat_name = stat_item['text']
        
        del char['stats'][stat_name]
        self.stats_tree.delete(stat_sel[0])
        self.modified.add('characters')

    @safe_operation
    def save_current_character(self):
        """Save the currently selected character"""
        if not (selection := self.chars_listbox.curselection()):
            return

        char_id = list(self.characters_data.keys())[selection[0]]
        character = self.characters_data[char_id]

        # Store old data for undo
        old_data = character.copy()
        
        # Update character data
        character.update({
            'name': self.char_name_var.get(),
            'type': self.char_type_var.get(),
            'description': self.char_desc_text.get('1.0', tk.END).strip(),
            'greeting': self.char_greeting_text.get('1.0', tk.END).strip(),
            'movable': self.char_movable_var.get(),
            'follows_player': self.char_follows_var.get()
        })

        self.add_undo_action('modify', 'characters',
                            {'id': char_id, 'data': old_data},
                            {'id': char_id, 'data': character.copy()},
                            f"Modified character {character['name']}")

        self.modified.add('characters')
        self.update_status(f"Saved character {character['name']}")

    @safe_operation
    def delete_current_character(self):
        """Delete the currently selected character"""
        if not (selection := self.chars_listbox.curselection()):
            return

        char_id = list(self.characters_data.keys())[selection[0]]
        character = self.characters_data[char_id]

        if not messagebox.askyesno("Confirm Deletion", 
                                f"Delete character '{character['name']}'?"):
            return

        # Store for undo
        old_data = character.copy()
        
        # Remove character
        del self.characters_data[char_id]
        self.chars_listbox.delete(selection)

        self.add_undo_action('delete', 'characters',
                            {'id': char_id, 'data': old_data},
                            None,
                            f"Deleted character {character['name']}")

        self.modified.add('characters')
        self.update_status(f"Deleted character {character['name']}")

    @safe_operation
    def duplicate_current_character(self):
        """Duplicate the currently selected character"""
        if not (selection := self.chars_listbox.curselection()):
            return

        char_id = list(self.characters_data.keys())[selection[0]]
        original = self.characters_data[char_id]

        # Create new ID
        new_id = f"{char_id}_copy"
        while new_id in self.characters_data:
            new_id += "_copy"

        # Copy character data
        new_char = copy.deepcopy(original)
        new_char['name'] = f"{original['name']} (Copy)"
        self.characters_data[new_id] = new_char

        # Add to list
        self.chars_listbox.insert(tk.END, new_char['name'])

        self.add_undo_action('create', 'characters',
                            None,
                            {'id': new_id, 'data': new_char},
                            f"Duplicated character {original['name']}")

        self.modified.add('characters')
        self.update_status(f"Duplicated character {original['name']}") 

    def add_dialogue_response(self):
        """Add a new response option to the current dialogue"""
        if not self.dialogue_tree.selection():
            messagebox.showwarning("Warning", "Please select a dialogue first")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Add Response")
        dialog.geometry("400x300")
        dialog.transient(self.root)
        dialog.grab_set()

        # Response text
        text_frame = ttk.Frame(dialog)
        text_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(text_frame, text="Response Text:").pack(anchor=tk.W)
        response_text = self.create_custom_text(text_frame, height=4)
        response_text.pack(fill=tk.X)

        # Next dialogue selection
        next_frame = ttk.Frame(dialog)
        next_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(next_frame, text="Next Dialogue:").pack(side=tk.LEFT)
        next_var = tk.StringVar()
        next_combo = ttk.Combobox(next_frame, textvariable=next_var)
        next_combo['values'] = self.get_dialogue_list()
        next_combo.pack(side=tk.LEFT, padx=5)

        # Conditions
        cond_frame = ttk.LabelFrame(dialog, text="Conditions")
        cond_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        conditions_list = self.create_custom_listbox(cond_frame)
        conditions_list.pack(fill=tk.BOTH, expand=True)

        button_frame = ttk.Frame(cond_frame)
        button_frame.pack(fill=tk.X)
        ttk.Button(button_frame, text="Add Condition",
                command=lambda: self.add_dialogue_condition(conditions_list)).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Remove Condition",
                command=lambda: self.remove_dialogue_condition(conditions_list)).pack(side=tk.LEFT, padx=2)

        def add():
            if not (text := response_text.get('1.0', tk.END).strip()):
                messagebox.showerror("Error", "Response text required")
                return

            response_data = {
                'text': text,
                'conditions': self.get_conditions_from_list(conditions_list)
            }

            if next_dialogue := next_var.get():
                response_data['next_dialogue'] = next_dialogue

            self.add_response_to_dialogue(response_data)
            dialog.destroy()

        ttk.Button(dialog, text="Add", command=add).pack(pady=10)

    def add_response_to_dialogue(self, response_data):
        """Add a response to the current dialogue"""
        selected = self.dialogue_tree.selection()[0]
        dialogue_data = self.dialogue_tree.item(selected)
        responses = dialogue_data.get('responses', [])
        responses.append(response_data)
        
        # Update dialogue data
        self.dialogue_tree.item(selected, responses=responses)
        self.response_list.insert(tk.END, response_data['text'])
        self.modified.add('dialogues')

    def edit_dialogue_response(self):
        """Edit selected dialogue response"""
        if not self.dialogue_tree.selection():
            return
        if not (response_sel := self.response_list.curselection()):
            messagebox.showwarning("Warning", "Please select a response to edit")
            return

        dialogue_item = self.dialogue_tree.item(self.dialogue_tree.selection()[0])
        response_data = dialogue_item['responses'][response_sel[0]]

        dialog = tk.Toplevel(self.root)
        dialog.title("Edit Response")
        dialog.geometry("400x300")
        dialog.transient(self.root)
        dialog.grab_set()

        # Response text
        text_frame = ttk.Frame(dialog)
        text_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(text_frame, text="Response Text:").pack(anchor=tk.W)
        response_text = self.create_custom_text(text_frame, height=4)
        response_text.insert('1.0', response_data['text'])
        response_text.pack(fill=tk.X)

        # Next dialogue selection
        next_frame = ttk.Frame(dialog)
        next_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(next_frame, text="Next Dialogue:").pack(side=tk.LEFT)
        next_var = tk.StringVar(value=response_data.get('next_dialogue', ''))
        next_combo = ttk.Combobox(next_frame, textvariable=next_var)
        next_combo['values'] = self.get_dialogue_list()
        next_combo.pack(side=tk.LEFT, padx=5)

        # Conditions
        cond_frame = ttk.LabelFrame(dialog, text="Conditions")
        cond_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        conditions_list = self.create_custom_listbox(cond_frame)
        conditions_list.pack(fill=tk.BOTH, expand=True)

        for cond_type, value in response_data.get('conditions', {}).items():
            conditions_list.insert(tk.END, f"{cond_type}: {value}")

        button_frame = ttk.Frame(cond_frame)
        button_frame.pack(fill=tk.X)
        ttk.Button(button_frame, text="Add Condition",
                command=lambda: self.add_dialogue_condition(conditions_list)).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Remove Condition",
                command=lambda: self.remove_dialogue_condition(conditions_list)).pack(side=tk.LEFT, padx=2)

        def update():
            if not (text := response_text.get('1.0', tk.END).strip()):
                messagebox.showerror("Error", "Response text required")
                return

            response_data.update({
                'text': text,
                'conditions': self.get_conditions_from_list(conditions_list)
            })

            if next_dialogue := next_var.get():
                response_data['next_dialogue'] = next_dialogue
            elif 'next_dialogue' in response_data:
                del response_data['next_dialogue']

            self.response_list.delete(response_sel)
            self.response_list.insert(response_sel, text)
            self.modified.add('dialogues')
            dialog.destroy()

        ttk.Button(dialog, text="Update", command=update).pack(pady=10)

    def remove_dialogue_response(self):
        """Remove selected dialogue response"""
        if not self.dialogue_tree.selection():
            return
        if not (response_sel := self.response_list.curselection()):
            messagebox.showwarning("Warning", "Please select a response to remove")
            return

        if not messagebox.askyesno("Confirm", "Remove this response?"):
            return

        selected = self.dialogue_tree.selection()[0]
        dialogue_data = self.dialogue_tree.item(selected)
        responses = dialogue_data.get('responses', [])
        del responses[response_sel[0]]
        
        # Update dialogue data
        self.dialogue_tree.item(selected, responses=responses)
        self.response_list.delete(response_sel)
        self.modified.add('dialogues')

    def get_dialogue_list(self):
        """Get list of all dialogue IDs"""
        dialogues = []
        def collect_dialogues(item):
            for child in self.dialogue_tree.get_children(item):
                dialogues.append(child)
                collect_dialogues(child)
        collect_dialogues('')
        return dialogues

    def get_conditions_from_list(self, listbox):
        """Convert listbox conditions to dictionary"""
        conditions = {}
        for i in range(listbox.size()):
            cond = listbox.get(i)
            type, value = cond.split(': ')
            conditions[type] = value
        return conditions     

    def on_dialogue_select(self, event=None):
        """Handle dialogue tree selection"""
        if not (selection := self.dialogue_tree.selection()):
            return

        # Get selected dialogue
        dialogue_item = self.dialogue_tree.item(selection[0])
        
        # Update content editor
        self.dialogue_content.delete('1.0', tk.END)
        if content := dialogue_item.get('content'):
            self.dialogue_content.insert('1.0', content)

        # Update response list
        self.response_list.delete(0, tk.END)
        for response in dialogue_item.get('responses', []):
            self.response_list.insert(tk.END, response['text'])

        # Clear current conditions
        self.dialogue_conditions.delete(0, tk.END)
        
        # Add conditions if any exist
        for cond_type, value in dialogue_item.get('conditions', {}).items():
            self.dialogue_conditions.insert(tk.END, f"{cond_type}: {value}")

    def refresh_dialogue_tree(self):
        """Refresh the dialogue tree view"""
        self.dialogue_tree.delete(*self.dialogue_tree.get_children())
        
        for dialogue_id, dialogue in self.dialogue_data.items():
            # Add main dialogue entry
            self.dialogue_tree.insert('', 'end', dialogue_id, text=dialogue.get('name', dialogue_id))
            
            # Add any child dialogues
            if children := dialogue.get('children', []):
                for child in children:
                    self.dialogue_tree.insert(dialogue_id, 'end', child['id'], text=child.get('name', child['id'])) 

    def add_story_text(self):
        """Add a new story text entry"""
        if not (text_key := simpledialog.askstring("Add Story Text", "Enter text key:")):
            return
            
        if text_key in self.story_texts_data:
            messagebox.showerror("Error", "Text key already exists")
            return

        self.story_texts_data[text_key] = {
            "text": "",
            "show_once": False
        }
        self.story_texts_listbox.insert(tk.END, text_key)
        self.modified.add('story_texts')
        
        # Select the new item
        index = self.story_texts_listbox.size() - 1
        self.story_texts_listbox.selection_clear(0, tk.END)
        self.story_texts_listbox.selection_set(index)
        self.story_texts_listbox.see(index)
        self.on_story_text_select()

    def save_story_text(self):
        """Save the currently selected story text"""
        if not (selection := self.story_texts_listbox.curselection()):
            return

        text_key = self.story_texts_listbox.get(selection)
        if not text_key:
            return

        if text_key not in self.story_texts_data:
            self.story_texts_data[text_key] = {}

        old_data = self.story_texts_data[text_key].copy()
        
        self.story_texts_data[text_key].update({
            "text": self.story_text_editor.get('1.0', tk.END).strip(),
            "show_once": self.show_once_var.get()
        })

        self.add_undo_action('modify', 'story_texts',
                            {'id': text_key, 'data': old_data},
                            {'id': text_key, 'data': self.story_texts_data[text_key].copy()},
                            f"Modified story text {text_key}")

        self.modified.add('story_texts')
        self.update_status(f"Saved story text {text_key}")

    def delete_story_text(self):
        """Delete the currently selected story text"""
        if not (selection := self.story_texts_listbox.curselection()):
            return

        text_key = self.story_texts_listbox.get(selection)
        if not messagebox.askyesno("Confirm Delete", f"Delete story text '{text_key}'?"):
            return

        old_data = self.story_texts_data[text_key].copy()
        del self.story_texts_data[text_key]
        self.story_texts_listbox.delete(selection)

        self.add_undo_action('delete', 'story_texts',
                            {'id': text_key, 'data': old_data},
                            None,
                            f"Deleted story text {text_key}")

        self.modified.add('story_texts')
        self.update_status(f"Deleted story text {text_key}")

    def on_story_text_select(self, event=None):
        """Handle story text selection"""
        if not (selection := self.story_texts_listbox.curselection()):
            return

        text_key = self.story_texts_listbox.get(selection)
        if not (text_data := self.story_texts_data.get(text_key)):
            return

        # Update editor
        self.text_key_var.set(text_key)
        self.show_once_var.set(text_data.get('show_once', False))
        
        self.story_text_editor.delete('1.0', tk.END)
        if text := text_data.get('text'):
            self.story_text_editor.insert('1.0', text)     

    def add_ingredient(self):
        """Add an ingredient to the current recipe"""
        if not self.items_data:
            messagebox.showwarning("Warning", "No items available")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Add Ingredient")
        dialog.geometry("300x200")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text="Select Item:").pack(pady=5)
        
        item_list = self.create_custom_listbox(dialog)
        item_list.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        for item_id, item in self.items_data.items():
            item_list.insert(tk.END, f"{item['name']} ({item_id})")

        amount_frame = ttk.Frame(dialog)
        amount_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(amount_frame, text="Amount:").pack(side=tk.LEFT)
        amount_var = tk.StringVar(value="1")
        ttk.Entry(amount_frame, textvariable=amount_var, width=10).pack(side=tk.LEFT, padx=5)

        def add_selected():
            if not (selection := item_list.curselection()):
                messagebox.showerror("Error", "Please select an item")
                return
                
            try:
                amount = int(amount_var.get())
                if amount < 1:
                    raise ValueError()
            except ValueError:
                messagebox.showerror("Error", "Amount must be a positive number")
                return

            item_id = list(self.items_data.keys())[selection[0]]
            item = self.items_data[item_id]
            
            self.ingredients_list.insert(tk.END, f"{item['name']} x{amount} ({item_id})")
            dialog.destroy()

        ttk.Button(dialog, text="Add", command=add_selected).pack(pady=10)

    def edit_ingredient(self):
        """Edit the selected ingredient"""
        if not (selection := self.ingredients_list.curselection()):
            messagebox.showwarning("Warning", "Please select an ingredient to edit")
            return

        ingredient_text = self.ingredients_list.get(selection)
        current_amount = int(re.search(r'x(\d+)', ingredient_text).group(1))
        item_id = re.search(r'\((.*?)\)', ingredient_text).group(1)

        dialog = tk.Toplevel(self.root)
        dialog.title("Edit Ingredient")
        dialog.geometry("250x100")
        dialog.transient(self.root)
        dialog.grab_set()

        amount_frame = ttk.Frame(dialog)
        amount_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(amount_frame, text=f"Amount of {self.items_data[item_id]['name']}:").pack(side=tk.LEFT)
        amount_var = tk.StringVar(value=str(current_amount))
        ttk.Entry(amount_frame, textvariable=amount_var, width=10).pack(side=tk.LEFT, padx=5)

        def update_amount():
            try:
                amount = int(amount_var.get())
                if amount < 1:
                    raise ValueError()
            except ValueError:
                messagebox.showerror("Error", "Amount must be a positive number")
                return

            new_text = f"{self.items_data[item_id]['name']} x{amount} ({item_id})"
            self.ingredients_list.delete(selection)
            self.ingredients_list.insert(selection, new_text)
            dialog.destroy()

        ttk.Button(dialog, text="Update", command=update_amount).pack(pady=10)

    def remove_ingredient(self):
        """Remove the selected ingredient"""
        if not (selection := self.ingredients_list.curselection()):
            messagebox.showwarning("Warning", "Please select an ingredient to remove")
            return

        if messagebox.askyesno("Confirm", "Remove this ingredient?"):
            self.ingredients_list.delete(selection)

    def new_recipe(self):
        """Create a new crafting recipe"""
        self.result_item_var.set('')
        self.ingredients_list.delete(0, tk.END)
        self.recipes_listbox.selection_clear(0, tk.END)

    def save_recipe(self):
        """Save the current recipe"""
        if not (result_item := self.result_item_var.get()):
            messagebox.showerror("Error", "Please select a result item")
            return

        if self.ingredients_list.size() == 0:
            messagebox.showerror("Error", "Please add at least one ingredient")
            return

        ingredients = []
        for i in range(self.ingredients_list.size()):
            ingredient_text = self.ingredients_list.get(i)
            amount = int(re.search(r'x(\d+)', ingredient_text).group(1))
            item_id = re.search(r'\((.*?)\)', ingredient_text).group(1)
            ingredients.append({
                'item_id': item_id,
                'amount': amount
            })

        recipe_data = {
            'result': result_item,
            'ingredients': ingredients
        }

        if selection := self.recipes_listbox.curselection():
            # Update existing recipe
            recipe_index = selection[0]
            old_recipe = self.recipes_data[recipe_index].copy()
            self.recipes_data[recipe_index] = recipe_data
            
            self.add_undo_action('modify', 'recipes',
                                {'index': recipe_index, 'data': old_recipe},
                                {'index': recipe_index, 'data': recipe_data},
                                "Modified recipe")
        else:
            # Add new recipe
            self.recipes_data.append(recipe_data)
            self.recipes_listbox.insert(tk.END, f"{self.items_data[result_item]['name']}")
            
            self.add_undo_action('create', 'recipes',
                                None,
                                {'index': len(self.recipes_data)-1, 'data': recipe_data},
                                "Added new recipe")

        self.modified.add('recipes')
        self.update_status("Saved recipe")

    def delete_recipe(self):
        """Delete the selected recipe"""
        if not (selection := self.recipes_listbox.curselection()):
            messagebox.showwarning("Warning", "Please select a recipe to delete")
            return

        if not messagebox.askyesno("Confirm", "Delete this recipe?"):
            return

        recipe_index = selection[0]
        old_recipe = self.recipes_data[recipe_index]
        del self.recipes_data[recipe_index]
        self.recipes_listbox.delete(selection)

        self.add_undo_action('delete', 'recipes',
                            {'index': recipe_index, 'data': old_recipe},
                            None,
                            "Deleted recipe")

        self.modified.add('recipes')
        self.update_status("Deleted recipe")

    def on_recipe_select(self, event=None):
        """Handle recipe selection"""
        if not (selection := self.recipes_listbox.curselection()):
            return

        recipe = self.recipes_data[selection[0]]
        
        # Update result item
        self.result_item_var.set(recipe['result'])
        
        # Update ingredients list
        self.ingredients_list.delete(0, tk.END)
        for ingredient in recipe['ingredients']:
            item = self.items_data[ingredient['item_id']]
            self.ingredients_list.insert(tk.END, 
                f"{item['name']} x{ingredient['amount']} ({ingredient['item_id']})")   

    def refresh_all_lists(self):
        """Refresh all listboxes"""
        self.refresh_scenes_list()
        self.refresh_items_list()
        self.refresh_characters_list()
        self.refresh_story_texts_list()

    def refresh_scenes_list(self):
        """Refresh scenes listbox"""
        self.scenes_listbox.delete(0, tk.END)
        for scene in self.scenes_data:
            self.scenes_listbox.insert(tk.END, scene['name'])

    def refresh_items_list(self):
        """Refresh items listbox"""
        self.items_listbox.delete(0, tk.END)
        for item_id, item in self.items_data.items():
            self.items_listbox.insert(tk.END, item.get('name', item_id))

    def refresh_characters_list(self):
        """Refresh characters listbox"""
        self.chars_listbox.delete(0, tk.END)
        for char_id, char in self.characters_data.items():
            self.chars_listbox.insert(tk.END, char.get('name', char_id))

    def refresh_story_texts_list(self):
        """Refresh story texts listbox"""
        self.story_texts_listbox.delete(0, tk.END)
        for text_key in self.story_texts_data:
            self.story_texts_listbox.insert(tk.END, text_key)

    def filter_scenes(self):
        """Filter scenes listbox based on search text"""
        search_text = self.search_vars['scene'].get().lower()
        self.scenes_listbox.delete(0, tk.END)
        for scene in self.scenes_data:
            if (search_text in scene['name'].lower() or 
                search_text in scene['id'].lower()):
                self.scenes_listbox.insert(tk.END, scene['name'])

    def filter_items(self):
        """Filter items listbox based on search text"""
        search_text = self.search_vars['item'].get().lower()
        self.items_listbox.delete(0, tk.END)
        for item_id, item in self.items_data.items():
            if (search_text in item_id.lower() or
                search_text in item.get('name', '').lower() or
                search_text in item.get('type', '').lower()):
                self.items_listbox.insert(tk.END, item.get('name', item_id))

    def filter_characters(self):
        """Filter characters listbox based on search text"""
        search_text = self.search_vars['character'].get().lower()
        self.chars_listbox.delete(0, tk.END)
        for char_id, char in self.characters_data.items():
            if (search_text in char_id.lower() or
                search_text in char.get('name', '').lower() or
                search_text in char.get('type', '').lower()):
                self.chars_listbox.insert(tk.END, char.get('name', char_id))

    def reload_data(self):
        """Reload all data from disk"""
        if self.modified:
            if not messagebox.askyesno("Confirm Reload", 
                "You have unsaved changes. Are you sure you want to reload?"):
                return

        self.load_data()
        self.modified.clear()
        self.update_status("Data reloaded from disk")                                                 

    def run(self):
        self.root.mainloop()

def main():
    root = ThemedTk(theme="equilux")
    app = GameDataEditor(root)
    app.run()

if __name__ == "__main__":
    main()