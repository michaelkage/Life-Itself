"""Explicit end-to-end bridge from inquiry answers to investigation beliefs."""
from __future__ import annotations

from dataclasses import dataclass

from .social_beliefs import SocialBeliefSystem
from .testimony import TestimonyLedger, TestimonyRecord
from .testimony_analysis import InvestigationReport, TestimonyAnalyzer
from .testimony_beliefs import TestimonyBeliefAdapter
from .testimony_inquiries import TestimonyInquiryLedger
from .testimony_materialization import TestimonyMaterializationAdapter


@dataclass(frozen=True)
class InquiryInvestigationResult:
    materialized: TestimonyRecord | None
    report: InvestigationReport
    belief_states: tuple[object, ...]


class InquiryInvestigationPipeline:
    """Materialize one response, analyze its event, and update one observer.

    All decisions remain explicit: caller supplies IDs, hours, observer, and
    tick. The pipeline does not ask witnesses, invent answers, or choose a
    preferred account. Existing ledger replay semantics protect each stage.
    """

    def __init__(
        self,
        materializer: TestimonyMaterializationAdapter | None = None,
        analyzer: TestimonyAnalyzer | None = None,
        belief_adapter: TestimonyBeliefAdapter | None = None,
    ) -> None:
        self.materializer = materializer or TestimonyMaterializationAdapter()
        self.analyzer = analyzer or TestimonyAnalyzer()
        self.belief_adapter = belief_adapter or TestimonyBeliefAdapter()

    def process(
        self,
        inquiries: TestimonyInquiryLedger,
        testimony: TestimonyLedger,
        beliefs: SocialBeliefSystem,
        inquiry_id: str,
        testimony_id: str,
        recorded_hour: float,
        observer_id: str,
        observed_tick: int,
    ) -> InquiryInvestigationResult:
        if not isinstance(beliefs, SocialBeliefSystem):
            raise TypeError("beliefs must be a SocialBeliefSystem")
        inquiry = inquiries.get_inquiry(inquiry_id)
        materialized = self.materializer.materialize(
            inquiries, testimony, inquiry_id, testimony_id, recorded_hour,
        )
        report = self.analyzer.analyze(testimony, inquiry.event_id, recorded_hour)
        states = self.belief_adapter.apply(
            beliefs, observer_id, report, observed_tick=observed_tick,
        )
        return InquiryInvestigationResult(materialized, report, states)
