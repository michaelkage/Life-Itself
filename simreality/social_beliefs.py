"""Deterministic integration of observer-specific trust and NPC beliefs.

At observation time, an NPC's trust in an evidence source is sampled as that
source's reliability. The resulting evidence is stored in that NPC's own belief
ledger, so later trust changes do not silently rewrite the past.
"""
from __future__ import annotations

from .beliefs import BeliefLedger, BeliefState, Evidence
from .social_trust import SocialTrustLedger


class SocialBeliefSystem:
    """Apply evidence to each observer's beliefs using their trust in its source.

    The reliability supplied on the incoming Evidence is deliberately replaced
    by the observer's current trust in ``evidence.source_id``. If no relationship
    exists, the neutral fallback is 0.5. Trust is sampled when the evidence is
    observed; callers that want retroactive reinterpretation must model that as
    an explicit new event rather than mutating historical evidence implicitly.

    Evidence IDs are unique within each observer's ledger. Identical replays are
    idempotent; reusing an ID with different effective content is rejected.
    """

    def __init__(self, trust: SocialTrustLedger) -> None:
        if not isinstance(trust, SocialTrustLedger):
            raise TypeError("trust must be a SocialTrustLedger")
        self.trust = trust
        self._ledgers: dict[str, BeliefLedger] = {}

    def observe(self, observer_id: str, evidence: Evidence) -> BeliefState:
        """Record one source-attributed observation for a particular NPC."""
        if not isinstance(observer_id, str) or not observer_id.strip():
            raise ValueError("observer_id must be a non-empty string")
        if not isinstance(evidence, Evidence):
            raise TypeError("evidence must be an Evidence instance")
        ledger = self._ledgers.setdefault(observer_id, BeliefLedger())
        try:
            reliability = self.trust.get(observer_id, evidence.source_id).trust
        except KeyError:
            reliability = 0.5
        effective = Evidence(
            evidence_id=evidence.evidence_id,
            claim_id=evidence.claim_id,
            source_id=evidence.source_id,
            direction=evidence.direction,
            strength=evidence.strength,
            source_reliability=reliability,
            observed_tick=evidence.observed_tick,
        )
        return ledger.add(effective)

    def get(self, observer_id: str, claim_id: str) -> BeliefState:
        """Return one NPC's belief about a claim."""
        if observer_id not in self._ledgers:
            raise KeyError(observer_id)
        return self._ledgers[observer_id].get(claim_id)

    def beliefs_for(self, observer_id: str) -> tuple[BeliefState, ...]:
        """Return a stable, claim-ID-sorted snapshot for one NPC."""
        if observer_id not in self._ledgers:
            return ()
        return self._ledgers[observer_id].snapshot()

    def snapshot(self) -> tuple[tuple[str, BeliefState], ...]:
        """Return a stable snapshot sorted by observer ID then claim ID."""
        return tuple(
            (observer_id, state)
            for observer_id in sorted(self._ledgers)
            for state in self._ledgers[observer_id].snapshot()
        )
