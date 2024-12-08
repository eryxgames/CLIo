import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
import json
import os
import re

class GameDataEditor:
    def __init__(self, root):
        self.root = root
        self.root.title("CLIo Game Data Editor")

        # Apply dark theme
        self.apply_dark_theme()

        self.notebook = ttk.Notebook(root)
        self.notebook.pack(expand=1, fill="both")

        self.scenes_tab = ttk.Frame(self.notebook)
        self.items_tab = ttk.Frame(self.notebook)
        self.characters_tab = ttk.Frame(self.notebook)
        self.dialogues_tab = ttk.Frame(self.notebook)

        self.notebook.add(self.scenes_tab, text='Scenes')
        self.notebook.add(self.items_tab, text='Items')
        self.notebook.add(self.characters_tab, text='Characters')
        self.notebook.add(self.dialogues_tab, text='Dialogues')

        self.create_scenes_tab()
        self.create_items_tab()
        self.create_characters_tab()
        self.create_dialogues_tab()

        self.load_data()

    def apply_dark_theme(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", background="#2e2e2e", foreground="#ffffff", fieldbackground="#2e2e2e")
        style.map("TButton", background=[("active", "#4a4a4a")])
        style.map("TNotebook.Tab", background=[("selected", "#4a4a4a")])

    def create_scenes_tab(self):
        self.scenes_frame = ttk.Frame(self.scenes_tab)
        self.scenes_frame.pack(padx=10, pady=10)

        self.scenes_listbox = tk.Listbox(self.scenes_frame, height=20, width=40)
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

        self.scene_details_text = tk.Text(self.scene_details_frame, height=30, width=80)
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

        self.items_listbox = tk.Listbox(self.items_frame, height=20, width=40)
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

        self.item_details_text = tk.Text(self.item_details_frame, height=30, width=80)
        self.item_details_text.pack(fill=tk.BOTH, expand=1)

    def create_characters_tab(self):
        self.characters_frame = ttk.Frame(self.characters_tab)
        self.characters_frame.pack(padx=10, pady=10)

        self.characters_listbox = tk.Listbox(self.characters_frame, height=20, width=40)
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

        self.character_details_text = tk.Text(self.character_details_frame, height=30, width=80)
        self.character_details_text.pack(fill=tk.BOTH, expand=1)

    def create_dialogues_tab(self):
        self.dialogues_frame = ttk.Frame(self.dialogues_tab)
        self.dialogues_frame.pack(padx=10, pady=10)

        self.dialogues_listbox = tk.Listbox(self.dialogues_frame, height=20, width=40)
        self.dialogues_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=1)
        self.dialogues_scrollbar = ttk.Scrollbar(self.dialogues_frame, orient=tk.VERTICAL, command=self.dialogues_listbox.yview)
        self.dialogues_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.dialogues_listbox.config(yscrollcommand=self.dialogues_scrollbar.set)

        self.dialogues_listbox.bind("<Double-Button-1>", self.on_dialogue_double_click)
        self.dialogues_listbox.bind("<Button-3>", self.show_context_menu)

        self.dialogues_buttons_frame = ttk.Frame(self.dialogues_tab)
        self.dialogues_buttons_frame.pack(pady=10)

        self.add_dialogue_button = ttk.Button(self.dialogues_buttons_frame, text="Add Dialogue", command=self.add_dialogue)
        self.add_dialogue_button.pack(side=tk.LEFT, padx=5)

        self.edit_dialogue_button = ttk.Button(self.dialogues_buttons_frame, text="Edit Dialogue", command=self.edit_dialogue)
        self.edit_dialogue_button.pack(side=tk.LEFT, padx=5)

        self.delete_dialogue_button = ttk.Button(self.dialogues_buttons_frame, text="Delete Dialogue", command=self.delete_dialogue)
        self.delete_dialogue_button.pack(side=tk.LEFT, padx=5)

        self.save_button = ttk.Button(self.dialogues_buttons_frame, text="Save Changes", command=self.save_data)
        self.save_button.pack(side=tk.LEFT, padx=5)

        self.dialogue_details_frame = ttk.Frame(self.dialogues_tab)
        self.dialogue_details_frame.pack(pady=10)

        self.dialogue_details_label = ttk.Label(self.dialogue_details_frame, text="Dialogue Details:")
        self.dialogue_details_label.pack(anchor=tk.W)

        self.dialogue_details_text = tk.Text(self.dialogue_details_frame, height=30, width=80)
        self.dialogue_details_text.pack(fill=tk.BOTH, expand=1)

    def load_data(self):
        try:
            with open('../game_files/scenes/scenes.json', 'r') as f:
                self.scenes_data = json.load(f)
                for index, scene in enumerate(self.scenes_data):
                    self.scenes_listbox.insert(tk.END, scene['name'])
                    self.scenes_listbox.selection_set(index)
        except FileNotFoundError:
            messagebox.showerror("Error", "Scenes file not found.")

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
                self.dialogues_data = json.load(f)
                for index, dialogue in enumerate(self.dialogues_data):
                    self.dialogues_listbox.insert(tk.END, dialogue)
        except FileNotFoundError:
            messagebox.showerror("Error", "Dialogues file not found.")

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

        if 'dialogues' in self.modified_files:
            try:
                with open('../game_files/story_texts.json', 'w') as f:
                    json.dump(self.dialogues_data, f, indent=4)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save dialogues data: {e}")

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
        item1_dropdown = ttk.Combobox(combine_frame, textvariable=item1_var)
        item1_dropdown['values'] = item_ids
        item1_dropdown.pack(pady=5)

        item2_label = ttk.Label(combine_frame, text="Select second item:")
        item2_label.pack(anchor=tk.W)
        item2_dropdown = ttk.Combobox(combine_frame, textvariable=item2_var)
        item2_dropdown['values'] = item_ids
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
                "name": character_name,
                "description": "",
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
        dialogue_key = simpledialog.askstring("Add Dialogue", "Enter dialogue key:")
        if dialogue_key:
            self.dialogues_data[dialogue_key] = {
                "text": "",
                "show_once": False
            }
            self.dialogues_listbox.insert(tk.END, dialogue_key)
            self.modified_files.add('dialogues')

    def edit_dialogue(self):
        selected_dialogue = self.dialogues_listbox.get(self.dialogues_listbox.curselection())
        if selected_dialogue:
            dialogue_data = self.dialogues_data[selected_dialogue]
            dialogue_data["text"] = simpledialog.askstring("Edit Dialogue", f"Enter text for {selected_dialogue}:", initialvalue=dialogue_data["text"])
            self.display_dialogue_details(dialogue_data)
            self.modified_files.add('dialogues')

    def delete_dialogue(self):
        selected_dialogue = self.dialogues_listbox.get(self.dialogues_listbox.curselection())
        if selected_dialogue:
            del self.dialogues_data[selected_dialogue]
            self.dialogues_listbox.delete(self.dialogues_listbox.curselection())
            self.modified_files.add('dialogues')

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
        item_dropdown = ttk.Combobox(item_frame, textvariable=item_var)
        item_dropdown['values'] = list(self.items_data.keys())
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
        character_dropdown = ttk.Combobox(character_frame, textvariable=character_var)
        character_dropdown['values'] = list(self.characters_data.keys())
        character_dropdown.pack(pady=5)

        def on_select():
            nonlocal character_id
            character_id = character_var.get()
            if character_id == "Create New Character":
                character_name = simpledialog.askstring("Create New Character", "Enter character name:")
                if character_name:
                    character_id = self.generate_character_id(character_name)
                    self.characters_data[character_id] = {
                        "name": character_name,
                        "description": "",
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
        scene_dropdown = ttk.Combobox(scene_frame, textvariable=scene_var)
        scene_dropdown['values'] = [scene["name"] for scene in self.scenes_data]
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
        preview_window = tk.Toplevel(self.root)
        preview_window.title("Scene Structure Preview")

        canvas = tk.Canvas(preview_window, width=800, height=600)
        canvas.pack(fill=tk.BOTH, expand=1)

        scrollbar = ttk.Scrollbar(preview_window, orient=tk.VERTICAL, command=canvas.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.configure(yscrollcommand=scrollbar.set)

        self.draw_scene_structure(canvas, scene_structure)

        # Add zoom functionality
        self.zoom_level = 1.0
        canvas.bind("<MouseWheel>", self.on_mouse_wheel)

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
        box_size = 200  # Increased box size to fit more text
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
            self.display_dialogue_details(self.dialogues_data[selected_dialogue])

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
        preview_window = tk.Toplevel(self.root)
        preview_window.title("Scene Map Preview")

        canvas = tk.Canvas(preview_window, width=800, height=600)
        canvas.pack(fill=tk.BOTH, expand=1)

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

if __name__ == "__main__":
    root = tk.Tk()
    app = GameDataEditor(root)
    root.mainloop()
