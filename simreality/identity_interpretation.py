"""Belief-conditioned interpretation of identity-change proposals.

Beliefs alter how an NPC interprets an event; they do not force acceptance.
The resulting proposal still requires an explicit decision in IdentityDecisionLedger.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from types import MappingProxyType
from typing import Iterable, Mapping

from .model import NPC

from .beliefs import BeliefLedger
from .identity_evolution import IdentityChangeProposal
from .social_beliefs import SocialBeliefSystem
from .social_trust import SocialTrustLedger


@dataclass(frozen=True)
class IdentityInterpretationRule:
    policy_id: str
    claim_id: str
    coefficient: float

    def __post_init__(self):
        if not isinstance(self.policy_id, str) or not self.policy_id.strip():
            raise ValueError("policy_id must be a non-empty string")
        if not isinstance(self.claim_id, str) or not self.claim_id.strip():
            raise ValueError("claim_id must be a non-empty string")
        if (isinstance(self.coefficient, bool)
                or not isinstance(self.coefficient, (int, float))
                or not math.isfinite(self.coefficient)
                or not -1.0 <= self.coefficient <= 1.0):
            raise ValueError("coefficient must be finite and in [-1, 1]")


@dataclass(frozen=True)
class InterpretedIdentityChange:
    original: IdentityChangeProposal
    interpreted: IdentityChangeProposal
    belief_contributions: tuple[tuple[str, float, float], ...]
    memory_contributions: tuple[tuple[int, float, float], ...] = ()
    relationship_contributions: tuple[tuple[str, float, float], ...] = ()
    personality_contributions: tuple[tuple[str, float, float], ...] = ()


@dataclass(frozen=True)
class NPCIdentityPersonality:
    """Bounded, individual personality axes used only when explicitly mapped.

    Axis values are normalized to [-1, 1]. The model does not prescribe a
    universal personality taxonomy; projects define axes such as fearfulness,
    confidence, stubbornness, openness, or sociability.
    """
    npc_id: str
    axes: Mapping[str, float]

    def __post_init__(self):
        if not isinstance(self.npc_id, str) or not self.npc_id.strip():
            raise ValueError("npc_id must be a non-empty string")
        if not isinstance(self.axes, Mapping):
            raise ValueError("axes must be a mapping")
        copied = dict(self.axes)
        for axis, value in copied.items():
            if not isinstance(axis, str) or not axis.strip():
                raise ValueError("personality axis names must be non-empty strings")
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or not -1.0 <= value <= 1.0):
                raise ValueError(f"personality axis {axis!r} must be finite and in [-1, 1]")
        object.__setattr__(self, "axes", MappingProxyType(copied))


@dataclass(frozen=True)
class IdentityPersonalityRule:
    """Map one normalized personality axis to one identity policy."""
    policy_id: str
    personality_axis: str
    coefficient: float

    def __post_init__(self):
        if not isinstance(self.policy_id, str) or not self.policy_id.strip():
            raise ValueError("policy_id must be a non-empty string")
        if not isinstance(self.personality_axis, str) or not self.personality_axis.strip():
            raise ValueError("personality_axis must be a non-empty string")
        if (isinstance(self.coefficient, bool) or not isinstance(self.coefficient, (int, float))
                or not math.isfinite(self.coefficient) or not -1.0 <= self.coefficient <= 1.0):
            raise ValueError("coefficient must be finite and in [-1, 1]")


@dataclass(frozen=True)
class IdentityRelationshipAssociation:
    """Explicitly connect an NPC's trust in another person to an event appraisal."""
    event_id: str
    npc_id: str
    policy_id: str
    target_id: str
    coefficient: float
    relevance_scale: float = 1.0

    def __post_init__(self):
        for name in ("event_id", "npc_id", "policy_id", "target_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if self.npc_id == self.target_id:
            raise ValueError("an NPC cannot have a relationship with itself")
        if (isinstance(self.coefficient, bool) or not isinstance(self.coefficient, (int, float))
                or not math.isfinite(self.coefficient) or not -1.0 <= self.coefficient <= 1.0):
            raise ValueError("coefficient must be finite and in [-1, 1]")
        if (isinstance(self.relevance_scale, bool) or not isinstance(self.relevance_scale, (int, float))
                or not math.isfinite(self.relevance_scale) or not 0.0 <= self.relevance_scale <= 1.0):
            raise ValueError("relevance_scale must be finite and in [0, 1]")


@dataclass(frozen=True)
class IdentityMemoryAssociation:
    """Explicitly link one NPC memory to one event/policy interpretation.

    The association is authored by the simulation because NPCMemory does not
    claim to know which later event it should influence. Retention scales the
    effect; coefficient supplies its signed meaning.
    """
    event_id: str
    npc_id: str
    policy_id: str
    memory_index: int
    coefficient: float
    relevance_scale: float = 1.0

    def __post_init__(self):
        for name in ("event_id", "npc_id", "policy_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if isinstance(self.memory_index, bool) or not isinstance(self.memory_index, int) or self.memory_index < 0:
            raise ValueError("memory_index must be a non-negative integer")
        if (isinstance(self.coefficient, bool) or not isinstance(self.coefficient, (int, float))
                or not math.isfinite(self.coefficient) or not -1.0 <= self.coefficient <= 1.0):
            raise ValueError("coefficient must be finite and in [-1, 1]")
        if (isinstance(self.relevance_scale, bool) or not isinstance(self.relevance_scale, (int, float))
                or not math.isfinite(self.relevance_scale) or not 0.0 <= self.relevance_scale <= 1.0):
            raise ValueError("relevance_scale must be finite and in [0, 1]")


class IdentityBeliefInterpreter:
    """Apply explicit per-policy belief effects to each NPC's proposal.

    Each rule contributes coefficient * (2 * confidence - 1) to the proposed
    trait delta. Confidence 0.5 is neutral; confidence 1 and 0 contribute the
    positive and negative coefficient respectively. Contributions are summed,
    then the original policy's per-event delta cap and trait bounds are retained.
    Missing NPC ledgers or claims are neutral rather than guessed.
    """

    def __init__(self, rules: Iterable[IdentityInterpretationRule]):
        rules = tuple(rules)
        if any(not isinstance(rule, IdentityInterpretationRule) for rule in rules):
            raise TypeError("rules must contain IdentityInterpretationRule values")
        keys = [(rule.policy_id, rule.claim_id) for rule in rules]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate policy/claim interpretation rule")
        self.rules = tuple(sorted(rules, key=lambda r: (r.policy_id, r.claim_id)))

    def interpret_with_memories(
        self,
        proposals: Iterable[IdentityChangeProposal],
        npcs_by_id: Mapping[str, NPC],
        associations: Iterable[IdentityMemoryAssociation],
        beliefs_by_npc: Mapping[str, BeliefLedger] | None = None,
    ) -> tuple[InterpretedIdentityChange, ...]:
        """Combine belief appraisal with explicitly linked personal memories.

        Each memory contributes coefficient * retained_strength * relevance.
        No event-to-memory relationship is inferred: callers must provide an
        association with matching event, NPC and policy IDs. Missing links are
        neutral. All effects remain bounded by the original proposal cap.
        """
        if not isinstance(npcs_by_id, Mapping):
            raise TypeError("npcs_by_id must be a mapping")
        for npc_id, npc in npcs_by_id.items():
            if not isinstance(npc_id, str) or not npc_id.strip() or not isinstance(npc, NPC):
                raise TypeError("npcs_by_id must map non-empty IDs to NPC instances")
            if npc.entity_id != npc_id:
                raise ValueError("NPC mapping key must match NPC entity_id")
        items = tuple(associations)
        if any(not isinstance(item, IdentityMemoryAssociation) for item in items):
            raise TypeError("associations must contain IdentityMemoryAssociation values")
        keys = [(x.event_id, x.npc_id, x.policy_id, x.memory_index) for x in items]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate identity memory association")
        proposals = tuple(proposals)
        base = self.interpret(proposals, beliefs_by_npc or {})
        grouped: dict[tuple[str, str, str], list[IdentityMemoryAssociation]] = {}
        for item in items:
            grouped.setdefault((item.event_id, item.npc_id, item.policy_id), []).append(item)
        results = []
        for result in base:
            proposal = result.interpreted
            contributions = []
            adjustment = 0.0
            for item in sorted(grouped.get((proposal.event_id, proposal.npc_id, proposal.policy_id), ()),
                               key=lambda x: x.memory_index):
                npc = npcs_by_id.get(item.npc_id)
                if npc is None:
                    continue
                if item.memory_index >= len(npc.memories):
                    raise ValueError(f"memory index out of range for {item.npc_id}: {item.memory_index}")
                retention = npc.memories[item.memory_index].retention
                contribution = item.coefficient * retention * item.relevance_scale
                adjustment += contribution
                contributions.append((item.memory_index, retention, contribution))
            maximum = proposal.maximum_delta
            delta = max(-maximum, min(maximum, proposal.delta + adjustment))
            after = max(-1.0, min(1.0, proposal.before + delta))
            interpreted = IdentityChangeProposal(
                proposal.event_id, proposal.npc_id, proposal.policy_id, proposal.axis,
                proposal.before, after, after - proposal.before,
                proposal.evidence_strength, proposal.role, maximum,
            )
            results.append(InterpretedIdentityChange(
                result.original, interpreted, result.belief_contributions, tuple(contributions)))
        return tuple(results)

    def interpret_with_personality(
        self,
        proposals: Iterable[IdentityChangeProposal],
        personalities_by_npc: Mapping[str, NPCIdentityPersonality],
        rules: Iterable[IdentityPersonalityRule],
        beliefs_by_npc: Mapping[str, BeliefLedger] | None = None,
    ) -> tuple[InterpretedIdentityChange, ...]:
        """Apply explicit personality-axis effects after belief appraisal.

        Each matching axis contributes coefficient * normalized_axis_value.
        Missing profiles or axes are neutral. Contributions are transparent,
        deterministic, and bounded by the proposal's original delta cap.
        """
        if not isinstance(personalities_by_npc, Mapping):
            raise TypeError("personalities_by_npc must be a mapping")
        for npc_id, profile in personalities_by_npc.items():
            if not isinstance(npc_id, str) or not npc_id.strip():
                raise ValueError("personality map NPC IDs must be non-empty strings")
            if not isinstance(profile, NPCIdentityPersonality):
                raise TypeError("personality map values must be NPCIdentityPersonality instances")
            if profile.npc_id != npc_id:
                raise ValueError("personality mapping key must match profile npc_id")
        rule_items = tuple(rules)
        if any(not isinstance(rule, IdentityPersonalityRule) for rule in rule_items):
            raise TypeError("rules must contain IdentityPersonalityRule values")
        rule_keys = [(rule.policy_id, rule.personality_axis) for rule in rule_items]
        if len(rule_keys) != len(set(rule_keys)):
            raise ValueError("duplicate policy/personality-axis rule")
        grouped: dict[str, list[IdentityPersonalityRule]] = {}
        for rule in sorted(rule_items, key=lambda item: (item.policy_id, item.personality_axis)):
            grouped.setdefault(rule.policy_id, []).append(rule)
        base = self.interpret(tuple(proposals), beliefs_by_npc or {})
        results = []
        for result in base:
            proposal = result.interpreted
            profile = personalities_by_npc.get(proposal.npc_id)
            contributions = []
            adjustment = 0.0
            for rule in grouped.get(proposal.policy_id, ()):
                value = profile.axes.get(rule.personality_axis, 0.0) if profile else 0.0
                contribution = rule.coefficient * value
                adjustment += contribution
                contributions.append((rule.personality_axis, value, contribution))
            maximum = proposal.maximum_delta
            delta = max(-maximum, min(maximum, proposal.delta + adjustment))
            after = max(-1.0, min(1.0, proposal.before + delta))
            interpreted = IdentityChangeProposal(
                proposal.event_id, proposal.npc_id, proposal.policy_id, proposal.axis,
                proposal.before, after, after - proposal.before,
                proposal.evidence_strength, proposal.role, maximum,
            )
            results.append(InterpretedIdentityChange(
                result.original, interpreted, result.belief_contributions,
                result.memory_contributions, result.relationship_contributions,
                tuple(contributions)))
        return tuple(results)

    def interpret_with_relationships(
        self,
        proposals: Iterable[IdentityChangeProposal],
        trust: SocialTrustLedger,
        associations: Iterable[IdentityRelationshipAssociation],
        beliefs_by_npc: Mapping[str, BeliefLedger] | None = None,
    ) -> tuple[InterpretedIdentityChange, ...]:
        """Apply explicit observer-to-target trust effects to identity appraisals.

        Trust 0.5 is neutral. Unknown pairs are neutral rather than assigned an
        invented value. The method is read-only and retains the proposal delta cap.
        """
        if not isinstance(trust, SocialTrustLedger):
            raise TypeError("trust must be a SocialTrustLedger")
        items = tuple(associations)
        if any(not isinstance(item, IdentityRelationshipAssociation) for item in items):
            raise TypeError("associations must contain IdentityRelationshipAssociation values")
        keys = [(x.event_id, x.npc_id, x.policy_id, x.target_id) for x in items]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate identity relationship association")
        proposals = tuple(proposals)
        base = self.interpret(proposals, beliefs_by_npc or {})
        grouped: dict[tuple[str, str, str], list[IdentityRelationshipAssociation]] = {}
        for item in items:
            grouped.setdefault((item.event_id, item.npc_id, item.policy_id), []).append(item)
        results = []
        for result in base:
            proposal = result.interpreted
            contributions = []
            adjustment = 0.0
            for item in sorted(grouped.get((proposal.event_id, proposal.npc_id, proposal.policy_id), ()), key=lambda x: x.target_id):
                try:
                    confidence = trust.get(item.npc_id, item.target_id).trust
                except KeyError:
                    confidence = 0.5
                contribution = item.coefficient * (2.0 * confidence - 1.0) * item.relevance_scale
                adjustment += contribution
                contributions.append((item.target_id, confidence, contribution))
            maximum = proposal.maximum_delta
            delta = max(-maximum, min(maximum, proposal.delta + adjustment))
            after = max(-1.0, min(1.0, proposal.before + delta))
            interpreted = IdentityChangeProposal(
                proposal.event_id, proposal.npc_id, proposal.policy_id, proposal.axis,
                proposal.before, after, after - proposal.before,
                proposal.evidence_strength, proposal.role, maximum,
            )
            results.append(InterpretedIdentityChange(
                result.original, interpreted, result.belief_contributions,
                result.memory_contributions, tuple(contributions)))
        return tuple(results)

    def interpret_comprehensively(
        self,
        proposals: Iterable[IdentityChangeProposal],
        *,
        beliefs_by_npc: Mapping[str, BeliefLedger] | None = None,
        npcs_by_id: Mapping[str, NPC] | None = None,
        memory_associations: Iterable[IdentityMemoryAssociation] = (),
        trust: SocialTrustLedger | None = None,
        relationship_associations: Iterable[IdentityRelationshipAssociation] = (),
        personalities_by_npc: Mapping[str, NPCIdentityPersonality] | None = None,
        personality_rules: Iterable[IdentityPersonalityRule] = (),
    ) -> tuple[InterpretedIdentityChange, ...]:
        """Run all configured identity-appraisal inputs in one transparent pass.

        Beliefs, explicitly linked memories, observer-to-target trust and
        personality axes are accumulated against the same original proposal.
        The combined adjustment is clamped once to the original policy delta
        cap and trait bounds. Missing inputs are neutral. This remains a
        read-only appraisal; acceptance belongs to IdentityDecisionLedger.
        """
        base = self.interpret(tuple(proposals), beliefs_by_npc or {})
        npc_map = {} if npcs_by_id is None else npcs_by_id
        if not isinstance(npc_map, Mapping):
            raise TypeError("npcs_by_id must be a mapping")
        for npc_id, npc in npc_map.items():
            if not isinstance(npc_id, str) or not npc_id.strip() or not isinstance(npc, NPC):
                raise TypeError("npcs_by_id must map non-empty IDs to NPC instances")
            if npc.entity_id != npc_id:
                raise ValueError("NPC mapping key must match NPC entity_id")

        memory_items = tuple(memory_associations)
        if any(not isinstance(item, IdentityMemoryAssociation) for item in memory_items):
            raise TypeError("memory_associations must contain IdentityMemoryAssociation values")
        memory_keys = [(x.event_id, x.npc_id, x.policy_id, x.memory_index) for x in memory_items]
        if len(memory_keys) != len(set(memory_keys)):
            raise ValueError("duplicate identity memory association")
        memories_by_key: dict[tuple[str, str, str], list[IdentityMemoryAssociation]] = {}
        for item in memory_items:
            memories_by_key.setdefault((item.event_id, item.npc_id, item.policy_id), []).append(item)

        if trust is not None and not isinstance(trust, SocialTrustLedger):
            raise TypeError("trust must be a SocialTrustLedger")
        relationship_items = tuple(relationship_associations)
        if relationship_items and trust is None:
            raise ValueError("trust is required when relationship associations are supplied")
        if any(not isinstance(item, IdentityRelationshipAssociation) for item in relationship_items):
            raise TypeError("relationship_associations must contain IdentityRelationshipAssociation values")
        relationship_keys = [(x.event_id, x.npc_id, x.policy_id, x.target_id) for x in relationship_items]
        if len(relationship_keys) != len(set(relationship_keys)):
            raise ValueError("duplicate identity relationship association")
        relationships_by_key: dict[tuple[str, str, str], list[IdentityRelationshipAssociation]] = {}
        for item in relationship_items:
            relationships_by_key.setdefault((item.event_id, item.npc_id, item.policy_id), []).append(item)

        personality_map = {} if personalities_by_npc is None else personalities_by_npc
        if not isinstance(personality_map, Mapping):
            raise TypeError("personalities_by_npc must be a mapping")
        for npc_id, profile in personality_map.items():
            if not isinstance(npc_id, str) or not npc_id.strip():
                raise ValueError("personality map NPC IDs must be non-empty strings")
            if not isinstance(profile, NPCIdentityPersonality):
                raise TypeError("personality map values must be NPCIdentityPersonality instances")
            if profile.npc_id != npc_id:
                raise ValueError("personality mapping key must match profile npc_id")
        personality_items = tuple(personality_rules)
        if any(not isinstance(rule, IdentityPersonalityRule) for rule in personality_items):
            raise TypeError("personality_rules must contain IdentityPersonalityRule values")
        personality_keys = [(rule.policy_id, rule.personality_axis) for rule in personality_items]
        if len(personality_keys) != len(set(personality_keys)):
            raise ValueError("duplicate policy/personality-axis rule")
        personality_by_policy: dict[str, list[IdentityPersonalityRule]] = {}
        for rule in sorted(personality_items, key=lambda item: (item.policy_id, item.personality_axis)):
            personality_by_policy.setdefault(rule.policy_id, []).append(rule)

        results = []
        for result in base:
            proposal = result.interpreted
            adjustment = 0.0
            memory_contributions = []
            relationship_contributions = []
            personality_contributions = []

            for item in sorted(
                memories_by_key.get((proposal.event_id, proposal.npc_id, proposal.policy_id), ()),
                key=lambda value: value.memory_index,
            ):
                npc = npc_map.get(item.npc_id)
                if npc is None:
                    continue
                if item.memory_index >= len(npc.memories):
                    raise ValueError(f"memory index out of range for {item.npc_id}: {item.memory_index}")
                retention = npc.memories[item.memory_index].retention
                contribution = item.coefficient * retention * item.relevance_scale
                adjustment += contribution
                memory_contributions.append((item.memory_index, retention, contribution))

            for item in sorted(
                relationships_by_key.get((proposal.event_id, proposal.npc_id, proposal.policy_id), ()),
                key=lambda value: value.target_id,
            ):
                try:
                    confidence = trust.get(item.npc_id, item.target_id).trust
                except KeyError:
                    confidence = 0.5
                contribution = item.coefficient * (2.0 * confidence - 1.0) * item.relevance_scale
                adjustment += contribution
                relationship_contributions.append((item.target_id, confidence, contribution))

            profile = personality_map.get(proposal.npc_id)
            for rule in personality_by_policy.get(proposal.policy_id, ()):
                value = profile.axes.get(rule.personality_axis, 0.0) if profile else 0.0
                contribution = rule.coefficient * value
                adjustment += contribution
                personality_contributions.append((rule.personality_axis, value, contribution))

            maximum = proposal.maximum_delta
            delta = max(-maximum, min(maximum, proposal.delta + adjustment))
            after = max(-1.0, min(1.0, proposal.before + delta))
            interpreted = IdentityChangeProposal(
                proposal.event_id, proposal.npc_id, proposal.policy_id, proposal.axis,
                proposal.before, after, after - proposal.before,
                proposal.evidence_strength, proposal.role, maximum,
            )
            results.append(InterpretedIdentityChange(
                result.original, interpreted, result.belief_contributions,
                tuple(memory_contributions), tuple(relationship_contributions),
                tuple(personality_contributions),
            ))
        return tuple(results)

    def interpret_from_social_beliefs(
        self,
        proposals: Iterable[IdentityChangeProposal],
        social_beliefs: SocialBeliefSystem,
    ) -> tuple[InterpretedIdentityChange, ...]:
        """Interpret proposals directly from observer-specific social beliefs.

        The adapter consumes public belief-state snapshots. It does not reach
        into or mutate SocialBeliefSystem internals. Trust has already been
        sampled when each NPC observed its evidence.
        """
        if not isinstance(social_beliefs, SocialBeliefSystem):
            raise TypeError("social_beliefs must be a SocialBeliefSystem")
        proposals = tuple(proposals)
        ledgers = {}
        for npc_id in sorted({p.npc_id for p in proposals}):
            states = social_beliefs.beliefs_for(npc_id)
            ledgers[npc_id] = BeliefLedger({state.claim_id: state.confidence for state in states})
        return self.interpret(proposals, ledgers)

    def interpret(
        self,
        proposals: Iterable[IdentityChangeProposal],
        beliefs_by_npc: Mapping[str, BeliefLedger],
    ) -> tuple[InterpretedIdentityChange, ...]:
        if not isinstance(beliefs_by_npc, Mapping):
            raise TypeError("beliefs_by_npc must be a mapping")
        for npc_id, ledger in beliefs_by_npc.items():
            if not isinstance(npc_id, str) or not npc_id.strip():
                raise ValueError("belief map NPC IDs must be non-empty strings")
            if not isinstance(ledger, BeliefLedger):
                raise TypeError("belief map values must be BeliefLedger instances")
        proposals = tuple(proposals)
        if any(not isinstance(p, IdentityChangeProposal) for p in proposals):
            raise TypeError("proposals must contain IdentityChangeProposal values")
        if len({(p.event_id, p.npc_id, p.policy_id) for p in proposals}) != len(proposals):
            raise ValueError("duplicate identity proposal")
        results = []
        for proposal in sorted(proposals, key=lambda p: (p.event_id, p.npc_id, p.axis, p.policy_id)):
            ledger = beliefs_by_npc.get(proposal.npc_id)
            contributions = []
            adjustment = 0.0
            for rule in self.rules:
                if rule.policy_id != proposal.policy_id:
                    continue
                confidence = 0.5
                if ledger is not None:
                    try:
                        confidence = ledger.get(rule.claim_id).confidence
                    except KeyError:
                        pass
                contribution = rule.coefficient * (2.0 * confidence - 1.0)
                adjustment += contribution
                contributions.append((rule.claim_id, confidence, contribution))
            maximum = getattr(proposal, "maximum_delta", 0.05)
            delta = max(-maximum, min(maximum, proposal.delta + adjustment))
            after = max(-1.0, min(1.0, proposal.before + delta))
            interpreted = IdentityChangeProposal(
                proposal.event_id, proposal.npc_id, proposal.policy_id, proposal.axis,
                proposal.before, after, after - proposal.before,
                proposal.evidence_strength, proposal.role, maximum,
            )
            results.append(InterpretedIdentityChange(
                proposal, interpreted, tuple(contributions)))
        return tuple(results)
