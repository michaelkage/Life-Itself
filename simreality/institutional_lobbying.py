"""Deterministic lobbying and coalition influence inside institutions.

Requests are explicit NPC/department actions. Existing political relationships
shape their prospects; a policy converts transparent inputs into a proposal
outcome. Committing an assessment emits a canonical political-history event.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math

from .institutional_politics import InstitutionalPoliticalEvent, InstitutionalPoliticalLedger


def _id(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _unit(value: float, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be finite and between 0 and 1")


@dataclass(frozen=True)
class PoliticalLobbyRequest:
    request_id: str
    institution_id: str
    period_index: int
    department_id: str
    priority_tag: str
    requested_priority_delta: float
    service_impact: float
    evidence_strength: float
    transparency: float
    public_visibility: float = 0.0
    urgency: float = 0.0
    personal_advantage: float = 0.0
    supporting_departments: tuple[str, ...] = ()
    opposing_departments: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("request_id", "institution_id", "department_id", "priority_tag"):
            _id(getattr(self, name), name)
        if isinstance(self.period_index, bool) or not isinstance(self.period_index, int) or self.period_index < 0:
            raise ValueError("period_index must be a non-negative integer")
        if isinstance(self.requested_priority_delta, bool) or not isinstance(self.requested_priority_delta, (int, float)) or not math.isfinite(self.requested_priority_delta) or not -1.0 <= self.requested_priority_delta <= 1.0:
            raise ValueError("requested_priority_delta must be finite and between -1 and 1")
        for name in ("service_impact", "evidence_strength", "transparency", "public_visibility", "urgency", "personal_advantage"):
            _unit(getattr(self, name), name)
        for name in ("supporting_departments", "opposing_departments"):
            values = getattr(self, name)
            if not isinstance(values, tuple) or any(not isinstance(x, str) or not x.strip() for x in values):
                raise TypeError(f"{name} must be a tuple of non-empty department IDs")
            if len(values) != len(set(values)):
                raise ValueError(f"{name} must not contain duplicates")
            if self.department_id in values:
                raise ValueError(f"{name} cannot contain the requesting department")
        if set(self.supporting_departments) & set(self.opposing_departments):
            raise ValueError("a department cannot both support and oppose the same request")


@dataclass(frozen=True)
class PoliticalLobbyPolicy:
    policy_id: str
    influence_weight: float = 0.15
    coalition_weight: float = 0.20
    service_weight: float = 0.20
    evidence_weight: float = 0.20
    transparency_weight: float = 0.10
    urgency_weight: float = 0.05
    visibility_weight: float = 0.05
    personal_advantage_penalty: float = 0.05
    accountability: float = 0.5
    political_pressure: float = 0.5
    approval_threshold: float = 0.65
    defer_threshold: float = 0.40

    def __post_init__(self) -> None:
        _id(self.policy_id, "policy_id")
        weights = (self.influence_weight, self.coalition_weight, self.service_weight,
                   self.evidence_weight, self.transparency_weight, self.urgency_weight,
                   self.visibility_weight, self.personal_advantage_penalty)
        for value in weights:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError("lobby policy weights must be finite and non-negative")
        if sum(weights) <= 0:
            raise ValueError("at least one lobby policy weight must be positive")
        for name in ("accountability", "political_pressure", "approval_threshold", "defer_threshold"):
            _unit(getattr(self, name), name)
        if self.defer_threshold > self.approval_threshold:
            raise ValueError("defer_threshold cannot exceed approval_threshold")


@dataclass(frozen=True)
class PoliticalLobbyAssessment:
    request_id: str
    institution_id: str
    department_id: str
    policy_id: str
    score: float
    decision: str
    coalition_score: float
    contributions: tuple[tuple[str, float], ...]
    rationale: str
    event: InstitutionalPoliticalEvent


class InstitutionalLobbyEvaluator:
    """Evaluate explicit lobbying requests against the current political ledger."""

    def assess(self, ledger: InstitutionalPoliticalLedger, request: PoliticalLobbyRequest,
               policy: PoliticalLobbyPolicy) -> PoliticalLobbyAssessment:
        if not isinstance(ledger, InstitutionalPoliticalLedger):
            raise TypeError("ledger must be an InstitutionalPoliticalLedger")
        if not isinstance(request, PoliticalLobbyRequest):
            raise TypeError("request must be a PoliticalLobbyRequest")
        if not isinstance(policy, PoliticalLobbyPolicy):
            raise TypeError("policy must be a PoliticalLobbyPolicy")
        if request.institution_id != ledger.institution_id:
            raise ValueError("request belongs to a different institution")

        state = ledger.state()
        influence = dict(state.department_influence).get(request.department_id, 0.5)
        relationships = {(a, b): value for a, b, value in state.department_relationships}
        influences = dict(state.department_influence)

        coalition_terms = []
        for supporter in request.supporting_departments:
            pair = tuple(sorted((request.department_id, supporter)))
            tie = relationships.get(pair, 0.0)
            coalition_terms.append(influences.get(supporter, 0.5) * max(0.0, tie))
        for opponent in request.opposing_departments:
            pair = tuple(sorted((request.department_id, opponent)))
            tie = relationships.get(pair, 0.0)
            coalition_terms.append(-influences.get(opponent, 0.5) * max(0.0, -tie))
        coalition_score = 0.5 if not coalition_terms else min(1.0, max(0.0, 0.5 + sum(coalition_terms) / (2.0 * len(coalition_terms))))

        parts = (
            ("department_influence", influence * policy.influence_weight),
            ("coalition_alignment", coalition_score * policy.coalition_weight),
            ("public_service_value", request.service_impact * policy.service_weight),
            ("evidence_strength", request.evidence_strength * policy.evidence_weight),
            ("transparency", request.transparency * policy.transparency_weight * policy.accountability),
            ("urgency", request.urgency * policy.urgency_weight),
            ("public_visibility", request.public_visibility * policy.visibility_weight * policy.political_pressure),
            ("personal_advantage_cost", -request.personal_advantage * policy.personal_advantage_penalty * policy.accountability),
        )
        total_weight = sum((policy.influence_weight, policy.coalition_weight, policy.service_weight,
                            policy.evidence_weight, policy.transparency_weight, policy.urgency_weight,
                            policy.visibility_weight, policy.personal_advantage_penalty))
        score = min(1.0, max(0.0, sum(value for _, value in parts) / total_weight))
        if score >= policy.approval_threshold:
            decision = "approved"
        elif score >= policy.defer_threshold:
            decision = "deferred"
        else:
            decision = "rejected"

        priority_delta = request.requested_priority_delta if decision == "approved" else 0.0
        influence_delta = 0.04 if decision == "approved" else (-0.02 if decision == "rejected" else 0.0)
        signature_payload = json.dumps({"request": asdict(request), "policy": asdict(policy)}, sort_keys=True, separators=(",", ":"), allow_nan=False)
        signature = hashlib.sha256(signature_payload.encode("utf-8")).hexdigest()
        rationale = f"lobby:{request.request_id};decision:{decision};policy:{policy.policy_id};signature:{signature}"
        event = InstitutionalPoliticalEvent(
            event_id=f"lobby:{request.request_id}",
            institution_id=request.institution_id,
            period_index=request.period_index,
            department_id=request.department_id,
            influence_delta=influence_delta,
            priority_tag=request.priority_tag if priority_delta else None,
            leadership_priority_delta=priority_delta,
            rationale=rationale,
        )
        return PoliticalLobbyAssessment(
            request.request_id, request.institution_id, request.department_id,
            policy.policy_id, score, decision, coalition_score, parts, rationale, event,
        )

    def assess_many(self, ledger: InstitutionalPoliticalLedger,
                    requests: tuple[PoliticalLobbyRequest, ...],
                    policy: PoliticalLobbyPolicy) -> tuple[PoliticalLobbyAssessment, ...]:
        if not isinstance(requests, tuple) or any(not isinstance(x, PoliticalLobbyRequest) for x in requests):
            raise TypeError("requests must be a tuple of PoliticalLobbyRequest values")
        if len({item.request_id for item in requests}) != len(requests):
            raise ValueError("request IDs must be unique")
        if len({item.department_id for item in requests}) != len(requests):
            raise ValueError("each department may lobby once per evaluation period")
        # All requests are assessed against the same pre-resolution state.
        return tuple(sorted((self.assess(ledger, item, policy) for item in requests),
                            key=lambda item: item.request_id))

    @staticmethod
    def commit(ledger: InstitutionalPoliticalLedger,
               assessments: tuple[PoliticalLobbyAssessment, ...]) -> None:
        if not isinstance(ledger, InstitutionalPoliticalLedger):
            raise TypeError("ledger must be an InstitutionalPoliticalLedger")
        if not isinstance(assessments, tuple) or any(not isinstance(x, PoliticalLobbyAssessment) for x in assessments):
            raise TypeError("assessments must be a tuple of PoliticalLobbyAssessment values")
        ledger.append_many(tuple(item.event for item in assessments))
