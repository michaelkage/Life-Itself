"""Checkpointable mutable world facts and resources consumed by NPC actions.

The object owns the authoritative per-NPC action state. Nested sets and dictionaries
are restored in place so action adapters and simulation systems keep live references.
"""
from __future__ import annotations

import json
import math
from typing import Mapping


class ActionWorldState:
    """Live, checkpointable fact and resource state for action execution."""

    SCHEMA_VERSION = 1

    def __init__(
        self,
        world_facts_by_owner: Mapping[str, set[str]] | None = None,
        resources_by_owner: Mapping[str, dict[str, float]] | None = None,
    ) -> None:
        facts = {} if world_facts_by_owner is None else world_facts_by_owner
        resources = {} if resources_by_owner is None else resources_by_owner
        if not isinstance(facts, Mapping) or not isinstance(resources, Mapping):
            raise TypeError("action facts and resources must be mappings")
        if set(facts) != set(resources):
            raise ValueError("action facts and resources must cover the same owners")
        self.world_facts_by_owner: dict[str, set[str]] = {}
        self.resources_by_owner: dict[str, dict[str, float]] = {}
        for owner in sorted(facts):
            self._validate_owner(owner)
            if not isinstance(facts[owner], set):
                raise TypeError("world facts must be mutable sets")
            if not isinstance(resources[owner], dict):
                raise TypeError("resources must be mutable dictionaries")
            self._validate_facts(facts[owner])
            self._validate_resources(resources[owner])
            self.world_facts_by_owner[owner] = facts[owner]
            self.resources_by_owner[owner] = resources[owner]

    @staticmethod
    def _validate_owner(owner: str) -> None:
        if not isinstance(owner, str) or not owner.strip():
            raise ValueError("action state owner IDs must be non-empty strings")

    @staticmethod
    def _validate_facts(facts: set[str]) -> None:
        if any(not isinstance(fact, str) or not fact.strip() for fact in facts):
            raise ValueError("world facts must contain non-empty strings")

    @staticmethod
    def _validate_resources(resources: dict[str, float]) -> None:
        for name, amount in resources.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError("resource names must be non-empty strings")
            if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount) or amount < 0:
                raise ValueError("resource balances must be finite and non-negative")

    def ensure_owner(self, owner_id: str, *, world_facts: set[str] | None = None,
                     resources: dict[str, float] | None = None) -> None:
        self._validate_owner(owner_id)
        facts = set() if world_facts is None else world_facts
        balances = {} if resources is None else resources
        if not isinstance(facts, set) or not isinstance(balances, dict):
            raise TypeError("owner facts/resources must be a mutable set and dictionary")
        self._validate_facts(facts)
        self._validate_resources(balances)
        prior_facts = self.world_facts_by_owner.get(owner_id)
        prior_resources = self.resources_by_owner.get(owner_id)
        if prior_facts is not None and prior_facts is not facts and prior_facts != facts:
            raise ValueError(f"conflicting world facts for owner: {owner_id}")
        if prior_resources is not None and prior_resources is not balances and prior_resources != balances:
            raise ValueError(f"conflicting resources for owner: {owner_id}")
        self.world_facts_by_owner.setdefault(owner_id, facts)
        self.resources_by_owner.setdefault(owner_id, balances)

    def to_json(self) -> str:
        owners = []
        for owner in sorted(self.world_facts_by_owner):
            facts = self.world_facts_by_owner[owner]
            resources = self.resources_by_owner[owner]
            self._validate_facts(facts)
            self._validate_resources(resources)
            owners.append({
                "owner_id": owner,
                "world_facts": sorted(facts),
                "resources": [[name, resources[name]] for name in sorted(resources)],
            })
        return json.dumps(
            {"schema_version": self.SCHEMA_VERSION, "owners": owners},
            sort_keys=True, separators=(",", ":"), allow_nan=False,
        )

    def restore_json(self, payload: str) -> None:
        try:
            raw = json.loads(payload)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid action world-state checkpoint JSON") from exc
        if not isinstance(raw, dict) or set(raw) != {"schema_version", "owners"} or raw["schema_version"] != self.SCHEMA_VERSION or not isinstance(raw["owners"], list):
            raise ValueError("unsupported action world-state checkpoint")
        restored = {}
        for item in raw["owners"]:
            if not isinstance(item, dict) or set(item) != {"owner_id", "world_facts", "resources"}:
                raise ValueError("malformed action world-state owner checkpoint")
            owner = item["owner_id"]
            self._validate_owner(owner)
            if owner in restored:
                raise ValueError("duplicate action world-state owner")
            facts = item["world_facts"]
            resources = item["resources"]
            if not isinstance(facts, list) or any(not isinstance(fact, str) or not fact.strip() for fact in facts) or len(facts) != len(set(facts)):
                raise ValueError("invalid action world-state facts")
            if not isinstance(resources, list):
                raise ValueError("invalid action world-state resources")
            balance_map = {}
            for pair in resources:
                if not isinstance(pair, list) or len(pair) != 2:
                    raise ValueError("invalid action world-state resource entry")
                name, amount = pair
                if name in balance_map:
                    raise ValueError("duplicate action world-state resource")
                balance_map[name] = amount
            self._validate_resources(balance_map)
            restored[owner] = (set(facts), balance_map)
        self.world_facts_by_owner.clear()
        self.resources_by_owner.clear()
        for owner, (facts, resources) in restored.items():
            self.world_facts_by_owner[owner] = facts
            self.resources_by_owner[owner] = resources

    @classmethod
    def from_json(cls, payload: str) -> "ActionWorldState":
        state = cls()
        state.restore_json(payload)
        return state
