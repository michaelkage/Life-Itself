"""Belief-conditioned interpretation of identity-change proposals.

Beliefs alter how an NPC interprets an event; they do not force acceptance.
The resulting proposal still requires an explicit decision in IdentityDecisionLedger.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Mapping

from .model import NPC

from .beliefs import BeliefLedger
from .identity_evolution import IdentityChangeProposal
from .social_beliefs import SocialBeliefSystem


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
