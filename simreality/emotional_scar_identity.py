"""Evidence-grounded bridge from accepted emotional scars to identity proposals.

Scars can inform a possible identity reassessment, but this adapter never
changes an identity profile or records an NPC decision. The NPC must still
explicitly accept or reject the resulting identity proposal.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from .emotional_scars import NPCEmotionalScarLedger
from .identity_decisions import IdentityDecisionLedger
from .identity_evolution import IdentityChangeProposal
from .world_events import WorldEventLedger


@dataclass(frozen=True)
class ScarIdentityPolicy:
    policy_id: str
    emotion_axis: str
    cue_id: str
    identity_axis: str
    delta_per_severity: float
    minimum_severity: float = 0.1
    maximum_delta: float = 0.05
    include_witnesses: bool = True

    def __post_init__(self):
        for name in ("policy_id", "emotion_axis", "cue_id", "identity_axis"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        for name, value, low, high, exclusive in (
            ("delta_per_severity", self.delta_per_severity, -1.0, 1.0, False),
            ("minimum_severity", self.minimum_severity, 0.0, 1.0, False),
            ("maximum_delta", self.maximum_delta, 0.0, 0.1, True),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
            if value < low or value > high or (exclusive and value == low):
                raise ValueError(f"{name} is outside its permitted range")
        if not isinstance(self.include_witnesses, bool):
            raise TypeError("include_witnesses must be bool")


class EmotionalScarIdentityAdapter:
    """Convert active accepted scars into bounded, read-only identity proposals."""

    @staticmethod
    def propose(scars: NPCEmotionalScarLedger, identities: IdentityDecisionLedger,
                events: WorldEventLedger, policies, tick: int):
        if not isinstance(scars, NPCEmotionalScarLedger):
            raise TypeError("scars must be NPCEmotionalScarLedger")
        if not isinstance(identities, IdentityDecisionLedger):
            raise TypeError("identities must be IdentityDecisionLedger")
        if not isinstance(events, WorldEventLedger):
            raise TypeError("events must be WorldEventLedger")
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < scars.current_tick or tick < max((event.tick for event in events.snapshot()), default=0):
            raise ValueError("tick cannot precede scar or event history")
        policies = tuple(policies)
        if any(not isinstance(p, ScarIdentityPolicy) for p in policies):
            raise TypeError("policies must contain ScarIdentityPolicy values")
        if len({p.policy_id for p in policies}) != len(policies):
            raise ValueError("duplicate scar identity policy")
        profiles = {p.npc_id: p for p in identities.profiles()}
        journal = {e.event_id: e for e in events.snapshot()}
        result = []
        for scar in scars.scars():
            if scar.owner_id not in profiles:
                continue
            source = journal.get(scar.source_event_id)
            if source is None or source.tick > scar.created_tick:
                continue
            if scar.owner_id in source.participants:
                role = "participant"
            elif scar.owner_id in source.witnesses:
                role = "witness"
            else:
                continue
            for policy in sorted(policies, key=lambda p: p.policy_id):
                if (scar.emotion_axis != policy.emotion_axis or scar.cue_id != policy.cue_id
                        or (role == "witness" and not policy.include_witnesses)):
                    continue
                severity = scars.severity_for(scar.scar_id, tick)
                if severity < policy.minimum_severity:
                    continue
                profile = profiles[scar.owner_id]
                if policy.identity_axis not in profile.traits:
                    continue
                sensitivity = (profile.sensitivities or {}).get(policy.identity_axis, 1.0)
                raw = policy.delta_per_severity * severity * sensitivity
                delta = max(-policy.maximum_delta, min(policy.maximum_delta, raw))
                before = profile.traits[policy.identity_axis]
                after = max(-1.0, min(1.0, before + delta))
                delta = after - before
                if delta == 0:
                    continue
                # Each scar receives a distinct policy key because the identity
                # decision ledger indexes decisions by event/NPC/policy.
                proposal_policy_id = f"{policy.policy_id}:{scar.scar_id}"
                result.append(IdentityChangeProposal(
                    scar.source_event_id, scar.owner_id, proposal_policy_id,
                    policy.identity_axis, before, after, delta, severity, role,
                    policy.maximum_delta,
                ))
        return tuple(sorted(result, key=lambda p: (
            p.event_id, p.npc_id, p.policy_id, p.axis,
        )))
