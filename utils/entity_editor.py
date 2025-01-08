import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
from ttkthemes import ThemedTk
import json
import shutil
import os
import re
import sys
sys.path.append('.')
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
from game_map import MapViewer

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

class ThemeManager:
    def __init__(self):
        self.themes = {
            'Dark': {
                'bg': '#1e1e1e',
                'fg': '#ffffff',
                'select_bg': '#404040',
                'select_fg': '#ffffff',
                'input_bg': '#2d2d2d',
                'button_bg': '#3d3d3d',
                'button_active': '#4d4d4d',
                'labelframe_bg': '#2d2d2d',
                'entry_bg': '#2d2d2d',
                'entry_fg': '#ffffff',
                'treeview_bg': '#2d2d2d',
                'treeview_fg': '#ffffff',
                'treeview_selected_bg': '#404040',
                'menu_bg': '#2d2d2d',
                'menu_fg': '#ffffff',
                'dialog_bg': '#1e1e1e',
                'dialog_fg': '#ffffff',
                'toplevel_bg': '#1e1e1e',
                'notebook_bg': '#2d2d2d',
                'tab_bg': '#3d3d3d',
                'tab_selected_bg': '#404040'
            },
            'Light': {
                'bg': '#f0f0f0',
                'fg': '#000000',
                'select_bg': '#0078d7',
                'select_fg': '#ffffff',
                'input_bg': '#ffffff',
                'button_bg': '#e1e1e1',
                'button_active': '#cce4f7',
                'labelframe_bg': '#f0f0f0',
                'entry_bg': '#ffffff',
                'entry_fg': '#000000',
                'treeview_bg': '#ffffff',
                'treeview_fg': '#000000',
                'treeview_selected_bg': '#0078d7',
                'menu_bg': '#f0f0f0',
                'menu_fg': '#000000',
                'dialog_bg': '#f0f0f0',
                'dialog_fg': '#000000',
                'toplevel_bg': '#f0f0f0',
                'notebook_bg': '#f0f0f0',
                'tab_bg': '#e1e1e1',
                'tab_selected_bg': '#ffffff'
            },
            'Mocca': {
                'bg': '#f0f0f0',
                'fg': '#9e9e9e',
                'select_bg': '#0078d7',
                'select_fg': '#ffffff',
                'input_bg': '#2d2d2d',  # Dark input background
                'button_bg': '#e1e1e1',
                'button_active': '#cce4f7',
                'labelframe_bg': '#f0f0f0',
                'entry_bg': '#2d2d2d',  # Dark entry background
                'entry_fg': '#ffffff',   # Light text for dark backgrounds
                'treeview_bg': '#ffffff',
                'treeview_fg': '#000000',
                'treeview_selected_bg': '#0078d7',
                'menu_bg': '#f0f0f0',
                'menu_fg': '#000000',
                'dialog_bg': '#f0f0f0',
                'dialog_fg': '#000000',
                'toplevel_bg': '#f0f0f0',
                'notebook_bg': '#f0f0f0',
                'tab_bg': '#e1e1e1',
                'tab_selected_bg': '#ffffff'
            }
        }
        self.current_theme = 'Dark'

    def apply_theme(self, widget):
        """Apply theme to a single widget"""
        theme = self.themes[self.current_theme]
        
        if isinstance(widget, (tk.Toplevel, tk.Tk)):
            widget.configure(background=theme['bg'])
            self.apply_theme_recursive(widget, theme)
        else:
            self.apply_theme_recursive(widget, theme)

    def apply_theme_recursive(self, widget, theme):
        """Apply theme to widget and all its children recursively"""
        if isinstance(widget, tk.Menu):
            widget.configure(
                background=theme['menu_bg'],
                foreground=theme['menu_fg'],
                activebackground=theme['select_bg'],
                activeforeground=theme['select_fg']
            )
        elif isinstance(widget, tk.Text):
            widget.configure(
                background=theme['input_bg'],
                foreground=theme['fg'],
                selectbackground=theme['select_bg'],
                selectforeground=theme['select_fg']
            )
        elif isinstance(widget, tk.Entry):
            widget.configure(
                background=theme['input_bg'],
                foreground=theme['fg']
            )
        elif isinstance(widget, tk.Listbox):
            widget.configure(
                background=theme['input_bg'],
                foreground=theme['fg'],
                selectbackground=theme['select_bg'],
                selectforeground=theme['select_fg']
            )
        elif isinstance(widget, ttk.Notebook):
            widget.configure(style='TNotebook')
        elif isinstance(widget, ttk.LabelFrame):
            widget.configure(style='TLabelframe')
            # Handle LabelFrame label separately
            for child in widget.winfo_children():
                if str(child).endswith('Label'):
                    child.configure(background=theme['labelframe_bg'],
                                  foreground=theme['fg'])
        elif isinstance(widget, tk.Frame):
            widget.configure(background=theme['bg'])
        elif isinstance(widget, ttk.Frame):
            widget.configure(style='TFrame')

        # Apply theme to all child widgets
        for child in widget.winfo_children():
            self.apply_theme_recursive(child, theme)

    def configure_ttk_styles(self, style, theme):
        """Configure all ttk widget styles"""
        style.configure('TFrame', background=theme['bg'])
        style.configure('TLabel', background=theme['bg'], foreground=theme['fg'])
        style.configure('TButton',
                       background=theme['button_bg'],
                       foreground=theme['fg'])
        style.map('TButton',
                 background=[('active', theme['button_active'])])
        
        style.configure('TEntry',
                       fieldbackground=theme['entry_bg'],
                       foreground=theme['entry_fg'])
        
        style.configure('TNotebook',
                       background=theme['notebook_bg'],
                       borderwidth=0)
        style.configure('TNotebook.Tab',
                       background=theme['tab_bg'],
                       foreground=theme['fg'],
                       padding=[10, 2])
        style.map('TNotebook.Tab',
                 background=[('selected', theme['tab_selected_bg'])],
                 foreground=[('selected', theme['fg'])])
        
        style.configure('TLabelframe',
                       background=theme['labelframe_bg'],
                       foreground=theme['fg'])
        style.configure('TLabelframe.Label',
                       background=theme['labelframe_bg'],
                       foreground=theme['fg'])
        
        style.configure('Treeview',
                       background=theme['treeview_bg'],
                       foreground=theme['treeview_fg'],
                       fieldbackground=theme['treeview_bg'])
        style.map('Treeview',
                 background=[('selected', theme['treeview_selected_bg'])],
                 foreground=[('selected', theme['select_fg'])])

    def apply_theme_to_all(self, root, style):
        """Apply theme to all widgets and configure ttk styles"""
        theme = self.themes[self.current_theme]
        
        # Configure ttk styles
        self.configure_ttk_styles(style, theme)
        
        # Configure root window
        root.configure(background=theme['bg'])
        
        # Apply theme to all existing windows and widgets
        for window in root.winfo_children():
            if isinstance(window, tk.Toplevel):
                window.configure(background=theme['bg'])
                self.apply_theme_recursive(window, theme)
            else:
                self.apply_theme_recursive(window, theme)

    def apply_theme_to_dialog(self, dialog):
        """Apply theme to a dialog window"""
        theme = self.themes[self.current_theme]
        dialog.configure(background=theme['bg'])
        self.apply_theme_recursive(dialog, theme)

    def get_theme_colors(self):
        """Get current theme colors"""
        return self.themes[self.current_theme]
                        
class Settings:
    def __init__(self):
        # Theme settings
        self.theme = 'Dark'
        
        # Font settings
        self.menu_font_size = 10
        self.text_font_size = 12
        self.font_family = "TkDefaultFont"
        
        # Editor preferences
        self.auto_save = False
        self.backup_enabled = True
        self.max_undo_steps = 100
        self.show_line_numbers = True
        self.wrap_text = True
        
        # Window settings
        self.remember_window_size = True
        self.window_size = (1400, 900)
        self.split_positions = {}  # Store pane split positions
        
        # Path settings
        self.last_game_path = 'game_files'
        self.recent_paths = []  # List of recently used game paths
        
    def save(self, filename='editor_settings.json'):
        """Save settings to file"""
        settings_data = {
            'theme': self.theme,
            'menu_font_size': self.menu_font_size,
            'text_font_size': self.text_font_size,
            'font_family': self.font_family,
            'auto_save': self.auto_save,
            'backup_enabled': self.backup_enabled,
            'max_undo_steps': self.max_undo_steps,
            'show_line_numbers': self.show_line_numbers,
            'wrap_text': self.wrap_text,
            'window_size': self.window_size,
            'split_positions': self.split_positions,
            'last_game_path': self.last_game_path,
            'recent_paths': self.recent_paths
        }
        with open(filename, 'w') as f:
            json.dump(settings_data, f, indent=4)
            
    def load(self, filename='editor_settings.json'):
        """Load settings from file"""
        try:
            with open(filename, 'r') as f:
                settings_data = json.load(f)
                self.theme = settings_data.get('theme', 'Dark')
                self.menu_font_size = settings_data.get('menu_font_size', 10)
                self.text_font_size = settings_data.get('text_font_size', 12)
                self.font_family = settings_data.get('font_family', 'TkDefaultFont')
                self.auto_save = settings_data.get('auto_save', False)
                self.backup_enabled = settings_data.get('backup_enabled', True)
                self.max_undo_steps = settings_data.get('max_undo_steps', 100)
                self.show_line_numbers = settings_data.get('show_line_numbers', True)
                self.wrap_text = settings_data.get('wrap_text', True)
                self.window_size = settings_data.get('window_size', (1400, 900))
                self.split_positions = settings_data.get('split_positions', {})
                self.last_game_path = settings_data.get('last_game_path', 'game_files')
                self.recent_paths = settings_data.get('recent_paths', [])
        except (FileNotFoundError, json.JSONDecodeError):
            pass  # Use defaults if file doesn't exist or is invalid

class SettingsDialog:
    def __init__(self, parent, settings, theme_manager, editor):
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Settings")
        self.dialog.geometry("400x500")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        self.settings = settings
        self.theme_manager = theme_manager
        self.parent = parent
        self.editor = editor  # Store reference to editor
        
        # Apply current theme to dialog
        self.theme_manager.apply_theme_to_dialog(self.dialog)
        
        self.create_widgets()

    def create_widgets(self):
        # Theme settings
        theme_frame = ttk.LabelFrame(self.dialog, text="Theme")
        theme_frame.pack(fill=tk.X, padx=10, pady=5)

        self.theme_var = tk.StringVar(value=self.settings.theme)
        for theme in ['Dark', 'Light', 'Mocca']:
            ttk.Radiobutton(theme_frame, text=theme, value=theme,
                           variable=self.theme_var).pack(padx=10, pady=2, anchor=tk.W)

        # Font settings
        font_frame = ttk.LabelFrame(self.dialog, text="Font")
        font_frame.pack(fill=tk.X, padx=10, pady=5)

        # Font family
        ttk.Label(font_frame, text="Font Family:").pack(padx=10, pady=2, anchor=tk.W)
        self.font_var = tk.StringVar(value=self.settings.font_family)
        font_combo = ttk.Combobox(font_frame, textvariable=self.font_var)
        font_combo['values'] = ['TkDefaultFont', 'Courier', 'Helvetica', 'Times']
        font_combo.pack(padx=10, pady=2, fill=tk.X)

        # Menu font size
        ttk.Label(font_frame, text="Menu Font Size:").pack(padx=10, pady=2, anchor=tk.W)
        self.menu_size_var = tk.StringVar(value=str(self.settings.menu_font_size))
        ttk.Entry(font_frame, textvariable=self.menu_size_var).pack(padx=10, pady=2, fill=tk.X)

        # Text font size
        ttk.Label(font_frame, text="Text Font Size:").pack(padx=10, pady=2, anchor=tk.W)
        self.text_size_var = tk.StringVar(value=str(self.settings.text_font_size))
        ttk.Entry(font_frame, textvariable=self.text_size_var).pack(padx=10, pady=2, fill=tk.X)

        # Preview
        preview_frame = ttk.LabelFrame(self.dialog, text="Preview")
        preview_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.preview_text = tk.Text(preview_frame, height=5, width=40)
        self.preview_text.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)
        self.preview_text.insert('1.0', "This is a preview of how your text will look.\n"
                                      "You can see the effects of your font choices here.")

        # Buttons
        button_frame = ttk.Frame(self.dialog)
        button_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Button(button_frame, text="Apply", command=self.apply_settings).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="OK", command=self.save_settings).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=self.dialog.destroy).pack(side=tk.LEFT, padx=5)

        # Bind events for live preview
        self.theme_var.trace('w', self.update_preview)
        self.font_var.trace('w', self.update_preview)
        self.menu_size_var.trace('w', self.update_preview)
        self.text_size_var.trace('w', self.update_preview)

    def update_preview(self, *args):
        try:
            # Update preview text widget
            font_family = self.font_var.get()
            text_size = int(self.text_size_var.get())
            self.preview_text.configure(
                font=(font_family, text_size),
                bg=self.theme_manager.themes[self.theme_var.get()]['input_bg'],
                fg=self.theme_manager.themes[self.theme_var.get()]['fg']
            )
        except ValueError:
            pass  # Ignore invalid font sizes

    def apply_settings(self):
        try:
            # Validate font sizes
            menu_size = int(self.menu_size_var.get())
            text_size = int(self.text_size_var.get())
            if not (6 <= menu_size <= 72 and 6 <= text_size <= 72):
                raise ValueError("Font size must be between 6 and 72")

            # Update settings
            self.settings.theme = self.theme_var.get()
            self.settings.font_family = self.font_var.get()
            self.settings.menu_font_size = menu_size
            self.settings.text_font_size = text_size

            # Apply theme using editor's style reference
            self.theme_manager.current_theme = self.settings.theme
            self.theme_manager.apply_theme_to_all(self.parent, self.editor.style)

            # Create font configurations
            menu_font = (self.settings.font_family, self.settings.menu_font_size)
            text_font = (self.settings.font_family, self.settings.text_font_size)
            
            # Configure ttk styles with new fonts
            style = self.editor.style
            style.configure('TButton', font=menu_font)
            style.configure('TLabel', font=menu_font)
            style.configure('TEntry', font=text_font)
            style.configure('TNotebook.Tab', font=menu_font)
            style.configure('Treeview', font=text_font)
            
            # Update menu fonts
            self.parent.option_add('*Menu.font', menu_font)
            
            # Update all text widgets
            self.apply_fonts_recursive(self.parent, menu_font, text_font)

        except ValueError as e:
            messagebox.showerror("Error", str(e))

    def update_all_fonts(self, font):
        """Update fonts for all text widgets"""
        for widget in self.parent.winfo_children():
            self._update_widget_fonts(widget, font)

    def apply_fonts_recursive(self, widget, menu_font, text_font):
        """Recursively apply fonts to all widgets"""
        try:
            if isinstance(widget, (tk.Text, tk.Entry, ttk.Entry)):
                widget.configure(font=text_font)
            elif isinstance(widget, tk.Menu):
                widget.configure(font=menu_font)
            elif isinstance(widget, (ttk.Button, ttk.Label)):
                widget.configure(font=menu_font)
            elif isinstance(widget, (ttk.Treeview, tk.Listbox)):
                widget.configure(font=text_font)
                
            # Recursively apply to children
            for child in widget.winfo_children():
                self.apply_fonts_recursive(child, menu_font, text_font)
        except tk.TclError:
            pass  # Skip if widget doesn't support font configuration

    def save_settings(self):
        """Save settings and close dialog"""
        self.apply_settings()
        self.dialog.destroy()

class GameDataEditor:
    def __init__(self, root):
        """Initialize the editor"""
        self.root = root
        self.game_path = 'game_files'  # Default path
        
        # Initialize theme and settings first
        self.theme_manager = ThemeManager()
        self.settings = Settings()
        
        # Then do window setup
        self.setup_window()
        
        # Continue with other initializations
        self.initialize_data()
        self.load_config()
        
        # UI setup
        self.setup_ui()
        self.setup_error_handlers()
        self.setup_event_bindings()
        
        # Load game data
        self.initialize_game_path()
        self.load_data()

        self.current_character = None
        self.current_item = None

                # Add selection storage
        self._current_char_selection = None
        self._current_item_selection = None
        self._current_effect_selection = None
        self._current_component_selection = None
        self._current_interaction_selection = None
        self._current_event_selection = None
        self._current_dialogue_selection = None
        self._current_scene_selection = None

    def store_selection(self, listbox, selection_var):
        """Store selection from a listbox"""
        selection = listbox.curselection()
        if selection:
            setattr(self, selection_var, selection[0])

    def restore_selection(self, listbox, selection_var):
        """Restore previous selection in a listbox"""
        selection = getattr(self, selection_var, None)
        if selection is not None:
            listbox.selection_clear(0, tk.END)
            listbox.selection_set(selection)

    def get_current_selection(self, selection_var):
        """Get currently selected item index"""
        return getattr(self, selection_var, None)

    def format_number(self, value):
        """Format number to remove trailing zeros and decimal points"""
        try:
            num = float(value)
            if num.is_integer():
                return int(num)  # Return integer directly, not string
            return num  # Return float directly, not string
        except (ValueError, TypeError):
            return value

    def update_character_stats_display(self, character):
        self.stats_tree.delete(*self.stats_tree.get_children())
        stats = character.get('stats', {})
        for stat_name, value in stats.items():
            formatted_value = self.format_number(value)
            self.stats_tree.insert('', 'end', values=(stat_name, formatted_value))


    def setup_window(self):
        """Setup main window with theme"""
        self.root.title("CLIo Game Data Editor")
        self.root.geometry("1400x900")
        
        # Initialize style
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        # Apply initial theme
        self.theme_manager.apply_theme_to_all(self.root, self.style)

    def initialize_data(self):
        """Initialize all data structures"""
        # UI state variables need to be created before any UI elements
        self.path_var = tk.StringVar()
        self.status_var = tk.StringVar()
        
        # Search variables for each tab
        self.search_vars = {
            'scene': tk.StringVar(),
            'item': tk.StringVar(),
            'character': tk.StringVar()
        }

        # Scene variables
        self.scene_id_var = tk.StringVar()
        self.scene_name_var = tk.StringVar()

        # Item variables
        self.item_id_var = tk.StringVar()
        self.item_name_var = tk.StringVar()
        self.item_type_var = tk.StringVar()
        self.item_usable_var = tk.BooleanVar()
        self.item_equippable_var = tk.BooleanVar()
        self.item_consumable_var = tk.BooleanVar()

        # Character variables
        self.char_id_var = tk.StringVar()
        self.char_name_var = tk.StringVar()
        self.char_type_var = tk.StringVar()
        self.char_movable_var = tk.BooleanVar()
        self.char_follows_var = tk.BooleanVar()
        
        # Story text variables
        self.text_key_var = tk.StringVar()
        self.show_once_var = tk.BooleanVar()

        # Crafting variables
        self.result_item_var = tk.StringVar()

        # Undo/Redo stacks
        self.undo_stack = []
        self.redo_stack = []
        
        # Modification tracking
        self.modified = set()
        
        # Transaction state
        self.in_transaction = False
        self.transaction_backup = None

        # Game data structures
        self.scenes_data = []
        self.items_data = {}
        self.characters_data = {}
        self.story_texts_data = {}
        self.dialogue_data = {}
        self.recipes_data = []

        # Font settings
        self.font_settings = {
            'menu': ('TkDefaultFont', 10),
            'text': ('TkDefaultFont', 12),
            'heading': ('TkDefaultFont', 14, 'bold')
        }

        # Load application settings
        self.load_settings()

        # Initialize the theme manager if not already done
        if not hasattr(self, 'theme_manager'):
            self.theme_manager = ThemeManager()
            
        # Initialize settings if not already done
        if not hasattr(self, 'settings'):
            self.settings = Settings()

    def load_settings(self):
        """Load editor settings"""
        try:
            with open('editor_settings.json', 'r') as f:
                saved_settings = json.load(f)
                self.settings.theme = saved_settings.get('theme', 'Dark')
                self.settings.menu_font_size = saved_settings.get('menu_font_size', 10)
                self.settings.text_font_size = saved_settings.get('text_font_size', 12)
                self.settings.font_family = saved_settings.get('font_family', 'TkDefaultFont')
        except FileNotFoundError:
            pass  # Use defaults

    def save_settings(self):
        """Save editor settings"""
        settings_data = {
            'theme': self.settings.theme,
            'menu_font_size': self.settings.menu_font_size,
            'text_font_size': self.settings.text_font_size,
            'font_family': self.settings.font_family
        }
        with open('editor_settings.json', 'w') as f:
            json.dump(settings_data, f, indent=4)        

    def setup_ui(self):
            """Set up the user interface"""
            # Create main container frame
            main_container = ttk.Frame(self.root)
            main_container.pack(fill=tk.BOTH, expand=True)

            # Create toolbar at the top
            self.create_toolbar(main_container)

            # Create notebook
            self.notebook = ttk.Notebook(main_container)
            self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=(5, 10))

            # Create base frames for each tab
            self.tabs = {
                'scenes': ttk.Frame(self.notebook),
                'items': ttk.Frame(self.notebook),
                'characters': ttk.Frame(self.notebook),
                'dialogues': ttk.Frame(self.notebook),
                'story_texts': ttk.Frame(self.notebook),
                'crafting': ttk.Frame(self.notebook)
            }

            # Add tabs to notebook
            for name, frame in self.tabs.items():
                self.notebook.add(frame, text=name.title())

            # Create tab contents
            self.create_scenes_tab()
            self.create_items_tab()
            self.create_characters_tab()
            self.create_dialogues_tab()
            self.create_story_text_editor()
            self.create_crafting_editor()

            # Create menu
            self.create_menu()

            # Create status bar - must be last to stay at bottom
            self.create_status_bar()
            
    def create_menu(self):
        """Create the application menu"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Select Game Path", command=self.select_game_path)
        file_menu.add_command(label="Save All", command=self.save_all, accelerator="Ctrl+S")
        file_menu.add_command(label="Reload", command=self.reload_data, accelerator="Ctrl+R")
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_close)

        # Edit menu
        edit_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Edit", menu=edit_menu)
        edit_menu.add_command(label="Undo", command=self.undo, accelerator="Ctrl+Z")
        edit_menu.add_command(label="Redo", command=self.redo, accelerator="Ctrl+Y")
        edit_menu.add_separator()
        edit_menu.add_command(label="Find References", command=self.find_references, accelerator="Ctrl+F")

        # Tools menu
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Tools", menu=tools_menu)
        tools_menu.add_command(label="Validate Data", command=self.validate_all_data)
        tools_menu.add_command(label="Export Data", command=lambda: self.export_data("all"))
        tools_menu.add_command(label="Import Data", command=lambda: self.import_data("all"))

        # Settings menu
        settings_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Settings", menu=settings_menu)
        settings_menu.add_command(label="Preferences", command=self.show_settings)

        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="Documentation", command=self.show_documentation)
        help_menu.add_command(label="About", command=self.show_about)

        self.apply_menu_theme(menubar)

    def create_dialog(self, title, size="300x200"):
        """Create a themed dialog window"""
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.geometry(size)
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Apply theme
        self.theme_manager.apply_theme_to_dialog(dialog)
        
        return dialog

    def apply_menu_theme(self, menu):
        """Apply theme to menu and all submenus"""
        theme = self.theme_manager.themes[self.theme_manager.current_theme]
        
        menu.configure(
            bg=theme['menu_bg'],
            fg=theme['menu_fg'],
            activebackground=theme['select_bg'],
            activeforeground=theme['select_fg']
        )
        
        # Apply to all submenus
        for item in menu.winfo_children():
            if isinstance(item, tk.Menu):
                self.apply_menu_theme(item)    

    def show_settings(self):
        """Show settings dialog"""
        # Pass self instead of self.style
        SettingsDialog(self.root, self.settings, self.theme_manager, self)

    def apply_theme_to_dialog(self, dialog):
        """Apply current theme to a dialog window"""
        theme = self.theme_manager.themes[self.theme_manager.current_theme]
        
        dialog.configure(bg=theme['bg'])
        
        # Apply theme to all widgets in the dialog
        for widget in dialog.winfo_children():
            self._apply_theme_to_widget(widget, theme)

    def _apply_theme_to_widget(self, widget, theme):
        """Recursively apply theme to widget and its children"""
        if isinstance(widget, tk.Text):
            widget.configure(
                bg=theme['input_bg'],
                fg=theme['fg'],
                insertbackground=theme['fg'],
                selectbackground=theme['select_bg'],
                selectforeground=theme['select_fg']
            )
        elif isinstance(widget, tk.Entry):
            widget.configure(
                bg=theme['input_bg'],
                fg=theme['fg'],
                insertbackground=theme['fg']
            )
        elif isinstance(widget, tk.Listbox):
            widget.configure(
                bg=theme['input_bg'],
                fg=theme['fg'],
                selectbackground=theme['select_bg'],
                selectforeground=theme['select_fg']
            )
        elif isinstance(widget, ttk.Frame):
            style = ttk.Style()
            style.configure('TFrame', background=theme['bg'])

        # Recursively apply to children
        for child in widget.winfo_children():
            self._apply_theme_to_widget(child, theme)                  

    def show_about(self):
        """Show themed about dialog"""
        dialog = self.create_dialog("About", "400x300")
        
        content = ttk.Frame(dialog)
        content.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        ttk.Label(content, text="CLIo Game Data Editor", 
                font=('TkDefaultFont', 14, 'bold')).pack(pady=10)
        ttk.Label(content, text="Version 1.0").pack()
        ttk.Label(content, text="\nA tool for editing game data files\nfor CLIo text adventure games."
                ).pack(pady=10)
        
        ttk.Button(content, text="OK", command=dialog.destroy).pack(pady=20)

    def show_documentation(self):
        """Show themed documentation dialog"""
        dialog = self.create_dialog("Documentation", "600x400")
        
        content = ttk.Frame(dialog)
        content.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        doc_text = tk.Text(content, wrap=tk.WORD)
        doc_text.pack(fill=tk.BOTH, expand=True)
        
        # Apply theme to text widget
        theme = self.theme_manager.themes[self.theme_manager.current_theme]
        doc_text.configure(
            bg=theme['input_bg'],
            fg=theme['fg'],
            font=(self.settings.font_family, self.settings.text_font_size)
        )
        
        doc_text.insert('1.0', """CLIo Game Data Editor Documentation

    Sections:
    1. Scenes
    - Create and edit game scenes
    - Manage exits, items, and characters

    2. Items
    - Create and manage game items
    - Set item properties and effects

    3. Characters
    - Create and edit NPCs
    - Manage dialogue and stats

    4. Story Texts
    - Manage game text content
    - Set display conditions

    5. Crafting
    - Create crafting recipes
    - Manage ingredients and results

    For more detailed information, please refer to the user manual.""")
        
        doc_text.configure(state='disabled')
        
        ttk.Button(content, text="Close", command=dialog.destroy).pack(pady=10)

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

    def create_toolbar(self, parent):
            """Create toolbar with added game path selection"""
            toolbar = ttk.Frame(parent)
            toolbar.pack(fill=tk.X, padx=5, pady=2)

            # Left-side buttons
            left_buttons = ttk.Frame(toolbar)
            left_buttons.pack(side=tk.LEFT, fill=tk.X)

            ttk.Button(left_buttons, text="Select Game Path", 
                    command=self.select_game_path).pack(side=tk.LEFT, padx=2)
            ttk.Button(left_buttons, text="Save All", 
                    command=self.save_all).pack(side=tk.LEFT, padx=2)
            ttk.Button(left_buttons, text="Reload", 
                    command=self.reload_data).pack(side=tk.LEFT, padx=2)
            ttk.Button(left_buttons, text="Validate", 
                    command=self.validate_all_data).pack(side=tk.LEFT, padx=2)
            ttk.Button(left_buttons, text="Project Map", command=self.show_project_map).pack(side=tk.LEFT, padx=2)

    def create_status_bar(self):
            """Create status bar"""
            status_frame = ttk.Frame(self.root)
            status_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=2)

            # Status messages
            path_label = ttk.Label(status_frame, textvariable=self.path_var, 
                                relief=tk.SUNKEN, anchor=tk.W)
            path_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))

            status_label = ttk.Label(status_frame, textvariable=self.status_var, 
                                    relief=tk.SUNKEN, anchor=tk.W)
            status_label.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(2, 0))
            
    def update_status(self, message=None):
        """Update status bar messages"""
        # Update status message
        if message:
            self.status_var.set(message)
        else:
            modified = len(self.modified)
            self.status_var.set(f"Modified files: {', '.join(self.modified)}" if modified 
                            else "No modifications")

    def show_project_map(self):
        """Show the project map visualization"""
        if not self.scenes_data:
            messagebox.showwarning("Warning", "No scene data available to display")
            return
            
        try:
            # Create map viewer with current theme setting
            is_dark = self.theme_manager.current_theme == 'Dark'
            map_viewer = MapViewer(self.root, self.scenes_data, dark_theme=is_dark)
            
            # Apply current editor theme to map window
            self.theme_manager.apply_theme_to_dialog(map_viewer)
            
            # Position the window relative to main window
            map_viewer.geometry(f"+{self.root.winfo_x() + 50}+{self.root.winfo_y() + 50}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to display map: {str(e)}")

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
        """Handle application closing"""
        if self.modified:
            save = messagebox.askyesnocancel(
                "Save Changes",
                "There are unsaved changes. Save before closing?"
            )
            if save is None:  # Cancel
                return
            if save:
                self.save_all()
        
        # Save settings
        self.save_settings()
        
        self.root.quit()

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
        """Handle scene selection"""
        # Get current selection
        selection = self.scenes_listbox.curselection()
        if selection is None or len(selection) == 0:
            return
            
        # Store the selection
        self._current_scene_selection = selection[0]
        
        # Get the selected scene
        scene = self.scenes_data[selection[0]]
        
        # Update the UI with scene data
        self.scene_id_var.set(scene['id'])
        self.scene_name_var.set(scene['name'])
        self.scene_desc_text.delete('1.0', tk.END)
        self.scene_desc_text.insert('1.0', scene.get('description', ''))
        self.update_scene_contents(scene)

    def on_character_select(self, event=None):
        """Handle character selection"""
        # Get current selection
        selection = self.chars_listbox.curselection()
        if selection is None or len(selection) == 0:
            return
            
        # Store the selection
        self._current_char_selection = selection[0]
        
        # Get the selected character
        char_id = list(self.characters_data.keys())[selection[0]]
        character = self.characters_data[char_id]
        
        # Update UI with character data
        self.char_id_var.set(char_id)
        self.char_name_var.set(character.get('name', ''))
        self.char_type_var.set(character.get('type', 'neutral'))
        
        self.char_desc_text.delete('1.0', tk.END)
        self.char_desc_text.insert('1.0', character.get('description', ''))

        # Update greeting/dialogue
        self.char_greeting_text.delete('1.0', tk.END)
        self.char_greeting_text.insert('1.0', character.get('greeting', ''))

        # Update dialogue options
        self.dialogue_options_list.delete(0, tk.END)
        for option_text in character.get('dialogue_options', {}).keys():
            self.dialogue_options_list.insert(tk.END, option_text)

        # Update stats tree
        self.update_character_stats_display(character)

    def on_item_select(self, event=None):
        """Handle item selection"""
        # Get current selection
        selection = self.items_listbox.curselection()
        if selection is None or len(selection) == 0:
            return
            
        # Store the selection
        self._current_item_selection = selection[0]
        
        # Get the selected item
        item_id = list(self.items_data.keys())[selection[0]]
        item = self.items_data[item_id]
        
        # Update UI with item data
        self.item_id_var.set(item_id)
        self.item_name_var.set(item.get('name', ''))
        self.item_type_var.set(item.get('type', 'Regular'))
        
        # Update flags
        self.item_usable_var.set(item.get('usable', False))
        self.item_equippable_var.set(item.get('equippable', False))
        self.item_consumable_var.set(item.get('consumable', False))
        
        # Update description
        self.item_desc_text.delete('1.0', tk.END)
        self.item_desc_text.insert('1.0', item.get('description', ''))
        
        # Update effects list
        self.effects_list.delete(0, tk.END)
        if 'effects' in item:
            for effect_type, effect_data in item['effects'].items():
                if isinstance(effect_data, dict):
                    value = effect_data.get('value', '')
                    duration = effect_data.get('duration', 'permanent')
                    self.effects_list.insert(tk.END, f"{effect_type}: {value} ({duration})")
                else:
                    self.effects_list.insert(tk.END, f"{effect_type}: {effect_data}")
        
        # Update components list
        self.components_list.delete(0, tk.END)
        for component_id in item.get('components', []):
            if component := self.items_data.get(component_id):
                self.components_list.insert(tk.END, f"{component['name']} ({component_id})")
            else:
                self.components_list.insert(tk.END, f"Unknown item ({component_id})")

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
            paths_checked = self.verify_game_paths()
            if not paths_checked:
                return

            self.load_scenes()
            self.load_items()
            self.load_characters()
            self.load_story_texts()
            self.load_dialogue_data()
            self.refresh_all_lists()
        except Exception as e:
            self.show_error_dialog(f"Error loading data: {str(e)}")

    def verify_game_paths(self):
        """Verify game paths exist or prompt for creation"""
        required_paths = {
            'root': self.game_path,
            'scenes': os.path.join(self.game_path, 'scenes')
        }

        missing = [path for path, full_path in required_paths.items() 
                if not os.path.exists(full_path)]

        if missing:
            if messagebox.askyesno("Create Directories", 
                f"The following directories are missing:\n" + 
                "\n".join(missing) + "\n\nCreate them?"):
                for path in required_paths.values():
                    os.makedirs(path, exist_ok=True)
                return True
            else:
                return False
        return True            

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
        """Load scenes data"""
        file_path = os.path.join(self.game_path, 'scenes', 'scenes.json')
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                self.scenes_data = json.load(f)
        except FileNotFoundError:
            self.scenes_data = []
            self.create_default_scenes()
        except json.JSONDecodeError:
            self.handle_corrupted_file('scenes', file_path)

    def load_items(self):
        """Load items data"""
        file_path = os.path.join(self.game_path, 'items.json')
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                self.items_data = json.load(f)
        except FileNotFoundError:
            self.items_data = {}
            self.create_default_items()
        except json.JSONDecodeError:
            self.handle_corrupted_file('items', file_path)

    def load_characters(self):
        """Load characters data"""
        file_path = os.path.join(self.game_path, 'characters.json')
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                self.characters_data = json.load(f)
        except FileNotFoundError:
            self.characters_data = {}
            self.create_default_characters()
        except json.JSONDecodeError:
            self.handle_corrupted_file('characters', file_path)

    def load_story_texts(self):
        """Load story texts data"""
        file_path = os.path.join(self.game_path, 'story_texts.json')
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                self.story_texts_data = json.load(f)
        except FileNotFoundError:
            self.story_texts_data = {}
        except json.JSONDecodeError:
            self.handle_corrupted_file('story_texts', file_path)

    def handle_corrupted_file(self, data_type, file_path):
        """Handle corrupted JSON files"""
        backup_path = f"{file_path}.corrupted"
        try:
            if os.path.exists(file_path):
                shutil.copy2(file_path, backup_path)
                messagebox.showwarning("Warning", 
                    f"Corrupted {data_type} file found. Backup saved as:\n{backup_path}")
            
            # Create fresh data
            if data_type == 'scenes':
                self.scenes_data = []
                self.create_default_scenes()
            elif data_type == 'items':
                self.items_data = {}
                self.create_default_items()
            elif data_type == 'characters':
                self.characters_data = {}
                self.create_default_characters()
            elif data_type == 'story_texts':
                self.story_texts_data = {}
        except Exception as e:
            self.show_error_dialog(f"Error handling corrupted {data_type} file: {str(e)}")            

    def save_all(self):
        """Save all modified data"""
        if not self.modified:
            return

        try:
            self.create_backup()
            
            for data_type in self.modified:
                self.save_data_type(data_type)

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

    def save_data_type(self, data_type):
        """Save specific data type"""
        file_path = self.get_file_path(data_type)
        if not file_path:
            return

        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        try:
            data = getattr(self, f"{data_type}_data")
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            raise Exception(f"Failed to save {data_type}: {str(e)}")

    def create_backup(self):
        """Create backup of current data files"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_dir = os.path.join(self.game_path, 'backups', timestamp)
        os.makedirs(backup_dir, exist_ok=True)

        for data_type in self.modified:
            file_path = self.get_file_path(data_type)
            if file_path and os.path.exists(file_path):
                backup_path = os.path.join(backup_dir, os.path.basename(file_path))
                shutil.copy2(file_path, backup_path)

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
        """Create the scenes tab"""
        # Add buttons frame at the top
        buttons_frame = ttk.Frame(self.tabs['scenes'])
        buttons_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(buttons_frame, text="Add Scene", command=self.add_scene).pack(side=tk.LEFT, padx=2)

        # Create the main layout
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
        
        # Grid layout for properties
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
            """Create the items tab"""
            # Add buttons frame at the top
            buttons_frame = ttk.Frame(self.tabs['items'])
            buttons_frame.pack(fill=tk.X, padx=5, pady=5)
            ttk.Button(buttons_frame, text="Add Item", command=self.add_new_item).pack(side=tk.LEFT, padx=2)

            # Create the main layout
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

            # Grid layout for properties
            grid_items = [
                ("ID:", self.item_id_var, 'readonly'),
                ("Name:", self.item_name_var, 'normal'),
                ("Type:", self.item_type_var, ["Regular", "Quest", "Key", "Tool", "Weapon", "Consumable"])
            ]

            for i, (label, var, state_or_values) in enumerate(grid_items):
                ttk.Label(props_frame, text=label).grid(row=i, column=0, padx=5, pady=2)
                if isinstance(state_or_values, list):
                    ttk.Combobox(props_frame, textvariable=var, values=state_or_values).grid(
                        row=i, column=1, padx=5, pady=2, sticky='ew')
                else:
                    ttk.Entry(props_frame, textvariable=var, state=state_or_values).grid(
                        row=i, column=1, padx=5, pady=2, sticky='ew')

            props_frame.columnconfigure(1, weight=1)  # Make second column expandable

            # Checkboxes Frame
            checks_frame = ttk.Frame(props_frame)
            checks_frame.grid(row=len(grid_items), column=0, columnspan=2, padx=5, pady=2)

            self.item_usable_var = tk.BooleanVar()
            self.item_equippable_var = tk.BooleanVar()
            self.item_consumable_var = tk.BooleanVar()

            for text, var in [
                ("Usable", self.item_usable_var),
                ("Equippable", self.item_equippable_var),
                ("Consumable", self.item_consumable_var)
            ]:
                ttk.Checkbutton(checks_frame, text=text, variable=var).pack(side=tk.LEFT, padx=5)

            # Description Frame
            desc_frame = ttk.LabelFrame(editor_frame, text="Description")
            desc_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            self.item_desc_text = self.create_custom_text(desc_frame, height=5)
            self.item_desc_text.pack(fill=tk.BOTH, expand=True)

            # Effects Frame
            effects_frame = ttk.LabelFrame(editor_frame, text="Effects")
            effects_frame.pack(fill=tk.X, padx=5, pady=5)
            self.effects_list = self.create_custom_listbox(effects_frame, height=4)
            self.effects_list.pack(fill=tk.X)

            effect_buttons = ttk.Frame(effects_frame)
            effect_buttons.pack(fill=tk.X)
            for text, command in [
                ("Add Effect", self.add_item_effect),
                ("Edit Effect", self.edit_item_effect),
                ("Remove Effect", self.remove_item_effect)
            ]:
                ttk.Button(effect_buttons, text=text, command=command).pack(side=tk.LEFT, padx=2)

            # Components Frame
            components_frame = ttk.LabelFrame(editor_frame, text="Craftable Components")
            components_frame.pack(fill=tk.X, padx=5, pady=5)
            self.components_list = self.create_custom_listbox(components_frame, height=4)
            self.components_list.pack(fill=tk.X)

            component_buttons = ttk.Frame(components_frame)
            component_buttons.pack(fill=tk.X)
            for text, command in [
                ("Add Component", self.add_item_component),
                ("Remove Component", self.remove_item_component)
            ]:
                ttk.Button(component_buttons, text=text, command=command).pack(side=tk.LEFT, padx=2)

            # Save/Delete/Duplicate buttons
            button_frame = ttk.Frame(editor_frame)
            button_frame.pack(fill=tk.X, padx=5, pady=5)
            for text, command in [
                ("Save Item", self.save_current_item),
                ("Delete Item", self.delete_current_item),
                ("Duplicate Item", self.duplicate_current_item)
            ]:
                ttk.Button(button_frame, text=text, command=command).pack(side=tk.LEFT, padx=2)

            # Bindings
            self.items_listbox.bind('<<ListboxSelect>>', self.on_item_select)
            self.effects_list.bind('<Double-Button-1>', lambda e: self.edit_item_effect())

    def create_characters_tab(self):
        """Create the characters tab"""
        # Add buttons frame at the top
        buttons_frame = ttk.Frame(self.tabs['characters'])
        buttons_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(buttons_frame, text="Add Character", command=self.add_new_character).pack(side=tk.LEFT, padx=2)

        # Create the main layout
        self.chars_listbox, editor_frame = self.create_tab_layout(
            self.tabs['characters'],
            self.search_vars['character'],
            "Search characters..."
        )

        # Create notebook for character sections
        notebook = ttk.Notebook(editor_frame)
        notebook.pack(fill=tk.BOTH, expand=True)

        # Create all character tabs
        self.create_character_basic_info(notebook)
        self.create_character_dialogue(notebook)
        self.create_character_stats(notebook)
        self.create_character_interactions(notebook)
        self.create_character_random_events(notebook)

        # Main buttons
        button_frame = ttk.Frame(editor_frame)
        button_frame.pack(fill=tk.X, padx=5, pady=5)
        for text, command in [
            ("Save Character", self.save_current_character),
            ("Delete Character", self.delete_current_character),
            ("Duplicate Character", self.duplicate_current_character)
        ]:
            ttk.Button(button_frame, text=text, command=command).pack(side=tk.LEFT, padx=2)

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

        # Stats Treeview with two columns
        self.stats_tree = ttk.Treeview(stats_frame, columns=("name", "value"), show="headings")
        self.stats_tree.heading("name", text="Stat Name")
        self.stats_tree.heading("value", text="Value")
        self.stats_tree.column("name", width=150)
        self.stats_tree.column("value", width=100)
        self.stats_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        scrollbar = ttk.Scrollbar(stats_frame, orient=tk.VERTICAL, command=self.stats_tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.stats_tree.configure(yscrollcommand=scrollbar.set)

        button_frame = ttk.Frame(stats_frame)
        button_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(button_frame, text="Add Stat", command=self.add_character_stat).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Edit Stat", command=self.edit_character_stat).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Remove Stat", command=self.remove_character_stat).pack(side=tk.LEFT, padx=2)

        self.stats_tree.bind('<Double-Button-1>', lambda e: self.edit_character_stat())

    def create_character_interactions(self, notebook):
        interactions_frame = ttk.Frame(notebook)
        notebook.add(interactions_frame, text="Item Interactions")

        # Item Interactions Tree
        self.interactions_tree = ttk.Treeview(interactions_frame, columns=("type", "consume", "reward"), show="headings", height=10)
        self.interactions_tree.heading("type", text="Type")
        self.interactions_tree.heading("consume", text="Consumes Item")
        self.interactions_tree.heading("reward", text="Reward/Effect")
        
        self.interactions_tree.column("type", width=100)
        self.interactions_tree.column("consume", width=100)
        self.interactions_tree.column("reward", width=150)
        
        self.interactions_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Buttons frame
        button_frame = ttk.Frame(interactions_frame)
        button_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(button_frame, text="Add Interaction", command=self.add_item_interaction).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Edit Interaction", command=self.edit_item_interaction).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Remove Interaction", command=self.remove_item_interaction).pack(side=tk.LEFT, padx=2)

    def edit_item_interaction(self):
        """Edit selected item interaction"""
        char_sel = self.chars_listbox.curselection()
        interaction_sel = self.interactions_tree.selection()

        if not (char_sel and interaction_sel):
            messagebox.showwarning("Warning", "Please select a character and interaction")
            return

        char_id = list(self.characters_data.keys())[char_sel[0]]
        char = self.characters_data[char_id]
        
        # Get current interaction data
        item_id = self.interactions_tree.item(interaction_sel)['values'][0]
        interaction = char['item_interactions'][item_id]

        dialog = tk.Toplevel(self.root)
        dialog.title("Edit Item Interaction")
        dialog.geometry("500x400")
        dialog.transient(self.root)
        dialog.grab_set()

        # Interaction type
        type_frame = ttk.Frame(dialog)
        type_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(type_frame, text="Type:").pack(side=tk.LEFT)
        type_var = tk.StringVar(value=interaction.get('type', 'replicate'))
        ttk.Combobox(type_frame, textvariable=type_var, 
                    values=["replicate", "information", "analyze", "custom"]).pack(
            side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        # Response text
        resp_frame = ttk.LabelFrame(dialog, text="Response")
        resp_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        response_text = self.create_custom_text(resp_frame)
        response_text.pack(fill=tk.BOTH, expand=True)
        response_text.insert('1.0', interaction.get('response', ''))

        # Options frame
        options_frame = ttk.Frame(dialog)
        options_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Consume item option
        consume_var = tk.BooleanVar(value=interaction.get('consume_item', True))
        ttk.Checkbutton(options_frame, text="Consume Item", variable=consume_var).pack(side=tk.LEFT)

        # Reward/Flag frame
        reward_frame = ttk.LabelFrame(dialog, text="Reward or Story Flag")
        reward_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Reward type
        reward_type_var = tk.StringVar(value="none")
        reward_value_var = tk.StringVar()
        
        if 'reward_item' in interaction:
            reward_type_var.set("item")
            reward_value_var.set(interaction['reward_item'])
        elif 'story_flag' in interaction:
            reward_type_var.set("flag")
            reward_value_var.set(interaction['story_flag'])

        ttk.Radiobutton(reward_frame, text="None", value="none", 
                        variable=reward_type_var).pack(anchor=tk.W)
        ttk.Radiobutton(reward_frame, text="Item", value="item", 
                        variable=reward_type_var).pack(anchor=tk.W)
        ttk.Radiobutton(reward_frame, text="Story Flag", value="flag", 
                        variable=reward_type_var).pack(anchor=tk.W)
        
        ttk.Entry(reward_frame, textvariable=reward_value_var).pack(fill=tk.X, padx=5, pady=2)

        def update():
            response = response_text.get('1.0', tk.END).strip()
            if not response:
                messagebox.showwarning("Warning", "Response text is required")
                return

            updated_interaction = {
                'type': type_var.get(),
                'response': response,
                'consume_item': consume_var.get()
            }

            # Add reward or flag
            reward_type = reward_type_var.get()
            if reward_type == 'item' and reward_value_var.get():
                updated_interaction['reward_item'] = reward_value_var.get()
            elif reward_type == 'flag' and reward_value_var.get():
                updated_interaction['story_flag'] = reward_value_var.get()

            char['item_interactions'][item_id] = updated_interaction
            
            # Update treeview
            reward = updated_interaction.get('reward_item', updated_interaction.get('story_flag', ''))
            self.interactions_tree.item(interaction_sel, values=(
                item_id,
                updated_interaction['type'],
                'Yes' if updated_interaction['consume_item'] else 'No',
                reward
            ))
            
            self.modified.add('characters')
            dialog.destroy()

        ttk.Button(dialog, text="Update", command=update).pack(pady=10)

    def remove_item_interaction(self):
        """Remove selected item interaction"""
        char_sel = self.chars_listbox.curselection()
        interaction_sel = self.interactions_tree.selection()

        if not (char_sel and interaction_sel):
            messagebox.showwarning("Warning", "Please select a character and interaction")
            return

        if not messagebox.askyesno("Confirm", "Remove this item interaction?"):
            return

        char_id = list(self.characters_data.keys())[char_sel[0]]
        char = self.characters_data[char_id]
        
        # Get item ID from tree
        item_id = self.interactions_tree.item(interaction_sel)['values'][0]
        
        # Remove interaction
        del char['item_interactions'][item_id]
        self.interactions_tree.delete(interaction_sel)
        self.modified.add('characters')

    def create_dialogues_tab(self):
        """Create the dialogues tab"""
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

        # Bindings
        self.dialogue_tree.bind('<<TreeviewSelect>>', self.on_dialogue_select)

    def create_story_text_editor(self):
        """Create the story texts tab"""
        listbox, editor_frame = self.create_tab_layout(
            self.tabs['story_texts'],
            tk.StringVar(),  # No search needed
            "Search texts..."
        )
        self.story_texts_listbox = listbox

        # Properties
        props_frame = ttk.LabelFrame(editor_frame, text="Properties")
        props_frame.pack(fill=tk.X, pady=5)
        
        self.text_key_var = tk.StringVar()
        ttk.Label(props_frame, text="Key:").grid(row=0, column=0, padx=5, pady=2)
        ttk.Entry(props_frame, textvariable=self.text_key_var).grid(row=0, column=1, sticky='ew')
        
        self.show_once_var = tk.BooleanVar()
        ttk.Checkbutton(props_frame, text="Show Once", variable=self.show_once_var).grid(
            row=1, column=0, columnspan=2, pady=2)

        # Editor
        self.story_text_editor = self.create_custom_text(editor_frame)
        self.story_text_editor.pack(fill=tk.BOTH, expand=True, pady=5)

        # Controls
        controls = ttk.Frame(editor_frame)
        controls.pack(fill=tk.X)
        for text, command in [
            ("New Text", self.add_story_text),
            ("Save Text", self.save_story_text),
            ("Delete Text", self.delete_story_text)
        ]:
            ttk.Button(controls, text=text, command=command).pack(side=tk.LEFT, padx=2)

        # Bindings
        self.story_texts_listbox.bind('<<ListboxSelect>>', self.on_story_text_select)


    def create_crafting_editor(self):
        """Create the crafting tab"""
        craft_frame = ttk.Frame(self.tabs['crafting'])
        paned = ttk.PanedWindow(craft_frame, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # Recipe list panel
        list_frame = ttk.Frame(paned)
        paned.add(list_frame, weight=1)

        # Add button at top
        button_frame = ttk.Frame(list_frame)
        button_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(button_frame, text="New Recipe", command=self.new_recipe).pack(side=tk.LEFT, padx=2)

        # Recipe list
        list_frame = self.create_tab_layout(
            list_frame,
            tk.StringVar(),
            "Search recipes..."
        )[0]  # We only need the listbox

        # Editor panel
        editor_frame = ttk.Frame(paned)
        paned.add(editor_frame, weight=2)

        # Recipe details
        details_frame = ttk.LabelFrame(editor_frame, text="Recipe Details")
        details_frame.pack(fill=tk.X, pady=5)

        result_frame = ttk.Frame(details_frame)
        result_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(result_frame, text="Result Item:").pack(side=tk.LEFT)
        self.result_item_var = tk.StringVar()
        self.result_combo = ttk.Combobox(result_frame, textvariable=self.result_item_var)
        self.result_combo.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

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
            ("Save Recipe", self.save_recipe),
            ("Delete Recipe", self.delete_recipe)
        ]:
            ttk.Button(recipe_buttons, text=text, command=command).pack(side=tk.LEFT, padx=2)

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

    # Adding scene to the list
    def add_scene(self):
        """Add a new scene with themed dialog"""
        dialog = self.create_dialog("Add New Scene")

        # Scene ID
        id_frame = ttk.Frame(dialog)
        id_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(id_frame, text="Scene ID:").pack(side=tk.LEFT)
        id_var = tk.StringVar()
        ttk.Entry(id_frame, textvariable=id_var).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        # Scene Name
        name_frame = ttk.Frame(dialog)
        name_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(name_frame, text="Scene Name:").pack(side=tk.LEFT)
        name_var = tk.StringVar()
        ttk.Entry(name_frame, textvariable=name_var).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        def create_scene():
            scene_id = id_var.get().strip()
            scene_name = name_var.get().strip()

            if not scene_id or not scene_name:
                messagebox.showerror("Error", "Both ID and name are required")
                return

            if any(s['id'] == scene_id for s in self.scenes_data):
                messagebox.showerror("Error", "Scene ID already exists")
                return

            new_scene = {
                'id': scene_id,
                'name': scene_name,
                'description': '',
                'exits': [],
                'items': [],
                'characters': []
            }

            self.scenes_data.append(new_scene)
            self.scenes_listbox.insert(tk.END, scene_name)
            self.modified.add('scenes')
            dialog.destroy()

            # Select the new scene
            self.scenes_listbox.selection_clear(0, tk.END)
            self.scenes_listbox.selection_set(tk.END)
            self.scenes_listbox.see(tk.END)
            self.on_scene_select()

        button_frame = ttk.Frame(dialog)
        button_frame.pack(fill=tk.X, pady=10)
        ttk.Button(button_frame, text="Create", command=create_scene).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)

    def save_current_item(self):
        """Save the currently selected item"""
        if not (selection := self.items_listbox.curselection()):
            return

        item_id = list(self.items_data.keys())[selection[0]]
        old_item = self.items_data[item_id].copy()
        
        # Update item data
        self.items_data[item_id].update({
            'name': self.item_name_var.get(),
            'type': self.item_type_var.get(),
            'description': self.item_desc_text.get('1.0', tk.END).strip(),
            'usable': self.item_usable_var.get(),
            'equippable': self.item_equippable_var.get(),
            'consumable': self.item_consumable_var.get()
        })

        self.add_undo_action('modify', 'items',
                            {'id': item_id, 'data': old_item},
                            {'id': item_id, 'data': self.items_data[item_id].copy()},
                            f"Modified item {self.items_data[item_id]['name']}")

        self.modified.add('items')
        self.update_status(f"Saved item {self.items_data[item_id]['name']}")

    def delete_current_item(self):
        """Delete the currently selected item"""
        if not (selection := self.items_listbox.curselection()):
            return

        item_id = list(self.items_data.keys())[selection[0]]
        item = self.items_data[item_id]

        if not messagebox.askyesno("Confirm Delete", 
                                f"Delete item '{item['name']}'?"):
            return

        # Store for undo
        old_data = item.copy()
        
        # Check for references before deleting
        references = self.find_item_references(item_id)
        if references:
            if not messagebox.askyesno("Warning",
                f"This item is referenced in the following locations:\n\n" +
                "\n".join(references) + "\n\nDelete anyway?"):
                return

        # Remove item
        del self.items_data[item_id]
        self.items_listbox.delete(selection)

        self.add_undo_action('delete', 'items',
                            {'id': item_id, 'data': old_data},
                            None,
                            f"Deleted item {item['name']}")

        self.modified.add('items')
        self.update_status(f"Deleted item {item['name']}")

    def duplicate_current_item(self):
        """Duplicate the currently selected item"""
        if not (selection := self.items_listbox.curselection()):
            return

        item_id = list(self.items_data.keys())[selection[0]]
        original = self.items_data[item_id]

        # Create new ID
        new_id = f"{item_id}_copy"
        while new_id in self.items_data:
            new_id += "_copy"

        # Copy item data
        new_item = copy.deepcopy(original)
        new_item['name'] = f"{original['name']} (Copy)"
        self.items_data[new_id] = new_item

        # Add to list
        self.items_listbox.insert(tk.END, new_item['name'])

        self.add_undo_action('create', 'items',
                            None,
                            {'id': new_id, 'data': new_item},
                            f"Duplicated item {original['name']}")

        self.modified.add('items')
        self.update_status(f"Duplicated item {original['name']}")

    def find_item_references(self, item_id):
        """Find all references to an item"""
        references = []
        
        # Check scenes
        for scene in self.scenes_data:
            if item_id in scene.get('items', []):
                references.append(f"Scene: {scene['name']}")

        # Check characters
        for char_id, char in self.characters_data.items():
            if item_id in char.get('inventory', []):
                references.append(f"Character: {char['name']} (inventory)")
            if item_id in char.get('crafting_requirements', []):
                references.append(f"Character: {char['name']} (crafting)")

        # Check recipes
        for i, recipe in enumerate(self.recipes_data):
            if recipe.get('result') == item_id:
                references.append(f"Recipe {i+1} (result)")
            if item_id in recipe.get('ingredients', []):
                references.append(f"Recipe {i+1} (ingredient)")

        return references        

    def add_new_item(self):
        """Add a new item"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Add New Item")
        dialog.geometry("400x250")
        dialog.transient(self.root)
        dialog.grab_set()

        # Item ID
        id_frame = ttk.Frame(dialog)
        id_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(id_frame, text="Item ID:").pack(side=tk.LEFT)
        id_var = tk.StringVar()
        ttk.Entry(id_frame, textvariable=id_var).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        # Item Name
        name_frame = ttk.Frame(dialog)
        name_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(name_frame, text="Item Name:").pack(side=tk.LEFT)
        name_var = tk.StringVar()
        ttk.Entry(name_frame, textvariable=name_var).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        # Item Type
        type_frame = ttk.Frame(dialog)
        type_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(type_frame, text="Type:").pack(side=tk.LEFT)
        type_var = tk.StringVar(value="Regular")
        ttk.Combobox(type_frame, textvariable=type_var,
                    values=["Regular", "Quest", "Key", "Tool", "Weapon", "Consumable"]).pack(
            side=tk.LEFT, padx=5)

        def create_item():
            item_id = id_var.get().strip()
            item_name = name_var.get().strip()

            if not item_id or not item_name:
                messagebox.showerror("Error", "Both ID and name are required")
                return

            if item_id in self.items_data:
                messagebox.showerror("Error", "Item ID already exists")
                return

            new_item = {
                'name': item_name,
                'type': type_var.get(),
                'description': '',
                'usable': False,
                'equippable': False,
                'consumable': False,
            }

            self.items_data[item_id] = new_item
            self.items_listbox.insert(tk.END, item_name)
            self.modified.add('items')
            dialog.destroy()

            # Select the new item
            self.items_listbox.selection_clear(0, tk.END)
            self.items_listbox.selection_set(tk.END)
            self.items_listbox.see(tk.END)
            self.on_item_select()

        button_frame = ttk.Frame(dialog)
        button_frame.pack(fill=tk.X, pady=10)
        ttk.Button(button_frame, text="Create", command=create_item).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)

    def add_new_character(self):
        """Add a new character"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Add New Character")
        dialog.geometry("400x250")
        dialog.transient(self.root)
        dialog.grab_set()

        # Character ID
        id_frame = ttk.Frame(dialog)
        id_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(id_frame, text="Character ID:").pack(side=tk.LEFT)
        id_var = tk.StringVar()
        ttk.Entry(id_frame, textvariable=id_var).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        # Character Name
        name_frame = ttk.Frame(dialog)
        name_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(name_frame, text="Character Name:").pack(side=tk.LEFT)
        name_var = tk.StringVar()
        ttk.Entry(name_frame, textvariable=name_var).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        # Character Type
        type_frame = ttk.Frame(dialog)
        type_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(type_frame, text="Type:").pack(side=tk.LEFT)
        type_var = tk.StringVar(value="neutral")
        ttk.Combobox(type_frame, textvariable=type_var,
                    values=["friendly", "hostile", "neutral", "merchant"]).pack(
            side=tk.LEFT, padx=5)

        def create_character():
            char_id = id_var.get().strip()
            char_name = name_var.get().strip()

            if not char_id or not char_name:
                messagebox.showerror("Error", "Both ID and name are required")
                return

            if char_id in self.characters_data:
                messagebox.showerror("Error", "Character ID already exists")
                return

            new_char = {
                'name': char_name,
                'type': type_var.get(),
                'description': '',
                'greeting': '',
                'dialogue_options': {},
                'stats': {}
            }

            self.characters_data[char_id] = new_char
            self.chars_listbox.insert(tk.END, char_name)
            self.modified.add('characters')
            dialog.destroy()

            # Select the new character
            self.chars_listbox.selection_clear(0, tk.END)
            self.chars_listbox.selection_set(tk.END)
            self.chars_listbox.see(tk.END)
            self.on_character_select()

        button_frame = ttk.Frame(dialog)
        button_frame.pack(fill=tk.X, pady=10)
        ttk.Button(button_frame, text="Create", command=create_character).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)        

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
        dialog.geometry("300x250")
        dialog.transient(self.root)
        dialog.grab_set()

        type_frame = ttk.Frame(dialog)
        type_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(type_frame, text="Effect Type:").pack(side=tk.LEFT)
        type_var = tk.StringVar(value="health")
        ttk.Combobox(type_frame, textvariable=type_var, 
                    values=["health", "attack", "defense", "speed", "repair"]).pack(side=tk.LEFT, padx=5)

        value_frame = ttk.Frame(dialog)
        value_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(value_frame, text="Value:").pack(side=tk.LEFT)
        value_var = tk.StringVar()
        ttk.Entry(value_frame, textvariable=value_var).pack(side=tk.LEFT, padx=5)

        duration_frame = ttk.Frame(dialog)
        duration_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(duration_frame, text="Duration:").pack(side=tk.LEFT)
        duration_var = tk.StringVar(value="permanent")
        durations = ["permanent", "temporary", "single-use"]
        ttk.Combobox(duration_frame, textvariable=duration_var, values=durations).pack(side=tk.LEFT, padx=5)

        def add():
            try:
                value = float(value_var.get())
                formatted_value = self.format_number(value)                
                item_id = list(self.items_data.keys())[selection[0]]
                item = self.items_data[item_id]
                
                effect_type = type_var.get()
                duration = duration_var.get()

                if duration == "permanent":
                    if 'effect' not in item:
                        item['effect'] = {}
                    item['effect'][effect_type] = formatted_value
                else:
                    if 'effects' not in item:
                        item['effects'] = {}
                    item['effects'][effect_type] = {
                        'value': formatted_value,
                        'duration': duration
                    }

                effect_text = f"{effect_type}: {self.format_number(formatted_value)}"
                if duration != "permanent":
                    effect_text += f" ({duration})"
                self.effects_list.insert(tk.END, effect_text)
                
                self.modified.add('items')
                dialog.destroy()
            except ValueError:
                messagebox.showerror("Error", "Value must be a number")

        ttk.Button(dialog, text="Add", command=add).pack(pady=10)
                   
    def edit_item_effect(self):        
        item_selection = self.get_current_selection('_current_item_selection')
        if not item_selection:
            messagebox.showwarning("Warning", "Please select an item")
            return
            
        effect_sel = self.effects_list.curselection()
        if not effect_sel:
            messagebox.showwarning("Warning", "Please select an effect")
            return

        item_id = list(self.items_data.keys())[item_selection]
        item = self.items_data[item_id]
        
        effect_text = self.effects_list.get(effect_sel)
        effect_type = effect_text.split(':')[0].strip()

        current_value = 0
        if 'effect' in item and effect_type in item['effect']:
            current_value = item['effect'][effect_type]
        elif 'effects' in item and effect_type in item['effects']:
            current_value = item['effects'][effect_type].get('value', 0)

        dialog = tk.Toplevel(self.root)
        dialog.title(f"Edit {effect_type}")
        dialog.geometry("250x120")
        dialog.transient(self.root)
        dialog.grab_set()

        value_frame = ttk.Frame(dialog)
        value_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(value_frame, text=f"{effect_type}:").pack(side=tk.LEFT)
        value_var = tk.StringVar(value=self.format_number(current_value))
        ttk.Entry(value_frame, textvariable=value_var).pack(side=tk.LEFT, padx=5)

        def update():
            try:
                value = float(value_var.get())
                formatted_value = self.format_number(value)                
                if 'effect' in item and effect_type in item['effect']:
                    item['effect'][effect_type] = formatted_value
                elif 'effects' in item and effect_type in item['effects']:
                    item['effects'][effect_type]['value'] = formatted_value

                effect_text = f"{effect_type}: {self.format_number(formatted_value)}"
                if item.get('effects', {}).get(effect_type, {}).get('duration'):
                    effect_text += f" ({item['effects'][effect_type]['duration']})"
                    
                self.effects_list.delete(effect_sel)
                self.effects_list.insert(effect_sel, effect_text)
                self.modified.add('items')
                dialog.destroy()
                self.restore_selection(self.items_listbox, '_current_item_selection')
            except ValueError:
                messagebox.showerror("Error", "Value must be a number")

        ttk.Button(dialog, text="Update", command=update).pack(pady=10)

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

    def add_item_component(self):
        """Add a component to the current item"""
        if not (selection := self.items_listbox.curselection()):
            messagebox.showwarning("Warning", "Please select an item first")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Add Component")
        dialog.geometry("300x200")
        dialog.transient(self.root)
        dialog.grab_set()

        # Component selection listbox
        ttk.Label(dialog, text="Select Component:").pack(padx=5, pady=2)
        component_list = self.create_custom_listbox(dialog)
        component_list.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Populate with available items
        for item_id, item in self.items_data.items():
            component_list.insert(tk.END, f"{item['name']} ({item_id})")

        def add_selected():
            if not (comp_sel := component_list.curselection()):
                messagebox.showwarning("Warning", "Please select a component")
                return

            item_id = list(self.items_data.keys())[selection[0]]
            item = self.items_data[item_id]
            component_id = list(self.items_data.keys())[comp_sel[0]]
            
            if 'components' not in item:
                item['components'] = []
            
            if component_id not in item['components']:
                item['components'].append(component_id)
                self.components_list.insert(tk.END, 
                    f"{self.items_data[component_id]['name']} ({component_id})")
                self.modified.add('items')
            
            dialog.destroy()

        ttk.Button(dialog, text="Add", command=add_selected).pack(pady=5)

    def remove_item_component(self):
        """Remove selected component from current item"""
        item_sel = self.items_listbox.curselection()
        comp_sel = self.components_list.curselection()

        if not (item_sel and comp_sel):
            messagebox.showwarning("Warning", "Please select an item and component")
            return

        if not messagebox.askyesno("Confirm", "Remove this component?"):
            return

        item_id = list(self.items_data.keys())[item_sel[0]]
        item = self.items_data[item_id]
        component_index = comp_sel[0]

        if 'components' in item and component_index < len(item['components']):
            del item['components'][component_index]
            self.components_list.delete(comp_sel)
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
        ttk.Label(name_frame, text="Stat Name:").pack(side=tk.LEFT)
        name_var = tk.StringVar()
        ttk.Entry(name_frame, textvariable=name_var).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        value_frame = ttk.Frame(dialog)
        value_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(value_frame, text="Value:").pack(side=tk.LEFT)
        value_var = tk.StringVar()
        ttk.Entry(value_frame, textvariable=value_var).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        def add():
            try:
                stat_name = name_var.get().strip()
                if not stat_name:
                    raise ValueError("Stat name is required")
                value = float(value_var.get())
                formatted_value = self.format_number(value)
                char_id = list(self.characters_data.keys())[selection[0]]
                char = self.characters_data[char_id]
                
                if 'stats' not in char:
                    char['stats'] = {}

                char['stats'][stat_name] = formatted_value
                self.stats_tree.insert('', 'end', text=stat_name, values=(stat_name, self.format_number(formatted_value)))
                self.modified.add('characters')
                dialog.destroy()
            except ValueError as e:
                messagebox.showerror("Error", str(e))

        ttk.Button(dialog, text="Add", command=add).pack(pady=10)
   
    def edit_character_stat(self):
        char_selection = self.get_current_selection('_current_char_selection')
        if not char_selection:
            messagebox.showwarning("Warning", "Please select a character")
            return
            
        stat_sel = self.stats_tree.selection()
        if not stat_sel:
            messagebox.showwarning("Warning", "Please select a stat")
            return

        char_id = list(self.characters_data.keys())[char_selection]
        char = self.characters_data[char_id]
        
        stat_item = self.stats_tree.item(stat_sel[0])
        stat_name = stat_item['text']
        current_value = char['stats'][stat_name]

        dialog = tk.Toplevel(self.root)
        dialog.title(f"Edit {stat_name}")
        dialog.geometry("250x120")
        dialog.transient(self.root)
        dialog.grab_set()
        
        self.theme_manager.apply_theme_to_dialog(dialog)

        value_frame = ttk.Frame(dialog)
        value_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(value_frame, text=f"{stat_name}:").pack(side=tk.LEFT)
        value_var = tk.StringVar(value=self.format_number(current_value))
        ttk.Entry(value_frame, textvariable=value_var).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        def update():
            try:
                value = float(value_var.get())
                formatted_value = self.format_number(value)
                char['stats'][stat_name] = formatted_value
                self.stats_tree.set(stat_sel[0], "value", self.format_number(formatted_value))
                self.modified.add('characters')
                dialog.destroy()
                
                self.restore_selection(self.chars_listbox, '_current_char_selection')
            except ValueError:
                messagebox.showerror("Error", "Value must be a number")

        button_frame = ttk.Frame(dialog)
        button_frame.pack(fill=tk.X, pady=10, padx=5)
        ttk.Button(button_frame, text="Update", command=update).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=2)

        dialog.geometry("+%d+%d" % (self.root.winfo_rootx() + 50, self.root.winfo_rooty() + 50))

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
        # Select first item if list not empty
        if self.scenes_listbox.size() > 0:
            self.scenes_listbox.selection_set(0)
            self.on_scene_select()         

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

    def update_scene_contents(self, scene):
        """Update the scene contents lists (items and characters)"""
        # Update items list
        self.scene_items_list.delete(0, tk.END)
        for item_id in scene.get('items', []):
            if item := self.items_data.get(item_id):
                self.scene_items_list.insert(tk.END, f"{item.get('name', item_id)}")
            else:
                self.scene_items_list.insert(tk.END, f"Unknown item: {item_id}")

        # Update characters list
        self.scene_chars_list.delete(0, tk.END)
        for char_id in scene.get('characters', []):
            if char := self.characters_data.get(char_id):
                self.scene_chars_list.insert(tk.END, f"{char.get('name', char_id)}")
            else:
                self.scene_chars_list.insert(tk.END, f"Unknown character: {char_id}")

        # Update exits list
        self.scene_exits_list.delete(0, tk.END)
        for exit in scene.get('exits', []):
            if target_scene := next((s for s in self.scenes_data if s['id'] == exit['scene_id']), None):
                self.scene_exits_list.insert(tk.END, f"{exit['door_name']} → {target_scene['name']}")
            else:
                self.scene_exits_list.insert(tk.END, f"{exit['door_name']} → Unknown ({exit['scene_id']})")

    def update_scene_contents(self, scene):
        """Update the scene contents lists (items and characters)"""
        # Update items list
        self.scene_items_list.delete(0, tk.END)
        for item_id in scene.get('items', []):
            if item := self.items_data.get(item_id):
                self.scene_items_list.insert(tk.END, f"{item.get('name', item_id)}")
            else:
                self.scene_items_list.insert(tk.END, f"Unknown item: {item_id}")

        # Update characters list
        self.scene_chars_list.delete(0, tk.END)
        for char_id in scene.get('characters', []):
            if char := self.characters_data.get(char_id):
                self.scene_chars_list.insert(tk.END, f"{char.get('name', char_id)}")
            else:
                self.scene_chars_list.insert(tk.END, f"Unknown character: {char_id}")

        # Update exits list
        self.scene_exits_list.delete(0, tk.END)
        for exit in scene.get('exits', []):
            if target_scene := next((s for s in self.scenes_data if s['id'] == exit['scene_id']), None):
                self.scene_exits_list.insert(tk.END, f"{exit['door_name']} → {target_scene['name']}")
            else:
                self.scene_exits_list.insert(tk.END, f"{exit['door_name']} → Unknown ({exit['scene_id']})")     

    def update_item_editor(self, item_id, item):
            """Update item editor fields with item data"""
            # Update basic properties
            self.item_id_var.set(item_id)
            self.item_name_var.set(item.get('name', ''))
            self.item_type_var.set(item.get('type', 'Regular'))

            # Update flags
            self.item_usable_var.set(item.get('usable', False))
            self.item_equippable_var.set(item.get('equippable', False))
            self.item_consumable_var.set(item.get('consumable', False))

            # Update description
            self.item_desc_text.delete('1.0', tk.END)
            self.item_desc_text.insert('1.0', item.get('description', ''))

            # Update effects list
            self.effects_list.delete(0, tk.END)
            
            # Handle direct effects
            if effect := item.get('effect'):
                for effect_type, value in effect.items():
                    self.effects_list.insert(tk.END, f"{effect_type}: {value}")
            
            # Handle compound effects
            if effects := item.get('effects'):
                for effect_type, effect_data in effects.items():
                    if isinstance(effect_data, dict):
                        value = effect_data.get('value', '')
                        duration = effect_data.get('duration', 'permanent')
                        self.effects_list.insert(tk.END, f"{effect_type}: {value} ({duration})")
                    else:
                        self.effects_list.insert(tk.END, f"{effect_type}: {effect_data}")

            # Update components list
            self.components_list.delete(0, tk.END)
            if components := item.get('components', []):
                for component_id in components:
                    if component := self.items_data.get(component_id):
                        self.components_list.insert(tk.END, f"{component['name']} ({component_id})")
                    else:
                        self.components_list.insert(tk.END, f"Unknown item ({component_id})")

    def create_character_random_events(self, notebook):
        """Create the random events tab"""
        events_frame = ttk.Frame(notebook)
        notebook.add(events_frame, text="Random Events")

        # Events Listbox
        self.events_list = self.create_custom_listbox(events_frame)
        self.events_list.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Buttons frame
        button_frame = ttk.Frame(events_frame)
        button_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(button_frame, text="Add Event", command=self.add_random_event).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Edit Event", command=self.edit_random_event).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Remove Event", command=self.remove_random_event).pack(side=tk.LEFT, padx=2)

    def add_random_event(self):
        """Add a new random event"""
        if not (selection := self.chars_listbox.curselection()):
            messagebox.showwarning("Warning", "Please select a character first")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Add Random Event")
        dialog.geometry("400x200")
        dialog.transient(self.root)
        dialog.grab_set()

        # Event text
        ttk.Label(dialog, text="Event Text:").pack(anchor=tk.W, padx=5, pady=2)
        event_text = self.create_custom_text(dialog, height=5)
        event_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        def add():
            text = event_text.get('1.0', tk.END).strip()
            if not text:
                messagebox.showerror("Error", "Event text is required")
                return

            char_id = list(self.characters_data.keys())[selection[0]]
            char = self.characters_data[char_id]
            
            if 'random_events' not in char:
                char['random_events'] = []

            char['random_events'].append(text)
            self.events_list.insert(tk.END, text)
            self.modified.add('characters')
            dialog.destroy()

        ttk.Button(dialog, text="Add", command=add).pack(pady=10)

    def edit_random_event(self):
        """Edit selected random event"""
        char_sel = self.chars_listbox.curselection()
        event_sel = self.events_list.curselection()

        if not (char_sel and event_sel):
            messagebox.showwarning("Warning", "Please select a character and event")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Edit Random Event")
        dialog.geometry("400x200")
        dialog.transient(self.root)
        dialog.grab_set()

        # Event text
        ttk.Label(dialog, text="Event Text:").pack(anchor=tk.W, padx=5, pady=2)
        event_text = self.create_custom_text(dialog, height=5)
        event_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Load current text
        event_text.insert('1.0', self.events_list.get(event_sel))

        def update():
            text = event_text.get('1.0', tk.END).strip()
            if not text:
                messagebox.showerror("Error", "Event text is required")
                return

            char_id = list(self.characters_data.keys())[char_sel[0]]
            char = self.characters_data[char_id]
            event_idx = event_sel[0]
            
            char['random_events'][event_idx] = text
            self.events_list.delete(event_sel)
            self.events_list.insert(event_sel, text)
            self.modified.add('characters')
            dialog.destroy()

        ttk.Button(dialog, text="Update", command=update).pack(pady=10)

    def remove_random_event(self):
        """Remove selected random event"""
        char_sel = self.chars_listbox.curselection()
        event_sel = self.events_list.curselection()

        if not (char_sel and event_sel):
            messagebox.showwarning("Warning", "Please select a character and event")
            return

        if not messagebox.askyesno("Confirm", "Remove this random event?"):
            return

        char_id = list(self.characters_data.keys())[char_sel[0]]
        char = self.characters_data[char_id]
        event_idx = event_sel[0]
        
        del char['random_events'][event_idx]
        self.events_list.delete(event_sel)
        self.modified.add('characters')

    def add_item_interaction(self):
        """Add new item interaction"""
        if not (selection := self.chars_listbox.curselection()):
            messagebox.showwarning("Warning", "Please select a character first")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Add Item Interaction")
        dialog.geometry("500x400")
        dialog.transient(self.root)
        dialog.grab_set()

        # Item selection
        item_frame = ttk.LabelFrame(dialog, text="Select Item")
        item_frame.pack(fill=tk.X, padx=5, pady=5)
        
        item_list = self.create_custom_listbox(item_frame, height=5)
        item_list.pack(fill=tk.X, padx=5, pady=5)
        
        # Populate items list
        for item_id, item in self.items_data.items():
            item_list.insert(tk.END, f"{item['name']} ({item_id})")

        # Interaction type
        type_frame = ttk.Frame(dialog)
        type_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(type_frame, text="Type:").pack(side=tk.LEFT)
        type_var = tk.StringVar(value="replicate")
        ttk.Combobox(type_frame, textvariable=type_var, 
                    values=["replicate", "information", "analyze", "custom"]).pack(
            side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        # Response text
        resp_frame = ttk.LabelFrame(dialog, text="Response")
        resp_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        response_text = self.create_custom_text(resp_frame)
        response_text.pack(fill=tk.BOTH, expand=True)

        # Options frame
        options_frame = ttk.Frame(dialog)
        options_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Consume item option
        consume_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, text="Consume Item", variable=consume_var).pack(side=tk.LEFT)

        # Reward/Flag frame
        reward_frame = ttk.LabelFrame(dialog, text="Reward or Story Flag")
        reward_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Reward type
        reward_type_var = tk.StringVar(value="none")
        ttk.Radiobutton(reward_frame, text="None", value="none", 
                        variable=reward_type_var).pack(anchor=tk.W)
        ttk.Radiobutton(reward_frame, text="Item", value="item", 
                        variable=reward_type_var).pack(anchor=tk.W)
        ttk.Radiobutton(reward_frame, text="Story Flag", value="flag", 
                        variable=reward_type_var).pack(anchor=tk.W)
        
        reward_value_var = tk.StringVar()
        ttk.Entry(reward_frame, textvariable=reward_value_var).pack(fill=tk.X, padx=5, pady=2)

        def add():
            if not (item_sel := item_list.curselection()):
                messagebox.showwarning("Warning", "Please select an item")
                return
                
            response = response_text.get('1.0', tk.END).strip()
            if not response:
                messagebox.showwarning("Warning", "Response text is required")
                return

            # Get selected item ID
            item_text = item_list.get(item_sel)
            item_id = item_text.split('(')[-1].strip(')')

            char_id = list(self.characters_data.keys())[selection[0]]
            char = self.characters_data[char_id]
            
            if 'item_interactions' not in char:
                char['item_interactions'] = {}

            interaction = {
                'type': type_var.get(),
                'response': response,
                'consume_item': consume_var.get()
            }

            # Add reward or flag
            reward_type = reward_type_var.get()
            if reward_type == 'item' and reward_value_var.get():
                interaction['reward_item'] = reward_value_var.get()
            elif reward_type == 'flag' and reward_value_var.get():
                interaction['story_flag'] = reward_value_var.get()

            char['item_interactions'][item_id] = interaction
            
            # Update treeview
            reward = interaction.get('reward_item', interaction.get('story_flag', ''))
            self.interactions_tree.insert('', 'end', values=(
                item_id,
                interaction['type'],
                'Yes' if interaction['consume_item'] else 'No',
                reward
            ))
            
            self.modified.add('characters')
            dialog.destroy()

        ttk.Button(dialog, text="Add", command=add).pack(pady=10)

    def update_character_editor(self, char_id, character):
        """Update character editor fields with character data"""
        # Basic Info
        self.char_id_var.set(char_id)
        self.char_name_var.set(character.get('name', ''))
        self.char_type_var.set(character.get('type', 'neutral'))
        
        self.char_desc_text.delete('1.0', tk.END)
        self.char_desc_text.insert('1.0', character.get('description', ''))

        # Update greeting/dialogue
        self.char_greeting_text.delete('1.0', tk.END)
        self.char_greeting_text.insert('1.0', character.get('greeting', ''))

        # Update dialogue options
        self.dialogue_options_list.delete(0, tk.END)
        for option_text in character.get('dialogue_options', {}).keys():
            self.dialogue_options_list.insert(tk.END, option_text)

        # Update stats - maintain exact names from JSON
        self.stats_tree.delete(*self.stats_tree.get_children())
        stats = character.get('stats', {})
        for stat_name, value in stats.items():
            self.stats_tree.insert('', 'end', text=stat_name, values=(value,))

        # Update random events
        self.events_list.delete(0, tk.END)
        for event in character.get('random_events', []):
            self.events_list.insert(tk.END, event)

        # Update item interactions
        self.interactions_tree.delete(*self.interactions_tree.get_children())
        for item_id, interaction in character.get('item_interactions', {}).items():
            reward = interaction.get('reward_item', '')
            if not reward and 'story_flag' in interaction:
                reward = f"Flag: {interaction['story_flag']}"
                
            self.interactions_tree.insert('', 'end', values=(
                item_id,
                interaction.get('type', ''),
                'Yes' if interaction.get('consume_item') else 'No',
                reward
            ))

        # Game path for loading CLIo games

    def initialize_game_path(self):
        """Initialize or verify game data path"""
        # Check if game path exists
        if not os.path.exists(self.game_path):
            response = messagebox.askyesno(
                "Game Path Not Found",
                f"Game path '{self.game_path}' not found.\nWould you like to create it?"
            )
            if response:
                try:
                    os.makedirs(self.game_path)
                    os.makedirs(os.path.join(self.game_path, 'scenes'))
                    os.makedirs(os.path.join(self.game_path, 'backups'))
                except Exception as e:
                    messagebox.showerror(
                        "Error",
                        f"Failed to create game directories: {str(e)}"
                    )
                    self.select_game_path()
            else:
                self.select_game_path()
        
        # Update status
        self.path_var.set(f"Game Path: {self.game_path}")

    def select_game_path(self):
        """Let user select game data directory"""
        path = filedialog.askdirectory(
            title="Select Game Data Directory",
            mustexist=False
        )
        if path:
            self.game_path = path
            os.makedirs(self.game_path, exist_ok=True)
            os.makedirs(os.path.join(self.game_path, 'scenes'), exist_ok=True)
            self.save_config()

    def save_config(self):
        """Save configuration"""
        config = {
            'game_path': self.game_path
        }
        with open('editor_config.json', 'w') as f:
            json.dump(config, f)

    def load_config(self):
        """Load editor configuration"""
        try:
            config_path = os.path.join(os.path.dirname(__file__), 'editor_config.json')
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    self.game_path = config.get('game_path', 'game_files')
        except Exception as e:
            self.game_path = 'game_files'
            print(f"Failed to load config: {e}")

    def get_file_path(self, file_type):
        """Get full path for a game data file"""
        paths = {
            'scenes': os.path.join(self.game_path, 'scenes', 'scenes.json'),
            'items': os.path.join(self.game_path, 'items.json'),
            'characters': os.path.join(self.game_path, 'characters.json'),
            'story_texts': os.path.join(self.game_path, 'story_texts.json')
        }
        return paths.get(file_type)                                                                            

    def run(self):
        self.root.mainloop()

def main():
    root = ThemedTk(theme="equilux")
    app = GameDataEditor(root)
    app.run()

if __name__ == "__main__":
    main()