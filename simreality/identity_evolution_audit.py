"""Read-only, joined provenance for durable NPC identity evolution."""
from __future__ import annotations

from dataclasses import dataclass
from .emotional_scars import NPCEmotionalScarLedger
from .identity_decisions import IdentityDecisionLedger, IdentityChangeDecision
from .scar_identity_proposals import ScarIdentityProposalLedger
from .world_events import WorldEventLedger


@dataclass(frozen=True)
class IdentityEvolutionAuditRecord:
    event_id: str
    event_tick: int
    npc_id: str
    role: str
    memory_id: str
    scar_id: str
    emotion_axis: str
    cue_id: str
    evaluated_tick: int
    severity: float
    proposal_policy_id: str
    identity_axis: str
    before: float
    proposed_after: float
    delta: float
    decision: IdentityChangeDecision | None
    resulting_trait: float | None

    @property
    def status(self):
        if self.decision is None:
            return "pending"
        return "accepted" if self.decision.accepted else "rejected"


class IdentityEvolutionAuditTrail:
    """Join source experience, accepted scar, proposal, consent, and trait outcome.

    This is a read-only projection over the authoritative event, scar, proposal,
    and identity-decision ledgers. It never creates proposals or changes traits.
    """

    @staticmethod
    def build(events: WorldEventLedger, scars: NPCEmotionalScarLedger,
              proposals: ScarIdentityProposalLedger,
              decisions: IdentityDecisionLedger):
        if not isinstance(events, WorldEventLedger):
            raise TypeError("events must be WorldEventLedger")
        if not isinstance(scars, NPCEmotionalScarLedger):
            raise TypeError("scars must be NPCEmotionalScarLedger")
        if not isinstance(proposals, ScarIdentityProposalLedger):
            raise TypeError("proposals must be ScarIdentityProposalLedger")
        if not isinstance(decisions, IdentityDecisionLedger):
            raise TypeError("decisions must be IdentityDecisionLedger")
        journal = {event.event_id: event for event in events.snapshot()}
        scar_index = {scar.scar_id: scar for scar in scars.scars()}
        decision_index = {
            (item.event_id, item.npc_id, item.policy_id): item
            for item in decisions.entries()
        }
        output = []
        for evidence in proposals.entries():
            proposal = evidence.proposal
            scar = scar_index.get(evidence.scar_id)
            event = journal.get(proposal.event_id)
            if (scar is None or event is None or scar.owner_id != proposal.npc_id
                    or scar.source_event_id != proposal.event_id
                    or scar.emotion_axis != evidence.emotion_axis
                    or scar.cue_id != evidence.cue_id
                    or event.tick > scar.created_tick
                    or scar.created_tick > evidence.evaluated_tick
                    or event.tick > evidence.evaluated_tick
                    or not abs(scars.severity_for(scar.scar_id, evidence.evaluated_tick) - evidence.severity) <= 1e-12):
                raise ValueError("identity audit provenance does not match its source event and scar")
            if proposal.role == "participant":
                role_matches = proposal.npc_id in event.participants
            else:
                role_matches = proposal.npc_id in event.witnesses
            if not role_matches:
                raise ValueError("identity audit role does not match the source experience")
            decision = decision_index.get((proposal.event_id, proposal.npc_id, proposal.policy_id))
            if decision is not None:
                if (decision.axis != proposal.axis or decision.before != proposal.before
                        or decision.proposed_after != proposal.after or decision.delta != proposal.delta
                        or decision.evidence_strength != proposal.evidence_strength
                        or decision.role != proposal.role or decision.decision_tick < evidence.evaluated_tick):
                    raise ValueError("identity audit decision disagrees with its original proposal")
                resulting_trait = proposal.after if decision.accepted else proposal.before
            else:
                resulting_trait = None
            output.append(IdentityEvolutionAuditRecord(
                event.event_id, event.tick, proposal.npc_id, proposal.role,
                scar.source_memory_id, scar.scar_id, scar.emotion_axis, scar.cue_id,
                evidence.evaluated_tick, evidence.severity, proposal.policy_id,
                proposal.axis, proposal.before, proposal.after, proposal.delta,
                decision, resulting_trait,
            ))
        return tuple(sorted(output, key=lambda item: (
            item.event_tick, item.npc_id, item.scar_id, item.proposal_policy_id,
        )))
