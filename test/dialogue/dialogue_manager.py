import json

class DialogueManager:
    def __init__(self, player):
        self.player = player
        self.current_node = None
        self.dialogues = {}

    def load_dialogue(self, file_path):
        with open(file_path, 'r') as file:
            dialogue = json.load(file)
            self.validate_dialogue(dialogue)
            self.dialogues.update(dialogue)

    def validate_dialogue(self, dialogue):
        for node_id, node in dialogue.items():
            if 'character' not in node or 'text' not in node:
                print(f"Node {node_id} missing 'character' or 'text' field.")
            if 'responses' in node:
                for response in node['responses']:
                    if 'text' not in response or 'node_id' not in response:
                        print(f"In node {node_id}, response missing 'text' or 'node_id'.")
            if 'events' in node:
                for event in node['events']:
                    if 'type' not in event:
                        print(f"In node {node_id}, event missing 'type'.")
                    else:
                        event_type = event['type']
                        if event_type == 'give_item':
                            if 'item' not in event:
                                print(f"In node {node_id}, 'give_item' event missing 'item'.")
                        elif event_type == 'set_attribute':
                            if 'attribute' not in event or 'value' not in event:
                                print(f"In node {node_id}, 'set_attribute' event missing 'attribute' or 'value'.")
                        elif event_type == 'receive_item':
                            if 'item' not in event:
                                print(f"In node {node_id}, 'receive_item' event missing 'item'.")
                        else:
                            print(f"In node {node_id}, invalid event type: {event_type}.")

    def start(self, node_id):
        self.current_node = node_id

    def display_current_node(self):
        node = self.dialogues.get(self.current_node)
        if node:
            print(f"{node['character']}: {node['text']}")
        else:
            print("Invalid node")

    def get_available_responses(self):
        responses = self.dialogues[self.current_node].get('responses', [])
        available_responses = []
        for response in responses:
            conditions = response.get('conditions', {})
            if self.check_conditions(conditions):
                available_responses.append(response)
        return available_responses

    def check_conditions(self, conditions):
        for condition, value in conditions.items():
            if condition == 'has_item':
                if value not in self.player.inventory:
                    return False
            elif condition == 'attribute':
                attr_name = value.get('name')
                attr_value = value.get('value')
                if self.player.attributes.get(attr_name) != attr_value:
                    return False
        return True

    def choose_response(self, response_index):
        responses = self.get_available_responses()
        if response_index < len(responses):
            next_node_id = responses[response_index]['node_id']
            self.current_node = next_node_id
        else:
            print("Invalid response index")

    def handle_events(self):
        node = self.dialogues.get(self.current_node)
        if node and 'events' in node:
            for event in node['events']:
                if event['type'] == 'give_item':
                    self.player.add_item(event['item'])
                elif event['type'] == 'set_attribute':
                    attribute = event['attribute']
                    value = event['value']
                    self.player.set_attribute(attribute, value)
                elif event['type'] == 'receive_item':
                    item = event['item']
                    if item in self.player.inventory:
                        self.player.remove_item(item)
                    else:
                        print(f"You don't have the {item}. Can't proceed.")
                        return False
        return True