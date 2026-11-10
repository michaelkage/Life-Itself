"""Bridge repeated cognitive dissonance into gradual identity proposals.

The bridge is read-only. It requires authored mappings from conflict kinds to
identity axes and caller-supplied authoritative event IDs/roles. Acceptance or
rejection remains the responsibility of IdentityDecisionLedger.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Mapping

from .cognitive_dissonance import DissonanceInput
from .identity_evolution import IdentityChangeProposal, NPCIdentityProfile


@dataclass(frozen=True)
class DissonanceIdentityRule:
    policy_id: str
    conflict_kind: str
    identity_axis: str
    coefficient: float
    minimum_conflicts: int = 2
    maximum_delta: float = 0.02

    def __post_init__(self):
        for name in ("policy_id", "identity_axis"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if self.conflict_kind not in ("belief_conflict", "commitment_violation"):
            raise ValueError("unsupported conflict_kind")
        if (isinstance(self.coefficient, bool) or not isinstance(self.coefficient, (int, float))
                or not math.isfinite(self.coefficient) or not -1.0 <= self.coefficient <= 1.0):
            raise ValueError("coefficient must be finite and in [-1, 1]")
        if isinstance(self.minimum_conflicts, bool) or not isinstance(self.minimum_conflicts, int) or self.minimum_conflicts < 1:
            raise ValueError("minimum_conflicts must be a positive integer")
        if (isinstance(self.maximum_delta, bool) or not isinstance(self.maximum_delta, (int, float))
                or not math.isfinite(self.maximum_delta) or not 0.0 < self.maximum_delta <= 0.1):
            raise ValueError("maximum_delta must be in (0, 0.1]")


@dataclass(frozen=True)
class DissonanceIdentityAssessment:
    npc_id: str
    policy_id: str
    axis: str
    conflict_ids: tuple[str, ...]
    evidence_strength: float
    proposal: IdentityChangeProposal


class DissonanceIdentityBridge:
    """Turn repeated unresolved conflict into bounded, explicit trait proposals."""

    @staticmethod
    def propose(
        conflicts: Iterable[DissonanceInput],
        profiles: Iterable[NPCIdentityProfile],
        rules: Iterable[DissonanceIdentityRule],
        *,
        event_id_by_conflict: Mapping[str, str],
        role_by_npc: Mapping[str, str],
    ) -> tuple[DissonanceIdentityAssessment, ...]:
        conflicts, profiles, rules = tuple(conflicts), tuple(profiles), tuple(rules)
        if any(not isinstance(x, DissonanceInput) for x in conflicts):
            raise TypeError("conflicts must contain DissonanceInput values")
        if any(not isinstance(x, NPCIdentityProfile) for x in profiles):
            raise TypeError("profiles must contain NPCIdentityProfile values")
        if any(not isinstance(x, DissonanceIdentityRule) for x in rules):
            raise TypeError("rules must contain DissonanceIdentityRule values")
        if not isinstance(event_id_by_conflict, Mapping) or not isinstance(role_by_npc, Mapping):
            raise TypeError("event and role mappings are required")
        if len({x.conflict_id for x in conflicts}) != len(conflicts):
            raise ValueError("duplicate conflict IDs")
        profile_map = {x.npc_id: x for x in profiles}
        if len(profile_map) != len(profiles):
            raise ValueError("duplicate NPC identity profiles")
        rule_keys = [(x.policy_id, x.conflict_kind) for x in rules]
        if len(set(rule_keys)) != len(rule_keys):
            raise ValueError("duplicate policy/conflict-kind rules")
        grouped = {}
        for conflict in conflicts:
            for rule in rules:
                if conflict.kind == rule.conflict_kind:
                    grouped.setdefault((conflict.owner_id, rule.policy_id, rule.identity_axis), []).append((conflict, rule))
        results = []
        for (npc_id, policy_id, axis), items in sorted(grouped.items()):
            rule = items[0][1]
            if len(items) < rule.minimum_conflicts:
                continue
            profile = profile_map.get(npc_id)
            if profile is None or axis not in profile.traits:
                continue
            ordered = sorted((item for item, _ in items), key=lambda x: (x.tick, x.conflict_id))
            # Repeated unresolved conflicts accumulate, but the proposal is always
            # capped and is never applied here.
            total_pressure = sum(item.score for item in ordered)
            raw_delta = rule.coefficient * min(1.0, total_pressure)
            delta = max(-rule.maximum_delta, min(rule.maximum_delta, raw_delta))
            before = profile.traits[axis]
            after = max(-1.0, min(1.0, before + delta))
            if math.isclose(after, before, abs_tol=1e-15):
                continue
            latest = ordered[-1]
            event_id = event_id_by_conflict.get(latest.conflict_id)
            role = role_by_npc.get(npc_id)
            if not isinstance(event_id, str) or not event_id.strip():
                raise ValueError(f"missing authoritative event ID for conflict {latest.conflict_id}")
            if role not in ("participant", "witness"):
                raise ValueError(f"missing participant/witness role for {npc_id}")
            evidence = min(1.0, total_pressure / len(ordered))
            proposal = IdentityChangeProposal(
                event_id, npc_id, policy_id, axis, before, after, after - before,
                evidence, role, rule.maximum_delta,
            )
            results.append(DissonanceIdentityAssessment(
                npc_id, policy_id, axis, tuple(x.conflict_id for x in ordered),
                evidence, proposal,
            ))
        return tuple(sorted(results, key=lambda x: (x.npc_id, x.axis, x.policy_id)))
