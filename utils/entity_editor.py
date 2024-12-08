import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import json
import os

class GameDataEditor:
    def __init__(self, root):
        self.root = root
        self.root.title("GameData Editor")

        self.notebook = ttk.Notebook(root)
        self.notebook.pack(expand=1, fill="both")

        self.items_tab = ttk.Frame(self.notebook)
        self.characters_tab = ttk.Frame(self.notebook)
        self.scenes_tab = ttk.Frame(self.notebook)
        self.dialogues_tab = ttk.Frame(self.notebook)

        self.notebook.add(self.items_tab, text='Items')
        self.notebook.add(self.characters_tab, text='Characters')
        self.notebook.add(self.scenes_tab, text='Scenes')
        self.notebook.add(self.dialogues_tab, text='Dialogues')

        self.create_items_tab()
        self.create_characters_tab()
        self.create_scenes_tab()
        self.create_dialogues_tab()

        self.load_data()

    def create_items_tab(self):
        self.items_frame = ttk.Frame(self.items_tab)
        self.items_frame.pack(padx=10, pady=10)

        self.items_listbox = tk.Listbox(self.items_frame)
        self.items_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=1)

        self.items_scrollbar = ttk.Scrollbar(self.items_frame, orient=tk.VERTICAL, command=self.items_listbox.yview)
        self.items_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.items_listbox.config(yscrollcommand=self.items_scrollbar.set)

        self.items_buttons_frame = ttk.Frame(self.items_tab)
        self.items_buttons_frame.pack(pady=10)

        self.add_item_button = ttk.Button(self.items_buttons_frame, text="Add Item", command=self.add_item)
        self.add_item_button.pack(side=tk.LEFT, padx=5)

        self.edit_item_button = ttk.Button(self.items_buttons_frame, text="Edit Item", command=self.edit_item)
        self.edit_item_button.pack(side=tk.LEFT, padx=5)

        self.delete_item_button = ttk.Button(self.items_buttons_frame, text="Delete Item", command=self.delete_item)
        self.delete_item_button.pack(side=tk.LEFT, padx=5)

    def create_characters_tab(self):
        self.characters_frame = ttk.Frame(self.characters_tab)
        self.characters_frame.pack(padx=10, pady=10)

        self.characters_listbox = tk.Listbox(self.characters_frame)
        self.characters_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=1)

        self.characters_scrollbar = ttk.Scrollbar(self.characters_frame, orient=tk.VERTICAL, command=self.characters_listbox.yview)
        self.characters_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.characters_listbox.config(yscrollcommand=self.characters_scrollbar.set)

        self.characters_buttons_frame = ttk.Frame(self.characters_tab)
        self.characters_buttons_frame.pack(pady=10)

        self.add_character_button = ttk.Button(self.characters_buttons_frame, text="Add Character", command=self.add_character)
        self.add_character_button.pack(side=tk.LEFT, padx=5)

        self.edit_character_button = ttk.Button(self.characters_buttons_frame, text="Edit Character", command=self.edit_character)
        self.edit_character_button.pack(side=tk.LEFT, padx=5)

        self.delete_character_button = ttk.Button(self.characters_buttons_frame, text="Delete Character", command=self.delete_character)
        self.delete_character_button.pack(side=tk.LEFT, padx=5)

    def create_scenes_tab(self):
        self.scenes_frame = ttk.Frame(self.scenes_tab)
        self.scenes_frame.pack(padx=10, pady=10)

        self.scenes_listbox = tk.Listbox(self.scenes_frame)
        self.scenes_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=1)

        self.scenes_scrollbar = ttk.Scrollbar(self.scenes_frame, orient=tk.VERTICAL, command=self.scenes_listbox.yview)
        self.scenes_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.scenes_listbox.config(yscrollcommand=self.scenes_scrollbar.set)

        self.scenes_buttons_frame = ttk.Frame(self.scenes_tab)
        self.scenes_buttons_frame.pack(pady=10)

        self.add_scene_button = ttk.Button(self.scenes_buttons_frame, text="Add Scene", command=self.add_scene)
        self.add_scene_button.pack(side=tk.LEFT, padx=5)

        self.edit_scene_button = ttk.Button(self.scenes_buttons_frame, text="Edit Scene", command=self.edit_scene)
        self.edit_scene_button.pack(side=tk.LEFT, padx=5)

        self.delete_scene_button = ttk.Button(self.scenes_buttons_frame, text="Delete Scene", command=self.delete_scene)
        self.delete_scene_button.pack(side=tk.LEFT, padx=5)

    def create_dialogues_tab(self):
        self.dialogues_frame = ttk.Frame(self.dialogues_tab)
        self.dialogues_frame.pack(padx=10, pady=10)

        self.dialogues_listbox = tk.Listbox(self.dialogues_frame)
        self.dialogues_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=1)

        self.dialogues_scrollbar = ttk.Scrollbar(self.dialogues_frame, orient=tk.VERTICAL, command=self.dialogues_listbox.yview)
        self.dialogues_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.dialogues_listbox.config(yscrollcommand=self.dialogues_scrollbar.set)

        self.dialogues_buttons_frame = ttk.Frame(self.dialogues_tab)
        self.dialogues_buttons_frame.pack(pady=10)

        self.add_dialogue_button = ttk.Button(self.dialogues_buttons_frame, text="Add Dialogue", command=self.add_dialogue)
        self.add_dialogue_button.pack(side=tk.LEFT, padx=5)

        self.edit_dialogue_button = ttk.Button(self.dialogues_buttons_frame, text="Edit Dialogue", command=self.edit_dialogue)
        self.edit_dialogue_button.pack(side=tk.LEFT, padx=5)

        self.delete_dialogue_button = ttk.Button(self.dialogues_buttons_frame, text="Delete Dialogue", command=self.delete_dialogue)
        self.delete_dialogue_button.pack(side=tk.LEFT, padx=5)

    def load_data(self):
        try:
            with open('game_files/items.json', 'r') as f:
                self.items_data = json.load(f)
                for item in self.items_data:
                    self.items_listbox.insert(tk.END, item)
        except FileNotFoundError:
            messagebox.showerror("Error", "Items file not found.")

        try:
            with open('game_files/characters.json', 'r') as f:
                self.characters_data = json.load(f)
                for character in self.characters_data:
                    self.characters_listbox.insert(tk.END, character)
        except FileNotFoundError:
            messagebox.showerror("Error", "Characters file not found.")

        try:
            with open('game_files/scenes/scenes.json', 'r') as f:
                self.scenes_data = json.load(f)
                for scene in self.scenes_data:
                    self.scenes_listbox.insert(tk.END, scene['name'])
        except FileNotFoundError:
            messagebox.showerror("Error", "Scenes file not found.")

        try:
            with open('game_files/story_texts.json', 'r') as f:
                self.dialogues_data = json.load(f)
                for dialogue in self.dialogues_data:
                    self.dialogues_listbox.insert(tk.END, dialogue)
        except FileNotFoundError:
            messagebox.showerror("Error", "Dialogues file not found.")

    def save_data(self):
        try:
            with open('game_files/items.json', 'w') as f:
                json.dump(self.items_data, f, indent=4)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save items data: {e}")

        try:
            with open('game_files/characters.json', 'w') as f:
                json.dump(self.characters_data, f, indent=4)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save characters data: {e}")

        try:
            with open('game_files/scenes/scenes.json', 'w') as f:
                json.dump(self.scenes_data, f, indent=4)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save scenes data: {e}")

        try:
            with open('game_files/story_texts.json', 'w') as f:
                json.dump(self.dialogues_data, f, indent=4)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save dialogues data: {e}")

    def add_item(self):
        item_name = simpledialog.askstring("Add Item", "Enter item name:")
        if item_name:
            self.items_data[item_name] = {
                "name": item_name,
                "description": "",
                "usable": False,
                "readable_item": ""
            }
            self.items_listbox.insert(tk.END, item_name)
            self.save_data()

    def edit_item(self):
        selected_item = self.items_listbox.get(self.items_listbox.curselection())
        if selected_item:
            item_data = self.items_data[selected_item]
            item_data["description"] = simpledialog.askstring("Edit Item", f"Enter description for {selected_item}:", initialvalue=item_data["description"])
            self.save_data()

    def delete_item(self):
        selected_item = self.items_listbox.get(self.items_listbox.curselection())
        if selected_item:
            del self.items_data[selected_item]
            self.items_listbox.delete(self.items_listbox.curselection())
            self.save_data()

    def add_character(self):
        character_name = simpledialog.askstring("Add Character", "Enter character name:")
        if character_name:
            self.characters_data[character_name] = {
                "name": character_name,
                "description": "",
                "type": "",
                "dialogue": {},
                "dialogue_options": {},
                "interactions": {},
                "stats": {},
                "greeting": ""
            }
            self.characters_listbox.insert(tk.END, character_name)
            self.save_data()

    def edit_character(self):
        selected_character = self.characters_listbox.get(self.characters_listbox.curselection())
        if selected_character:
            character_data = self.characters_data[selected_character]
            character_data["description"] = simpledialog.askstring("Edit Character", f"Enter description for {selected_character}:", initialvalue=character_data["description"])
            self.save_data()

    def delete_character(self):
        selected_character = self.characters_listbox.get(self.characters_listbox.curselection())
        if selected_character:
            del self.characters_data[selected_character]
            self.characters_listbox.delete(self.characters_listbox.curselection())
            self.save_data()

    def add_scene(self):
        scene_name = simpledialog.askstring("Add Scene", "Enter scene name:")
        if scene_name:
            self.scenes_data.append({
                "name": scene_name,
                "description": "",
                "items": [],
                "characters": [],
                "exits": [],
                "music": "",
                "sound_effects": {},
                "random_events": [],
                "hint": ""
            })
            self.scenes_listbox.insert(tk.END, scene_name)
            self.save_data()

    def edit_scene(self):
        selected_scene = self.scenes_listbox.get(self.scenes_listbox.curselection())
        if selected_scene:
            scene_data = next(scene for scene in self.scenes_data if scene["name"] == selected_scene)
            scene_data["description"] = simpledialog.askstring("Edit Scene", f"Enter description for {selected_scene}:", initialvalue=scene_data["description"])
            self.save_data()

    def delete_scene(self):
        selected_scene = self.scenes_listbox.get(self.scenes_listbox.curselection())
        if selected_scene:
            self.scenes_data = [scene for scene in self.scenes_data if scene["name"] != selected_scene]
            self.scenes_listbox.delete(self.scenes_listbox.curselection())
            self.save_data()

    def add_dialogue(self):
        dialogue_key = simpledialog.askstring("Add Dialogue", "Enter dialogue key:")
        if dialogue_key:
            self.dialogues_data[dialogue_key] = {
                "text": "",
                "show_once": False
            }
            self.dialogues_listbox.insert(tk.END, dialogue_key)
            self.save_data()

    def edit_dialogue(self):
        selected_dialogue = self.dialogues_listbox.get(self.dialogues_listbox.curselection())
        if selected_dialogue:
            dialogue_data = self.dialogues_data[selected_dialogue]
            dialogue_data["text"] = simpledialog.askstring("Edit Dialogue", f"Enter text for {selected_dialogue}:", initialvalue=dialogue_data["text"])
            self.save_data()

    def delete_dialogue(self):
        selected_dialogue = self.dialogues_listbox.get(self.dialogues_listbox.curselection())
        if selected_dialogue:
            del self.dialogues_data[selected_dialogue]
            self.dialogues_listbox.delete(self.dialogues_listbox.curselection())
            self.save_data()

if __name__ == "__main__":
    root = tk.Tk()
    app = GameDataEditor(root)
    root.mainloop()
