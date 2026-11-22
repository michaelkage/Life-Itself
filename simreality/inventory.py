"""Deterministic owner-scoped inventory and action-linked material flows."""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from typing import Iterable, Mapping


def _quantity(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError("inventory quantity must be finite and positive")
    return float(value)


@dataclass(frozen=True)
class InventoryTransfer:
    transfer_id: str
    tick: int
    source_owner: str | None
    destination_owner: str | None
    item_id: str
    quantity: float
    reference: str

    def __post_init__(self):
        for name in ("transfer_id", "item_id", "reference"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty text")
        for name in ("source_owner", "destination_owner"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} must be None or non-empty text")
        if self.source_owner is None and self.destination_owner is None:
            raise ValueError("inventory movement must have a source or destination owner")
        if self.source_owner is not None and self.source_owner == self.destination_owner:
            raise ValueError("inventory movement must change ownership or consume stock")
        if isinstance(self.tick, bool) or not isinstance(self.tick, int) or self.tick < 0:
            raise ValueError("tick must be a non-negative integer")
        _quantity(self.quantity)


class InventoryLedger:
    """Replay-safe inventory stock ledger with explicit receipts, transfers and consumption."""

    SCHEMA_VERSION = 1

    def __init__(self, opening_stock: Mapping[tuple[str, str], float] | None = None):
        if opening_stock is not None and not isinstance(opening_stock, Mapping):
            raise TypeError("opening_stock must map (owner_id, item_id) to quantity")
        self._stock: dict[tuple[str, str], float] = {}
        self._transfers: dict[str, InventoryTransfer] = {}
        for key, quantity in (opening_stock or {}).items():
            if not isinstance(key, tuple) or len(key) != 2:
                raise ValueError("inventory stock keys must be (owner_id, item_id) tuples")
            owner, item = key
            if not isinstance(owner, str) or not owner.strip() or not isinstance(item, str) or not item.strip():
                raise ValueError("inventory owner and item IDs must be non-empty")
            if isinstance(quantity, bool) or not isinstance(quantity, (int, float)) or not math.isfinite(quantity) or quantity < 0:
                raise ValueError("opening inventory quantity must be finite and non-negative")
            self._stock[(owner, item)] = float(quantity)

    def quantity(self, owner_id: str, item_id: str) -> float:
        return self._stock.get((owner_id, item_id), 0.0)

    def apply(self, transfer: InventoryTransfer) -> InventoryTransfer:
        if not isinstance(transfer, InventoryTransfer):
            raise TypeError("transfer must be an InventoryTransfer")
        prior = self._transfers.get(transfer.transfer_id)
        if prior is not None:
            if prior != transfer:
                raise ValueError(f"conflicting inventory transfer replay: {transfer.transfer_id}")
            return prior
        source_key = None if transfer.source_owner is None else (transfer.source_owner, transfer.item_id)
        destination_key = None if transfer.destination_owner is None else (transfer.destination_owner, transfer.item_id)
        if source_key is not None and self._stock.get(source_key, 0.0) + 1e-12 < transfer.quantity:
            raise ValueError(f"insufficient inventory: {transfer.source_owner}/{transfer.item_id}")
        if source_key is not None:
            self._stock[source_key] = self._stock.get(source_key, 0.0) - transfer.quantity
        if destination_key is not None:
            self._stock[destination_key] = self._stock.get(destination_key, 0.0) + transfer.quantity
        self._transfers[transfer.transfer_id] = transfer
        return transfer

    def receive(self, receipt_id: str, tick: int, owner_id: str, item_id: str,
                quantity: float, reference: str) -> InventoryTransfer:
        return self.apply(InventoryTransfer(
            receipt_id, tick, None, owner_id, item_id, quantity, reference,
        ))

    def consume(self, consumption_id: str, tick: int, owner_id: str, item_id: str,
                quantity: float, reference: str) -> InventoryTransfer:
        return self.apply(InventoryTransfer(
            consumption_id, tick, owner_id, None, item_id, quantity, reference,
        ))

    def snapshot(self) -> tuple[InventoryTransfer, ...]:
        return tuple(sorted(self._transfers.values(), key=lambda item: (item.tick, item.transfer_id)))

    def stock_snapshot(self) -> tuple[tuple[str, str, float], ...]:
        return tuple((owner, item, self._stock[(owner, item)]) for owner, item in sorted(self._stock))

    def to_json(self) -> str:
        return json.dumps({
            "schema_version": self.SCHEMA_VERSION,
            "stock": [[owner, item, quantity] for owner, item, quantity in self.stock_snapshot()],
            "transfers": [item.__dict__ for item in self.snapshot()],
        }, sort_keys=True, separators=(",", ":"), allow_nan=False)

    def restore_json(self, payload: str) -> None:
        restored = self.from_json(payload)
        self._stock.clear()
        self._stock.update(restored._stock)
        self._transfers.clear()
        self._transfers.update(restored._transfers)

    @classmethod
    def from_json(cls, payload: str) -> "InventoryLedger":
        try:
            raw = json.loads(payload)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid inventory ledger JSON") from exc
        if not isinstance(raw, dict) or set(raw) != {"schema_version", "stock", "transfers"} or raw["schema_version"] != cls.SCHEMA_VERSION:
            raise ValueError("unsupported inventory ledger snapshot")
        stock = {}
        for item in raw["stock"]:
            if not isinstance(item, list) or len(item) != 3:
                raise ValueError("invalid inventory stock record")
            owner, sku, quantity = item
            key = (owner, sku)
            if key in stock:
                raise ValueError("duplicate inventory stock record")
            stock[key] = quantity
        ledger = cls({key: value for key, value in stock.items()})
        for item in raw["transfers"]:
            transfer = InventoryTransfer(**item)
            if transfer.transfer_id in ledger._transfers:
                raise ValueError("duplicate inventory transfer ID")
            ledger._transfers[transfer.transfer_id] = transfer
        return ledger


@dataclass(frozen=True)
class ActionInventoryEffect:
    action_id: str
    effect_id: str
    item_id: str
    quantity: float
    source_owner: str | None
    destination_owner: str | None
    effect_kind: str

    def __post_init__(self):
        for name in ("action_id", "effect_id", "item_id", "effect_kind"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty text")
        _quantity(self.quantity)
        if self.source_owner is None and self.destination_owner is None:
            raise ValueError("inventory effect requires a source or destination owner")
        for name in ("source_owner", "destination_owner"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} must be None or non-empty text")
        if self.source_owner is not None and self.source_owner == self.destination_owner:
            raise ValueError("inventory effect must change ownership or consume stock")


class ActionInventoryAdapter:
    """Apply multiple inventory effects exactly once for completed action executions."""

    def __init__(self, inventory: InventoryLedger, policies: Iterable[ActionInventoryEffect]):
        if not isinstance(inventory, InventoryLedger):
            raise TypeError("inventory must be an InventoryLedger")
        values = tuple(policies)
        if any(not isinstance(item, ActionInventoryEffect) for item in values):
            raise TypeError("policies must contain ActionInventoryEffect values")
        if len({(item.action_id, item.effect_id) for item in values}) != len(values):
            raise ValueError("inventory effect IDs must be unique per action")
        self.inventory = inventory
        grouped = {}
        for item in values:
            grouped.setdefault(item.action_id, []).append(item)
        self.policies = {
            action_id: tuple(sorted(items, key=lambda item: item.effect_id))
            for action_id, items in grouped.items()
        }
        self._applied: dict[str, tuple[str, ...]] = {}

    def apply_all(self, execution, tick: int) -> tuple[InventoryTransfer, ...]:
        from .action_execution import ActionExecution
        if not isinstance(execution, ActionExecution):
            raise TypeError("execution must be an ActionExecution")
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < 0:
            raise ValueError("tick must be a non-negative integer")
        if isinstance(execution.tick, bool) or not isinstance(execution.tick, int) or execution.tick < 0 or tick < execution.tick:
            raise ValueError("inventory effect tick cannot precede action completion")
        if execution.status != "completed":
            return ()
        prior = self._applied.get(execution.execution_id)
        if prior is not None:
            return tuple(self.inventory._transfers[item] for item in prior)
        effects = self.policies.get(execution.action_id, ())
        if not effects:
            return ()
        debits = {}
        transfers = []
        for effect in effects:
            if effect.source_owner is not None:
                key = (effect.source_owner, effect.item_id)
                debits[key] = debits.get(key, 0.0) + effect.quantity
            transfers.append(InventoryTransfer(
                f"action:{execution.execution_id}:{effect.effect_id}",
                tick, effect.source_owner, effect.destination_owner,
                effect.item_id, effect.quantity,
                f"action:{execution.execution_id}:{effect.effect_kind}",
            ))
        for (owner, item), quantity in debits.items():
            if self.inventory.quantity(owner, item) + 1e-12 < quantity:
                raise ValueError(f"insufficient inventory: {owner}/{item}")
        for transfer in transfers:
            prior_transfer = self.inventory._transfers.get(transfer.transfer_id)
            if prior_transfer is not None and prior_transfer != transfer:
                raise ValueError(f"conflicting inventory transfer replay: {transfer.transfer_id}")
        applied = tuple(self.inventory.apply(item) for item in transfers)
        self._applied[execution.execution_id] = tuple(item.transfer_id for item in applied)
        return applied
