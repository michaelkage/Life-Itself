"""Convert testimony analysis into explicit, replay-safe NPC evidence inputs."""
from __future__ import annotations

from dataclasses import dataclass
import math

from .beliefs import Evidence, BeliefState
from .social_beliefs import SocialBeliefSystem
from .testimony_analysis import InvestigationReport, TestimonyMatch


@dataclass(frozen=True)
class TestimonyEvidencePolicy:
    """Transparent strength mapping; source trust is resolved by the observer."""

    corroboration_scale: float = 0.5
    contradiction_scale: float = 0.5
    minimum_strength: float = 0.0

    def __post_init__(self) -> None:
        for name in ("corroboration_scale", "contradiction_scale", "minimum_strength"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be finite and in [0, 1]")


@dataclass(frozen=True)
class TestimonyEvidenceBatch:
    observer_id: str
    evidence: tuple[Evidence, ...]


class TestimonyBeliefAdapter:
    """Prepare evidence for one observer without deciding which witness is right.

    A match becomes a claim about an explicit attribute/value. Each witness is
    the source of its own evidence, allowing SocialBeliefSystem to apply that
    observer's current source trust. Conflicting accounts generate opposing
    evidence rather than selecting a winner.
    """

    def __init__(self, policy: TestimonyEvidencePolicy | None = None) -> None:
        self.policy = policy or TestimonyEvidencePolicy()

    def apply(
        self,
        beliefs: SocialBeliefSystem,
        observer_id: str,
        report: InvestigationReport,
        *,
        observed_tick: int,
    ) -> tuple[BeliefState, ...]:
        """Prepare and observe the report through observer-specific trust."""
        if not isinstance(beliefs, SocialBeliefSystem):
            raise TypeError("beliefs must be a SocialBeliefSystem")
        batch = self.prepare(observer_id, report, observed_tick=observed_tick)
        states = []
        for evidence in batch.evidence:
            states.append(beliefs.observe(observer_id, evidence))
        return tuple(states)

    @staticmethod
    def _claim_id(match: TestimonyMatch, value: object) -> str:
        # JSON-like repr is stable for the supported scalar values.
        return f"event:{match.event_id}|{match.attribute_key}={value!r}"

    def prepare(
        self,
        observer_id: str,
        report: InvestigationReport,
        *,
        observed_tick: int,
    ) -> TestimonyEvidenceBatch:
        if not isinstance(observer_id, str) or not observer_id.strip():
            raise ValueError("observer_id must be non-empty")
        if isinstance(observed_tick, bool) or not isinstance(observed_tick, int) or observed_tick < 0:
            raise ValueError("observed_tick must be a non-negative integer")

        result: list[Evidence] = []
        for match in (*report.corroborations, *report.contradictions):
            for index, (witness_id, value, confidence) in enumerate(
                zip(match.witness_ids, match.values, match.confidence)
            ):
                # The proposition is that this event attribute had this value.
                claim_id = self._claim_id(match, value)
                scale = (
                    self.policy.corroboration_scale
                    if match.values[0] == match.values[1]
                    else self.policy.contradiction_scale
                )
                strength = max(self.policy.minimum_strength, min(1.0, confidence * scale))
                direction = 1
                evidence_id = (
                    f"testimony:{match.testimony_ids[index]}:{match.attribute_key}:"
                    f"{value!r}:observer:{observer_id}"
                )
                result.append(Evidence(
                    evidence_id=evidence_id,
                    claim_id=claim_id,
                    source_id=witness_id,
                    direction=direction,
                    strength=strength,
                    source_reliability=0.5,  # replaced by observer-specific trust at observation
                    observed_tick=observed_tick,
                ))
        return TestimonyEvidenceBatch(
            observer_id,
            tuple(sorted(result, key=lambda e: (e.claim_id, e.source_id, e.evidence_id))),
        )
