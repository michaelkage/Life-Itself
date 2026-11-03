"""Read-only, observer-specific queries over testimony-derived beliefs."""
from __future__ import annotations

from dataclasses import dataclass

from .social_beliefs import SocialBeliefSystem


@dataclass(frozen=True)
class TestimonyBeliefQuery:
    observer_id: str
    event_id: str
    attribute_key: str
    value: object
    claim_id: str
    confidence: float | None
    known: bool

    @property
    def believes(self) -> bool | None:
        """True/False only when confidence crosses explicit thresholds."""
        if self.confidence is None:
            return None
        if self.confidence >= 0.65:
            return True
        if self.confidence <= 0.35:
            return False
        return None


class TestimonyBeliefQueryAdapter:
    """Resolve a specific event attribute/value proposition for one NPC.

    Unknown claims remain unknown. Confidence is descriptive, not objective
    truth, and the adapter never changes evidence, trust, or belief state.
    """

    @staticmethod
    def claim_id(event_id: str, attribute_key: str, value: object) -> str:
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError("event_id must be non-empty")
        if not isinstance(attribute_key, str) or not attribute_key.strip():
            raise ValueError("attribute_key must be non-empty")
        return f"event:{event_id}|{attribute_key}={value!r}"

    def query(
        self,
        beliefs: SocialBeliefSystem,
        observer_id: str,
        event_id: str,
        attribute_key: str,
        value: object,
    ) -> TestimonyBeliefQuery:
        if not isinstance(beliefs, SocialBeliefSystem):
            raise TypeError("beliefs must be a SocialBeliefSystem")
        claim_id = self.claim_id(event_id, attribute_key, value)
        try:
            state = beliefs.get(observer_id, claim_id)
        except KeyError:
            return TestimonyBeliefQuery(
                observer_id, event_id, attribute_key, value, claim_id, None, False
            )
        return TestimonyBeliefQuery(
            observer_id, event_id, attribute_key, value, claim_id,
            state.confidence, True,
        )
