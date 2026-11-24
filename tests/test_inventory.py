"""Inventory ledger and action-effect adapter tests."""
import unittest

from simreality.action_execution import ActionExecution
from simreality.inventory import (
    ActionInventoryAdapter, ActionInventoryEffect, InventoryLedger, InventoryTransfer,
)


class InventoryLedgerTests(unittest.TestCase):
    def setUp(self):
        self.inventory = InventoryLedger({
            ("store", "meal"): 20.0,
            ("npc-a", "meal"): 0.0,
        })

    def test_receipt_transfer_and_consumption_are_replay_safe(self):
        receipt = self.inventory.receive("receipt-1", 1, "store", "meal", 5, "restock")
        self.assertEqual(self.inventory.receive("receipt-1", 1, "store", "meal", 5, "restock"), receipt)
        transfer = self.inventory.apply(
            InventoryTransfer("transfer-1", 2, "store", "npc-a", "meal", 3, "purchase")
        )
        self.assertEqual(self.inventory.apply(transfer), transfer)
        consumed = self.inventory.consume("consume-1", 3, "npc-a", "meal", 1, "breakfast")
        self.assertEqual(consumed.destination_owner, None)
        self.assertEqual(self.inventory.quantity("store", "meal"), 22.0)
        self.assertEqual(self.inventory.quantity("npc-a", "meal"), 2.0)
        self.assertEqual(len(self.inventory.snapshot()), 3)

    def test_insufficient_stock_does_not_create_a_transfer(self):
        with self.assertRaisesRegex(ValueError, "insufficient inventory"):
            self.inventory.consume("consume-too-much", 1, "npc-a", "meal", 1, "meal")
        self.assertEqual(self.inventory.snapshot(), ())
        self.assertEqual(self.inventory.quantity("npc-a", "meal"), 0.0)

    def test_action_inventory_effects_apply_once_and_checkpoint(self):
        adapter = ActionInventoryAdapter(self.inventory, (
            ActionInventoryEffect("work", "ration", "meal", 2, "store", "npc-a", "ration_award"),
        ))
        execution = ActionExecution(
            "exec-ration", "npc-a", 1, "work", "completed", "done",
            (), (), (), (), "event-ration",
        )
        first = adapter.apply_all(execution, 1)
        self.assertEqual(len(first), 1)
        self.assertEqual(self.inventory.quantity("store", "meal"), 18.0)
        self.assertEqual(self.inventory.quantity("npc-a", "meal"), 2.0)
        self.assertEqual(adapter.apply_all(execution, 1), first)
        restored = InventoryLedger.from_json(self.inventory.to_json())
        self.assertEqual(restored.stock_snapshot(), self.inventory.stock_snapshot())
        self.assertEqual(restored.snapshot(), self.inventory.snapshot())

    def test_atomic_batch_nets_same_batch_receipts_before_outgoing_stock(self):
        inventory = InventoryLedger({
            ("supplier", "meal"): 5.0,
            ("store", "meal"): 0.0,
            ("npc-a", "meal"): 0.0,
        })
        adapter = ActionInventoryAdapter(inventory, (
            ActionInventoryEffect("work", "a-sale", "meal", 4, "store", "npc-a", "sale"),
            ActionInventoryEffect("work", "z-restock", "meal", 5, "supplier", "store", "restock"),
        ))
        execution = ActionExecution(
            "exec-netted", "npc-a", 1, "work", "completed", "done",
            (), (), (), (), "event-netted",
        )
        applied = adapter.apply_all(execution, 1)
        self.assertEqual(tuple(item.transfer_id for item in applied), (
            "action:exec-netted:a-sale", "action:exec-netted:z-restock",
        ))
        self.assertEqual(inventory.quantity("supplier", "meal"), 0.0)
        self.assertEqual(inventory.quantity("store", "meal"), 1.0)
        self.assertEqual(inventory.quantity("npc-a", "meal"), 4.0)

    def test_conflicting_transfer_replay_preflight_leaves_batch_unchanged(self):
        inventory = InventoryLedger({("store", "meal"): 5.0, ("npc-a", "meal"): 0.0})
        original = InventoryTransfer("existing", 1, "store", "npc-a", "meal", 1, "purchase")
        inventory.apply(original)
        before_stock = inventory.stock_snapshot()
        with self.assertRaisesRegex(ValueError, "conflicting inventory transfer replay"):
            inventory.apply_many((
                InventoryTransfer("new", 2, "store", "npc-a", "meal", 1, "purchase"),
                InventoryTransfer("existing", 2, "store", "npc-a", "meal", 2, "different"),
            ))
        self.assertEqual(inventory.stock_snapshot(), before_stock)
        self.assertEqual(tuple(item.transfer_id for item in inventory.snapshot()), ("existing",))

    def test_multi_effect_inventory_preflights_all_debits(self):
        adapter = ActionInventoryAdapter(self.inventory, (
            ActionInventoryEffect("work", "one", "meal", 15, "store", "npc-a", "award"),
            ActionInventoryEffect("work", "two", "meal", 10, "store", "npc-a", "award"),
        ))
        execution = ActionExecution(
            "exec-short", "npc-a", 1, "work", "completed", "done",
            (), (), (), (), "event-short",
        )
        with self.assertRaisesRegex(ValueError, "insufficient inventory"):
            adapter.apply_all(execution, 1)
        self.assertEqual(self.inventory.quantity("store", "meal"), 20.0)
        self.assertEqual(self.inventory.quantity("npc-a", "meal"), 0.0)
        self.assertEqual(self.inventory.snapshot(), ())


if __name__ == "__main__":
    unittest.main()
