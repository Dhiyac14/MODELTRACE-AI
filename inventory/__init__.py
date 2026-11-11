"""Model inventory and SS1/23 risk tiering (Person 2).

When merging with ml-engineering, keep this file: Person 1's version imports ModelInventory and
ModelRecord from inventory.registry, which this registry replaces with InventoryRecord.
"""
from .registry import InventoryRecord, load_inventory, save_inventory

__all__ = ["InventoryRecord", "load_inventory", "save_inventory"]
