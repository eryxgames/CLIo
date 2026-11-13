import json
import graphviz
from typing import Dict, List, Any
import sys

def create_game_map(data: List[Dict[str, Any]], dark_theme: bool = False) -> graphviz.Digraph:
    """
    Create a visual map of the game scenes, their connections, items, and characters.

    To run this separately, you need Graphviz library https://graphviz.org/download/
    IMPORTANT: Download graphviz, install it with system PATHs checked for it to work on Windows.

    Args:
        data: List of scene dictionaries containing game data
        dark_theme: Boolean to toggle dark theme colors
    
    Returns:
        Graphviz Digraph object representing the game map

    Example use (map.py will output parsed 'game_map' data and 'game_map.png'):    
        python map.py scenes.json  # Light theme
        python map.py scenes.json --dark  # Dark theme
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
    
    # Create a mapping of scene IDs to scene data for easier lookup
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

def main():
    if len(sys.argv) < 2:
        print("Usage: python map.py <scenes_file> [--dark]")
        sys.exit(1)

    dark_theme = "--dark" in sys.argv

    try:
        # Read the JSON data from the specified file
        with open(sys.argv[1], 'r') as f:
            data = json.load(f)
            
        # Create the graph
        dot = create_game_map(data, dark_theme)
        
        # Set global graph attributes
        dot.attr('graph', dpi='300')  # Increase DPI for better resolution
        dot.attr('node', shape='none')  # Using HTML-like labels, so no native shapes
        
        # Save the dot file
        output_file = 'game_map'
        dot.save(output_file)
        print(f"Graphviz dot file saved as '{output_file}'")
        
        # Render the PNG without cleanup to keep both files
        dot.render(output_file, format='png', cleanup=False)
        print(f"Game map has been saved as '{output_file}.png'")
        
    except FileNotFoundError:
        print(f"Error: Could not find file '{sys.argv[1]}'")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"Error: '{sys.argv[1]}' is not a valid JSON file")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()