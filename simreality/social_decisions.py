"""Trust-aware decision appraisal for individual NPCs.

This adapter joins an observer's current social beliefs to the explicit,
value-relative choice appraiser. It is read-only: callers provide value/bias
profiles, candidate options, and claim-to-effect mappings.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .appraisal import ChoiceOption, NPCValueProfile
from .belief_appraisal import BeliefAwareAppraiser, BeliefAwareResult
from .beliefs import BeliefLedger
from .social_beliefs import SocialBeliefSystem


@dataclass(frozen=True)
class SocialDecisionResult:
    """Stable ranked choices plus the observer whose beliefs were used."""

    observer_id: str
    ranked: tuple[BeliefAwareResult, ...]

    @property
    def preferred(self) -> BeliefAwareResult | None:
        """Highest-ranked option, or None when no options were supplied."""
        return self.ranked[0] if self.ranked else None


class SocialBeliefDecisionAdapter:
    """Rank choices using one NPC's current beliefs and an explicit profile.

    The profile's npc_id must match observer_id. Unknown claims referenced by
    effect mappings raise KeyError rather than silently receiving an invented
    confidence. Existing beliefs are copied into a temporary ledger, so ranking
    cannot mutate social memory or add evidence.
    """

    @staticmethod
    def rank(
        observer_id: str,
        beliefs: SocialBeliefSystem,
        profile: NPCValueProfile,
        options: tuple[ChoiceOption, ...] | list[ChoiceOption],
        *,
        value_effects: Mapping[str, Mapping[str, float]] | None = None,
        bias_effects: Mapping[str, Mapping[str, float]] | None = None,
    ) -> SocialDecisionResult:
        if not isinstance(observer_id, str) or not observer_id.strip():
            raise ValueError("observer_id must be a non-empty string")
        if not isinstance(beliefs, SocialBeliefSystem):
            raise TypeError("beliefs must be a SocialBeliefSystem")
        if not isinstance(profile, NPCValueProfile):
            raise TypeError("profile must be an NPCValueProfile")
        if profile.npc_id != observer_id:
            raise ValueError("profile.npc_id must match observer_id")

        confidence = {
            state.claim_id: state.confidence
            for state in beliefs.beliefs_for(observer_id)
        }
        ledger = BeliefLedger(confidence)
        ranked = BeliefAwareAppraiser.rank(
            profile, options, ledger,
            value_effects=value_effects,
            bias_effects=bias_effects,
        )
        return SocialDecisionResult(observer_id=observer_id, ranked=ranked)
