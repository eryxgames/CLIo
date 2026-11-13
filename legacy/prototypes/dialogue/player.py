class Player:
    def __init__(self):
        self.inventory = []
        self.attributes = {}

    def add_item(self, item):
        self.inventory.append(item)

    def remove_item(self, item):
        if item in self.inventory:
            self.inventory.remove(item)
        else:
            raise ValueError(f"Item {item} not in inventory.")

    def set_attribute(self, attribute, value):
        self.attributes[attribute] = value

    def has_item(self, item):
        return item in self.inventory

    def get_attribute(self, attribute):
        return self.attributes.get(attribute)