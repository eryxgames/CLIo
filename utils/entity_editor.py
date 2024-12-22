import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
from ttkthemes import ThemedTk
import json
import os
import re
from tkinter.scrolledtext import ScrolledText
from pygments import highlight
from pygments.lexers import get_lexer_by_name
from pygments.formatters import HtmlFormatter
from tkhtmlview import HTMLScrolledText

class GameDataEditor:
    def __init__(self, root):
        self.root = root
        self.root.title("CLIo Game Data Editor")
        self.root.configure(bg='#1e1e1e')

        # Apply dark theme
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.configure_dark_theme()

        # Initialize data attributes
        self.scenes_data = []
        self.items_data = {}
        self.characters_data = {}
        self.story_texts_data = {}

        self.notebook = ttk.Notebook(root)
        self.notebook.pack(expand=1, fill="both", padx=10, pady=10)

        # Create tabs
        self.scenes_tab = ttk.Frame(self.notebook)
        self.items_tab = ttk.Frame(self.notebook)
        self.characters_tab = ttk.Frame(self.notebook)
        self.dialogues_tab = ttk.Frame(self.notebook)
        self.story_texts_tab = ttk.Frame(self.notebook)
        self.crafting_tab = ttk.Frame(self.notebook)

        # Add tabs to notebook
        self.notebook.add(self.scenes_tab, text='Scenes')
        self.notebook.add(self.items_tab, text='Items')
        self.notebook.add(self.characters_tab, text='Characters')
        self.notebook.add(self.dialogues_tab, text='Dialogues')
        self.notebook.add(self.story_texts_tab, text='Story Texts')
        self.notebook.add(self.crafting_tab, text='Crafting')

        # Create tabs and their components
        self.create_tabs()

        # Bind events after the listboxes are created
        self.scene_details_text.bind("<<Modified>>", lambda event: self.apply_syntax_highlighting(self.scene_details_text))

        self.load_data()

        # Initialize syntax highlighting variable
        self.syntax_highlighting_var = tk.BooleanVar(value=False)

    def create_tabs(self):
        self.create_scenes_tab()
        self.create_items_tab()
        self.create_characters_tab()
        self.create_dialogues_tab()
        self.create_story_text_editor()
        self.create_crafting_editor()

    def create_story_text_editor(self):
        story_frame = ttk.Frame(self.story_texts_tab)
        story_frame.pack(padx=20, pady=20, fill=tk.BOTH, expand=True)

        # Left side - Text keys list
        list_frame = ttk.Frame(story_frame)
        list_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0,10))

        self.story_texts_listbox = self.create_custom_listbox(list_frame)
        self.story_texts_listbox.pack(side=tk.LEFT, fill=tk.Y)

        # Bind the selection event after creating the listbox
        self.story_texts_listbox.bind('<<ListboxSelect>>', self.on_story_text_select)

        # Right side - Text editor
        editor_frame = ttk.Frame(story_frame)
        editor_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # Text content
        self.story_text_editor = self.create_custom_text(editor_frame)
        self.story_text_editor.pack(fill=tk.BOTH, expand=True)

        # Control buttons
        button_frame = ttk.Frame(editor_frame)
        button_frame.pack(fill=tk.X, pady=10)

        ttk.Button(button_frame, text="New Text",
                   command=self.add_story_text).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Save Text",
                   command=self.save_story_text).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Delete Text",
                   command=self.delete_story_text).pack(side=tk.LEFT, padx=5)

        # Search functionality
        search_var = tk.StringVar()
        search_entry = ttk.Entry(button_frame, textvariable=search_var)
        search_entry.pack(side=tk.LEFT, padx=5)

        def on_search():
            search_term = search_var.get().lower()
            self.story_texts_listbox.selection_clear(0, tk.END)
            for i in range(self.story_texts_listbox.size()):
                item = self.story_texts_listbox.get(i)
                if search_term in item.lower():
                    self.story_texts_listbox.selection_set(i)
                    self.story_texts_listbox.see(i)

        search_button = ttk.Button(button_frame, text="Search", command=on_search)
        search_button.pack(side=tk.LEFT, padx=5)

    def on_story_text_select(self, event):
        if not hasattr(self, 'story_texts_listbox') or not hasattr(self, 'story_text_editor'):
            return
        selected_index = self.story_texts_listbox.curselection()
        if not selected_index:
            return
        text_key = self.story_texts_listbox.get(selected_index)
        text_data = self.story_texts_data.get(text_key, {})
        text_content = text_data.get("text", "")
        self.story_text_editor.delete(1.0, tk.END)
        self.story_text_editor.insert(tk.END, text_content)

    def toggle_light_mode(self):
        if self.light_mode.get():
            self.style.theme_use('clam')
        else:
            self.style.theme_use('equilux')

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

        self.style.configure('TFrame', background=colors['bg'])
        self.style.configure('TLabel', background=colors['bg'], foreground=colors['fg'])
        self.style.configure('TButton',
                           background=colors['button_bg'],
                           foreground=colors['fg'],
                           borderwidth=1,
                           focusthickness=3,
                           focuscolor='none')
        self.style.map('TButton',
                      background=[('active', colors['button_active'])])
        self.style.configure('TNotebook',
                           background=colors['bg'],
                           borderwidth=0)
        self.style.configure('TNotebook.Tab',
                           background=colors['button_bg'],
                           foreground=colors['fg'],
                           padding=[10, 2],
                           borderwidth=1)
        self.style.map('TNotebook.Tab',
                      background=[('selected', colors['select_bg'])],
                      foreground=[('selected', colors['select_fg'])])

        return colors

    def create_custom_listbox(self, parent, height=20, width=40):
        listbox = tk.Listbox(parent,
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

    def create_item_form(self):
        form_window = tk.Toplevel(self.root)
        form_window.title("Create/Edit Item")
        form_window.configure(bg='#1e1e1e')

        form_frame = ttk.Frame(form_window)
        form_frame.pack(padx=20, pady=20)

        # Create form fields
        fields = [
            ("Name", "name"),
            ("Description", "description"),
            ("Type", "type", ["Story", "Quest", "Usable", "Craftable"]),
            ("Usable", "usable", ["True", "False"]),
            ("Readable Text", "readable_item"),
            ("Use Effect", "use_effect"),
            ("Crafting Requirements", "crafting_requirements"),
        ]

        entries = {}
        for field in fields:
            label = ttk.Label(form_frame, text=field[0])
            label.pack(anchor=tk.W, pady=(10,0))

            if len(field) > 2 and isinstance(field[2], list):
                var = tk.StringVar()
                entry = ttk.Combobox(form_frame, textvariable=var, values=field[2])
                entry.set(field[2][0])
            else:
                if field[0] == "Description" or field[0] == "Readable Text":
                    entry = self.create_custom_text(form_frame, height=5, width=40)
                else:
                    entry = ttk.Entry(form_frame, width=40)

            entry.pack(fill=tk.X, pady=(0,5))
            entries[field[1]] = entry

        return form_window, entries

    def create_character_dialogue_editor(self, character_id):
        dialogue_window = tk.Toplevel(self.root)
        dialogue_window.title(f"Edit Dialogues - {character_id}")
        dialogue_window.configure(bg='#1e1e1e')

        main_frame = ttk.Frame(dialogue_window)
        main_frame.pack(padx=20, pady=20, fill=tk.BOTH, expand=True)

        # Left side - Dialog list
        list_frame = ttk.Frame(main_frame)
        list_frame.pack(side=tk.LEFT, fill=tk.BOTH, padx=(0,10))

        dialogue_list = self.create_custom_listbox(list_frame)
        dialogue_list.pack(side=tk.LEFT, fill=tk.BOTH)

        # Right side - Dialog editor
        editor_frame = ttk.Frame(main_frame)
        editor_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # Dialog content
        content_label = ttk.Label(editor_frame, text="Dialog Content:")
        content_label.pack(anchor=tk.W)

        content_text = self.create_custom_text(editor_frame)
        content_text.pack(fill=tk.BOTH, expand=True)

        # Response options
        responses_frame = ttk.LabelFrame(editor_frame, text="Response Options")
        responses_frame.pack(fill=tk.X, pady=10)

        def add_response():
            response_text = response_entry.get()
            if response_text:
                responses_list.insert(tk.END, response_text)
                response_entry.delete(0, tk.END)

        response_entry = ttk.Entry(responses_frame)
        response_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        add_button = ttk.Button(responses_frame, text="Add Response", command=add_response)
        add_button.pack(side=tk.RIGHT, padx=5)

        responses_list = self.create_custom_listbox(responses_frame, height=5)
        responses_list.pack(fill=tk.X, pady=5)

    def on_story_text_select(self, event):
        selected_index = self.story_texts_listbox.curselection()
        if not selected_index:
            return
        text_key = self.story_texts_listbox.get(selected_index)
        text_data = self.story_texts_data.get(text_key, {})
        text_content = text_data.get("text", "")
        self.story_text_editor.delete(1.0, tk.END)
        self.story_text_editor.insert(tk.END, text_content)


        def on_search():
            search_term = search_var.get().lower()
            self.story_texts_listbox.selection_clear(0, tk.END)
            for i in range(self.story_texts_listbox.size()):
                item = self.story_texts_listbox.get(i)
                if search_term in item.lower():
                    self.story_texts_listbox.selection_set(i)
                    self.story_texts_listbox.see(i)

        search_button = ttk.Button(button_frame, text="Search", command=on_search)
        search_button.pack(side=tk.LEFT, padx=5)

    def create_crafting_editor(self):
        crafting_frame = ttk.Frame(self.crafting_tab)
        crafting_frame.pack(padx=20, pady=20, fill=tk.BOTH, expand=True)

        # Left side - Recipes list
        list_frame = ttk.Frame(crafting_frame)
        list_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0,10))

        self.recipes_listbox = self.create_custom_listbox(list_frame)
        self.recipes_listbox.pack(side=tk.LEFT, fill=tk.Y)

        # Right side - Recipe editor
        editor_frame = ttk.Frame(crafting_frame)
        editor_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # Recipe details
        details_frame = ttk.LabelFrame(editor_frame, text="Recipe Details")
        details_frame.pack(fill=tk.X, pady=10)

        ttk.Label(details_frame, text="Result Item:").grid(row=0, column=0, padx=5, pady=5)
        self.result_item_entry = ttk.Entry(details_frame)
        self.result_item_entry.grid(row=0, column=1, padx=5, pady=5)

        # Ingredients list
        ingredients_frame = ttk.LabelFrame(editor_frame, text="Ingredients")
        ingredients_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        self.ingredients_list = self.create_custom_listbox(ingredients_frame, height=10)
        self.ingredients_list.pack(fill=tk.BOTH, expand=True)

        # Control buttons
        button_frame = ttk.Frame(editor_frame)
        button_frame.pack(fill=tk.X, pady=10)

        ttk.Button(button_frame, text="Add Ingredient",
                  command=self.add_ingredient).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Remove Ingredient",
                  command=self.remove_ingredient).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Save Recipe",
                  command=self.save_recipe).pack(side=tk.LEFT, padx=5)

    def create_preview_window(self, title="Preview", width=1000, height=800):
        preview_window = tk.Toplevel(self.root)
        preview_window.title(title)
        preview_window.configure(bg='#1e1e1e')

        # Make the window resizable
        preview_window.geometry(f"{width}x{height}")
        preview_window.minsize(800, 600)

        # Create canvas with scrollbars
        canvas_frame = ttk.Frame(preview_window)
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        canvas = tk.Canvas(canvas_frame,
                         bg='#e0e0e0',  # Light grey background for better visibility
                         highlightthickness=0)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        v_scrollbar = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=canvas.yview)
        v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        h_scrollbar = ttk.Scrollbar(preview_window, orient=tk.HORIZONTAL, command=canvas.xview)
        h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)

        canvas.configure(xscrollcommand=h_scrollbar.set, yscrollcommand=v_scrollbar.set)

        # Add zoom controls
        control_frame = ttk.Frame(preview_window)
        control_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=5)

        ttk.Button(control_frame, text="Zoom In",
                  command=lambda: self.zoom_canvas(canvas, 1.2)).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Zoom Out",
                  command=lambda: self.zoom_canvas(canvas, 0.8)).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Reset Zoom",
                  command=lambda: self.reset_zoom(canvas)).pack(side=tk.LEFT, padx=5)

        # Add light/dark mode toggle
        self.light_mode = tk.BooleanVar(value=False)
        ttk.Checkbutton(control_frame, text="Light Mode", variable=self.light_mode, command=self.toggle_light_mode).pack(side=tk.LEFT, padx=5)

        return canvas

    def zoom_canvas(self, canvas, factor):
        canvas.scale('all', 0, 0, factor, factor)
        canvas.configure(scrollregion=canvas.bbox('all'))

    def reset_zoom(self, canvas):
        # Reset to original scale
        canvas.scale('all', 0, 0, 1.0, 1.0)
        canvas.configure(scrollregion=canvas.bbox('all'))

    def create_scenes_tab(self):
        self.scenes_frame = ttk.Frame(self.scenes_tab)
        self.scenes_frame.pack(padx=10, pady=10)

        self.scenes_listbox = self.create_custom_listbox(self.scenes_frame, height=20, width=40)
        self.scenes_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=1)
        self.scenes_scrollbar = ttk.Scrollbar(self.scenes_frame, orient=tk.VERTICAL, command=self.scenes_listbox.yview)
        self.scenes_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.scenes_listbox.config(yscrollcommand=self.scenes_scrollbar.set)

        self.scenes_listbox.bind("<Double-Button-1>", self.on_scene_double_click)
        self.scenes_listbox.bind("<Button-3>", self.show_context_menu)

        self.scenes_buttons_frame = ttk.Frame(self.scenes_tab)
        self.scenes_buttons_frame.pack(pady=10)

        self.add_scene_button = ttk.Button(self.scenes_buttons_frame, text="Add Scene", command=self.add_scene)
        self.add_scene_button.pack(side=tk.LEFT, padx=5)

        self.edit_scene_button = ttk.Button(self.scenes_buttons_frame, text="Edit Scene", command=self.edit_scene)
        self.edit_scene_button.pack(side=tk.LEFT, padx=5)

        self.delete_scene_button = ttk.Button(self.scenes_buttons_frame, text="Delete Scene", command=self.delete_scene)
        self.delete_scene_button.pack(side=tk.LEFT, padx=5)

        self.add_item_to_scene_button = ttk.Button(self.scenes_buttons_frame, text="Add Item to Scene", command=self.add_item_to_scene)
        self.add_item_to_scene_button.pack(side=tk.LEFT, padx=5)

        self.add_character_to_scene_button = ttk.Button(self.scenes_buttons_frame, text="Add Character to Scene", command=self.add_character_to_scene)
        self.add_character_to_scene_button.pack(side=tk.LEFT, padx=5)

        self.add_exit_to_scene_button = ttk.Button(self.scenes_buttons_frame, text="Add Exit to Scene", command=self.add_exit_to_scene)
        self.add_exit_to_scene_button.pack(side=tk.LEFT, padx=5)

        self.save_button = ttk.Button(self.scenes_buttons_frame, text="Save Changes", command=self.save_data)
        self.save_button.pack(side=tk.LEFT, padx=5)

        self.scene_details_frame = ttk.Frame(self.scenes_tab)
        self.scene_details_frame.pack(pady=10)

        self.scene_details_label = ttk.Label(self.scene_details_frame, text="Scene Details:")
        self.scene_details_label.pack(anchor=tk.W)

        # Use HTMLScrolledText for syntax highlighting
        self.scene_details_text = HTMLScrolledText(self.scene_details_frame, height=30, width=80)
        self.scene_details_text.pack(fill=tk.BOTH, expand=1)

        self.preview_button = ttk.Button(self.scenes_tab, text="Preview Scene Structure", command=self.preview_scene_structure)
        self.preview_button.pack(pady=10)

        self.preview_map_button = ttk.Button(self.scenes_tab, text="Preview Scene Map", command=self.preview_scene_map)
        self.preview_map_button.pack(pady=10)

        self.settings_button = ttk.Button(self.scenes_buttons_frame, text="Settings", command=self.create_settings_menu)
        self.settings_button.pack(side=tk.LEFT, padx=5)

    def create_items_tab(self):
        self.items_frame = ttk.Frame(self.items_tab)
        self.items_frame.pack(padx=10, pady=10)

        self.items_listbox = self.create_custom_listbox(self.items_frame, height=20, width=40)
        self.items_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=1)
        self.items_scrollbar = ttk.Scrollbar(self.items_frame, orient=tk.VERTICAL, command=self.items_listbox.yview)
        self.items_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.items_listbox.config(yscrollcommand=self.items_scrollbar.set)

        self.items_listbox.bind("<Double-Button-1>", self.on_item_double_click)
        self.items_listbox.bind("<Button-3>", self.show_context_menu)

        self.items_buttons_frame = ttk.Frame(self.items_tab)
        self.items_buttons_frame.pack(pady=10)

        self.add_item_button = ttk.Button(self.items_buttons_frame, text="Add Item", command=self.add_item)
        self.add_item_button.pack(side=tk.LEFT, padx=5)

        self.edit_item_button = ttk.Button(self.items_buttons_frame, text="Edit Item", command=self.edit_item)
        self.edit_item_button.pack(side=tk.LEFT, padx=5)

        self.delete_item_button = ttk.Button(self.items_buttons_frame, text="Delete Item", command=self.delete_item)
        self.delete_item_button.pack(side=tk.LEFT, padx=5)

        self.duplicate_item_button = ttk.Button(self.items_buttons_frame, text="Duplicate Item", command=self.duplicate_item)
        self.duplicate_item_button.pack(side=tk.LEFT, padx=5)

        self.combine_items_button = ttk.Button(self.items_buttons_frame, text="Combine Items", command=self.combine_items)
        self.combine_items_button.pack(side=tk.LEFT, padx=5)

        self.save_button = ttk.Button(self.items_buttons_frame, text="Save Changes", command=self.save_data)
        self.save_button.pack(side=tk.LEFT, padx=5)

        self.item_details_frame = ttk.Frame(self.items_tab)
        self.item_details_frame.pack(pady=10)

        self.item_details_label = ttk.Label(self.item_details_frame, text="Item Details:")
        self.item_details_label.pack(anchor=tk.W)

        self.item_details_text = self.create_custom_text(self.item_details_frame, height=30, width=80)
        self.item_details_text.pack(fill=tk.BOTH, expand=1)

    def create_characters_tab(self):
        self.characters_frame = ttk.Frame(self.characters_tab)
        self.characters_frame.pack(padx=10, pady=10)

        self.characters_listbox = self.create_custom_listbox(self.characters_frame, height=20, width=40)
        self.characters_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=1)
        self.characters_scrollbar = ttk.Scrollbar(self.characters_frame, orient=tk.VERTICAL, command=self.characters_listbox.yview)
        self.characters_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.characters_listbox.config(yscrollcommand=self.characters_scrollbar.set)

        self.characters_listbox.bind("<Double-Button-1>", self.on_character_double_click)
        self.characters_listbox.bind("<Button-3>", self.show_context_menu)

        self.characters_buttons_frame = ttk.Frame(self.characters_tab)
        self.characters_buttons_frame.pack(pady=10)

        self.add_character_button = ttk.Button(self.characters_buttons_frame, text="Add Character", command=self.add_character)
        self.add_character_button.pack(side=tk.LEFT, padx=5)

        self.edit_character_button = ttk.Button(self.characters_buttons_frame, text="Edit Character", command=self.edit_character)
        self.edit_character_button.pack(side=tk.LEFT, padx=5)

        self.delete_character_button = ttk.Button(self.characters_buttons_frame, text="Delete Character", command=self.delete_character)
        self.delete_character_button.pack(side=tk.LEFT, padx=5)

        self.duplicate_character_button = ttk.Button(self.characters_buttons_frame, text="Duplicate Character", command=self.duplicate_character)
        self.duplicate_character_button.pack(side=tk.LEFT, padx=5)

        self.save_button = ttk.Button(self.characters_buttons_frame, text="Save Changes", command=self.save_data)
        self.save_button.pack(side=tk.LEFT, padx=5)

        self.character_details_frame = ttk.Frame(self.characters_tab)
        self.character_details_frame.pack(pady=10)

        self.character_details_label = ttk.Label(self.character_details_frame, text="Character Details:")
        self.character_details_label.pack(anchor=tk.W)

        self.character_details_text = self.create_custom_text(self.character_details_frame, height=30, width=80)
        self.character_details_text.pack(fill=tk.BOTH, expand=1)

    def on_character_select(self, event):
        selected_index = self.characters_listbox.curselection()
        if not selected_index:
            return
        character_id = self.characters_listbox.get(selected_index)
        character_data = self.characters_data.get(character_id, {})
        dialogues = character_data.get("dialogue", {})
        if isinstance(dialogues, str):
            dialogues = json.loads(dialogues)
        dialogue_text = ""
        for key, value in dialogues.items():
            dialogue_text += f"{key}:\n{value.get('text', '')}\n\n"
        self.dialogue_details_text.delete(1.0, tk.END)
        self.dialogue_details_text.insert(tk.END, dialogue_text)

    def create_dialogues_tab(self):
        self.dialogues_frame = ttk.Frame(self.dialogues_tab)
        self.dialogues_frame.pack(padx=10, pady=10)

        # Left side - Characters list
        list_frame = ttk.Frame(self.dialogues_frame)
        list_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0,10))

        self.characters_listbox = self.create_custom_listbox(list_frame)
        self.characters_listbox.pack(side=tk.LEFT, fill=tk.Y)

        # Populate characters listbox
        for character_id in self.characters_data:
            self.characters_listbox.insert(tk.END, character_id)

        # Right side - Dialogues editor
        editor_frame = ttk.Frame(self.dialogues_frame)
        editor_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # Dialogues content
        self.dialogue_details_label = ttk.Label(editor_frame, text="Dialogues:")
        self.dialogue_details_label.pack(anchor=tk.W)

        self.dialogue_details_text = self.create_custom_text(editor_frame)
        self.dialogue_details_text.pack(fill=tk.BOTH, expand=True)

        # Bind selection event
        self.characters_listbox.bind('<<ListboxSelect>>', self.on_character_select)

    def load_data(self):
        try:
            with open('../game_files/scenes/scenes.json', 'r') as f:
                self.scenes_data = json.load(f)
                for index, scene in enumerate(self.scenes_data):
                    self.scenes_listbox.insert(tk.END, scene['name'])
                    self.scenes_listbox.selection_set(index)
        except (FileNotFoundError, json.JSONDecodeError):
            messagebox.showerror("Error", "Scenes file not found or invalid JSON.")

        try:
            with open('../game_files/items.json', 'r') as f:
                self.items_data = json.load(f)
                for index, item in enumerate(self.items_data):
                    self.items_listbox.insert(tk.END, item)
                    self.items_listbox.selection_set(index)
        except FileNotFoundError:
            messagebox.showerror("Error", "Items file not found.")

        try:
            with open('../game_files/characters.json', 'r') as f:
                self.characters_data = json.load(f)
                for index, character in enumerate(self.characters_data):
                    self.characters_listbox.insert(tk.END, character)
                    self.characters_listbox.selection_set(index)
        except FileNotFoundError:
            messagebox.showerror("Error", "Characters file not found.")

        try:
            with open('../game_files/story_texts.json', 'r') as f:
                self.story_texts_data = json.load(f)
                for index, story_text in enumerate(self.story_texts_data):
                    self.story_texts_listbox.insert(tk.END, story_text)
        except FileNotFoundError:
            messagebox.showerror("Error", "Story Texts file not found.")

        self.modified_files = set()

    def save_data(self):
        if 'scenes' in self.modified_files:
            try:
                with open('../game_files/scenes/scenes.json', 'w') as f:
                    json.dump(self.scenes_data, f, indent=4)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save scenes data: {e}")

        if 'items' in self.modified_files:
            try:
                with open('../game_files/items.json', 'w') as f:
                    json.dump(self.items_data, f, indent=4)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save items data: {e}")

        if 'characters' in self.modified_files:
            try:
                with open('../game_files/characters.json', 'w') as f:
                    json.dump(self.characters_data, f, indent=4)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save characters data: {e}")

        if 'story_texts' in self.modified_files:
            try:
                with open('../game_files/story_texts.json', 'w') as f:
                    json.dump(self.story_texts_data, f, indent=4)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save story texts data: {e}")

        self.modified_files.clear()

    def add_scene(self):
        scene_name = simpledialog.askstring("Add Scene", "Enter scene name:")
        if scene_name:
            scene_id = self.generate_scene_id(scene_name)
            scene_data = {
                "id": scene_id,
                "name": scene_name,
                "description": "",
                "items": [],
                "characters": [],
                "exits": [],
                "music": "",
                "sound_effects": {},
                "random_events": [],
                "hint": ""
            }
            self.scenes_data.append(scene_data)
            self.scenes_listbox.insert(tk.END, scene_name)
            self.scenes_listbox.selection_set(tk.END)
            self.modified_files.add('scenes')

    def generate_scene_id(self, scene_name):
        base_id = re.sub(r'\s+', '_', scene_name.lower())
        scene_id = base_id
        counter = 1
        while any(scene["id"] == scene_id for scene in self.scenes_data):
            scene_id = f"{base_id}{counter:02}"
            counter += 1
        return scene_id

    def edit_scene(self):
        selected_scene = self.scenes_listbox.get(self.scenes_listbox.curselection())
        if selected_scene:
            try:
                scene_data = next(scene for scene in self.scenes_data if scene["name"] == selected_scene)
                scene_data["description"] = simpledialog.askstring("Edit Scene", f"Enter description for {selected_scene}:", initialvalue=scene_data["description"])
                self.display_scene_details(scene_data)
                self.modified_files.add('scenes')
            except StopIteration:
                messagebox.showerror("Error", f"Scene with name {selected_scene} not found.")

    def delete_scene(self):
        selected_scene = self.scenes_listbox.get(self.scenes_listbox.curselection())
        if selected_scene:
            self.scenes_data = [scene for scene in self.scenes_data if scene["name"] != selected_scene]
            self.scenes_listbox.delete(self.scenes_listbox.curselection())
            self.modified_files.add('scenes')

    def add_item(self):
        item_name = simpledialog.askstring("Add Item", "Enter item name:")
        if item_name:
            item_id = self.generate_item_id(item_name)
            self.items_data[item_id] = {
                "name": item_name,
                "description": "",
                "usable": False,
                "readable_item": "",
                "type": "Story"
            }
            self.items_listbox.insert(tk.END, item_id)
            self.items_listbox.selection_set(tk.END)
            self.modified_files.add('items')

    def generate_item_id(self, item_name):
        base_id = re.sub(r'\s+', '_', item_name.lower())
        item_id = base_id
        counter = 1
        while item_id in self.items_data:
            item_id = f"{base_id}{counter:02}"
            counter += 1
        return item_id

    def edit_item(self):
        selected_item = self.items_listbox.get(self.items_listbox.curselection())
        if selected_item:
            item_data = self.items_data[selected_item]
            item_data["description"] = simpledialog.askstring("Edit Item", f"Enter description for {selected_item}:", initialvalue=item_data["description"])
            self.display_item_details(item_data)
            self.modified_files.add('items')

    def delete_item(self):
        selected_item = self.items_listbox.get(self.items_listbox.curselection())
        if selected_item:
            del self.items_data[selected_item]
            self.items_listbox.delete(self.items_listbox.curselection())
            self.modified_files.add('items')

    def duplicate_item(self):
        selected_item = self.items_listbox.get(self.items_listbox.curselection())
        if selected_item:
            new_item_id = self.generate_item_id(selected_item + "_copy")
            self.items_data[new_item_id] = self.items_data[selected_item].copy()
            self.items_listbox.insert(tk.END, new_item_id)
            self.items_listbox.selection_set(tk.END)
            self.modified_files.add('items')

    def combine_items(self):
        item_ids = list(self.items_data.keys())
        if len(item_ids) < 2:
            messagebox.showerror("Error", "Not enough items to combine.")
            return

        item1_var = tk.StringVar(value=item_ids[0])
        item2_var = tk.StringVar(value=item_ids[1])

        combine_window = tk.Toplevel(self.root)
        combine_window.title("Combine Items")
        combine_window.geometry("400x200")

        combine_frame = ttk.Frame(combine_window)
        combine_frame.pack(padx=10, pady=10)

        item1_label = ttk.Label(combine_frame, text="Select first item:")
        item1_label.pack(anchor=tk.W)
        item1_dropdown = ttk.Combobox(combine_frame, textvariable=item1_var, values=item_ids)
        item1_dropdown.pack(pady=5)

        item2_label = ttk.Label(combine_frame, text="Select second item:")
        item2_label.pack(anchor=tk.W)
        item2_dropdown = ttk.Combobox(combine_frame, textvariable=item2_var, values=item_ids)
        item2_dropdown.pack(pady=5)

        new_item_name_var = tk.StringVar()
        new_item_name_label = ttk.Label(combine_frame, text="Enter the name of the combined item:")
        new_item_name_label.pack(anchor=tk.W)
        new_item_name_entry = ttk.Entry(combine_frame, textvariable=new_item_name_var)
        new_item_name_entry.pack(pady=5)

        def on_combine():
            item1_id = item1_var.get()
            item2_id = item2_var.get()
            new_item_name = new_item_name_var.get()
            if not new_item_name:
                messagebox.showerror("Error", "New item name cannot be empty.")
                return

            combination_key = f"{item1_id} + {item2_id}"
            new_item_id = self.generate_item_id(new_item_name)
            self.items_data[new_item_id] = {
                "name": new_item_name,
                "description": f"Combined from {item1_id} and {item2_id}",
                "usable": False,
                "readable_item": "",
                "type": "Story"
            }
            if "combinations" not in self.items_data:
                self.items_data["combinations"] = {}
            self.items_data["combinations"][combination_key] = new_item_id
            self.items_listbox.insert(tk.END, new_item_id)
            self.items_listbox.selection_set(tk.END)
            self.modified_files.add('items')
            combine_window.destroy()

        combine_button = ttk.Button(combine_frame, text="Combine", command=on_combine)
        combine_button.pack(pady=5)

        combine_window.wait_window(combine_window)

    def add_character(self):
        character_name = simpledialog.askstring("Add Character", "Enter character name:")
        if character_name:
            character_id = self.generate_character_id(character_name)
            self.characters_data[character_id] = {
                "id": character_id,
                "name": character_name,
                "type": "Friendly",
                "dialogue": {},
                "dialogue_options": {},
                "interactions": {},
                "stats": {},
                "greeting": ""
            }
            self.characters_listbox.insert(tk.END, character_id)
            self.characters_listbox.selection_set(tk.END)
            self.modified_files.add('characters')

    def generate_character_id(self, character_name):
        base_id = re.sub(r'\s+', '_', character_name.lower())
        character_id = base_id
        counter = 1
        while character_id in self.characters_data:
            character_id = f"{base_id}{counter:02}"
            counter += 1
        return character_id

    def edit_character(self):
        selected_character = self.characters_listbox.get(self.characters_listbox.curselection())
        if selected_character:
            character_data = self.characters_data[selected_character]
            character_data["description"] = simpledialog.askstring("Edit Character", f"Enter description for {selected_character}:", initialvalue=character_data["description"])
            self.display_character_details(character_data)
            self.modified_files.add('characters')

    def delete_character(self):
        selected_character = self.characters_listbox.get(self.characters_listbox.curselection())
        if selected_character:
            del self.characters_data[selected_character]
            self.characters_listbox.delete(self.characters_listbox.curselection())
            self.modified_files.add('characters')

    def duplicate_character(self):
        selected_character = self.characters_listbox.get(self.characters_listbox.curselection())
        if selected_character:
            new_character_id = self.generate_character_id(selected_character + "_copy")
            self.characters_data[new_character_id] = self.characters_data[selected_character].copy()
            self.characters_listbox.insert(tk.END, new_character_id)
            self.characters_listbox.selection_set(tk.END)
            self.modified_files.add('characters')

    def add_dialogue(self):
        character_id = simpledialog.askstring("Add Dialogue", "Enter character ID:")
        if character_id:
            dialogue_key = simpledialog.askstring("Add Dialogue", "Enter dialogue key:")
            if dialogue_key:
                self.characters_data[character_id]["dialogue"][dialogue_key] = {
                    "text": "",
                    "show_once": False
                }
                self.dialogues_listbox.insert(tk.END, dialogue_key)
                self.modified_files.add('characters')

    def edit_dialogue(self):
        selected_dialogue = self.dialogues_listbox.get(self.dialogues_listbox.curselection())
        if selected_dialogue:
            character_id = simpledialog.askstring("Edit Dialogue", "Enter character ID:")
            if character_id:
                dialogue_data = self.characters_data[character_id]["dialogue"][selected_dialogue]
                dialogue_data["text"] = simpledialog.askstring("Edit Dialogue", f"Enter text for {selected_dialogue}:", initialvalue=dialogue_data["text"])
                self.display_dialogue_details(dialogue_data)
                self.modified_files.add('characters')

    def delete_dialogue(self):
        selected_dialogue = self.dialogues_listbox.get(self.dialogues_listbox.curselection())
        if selected_dialogue:
            character_id = simpledialog.askstring("Delete Dialogue", "Enter character ID:")
            if character_id:
                del self.characters_data[character_id]["dialogue"][selected_dialogue]
                self.dialogues_listbox.delete(self.dialogues_listbox.curselection())
                self.modified_files.add('characters')

    def add_item_to_scene(self):
        selected_scene = self.scenes_listbox.get(self.scenes_listbox.curselection())
        if not selected_scene:
            selected_scene = self.get_current_scene()
        if selected_scene:
            try:
                scene_data = next(scene for scene in self.scenes_data if scene["name"] == selected_scene)
                item_id = self.select_or_create_item()
                if item_id:
                    scene_data["items"].append(item_id)
                    self.display_scene_details(scene_data)
                    self.modified_files.add('scenes')
            except StopIteration:
                messagebox.showerror("Error", f"Scene with name {selected_scene} not found.")

    def get_current_scene(self):
        selected_scene = self.scenes_listbox.get(self.scenes_listbox.curselection())
        if selected_scene:
            return next(scene for scene in self.scenes_data if scene["name"] == selected_scene)["id"]
        return None

    def select_or_create_item(self):
        item_id = None  # Initialize item_id here
        item_window = tk.Toplevel(self.root)
        item_window.title("Item | Select or Create")
        item_window.geometry("400x200")

        item_frame = ttk.Frame(item_window)
        item_frame.pack(padx=10, pady=10)

        item_label = ttk.Label(item_frame, text="Select an existing item or create a new one:")
        item_label.pack(anchor=tk.W)

        item_var = tk.StringVar(value="Create New Item")
        item_dropdown = ttk.Combobox(item_frame, textvariable=item_var, values=list(self.items_data.keys()))
        item_dropdown.pack(pady=5)

        def on_select():
            nonlocal item_id
            item_id = item_var.get()
            if item_id == "Create New Item":
                item_name = simpledialog.askstring("Create New Item", "Enter item name:")
                if item_name:
                    item_id = self.generate_item_id(item_name)
                    self.items_data[item_id] = {
                        "name": item_name,
                        "description": "",
                        "usable": False,
                        "readable_item": "",
                        "type": "Story"
                    }
                    self.items_listbox.insert(tk.END, item_id)
                    self.items_listbox.selection_set(tk.END)
                    self.modified_files.add('items')
            item_window.destroy()

        item_button = ttk.Button(item_frame, text="Select", command=on_select)
        item_button.pack(pady=5)

        item_window.wait_window(item_window)
        return item_id

    def add_character_to_scene(self):
        selected_scene = self.scenes_listbox.get(self.scenes_listbox.curselection())
        if not selected_scene:
            selected_scene = self.get_current_scene()
        if selected_scene:
            try:
                scene_data = next(scene for scene in self.scenes_data if scene["name"] == selected_scene)
                character_id = self.select_or_create_character()
                if character_id:
                    scene_data["characters"].append(character_id)
                    self.display_scene_details(scene_data)
                    self.modified_files.add('scenes')
            except StopIteration:
                messagebox.showerror("Error", f"Scene with name {selected_scene} not found.")

    def select_or_create_character(self):
        character_id = None  # Initialize character_id here
        character_window = tk.Toplevel(self.root)
        character_window.title("Character | Select or Create")
        character_window.geometry("400x200")

        character_frame = ttk.Frame(character_window)
        character_frame.pack(padx=10, pady=10)

        character_label = ttk.Label(character_frame, text="Select an existing character or create a new one:")
        character_label.pack(anchor=tk.W)

        character_var = tk.StringVar(value="Create New Character")
        character_dropdown = ttk.Combobox(character_frame, textvariable=character_var, values=list(self.characters_data.keys()))
        character_dropdown.pack(pady=5)

        def on_select():
            nonlocal character_id
            character_id = character_var.get()
            if character_id == "Create New Character":
                character_name = simpledialog.askstring("Create New Character", "Enter character name:")
                if character_name:
                    character_id = self.generate_character_id(character_name)
                    self.characters_data[character_id] = {
                        "id": character_id,
                        "name": character_name,
                        "type": "Friendly",
                        "dialogue": {},
                        "dialogue_options": {},
                        "interactions": {},
                        "stats": {},
                        "greeting": ""
                    }
                    self.characters_listbox.insert(tk.END, character_id)
                    self.characters_listbox.selection_set(tk.END)
                    self.modified_files.add('characters')
            character_window.destroy()

        character_button = ttk.Button(character_frame, text="Select", command=on_select)
        character_button.pack(pady=5)

        character_window.wait_window(character_window)
        return character_id

    def add_exit_to_scene(self):
        selected_scene = self.scenes_listbox.get(self.scenes_listbox.curselection())
        if not selected_scene:
            selected_scene = self.get_current_scene()
        if selected_scene:
            try:
                scene_data = next(scene for scene in self.scenes_data if scene["name"] == selected_scene)
                door_name = simpledialog.askstring("Add Exit to Scene", "Enter door name:")
                if door_name:
                    target_scene_id = self.select_or_create_scene()
                    if target_scene_id:
                        exit_data = {
                            "door_name": door_name,
                            "locked": False,
                            "lock_text": "",
                            "unlock_text": "",
                            "required_item": "",
                            "scene_id": target_scene_id
                        }
                        scene_data["exits"].append(exit_data)
                        self.display_scene_details(scene_data)
                        self.modified_files.add('scenes')
            except StopIteration:
                messagebox.showerror("Error", f"Scene with name {selected_scene} not found.")

    def select_or_create_scene(self):
        scene_id = None  # Initialize scene_id here
        scene_window = tk.Toplevel(self.root)
        scene_window.title("Scene | Select or Create")
        scene_window.geometry("400x200")

        scene_frame = ttk.Frame(scene_window)
        scene_frame.pack(padx=10, pady=10)

        scene_label = ttk.Label(scene_frame, text="Select an existing scene or create a new one:")
        scene_label.pack(anchor=tk.W)

        scene_var = tk.StringVar(value="Create New Scene")
        scene_dropdown = ttk.Combobox(scene_frame, textvariable=scene_var, values=[scene["name"] for scene in self.scenes_data])
        scene_dropdown.pack(pady=5)

        def on_select():
            nonlocal scene_id
            scene_id = scene_var.get()
            if scene_id == "Create New Scene":
                scene_name = simpledialog.askstring("Create New Scene", "Enter scene name:")
                if scene_name:
                    scene_data = {
                        "id": self.generate_scene_id(scene_name),
                        "name": scene_name,
                        "description": "",
                        "items": [],
                        "characters": [],
                        "exits": [],
                        "music": "",
                        "sound_effects": {},
                        "random_events": [],
                        "hint": ""
                    }
                    self.scenes_data.append(scene_data)
                    self.scenes_listbox.insert(tk.END, scene_name)
                    self.scenes_listbox.selection_set(tk.END)
                    self.modified_files.add('scenes')
                    scene_id = scene_data["id"]
            scene_window.destroy()

        scene_button = ttk.Button(scene_frame, text="Select", command=on_select)
        scene_button.pack(pady=5)

        scene_window.wait_window(scene_window)
        return scene_id

    def display_scene_details(self, scene_data):
        self.scene_details_text.delete(1.0, tk.END)
        self.scene_details_text.insert(tk.END, json.dumps(scene_data, indent=4))

    def display_item_details(self, item_data):
        self.item_details_text.delete(1.0, tk.END)
        self.item_details_text.insert(tk.END, json.dumps(item_data, indent=4))

    def display_character_details(self, character_data):
        self.character_details_text.delete(1.0, tk.END)
        self.character_details_text.insert(tk.END, json.dumps(character_data, indent=4))

    def display_dialogue_details(self, dialogue_data):
        self.dialogue_details_text.delete(1.0, tk.END)
        self.dialogue_details_text.insert(tk.END, json.dumps(dialogue_data, indent=4))

    def preview_scene_structure(self):
        scene_structure = self.generate_scene_structure()
        preview_window = self.create_preview_window(title="Scene Structure Preview", width=1200, height=800)
        canvas = preview_window
        self.draw_scene_structure(canvas, scene_structure)

    def generate_scene_structure(self):
        scene_structure = {}
        for scene in self.scenes_data:
            scene_structure[scene["id"]] = {
                "name": scene["name"],
                "description": scene["description"],
                "items": scene["items"],
                "characters": scene["characters"],
                "exits": [(exit["door_name"], exit["scene_id"]) for exit in scene["exits"]]
            }
        return scene_structure

    def draw_scene_structure(self, canvas, scene_structure):
        padding = 50
        box_size = 300  # Increased box size to fit more text
        arrow_length = 40

        positions = {}
        x = padding
        y = padding
        for scene_id in scene_structure:
            positions[scene_id] = (x, y)
            x += box_size + padding
            if x > canvas.winfo_width() - box_size - padding:
                x = padding
                y += box_size + padding

        for scene_id, (x, y) in positions.items():
            scene_info = scene_structure[scene_id]
            canvas.create_rectangle(x, y, x + box_size, y + box_size, outline="black")
            canvas.create_text(x + box_size / 2, y + 10, text=scene_info["name"])

            # Display items and characters
            y_offset = 30
            for item_id in scene_info["items"]:
                item_name = self.items_data.get(item_id, {}).get("name", "Unknown Item")
                canvas.create_text(x + 10, y + y_offset, text=item_name, anchor=tk.W, fill="dark green")
                y_offset += 20
            for char_id in scene_info["characters"]:
                char_name = self.characters_data.get(char_id, {}).get("name", "Unknown Character")
                canvas.create_text(x + 10, y + y_offset, text=char_name, anchor=tk.W, fill="dark red")
                y_offset += 20

        for scene_id, (x, y) in positions.items():
            scene_info = scene_structure[scene_id]
            exit_y_offset = y + box_size + 10
            for exit_name, target_scene_id in scene_info["exits"]:
                if target_scene_id in positions:
                    target_x, target_y = positions[target_scene_id]
                    arrow_x = x + box_size
                    arrow_y = y + box_size / 2
                    target_arrow_x = target_x
                    target_arrow_y = target_y + box_size / 2
                    canvas.create_line(arrow_x, arrow_y, target_arrow_x, target_arrow_y, arrow=tk.LAST, fill="blue")
                    canvas.create_text(canvas.winfo_width() - 10, exit_y_offset, text=exit_name, anchor=tk.W, fill="blue")
                    exit_y_offset += 20

        canvas.configure(scrollregion=canvas.bbox(tk.ALL))

    def on_mouse_wheel(self, event):
        if event.delta > 0:
            self.zoom_level *= 1.1
        else:
            self.zoom_level /= 1.1
        self.zoom_level = max(0.5, min(2.0, self.zoom_level))
        self.preview_scene_structure()

    def create_settings_menu(self):
        settings_window = tk.Toplevel(self.root)
        settings_window.title("Settings")
        settings_window.geometry("200x200")

        settings_frame = ttk.Frame(settings_window)
        settings_frame.pack(padx=10, pady=10)

        settings_label = ttk.Label(settings_frame, text="Settings:")
        settings_label.pack(anchor=tk.W)

        text_size_var = tk.StringVar(value="12")
        text_size_label = ttk.Label(settings_frame, text="Text Size:")
        text_size_label.pack(anchor=tk.W)
        text_size_entry = ttk.Entry(settings_frame, textvariable=text_size_var)
        text_size_entry.pack(pady=5)

        light_mode_check = ttk.Checkbutton(settings_frame, text="Light Mode", variable=self.light_mode, command=self.toggle_light_mode)
        light_mode_check.pack(anchor=tk.W, pady=5)

        syntax_highlighting_check = ttk.Checkbutton(settings_frame, text="Syntax Highlighting", variable=self.syntax_highlighting_var, command=self.toggle_syntax_highlighting)
        syntax_highlighting_check.pack(anchor=tk.W, pady=5)

        def apply_settings():
            text_size = text_size_var.get()
            try:
                text_size = int(text_size)
            except ValueError:
                messagebox.showerror("Error", "Invalid text size. Please enter a number.")
                return

            self.scene_details_text.config(font=("Helvetica", text_size))
            self.item_details_text.config(font=("Helvetica", text_size))
            self.character_details_text.config(font=("Helvetica", text_size))
            self.dialogue_details_text.config(font=("Helvetica", text_size))

        apply_button = ttk.Button(settings_frame, text="Apply", command=apply_settings)
        apply_button.pack(pady=5)

        settings_window.wait_window(settings_window)

    def toggle_light_mode(self):
        if self.light_mode.get():
            self.style.theme_use('clam')
        else:
            self.style.theme_use('equilux')

    def toggle_syntax_highlighting(self):
        if self.syntax_highlighting_var.get():
            # Implement syntax highlighting
            self.apply_syntax_highlighting()
        else:
            # Disable syntax highlighting
            self.remove_syntax_highlighting()

        # Apply syntax highlighting using pygments

    def apply_syntax_highlighting(self, text_widget):
        text = text_widget.get(1.0, tk.END)
        # Simple example: highlight JSON keys
        import json
        try:
            data = json.loads(text)
            for key in data.keys():
                start = text.find(f'"{key}":')
                if start != -1:
                    end = start + len(key) + 2  # Account for quotes
                    text_widget.tag_add("key", f"1.{start}", f"1.{end}")
                    text_widget.tag_config("key", foreground="blue")
        except json.JSONDecodeError:
            pass

    def remove_syntax_highlighting(self):
        # Remove syntax highlighting
        self.scene_details_text.config(font=("Helvetica", 12))

    def on_scene_double_click(self, event):
        selected_scene = self.scenes_listbox.get(self.scenes_listbox.curselection())
        if selected_scene:
            try:
                scene_data = next(scene for scene in self.scenes_data if scene["name"] == selected_scene)
                self.display_scene_details(scene_data)
            except StopIteration:
                messagebox.showerror("Error", f"Scene with name {selected_scene} not found.")

    def on_item_double_click(self, event):
        selected_item = self.items_listbox.get(self.items_listbox.curselection())
        if selected_item:
            self.display_item_details(self.items_data[selected_item])

    def on_character_double_click(self, event):
        selected_character = self.characters_listbox.get(self.characters_listbox.curselection())
        if selected_character:
            self.display_character_details(self.characters_data[selected_character])

    def on_dialogue_double_click(self, event):
        selected_dialogue = self.dialogues_listbox.get(self.dialogues_listbox.curselection())
        if selected_dialogue:
            character_id = simpledialog.askstring("Dialogue Details", "Enter character ID:")
            if character_id:
                dialogue_data = self.characters_data[character_id]["dialogue"][selected_dialogue]
                dialogue_text = f"Greet: {dialogue_data.get('greet', '')}\n"
                dialogue_text += "Dialogue Options:\n"
                for option, response in dialogue_data.get("dialogue_options", {}).items():
                    dialogue_text += f"{option}: {response}\n"
                dialogue_text += "Dialogue Rewards:\n"
                for reward, details in dialogue_data.get("dialogue_rewards", {}).items():
                    dialogue_text += f"{reward}: {details}\n"
                self.dialogue_details_text.delete(1.0, tk.END)
                self.dialogue_details_text.insert(tk.END, dialogue_text)

    def show_context_menu(self, event):
        context_menu = tk.Menu(self.root, tearoff=0)
        context_menu.add_command(label="Copy", command=self.copy_to_clipboard)
        context_menu.add_command(label="Paste", command=self.paste_from_clipboard)
        context_menu.add_command(label="Undo", command=self.undo)
        context_menu.add_command(label="Redo", command=self.redo)
        context_menu.post(event.x_root, event.y_root)

    def copy_to_clipboard(self):
        selected_text = self.root.clipboard_get()
        if selected_text:
            self.root.clipboard_clear()
            self.root.clipboard_append(selected_text)

    def paste_from_clipboard(self):
        clipboard_text = self.root.clipboard_get()
        if clipboard_text:
            self.root.insert(tk.END, clipboard_text)
            self.root.clipboard_clear()

    def undo(self):
        self.root.edit_undo()

    def redo(self):
        self.root.edit_redo()

    def preview_scene_map(self):
        scene_map = self.generate_scene_map()
        preview_window = self.create_preview_window(title="Scene Map Preview", width=1200, height=800)
        canvas = preview_window
        self.draw_scene_map(canvas, scene_map)

    def generate_scene_map(self):
        scene_map = {}
        for scene in self.scenes_data:
            scene_map[scene["id"]] = {
                "name": scene["name"],
                "exits": [(exit["door_name"], exit["scene_id"]) for exit in scene["exits"]]
            }
        return scene_map

    def draw_scene_map(self, canvas, scene_map):
        padding = 50
        box_size = 80
        arrow_length = 40

        positions = {}
        x = padding
        y = padding
        for scene_id in scene_map:
            positions[scene_id] = (x, y)
            x += box_size + padding
            if x > canvas.winfo_width() - box_size - padding:
                x = padding
                y += box_size + padding

        for scene_id, (x, y) in positions.items():
            scene_info = scene_map[scene_id]
            canvas.create_rectangle(x, y, x + box_size, y + box_size, outline="black")
            canvas.create_text(x + box_size / 2, y + box_size / 2, text=scene_info["name"])

        for scene_id, (x, y) in positions.items():
            scene_info = scene_map[scene_id]
            for exit_name, target_scene_id in scene_info["exits"]:
                if target_scene_id in positions:
                    target_x, target_y = positions[target_scene_id]
                    arrow_x = x + box_size
                    arrow_y = y + box_size / 2
                    target_arrow_x = target_x
                    target_arrow_y = target_y + box_size / 2
                    canvas.create_line(arrow_x, arrow_y, target_arrow_x, target_arrow_y, arrow=tk.LAST, fill="red")
                    canvas.create_rectangle(arrow_x + 10, arrow_y - 10, arrow_x + 110, arrow_y + 10, fill="white")
                    canvas.create_text(arrow_x + 60, arrow_y, text=exit_name, fill="black")

        canvas.configure(scrollregion=canvas.bbox(tk.ALL))

    def add_story_text(self):
        text_key = simpledialog.askstring("Add Story Text", "Enter text key:")
        if text_key:
            self.story_texts_data[text_key] = {
                "text": "",
                "show_once": False
            }
            self.story_texts_listbox.insert(tk.END, text_key)
            self.modified_files.add('story_texts')

    def save_story_text(self):
        selected_text = self.story_texts_listbox.get(self.story_texts_listbox.curselection())
        if selected_text:
            text_content = self.story_text_editor.get(1.0, tk.END).strip()
            self.story_texts_data[selected_text]["text"] = text_content
            self.modified_files.add('story_texts')

    def delete_story_text(self):
        selected_text = self.story_texts_listbox.get(self.story_texts_listbox.curselection())
        if selected_text:
            del self.story_texts_data[selected_text]
            self.story_texts_listbox.delete(self.story_texts_listbox.curselection())
            self.modified_files.add('story_texts')

    def add_ingredient(self):
        ingredient_name = simpledialog.askstring("Add Ingredient", "Enter ingredient name:")
        if ingredient_name:
            self.ingredients_list.insert(tk.END, ingredient_name)

    def remove_ingredient(self):
        selected_ingredient = self.ingredients_list.get(self.ingredients_list.curselection())
        if selected_ingredient:
            self.ingredients_list.delete(self.ingredients_list.curselection())

    def save_recipe(self):
        result_item = self.result_item_entry.get()
        ingredients = list(self.ingredients_list.get(0, tk.END))
        if result_item and ingredients:
            recipe_data = {
                "result_item": result_item,
                "ingredients": ingredients
            }
            # Save the recipe data to the appropriate file or data structure
            self.modified_files.add('recipes')

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    root = ThemedTk(theme="equilux")  # Using ThemedTk for better dark theme support
    app = GameDataEditor(root)
    app.run()
