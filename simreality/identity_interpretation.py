"""Belief-conditioned interpretation of identity-change proposals.

Beliefs alter how an NPC interprets an event; they do not force acceptance.
The resulting proposal still requires an explicit decision in IdentityDecisionLedger.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Mapping

from .beliefs import BeliefLedger
from .identity_evolution import IdentityChangeProposal


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
