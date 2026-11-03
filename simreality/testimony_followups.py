"""Deterministic, read-only follow-up proposals for uncertain testimony."""
from __future__ import annotations
from dataclasses import dataclass
import math
from .social_beliefs import SocialBeliefSystem
from .testimony_analysis import InvestigationReport
from .testimony_belief_queries import TestimonyBeliefQueryAdapter

@dataclass(frozen=True)
class TestimonyFollowUp:
    event_id: str
    attribute_key: str
    witness_id: str
    testimony_id: str
    reported_value: object
    belief_confidence: float | None
    testimony_confidence: float
    priority: float
    reason: str

@dataclass(frozen=True)
class TestimonyFollowUpPlan:
    observer_id: str
    event_id: str
    proposals: tuple[TestimonyFollowUp, ...]

class TestimonyFollowUpPlanner:
    """Rank clarification proposals; never chooses which account is true."""
    def __init__(self, query_adapter: TestimonyBeliefQueryAdapter | None = None):
        self.query_adapter = query_adapter or TestimonyBeliefQueryAdapter()

    @staticmethod
    def _uncertainty(confidence: float | None) -> float:
        return 1.0 if confidence is None else 1.0 - abs(confidence - 0.5) * 2.0

    def plan(self, observer_id: str, beliefs: SocialBeliefSystem,
             report: InvestigationReport, *, minimum_priority: float = 0.0) -> TestimonyFollowUpPlan:
        if not isinstance(observer_id, str) or not observer_id.strip():
            raise ValueError("observer_id must be non-empty")
        if not isinstance(beliefs, SocialBeliefSystem):
            raise TypeError("beliefs must be SocialBeliefSystem")
        if not isinstance(report, InvestigationReport):
            raise TypeError("report must be InvestigationReport")
        if isinstance(minimum_priority, bool) or not isinstance(minimum_priority, (int, float)) or not math.isfinite(minimum_priority) or not 0 <= minimum_priority <= 1:
            raise ValueError("minimum_priority must be in [0, 1]")

        proposals = []
        for is_conflict, matches in ((True, report.contradictions), (False, report.corroborations)):
            for match in matches:
                for i, (witness, testimony, value, reliability) in enumerate(
                    zip(match.witness_ids, match.testimony_ids, match.values, match.confidence)
                ):
                    q = self.query_adapter.query(beliefs, observer_id, match.event_id, match.attribute_key, value)
                    priority = max(0.0, min(1.0, self._uncertainty(q.confidence) * reliability))
                    if priority < minimum_priority:
                        continue
                    reason = ("conflicting accounts need clarification" if is_conflict else
                              "corroborated detail remains unknown or uncertain")
                    proposals.append(TestimonyFollowUp(match.event_id, match.attribute_key,
                        witness, testimony, value, q.confidence, reliability, priority, reason))
        proposals.sort(key=lambda p: (-p.priority, p.attribute_key, p.witness_id,
                                      p.testimony_id, repr(p.reported_value)))
        return TestimonyFollowUpPlan(observer_id, report.event_id, tuple(proposals))
