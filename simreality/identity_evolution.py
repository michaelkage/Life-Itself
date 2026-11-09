"""Deterministic, read-only proposals for gradual NPC identity change."""
from dataclasses import dataclass
from typing import Iterable, Mapping
import math
from types import MappingProxyType
from .world_events import WorldEvent


@dataclass(frozen=True)
class NPCIdentityProfile:
    npc_id: str
    traits: Mapping[str, float]
    sensitivities: Mapping[str, float] | None = None

    def __post_init__(self):
        if not isinstance(self.npc_id, str) or not self.npc_id.strip():
            raise ValueError("npc_id must be non-empty")
        for values, low, high in ((self.traits, -1.0, 1.0),
                                  (self.sensitivities or {}, 0.0, 2.0)):
            if not isinstance(values, Mapping):
                raise ValueError("identity axes must be mappings")
            for key, value in values.items():
                if (not isinstance(key, str) or not key.strip()
                    or isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or not low <= value <= high):
                    raise ValueError("invalid identity axis")
        object.__setattr__(self, "traits", MappingProxyType(dict(self.traits)))
        if self.sensitivities is not None:
            object.__setattr__(self, "sensitivities", MappingProxyType(dict(self.sensitivities)))


@dataclass(frozen=True)
class IdentityChangePolicy:
    policy_id: str
    event_type: str
    axis: str
    delta: float
    strength_attribute: str | None = None
    minimum_strength: float = 0.0
    maximum_delta: float = 0.05
    include_witnesses: bool = True

    def __post_init__(self):
        if not all(isinstance(v, str) and v.strip()
                   for v in (self.policy_id, self.event_type, self.axis)):
            raise ValueError("policy identifiers must be non-empty")
        if self.strength_attribute is not None and (
                not isinstance(self.strength_attribute, str) or not self.strength_attribute.strip()):
            raise ValueError("strength_attribute must be None or a non-empty string")
        if not isinstance(self.include_witnesses, bool):
            raise TypeError("include_witnesses must be bool")
        for name, value, low, high, inclusive_low in (
            ("delta", self.delta, -1.0, 1.0, True),
            ("minimum_strength", self.minimum_strength, 0.0, 1.0, True),
            ("maximum_delta", self.maximum_delta, 0.0, 0.1, False),
        ):
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    or (value < low if inclusive_low else value <= low)
                    or value > high):
                interval = "[-1, 1]" if name == "delta" else (
                    "[0, 1]" if name == "minimum_strength" else "(0, 0.1]")
                raise ValueError(f"{name} must be in {interval}")


@dataclass(frozen=True)
class IdentityChangeProposal:
    event_id: str
    npc_id: str
    policy_id: str
    axis: str
    before: float
    after: float
    delta: float
    evidence_strength: float
    role: str
    maximum_delta: float = 0.05

    def __post_init__(self):
        for name in ("event_id", "npc_id", "policy_id", "axis"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if self.role not in ("participant", "witness"):
            raise ValueError("role must be participant or witness")
        for name in ("before", "after", "delta", "evidence_strength", "maximum_delta"):
            value = getattr(self, name)
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value)):
                raise ValueError(f"{name} must be finite numeric")
        if not -1.0 <= self.before <= 1.0 or not -1.0 <= self.after <= 1.0:
            raise ValueError("trait values must be in [-1, 1]")
        if not 0.0 < self.maximum_delta <= 0.1:
            raise ValueError("maximum_delta must be in (0, 0.1]")
        if not -self.maximum_delta <= self.delta <= self.maximum_delta:
            raise ValueError("delta exceeds maximum_delta")
        if not 0.0 <= self.evidence_strength <= 1.0:
            raise ValueError("evidence_strength must be in [0, 1]")
        if not math.isclose(self.after - self.before, self.delta, abs_tol=1e-12):
            raise ValueError("delta must match proposed trait change")


class IdentityEvolutionEvaluator:
    """Evaluate explicit event policies without mutating identity profiles."""

    def __init__(self, profiles: Iterable[NPCIdentityProfile],
                 policies: Iterable[IdentityChangePolicy]):
        profiles, policies = tuple(profiles), tuple(policies)
        if any(not isinstance(profile, NPCIdentityProfile) for profile in profiles):
            raise TypeError("profiles must contain NPCIdentityProfile values")
        if any(not isinstance(policy, IdentityChangePolicy) for policy in policies):
            raise TypeError("policies must contain IdentityChangePolicy values")
        if len({p.npc_id for p in profiles}) != len(profiles):
            raise ValueError("duplicate NPC profile")
        if len({p.policy_id for p in policies}) != len(policies):
            raise ValueError("duplicate identity policy")
        self.profiles = {p.npc_id: p for p in profiles}
        self.policies = tuple(sorted(policies, key=lambda p: p.policy_id))

    def assess(self, events: Iterable[WorldEvent]) -> tuple[IdentityChangeProposal, ...]:
        events = tuple(events)
        if any(not isinstance(e, WorldEvent) for e in events):
            raise TypeError("events must be WorldEvent values")
        if len({e.event_id for e in events}) != len(events):
            raise ValueError("duplicate event IDs in batch")
        result = []
        for event in sorted(events, key=lambda e: (e.tick, e.event_id)):
            attrs = dict(event.attributes)
            for policy in self.policies:
                if event.event_type != policy.event_type:
                    continue
                strength = 1.0 if policy.strength_attribute is None else attrs.get(policy.strength_attribute)
                if (isinstance(strength, bool) or not isinstance(strength, (int, float))
                    or not math.isfinite(strength) or not 0 <= strength <= 1
                    or strength < policy.minimum_strength):
                    continue
                for npc_id, profile in sorted(self.profiles.items()):
                    if npc_id in event.participants:
                        role = "participant"
                    elif policy.include_witnesses and npc_id in event.witnesses:
                        role = "witness"
                    else:
                        continue
                    if policy.axis not in profile.traits:
                        continue
                    sensitivity = (profile.sensitivities or {}).get(policy.axis, 1.0)
                    raw = policy.delta * sensitivity * strength
                    shift = max(-policy.maximum_delta, min(policy.maximum_delta, raw))
                    before = profile.traits[policy.axis]
                    after = max(-1.0, min(1.0, before + shift))
                    if after != before:
                        result.append(IdentityChangeProposal(
                            event.event_id, npc_id, policy.policy_id, policy.axis,
                            before, after, after - before, float(strength), role,
                            policy.maximum_delta))
        return tuple(sorted(result, key=lambda p: (
            p.event_id, p.npc_id, p.axis, p.policy_id)))
