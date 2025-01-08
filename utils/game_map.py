"""
Game map visualization module for CLIo Game Data Editor.
Provides functionality to generate and display interactive game world maps.
"""

import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import graphviz
from typing import Dict, List, Any
import os
import json
import tempfile
from pathlib import Path

class MapViewer(tk.Toplevel):
    """Interactive map viewer window with zoom and pan capabilities."""
    
    def __init__(self, parent, scenes_data: List[Dict], dark_theme: bool = False):
        """
        Initialize the map viewer.
        
        Args:
            parent: Parent tkinter window
            scenes_data: List of scene dictionaries containing game data
            dark_theme: Boolean to toggle dark theme colors
        """
        super().__init__(parent)
        self.title("Game Map Viewer")
        self.geometry("1200x800")
        
        # Initialize state
        self.scenes_data = scenes_data
        self.dark_theme = dark_theme
        self.zoom_factor = 1.0
        self.pan_start = None
        
        # Create UI
        self.create_toolbar()
        self.create_canvas()
        
        # Generate and display initial map
        try:
            self.check_graphviz()
            self.generate_map()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to generate map: {str(e)}")
            self.destroy()
    
    def check_graphviz(self):
        """Verify Graphviz is installed and accessible."""
        try:
            graphviz.version()
        except Exception:
            raise RuntimeError(
                "Graphviz is not installed or not in PATH.\n"
                "Please install Graphviz from https://graphviz.org/download/\n"
                "Make sure to check 'Add to system PATH' during installation."
            )
    
    def create_toolbar(self):
        """Create toolbar with map controls."""
        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, padx=5, pady=2)
        
        # Theme toggle
        self.theme_var = tk.BooleanVar(value=self.dark_theme)
        ttk.Checkbutton(
            toolbar, 
            text="Dark Theme", 
            variable=self.theme_var, 
            command=self.regenerate_map
        ).pack(side=tk.LEFT, padx=2)
        
        # Zoom controls
        ttk.Button(
            toolbar,
            text="Zoom In",
            command=lambda: self.zoom(1.2)
        ).pack(side=tk.LEFT, padx=2)
        
        ttk.Button(
            toolbar,
            text="Zoom Out",
            command=lambda: self.zoom(0.8)
        ).pack(side=tk.LEFT, padx=2)
        
        ttk.Button(
            toolbar,
            text="Reset View",
            command=self.reset_view
        ).pack(side=tk.LEFT, padx=2)
        
        # Export button
        ttk.Button(
            toolbar,
            text="Export PNG",
            command=self.export_map
        ).pack(side=tk.LEFT, padx=2)
        
    def create_canvas(self):
        """Create scrollable canvas for the map."""
        # Create canvas with scrollbars
        self.canvas_frame = ttk.Frame(self)
        self.canvas_frame.pack(fill=tk.BOTH, expand=True)
        
        self.canvas = tk.Canvas(self.canvas_frame, bg='white')
        self.scrollbar_x = ttk.Scrollbar(self.canvas_frame, orient=tk.HORIZONTAL)
        self.scrollbar_y = ttk.Scrollbar(self.canvas_frame, orient=tk.VERTICAL)
        
        # Configure scrollbars
        self.scrollbar_x.pack(side=tk.BOTTOM, fill=tk.X)
        self.scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.scrollbar_x.config(command=self.canvas.xview)
        self.scrollbar_y.config(command=self.canvas.yview)
        self.canvas.config(
            xscrollcommand=self.scrollbar_x.set,
            yscrollcommand=self.scrollbar_y.set
        )
        
        # Bind mouse events
        self.canvas.bind("<ButtonPress-1>", self.start_pan)
        self.canvas.bind("<B1-Motion>", self.pan)
        self.canvas.bind("<ButtonRelease-1>", self.end_pan)
        self.canvas.bind("<MouseWheel>", self.mouse_zoom)  # Windows
        self.canvas.bind("<Button-4>", lambda e: self.mouse_zoom(e, up=True))  # Linux
        self.canvas.bind("<Button-5>", lambda e: self.mouse_zoom(e, up=False))  # Linux
        
    def generate_map(self):
        """Generate the game map using graphviz."""
        # Create temporary directory for map files
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create the graph
            dot = create_game_map(self.scenes_data, self.dark_theme)
            
            # Set output path in temp directory
            output_path = os.path.join(tmp_dir, 'game_map')
            
            try:
                # Render the map
                dot.render(output_path, format='png', cleanup=True)
                
                # Load and display the image
                self.load_map_image(output_path + '.png')
            except Exception as e:
                messagebox.showerror("Error", f"Failed to generate map: {str(e)}")
                self.destroy()
            
    def load_map_image(self, image_path: str):
        """
        Load and display the map image.
        
        Args:
            image_path: Path to the generated map image
        """
        # Load image using PIL
        self.original_image = Image.open(image_path)
        self.display_image = self.original_image.copy()
        
        # Convert to PhotoImage and display
        self.photo = ImageTk.PhotoImage(self.display_image)
        self.image_item = self.canvas.create_image(0, 0, anchor=tk.NW, image=self.photo)
        
        # Configure canvas scrolling
        self.canvas.config(scrollregion=self.canvas.bbox(tk.ALL))
        
    def regenerate_map(self):
        """Regenerate the map with current settings."""
        self.dark_theme = self.theme_var.get()
        self.generate_map()
        
    def zoom(self, factor: float):
        """
        Zoom the map by a factor.
        
        Args:
            factor: Zoom factor (>1 for zoom in, <1 for zoom out)
        """
        self.zoom_factor *= factor
        
        # Limit zoom range
        self.zoom_factor = min(max(self.zoom_factor, 0.1), 5.0)
        
        # Resize image
        new_size = (
            int(self.original_image.width * self.zoom_factor),
            int(self.original_image.height * self.zoom_factor)
        )
        self.display_image = self.original_image.resize(new_size, Image.Resampling.LANCZOS)
        
        # Update display
        self.photo = ImageTk.PhotoImage(self.display_image)
        self.canvas.delete(self.image_item)
        self.image_item = self.canvas.create_image(0, 0, anchor=tk.NW, image=self.photo)
        self.canvas.config(scrollregion=self.canvas.bbox(tk.ALL))
        
    def mouse_zoom(self, event, up=None):
        """
        Handle mouse wheel zoom.
        
        Args:
            event: Mouse wheel event
            up: Boolean indicating zoom direction (None for Windows event)
        """
        if up is None:  # Windows
            factor = 1.1 if event.delta > 0 else 0.9
        else:  # Linux
            factor = 1.1 if up else 0.9
        self.zoom(factor)
        
    def start_pan(self, event):
        """Start panning on mouse button press."""
        self.canvas.scan_mark(event.x, event.y)
        self.pan_start = (event.x, event.y)
        
    def pan(self, event):
        """Pan the image during mouse drag."""
        if self.pan_start:
            self.canvas.scan_dragto(event.x, event.y, gain=1)
            
    def end_pan(self, event):
        """End panning on mouse button release."""
        self.pan_start = None
        
    def reset_view(self):
        """Reset zoom and pan to initial state."""
        self.zoom_factor = 1.0
        self.zoom(1.0)
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)
        
    def export_map(self):
        """Export current map view as PNG."""
        from tkinter import filedialog
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG files", "*.png"), ("All files", "*.*")],
            title="Export Map"
        )
        
        if filename:
            try:
                # Save current view
                self.display_image.save(filename, "PNG")
                messagebox.showinfo("Success", f"Map exported to {filename}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to export map: {str(e)}")


def create_game_map(data: List[Dict[str, Any]], dark_theme: bool = False) -> graphviz.Digraph:
    """
    Create a visual map of the game scenes.
    
    Args:
        data: List of scene dictionaries containing game data
        dark_theme: Boolean to toggle dark theme colors
    
    Returns:
        Graphviz Digraph object representing the game map
    """
    # Create a new directed graph
    dot = graphviz.Digraph(comment='Game Map')
    dot.attr(rankdir='LR')  # Left to right layout
    
    # Set font family globally
    dot.attr('node', fontname='Arial')
    dot.attr('edge', fontname='Arial')
    
    # Define color schemes
    if dark_theme:
        colors = {
            'background': '#1E1E1E',
            'header': '#2C2C54',
            'description': '#2C2C2C',
            'items': '#1B4332',
            'characters': '#2C3E50',
            'passive': '#4A235A',
            'text': '#FFFFFF',
            'edge': '#FFFFFF'
        }
        # Set global dark theme
        dot.attr(bgcolor=colors['background'])
        dot.attr('edge', color=colors['edge'], fontcolor=colors['edge'])
    else:
        colors = {
            'background': 'white',
            'header': 'lightblue',
            'description': 'lightgray',
            'items': 'lightgreen',
            'characters': 'lightyellow',
            'passive': 'lightpink',
            'text': 'black',
            'edge': 'black'
        }
    
    # Create a mapping of scene IDs to scene data
    scene_map = {scene['id']: scene for scene in data}
    
    # Process each scene
    for scene in data:
        scene_id = scene['id']
        
        # Create node content with scene details
        node_content = f"""<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" CELLPADDING="8">
            <TR><TD PORT="header" BGCOLOR="{colors['header']}"><FONT FACE="Arial" COLOR="{colors['text']}"><B>{scene.get('name', scene_id)}</B></FONT></TD></TR>
            <TR><TD BGCOLOR="{colors['description']}"><FONT FACE="Arial" COLOR="{colors['text']}">{scene.get('description', '')}</FONT></TD></TR>"""
        
        # Add items section if there are items
        if scene.get('items'):
            items_str = '<BR/>'.join(scene['items'])
            node_content += f"""<TR><TD BGCOLOR="{colors['items']}">
                <FONT FACE="Arial" COLOR="{colors['text']}"><B>Items:</B><BR/>{items_str}</FONT>
            </TD></TR>"""
            
        # Add characters section if there are characters
        if scene.get('characters'):
            chars_str = '<BR/>'.join(scene['characters'])
            node_content += f"""<TR><TD BGCOLOR="{colors['characters']}">
                <FONT FACE="Arial" COLOR="{colors['text']}"><B>Characters:</B><BR/>{chars_str}</FONT>
            </TD></TR>"""
        
        # Add passive items if they exist
        if scene.get('passive_items'):
            passive_str = '<BR/>'.join(scene['passive_items'])
            node_content += f"""<TR><TD BGCOLOR="{colors['passive']}">
                <FONT FACE="Arial" COLOR="{colors['text']}"><B>Passive Items:</B><BR/>{passive_str}</FONT>
            </TD></TR>"""
            
        node_content += "</TABLE>>"
        
        # Add the node to the graph
        dot.node(scene_id, node_content)
        
        # Process exits/connections
        if scene.get('exits'):
            for exit_info in scene['exits']:
                target_scene_id = exit_info.get('scene_id')
                if target_scene_id and target_scene_id in scene_map:
                    # Create edge label with door info
                    edge_label = exit_info.get('door_name', '')
                    if exit_info.get('locked'):
                        edge_label += '\n(Locked)'
                        if exit_info.get('required_item'):
                            edge_label += f"\nNeeds: {exit_info['required_item']}"
                    elif exit_info.get('blocked'):
                        edge_label += '\n(Blocked)'
                        if exit_info.get('required_condition'):
                            edge_label += f"\nNeeds: {exit_info['required_condition']}"
                        elif exit_info.get('required_stat'):
                            edge_label += f"\nNeeds: {exit_info['required_stat']}={exit_info['required_value']}"
                    
                    # Add the edge to the graph
                    dot.edge(scene_id, target_scene_id, label=edge_label)
    
    return dot