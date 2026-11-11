"""Composite persistence for the currently integrated simulation pipeline."""
from __future__ import annotations

from dataclasses import dataclass
import json
import math

from .adapter_replay_state import WorldEventMemoryReplaySnapshot
from .campaign import LifeItselfCampaign
from .misconduct import MisconductReportingSystem
from .misconduct_save_state import MisconductSnapshot
from .routine_save_state import RoutineBookSnapshot
from .routine_execution import RoutineExecutionLedger
from .routine_execution_save_state import RoutineExecutionSnapshot
from .routine_institution_ledger import RoutineInstitutionLedger
from .routine_institution_save_state import RoutineInstitutionSnapshot
from .routines import RoutineBook
from .npc_save_state import NPCCollectionSnapshot, SocialTrustSnapshot
from .save_state import SimulationSaveEnvelope
from .social_belief_save_state import SocialBeliefSnapshot
from .social_conversations import SocialConversationAdapter
from .social_consequences import SocialConsequenceRecorder
from .social_replay_save_state import SocialConsequenceReplaySnapshot, SocialConversationReplaySnapshot
from .simulation_tick import SimulationTickCoordinator
from .social_trust import SocialTrustLedger
from .tick_replay_save_state import SimulationTickReplaySnapshot
from .world_event_memory import WorldEventMemoryAdapter
from .world_events import WorldEventLedger
from .institutional_politics import InstitutionalPoliticalLedger
from .goals import GoalBook
from .goal_events import GoalEventAdapter
from .goal_save_state import GoalBookSnapshot
from .goal_events_save_state import GoalEventReplaySnapshot
from .goal_review_decisions import GoalReviewDecisionLedger
from .goal_review_decisions_save_state import GoalReviewDecisionSnapshot
from .goal_review_application import GoalReviewApplicationLedger
from .goal_review_application_save_state import GoalReviewApplicationSnapshot
from .goal_arbitration import GoalCommitmentLedger
from .goal_arbitration_save_state import GoalCommitmentSnapshot
from .identity_decisions import IdentityDecisionLedger
from .identity_decisions_save_state import IdentityDecisionSnapshot
from .testimony_inquiries import TestimonyInquiryLedger
from .testimony_inquiry_save_state import TestimonyInquirySnapshot
from .testimony import TestimonyLedger
from .travel import TravelLedger
from .travel_save_state import TravelSnapshot
from .presence import PresenceLedger
from .presence_save_state import PresenceSnapshot
from .presence_encounters import PresenceEncounterLedger
from .presence_encounter_save_state import PresenceEncounterSnapshot
from .social_familiarity import SocialFamiliarityLedger, SocialFamiliaritySnapshot
from .social_relationships import SocialRelationshipLedger, SocialRelationshipSnapshot
from .emotional_events import NPCEmotionalEventLedger
from .emotional_events_save_state import EmotionalEventSnapshot
from .emotional_stress import NPCStressLedger
from .emotional_stress_save_state import NPCStressSnapshot
from .psychological_conditioning import NPCConditioningLedger, NPCConditioningSnapshot
from .psychological_learning_decisions import PsychologicalLearningDecisionSnapshot, PsychologicalLearningDecisionLedger
from .npc_life_history import NPCLifeHistory, LifeHistorySnapshot
from .npc_experience_transfer import ExperienceTransferSnapshot, NPCExperienceTransferLedger
from .npc_memory_reflection import MemoryReflectionLedger, MemoryReflectionSnapshot
from .emotional_scars import NPCEmotionalScarLedger
from .emotional_scars_save_state import EmotionalScarSnapshot
from .emotional_scar_formation import EmotionalScarDecisionLedger, EmotionalScarDecisionSnapshot
from .scar_identity_proposals import ScarIdentityProposalLedger, ScarIdentityProposalSnapshot
from .identity_goal_alignment import IdentityGoalReviewDecisionLedger, IdentityGoalReviewSnapshot
from .action_execution import ActionExecutionLedger, ActionExecutionSnapshot
from .action_evaluation import ActionPlanEvaluationLedger, ActionEvaluationSnapshot
from .npc_action_replanning import NPCActionReplanningCoordinator, NPCReplanningSnapshot
from .npc_goal_emergence import GoalLifecycleLedger
from .goal_lifecycle_save_state import GoalLifecycleSnapshot


@dataclass(frozen=True)
class RestoredSimulation:
    current_tick: int
    events: WorldEventLedger
    npcs: dict
    trust: SocialTrustLedger
    beliefs: object
    memory_adapter: WorldEventMemoryAdapter
    conversation_adapter: SocialConversationAdapter
    coordinator: SimulationTickCoordinator
    metadata: tuple
    consequence_recorder: SocialConsequenceRecorder | None = None
    campaign: LifeItselfCampaign | None = None
    misconduct: MisconductReportingSystem | None = None
    routines: RoutineBook | None = None
    routine_executions: RoutineExecutionLedger | None = None
    routine_institutions: RoutineInstitutionLedger | None = None
    institutional_politics: InstitutionalPoliticalLedger | None = None
    goals: GoalBook | None = None
    goal_event_replay: GoalEventReplaySnapshot | None = None
    goal_review_decisions: GoalReviewDecisionLedger | None = None
    identity_decisions: IdentityDecisionLedger | None = None
    testimony_inquiries: TestimonyInquiryLedger | None = None
    testimony: TestimonyLedger | None = None
    travel: TravelLedger | None = None
    presence: PresenceLedger | None = None
    presence_encounters: PresenceEncounterLedger | None = None
    familiarity: SocialFamiliarityLedger | None = None
    relationships: SocialRelationshipLedger | None = None
    emotions: NPCEmotionalEventLedger | None = None
    stress: NPCStressLedger | None = None
    conditioning: NPCConditioningLedger | None = None
    psychological_learning_decisions: PsychologicalLearningDecisionLedger | None = None
    life_history: NPCLifeHistory | None = None
    memory_reflections: MemoryReflectionLedger | None = None
    emotional_scars: NPCEmotionalScarLedger | None = None
    emotional_scar_decisions: EmotionalScarDecisionLedger | None = None
    scar_identity_proposals: ScarIdentityProposalLedger | None = None
    identity_goal_reviews: IdentityGoalReviewDecisionLedger | None = None
    action_execution_snapshot: ActionExecutionSnapshot | None = None
    action_world_facts: set[str] | None = None
    action_resources: dict[str, float] | None = None
    action_replanning_snapshot: NPCReplanningSnapshot | None = None
    action_evaluation_snapshot: ActionEvaluationSnapshot | None = None
    experience_transfers: NPCExperienceTransferLedger | None = None
    goal_lifecycle: GoalLifecycleLedger | None = None
    goal_review_applications: GoalReviewApplicationLedger | None = None
    goal_commitments: GoalCommitmentLedger | None = None

    def restore_action_execution_ledger(self, planner, policies, goals=None):
        """Rebind persisted execution progress to runtime planning and goal definitions."""
        if self.action_execution_snapshot is None:
            return None
        return ActionExecutionLedger.from_snapshot(
            planner, policies, self.events, self.action_execution_snapshot,
            self.goals if goals is None else goals,
        )

    def restore_action_evaluation_ledger(self, executions):
        """Restore immutable action assessments and learned reliability over executions."""
        if self.action_evaluation_snapshot is None:
            return None
        if executions.events is not self.events:
            raise ValueError("restored execution ledger must share the restored event journal")
        if self.action_execution_snapshot is None or executions.to_snapshot() != self.action_execution_snapshot:
            raise ValueError("execution ledger does not match the restored checkpoint")
        return ActionPlanEvaluationLedger.from_snapshot(
            executions, self.events, self.action_evaluation_snapshot,
        )

    def restore_action_replanning_coordinator(self, decisions, executions, evaluations=None):
        """Restore replay-safe replanning requests over the restored execution ledger."""
        if self.action_replanning_snapshot is None:
            return None
        if executions.events is not self.events:
            raise ValueError("restored execution ledger must share the restored event journal")
        if self.action_execution_snapshot is None or executions.to_snapshot() != self.action_execution_snapshot:
            raise ValueError("execution ledger does not match the restored checkpoint")
        if self.goals is not None and decisions.goals is not self.goals:
            raise ValueError("decision cycle must use the restored GoalBook")
        if self.action_evaluation_snapshot is not None:
            if evaluations is None or evaluations.to_snapshot() != self.action_evaluation_snapshot:
                raise ValueError("replanning restore requires the matching restored action evaluation ledger")
        elif evaluations is not None:
            raise ValueError("evaluation ledger was not part of the restored checkpoint")
        return NPCActionReplanningCoordinator.from_snapshot(
            decisions, executions, self.events, self.action_replanning_snapshot,
            evaluations=evaluations,
            life_history=self.life_history if self.experience_transfers is not None else None,
            experience_transfers=self.experience_transfers,
        )


@dataclass(frozen=True)
class SimulationWorldCheckpoint:
    """One versioned container composed from the existing component codecs.

    Restore order is event journal, NPCs, trust, beliefs, memory replay index,
    conversation replay index, coordinator replay history, then optional
    misconduct reports validated against the authoritative event journal.
    """
    current_tick: int
    events_json: str
    npcs_json: str
    trust_json: str
    beliefs_json: str
    memory_replay_json: str
    conversations_json: str
    tick_replay_json: str
    ticks_per_hour: float = 1.0
    metadata: tuple = ()
    consequence_replay_json: str | None = None
    campaign_json: str | None = None
    misconduct_json: str | None = None
    routines_json: str | None = None
    routine_executions_json: str | None = None
    routine_institutions_json: str | None = None
    institutional_politics_json: str | None = None
    goals_json: str | None = None
    goal_event_replay_json: str | None = None
    goal_review_decisions_json: str | None = None
    identity_decisions_json: str | None = None
    testimony_inquiries_json: str | None = None
    testimony_json: str | None = None
    travel_json: str | None = None
    presence_json: str | None = None
    presence_encounters_json: str | None = None
    familiarity_json: str | None = None
    relationships_json: str | None = None
    emotions_json: str | None = None
    stress_json: str | None = None
    conditioning_json: str | None = None
    psychological_learning_decisions_json: str | None = None
    life_history_json: str | None = None
    memory_reflections_json: str | None = None
    emotional_scars_json: str | None = None
    emotional_scar_decisions_json: str | None = None
    scar_identity_proposals_json: str | None = None
    identity_goal_reviews_json: str | None = None
    action_executions_json: str | None = None
    action_world_facts_json: str | None = None
    action_resources_json: str | None = None
    action_replanning_json: str | None = None
    action_evaluations_json: str | None = None
    experience_transfers_json: str | None = None
    goal_lifecycle_json: str | None = None
    goal_review_applications_json: str | None = None
    goal_commitments_json: str | None = None

    SCHEMA_VERSION = 1

    def __post_init__(self):
        if isinstance(self.current_tick, bool) or not isinstance(self.current_tick, int) or self.current_tick < 0:
            raise ValueError("current_tick must be a non-negative integer")
        if isinstance(self.ticks_per_hour, bool) or not isinstance(self.ticks_per_hour, (int, float)) or not math.isfinite(self.ticks_per_hour) or self.ticks_per_hour <= 0:
            raise ValueError("ticks_per_hour must be positive and finite")
        if not isinstance(self.metadata, tuple):
            raise ValueError("metadata must be a tuple")
        keys = []
        for pair in self.metadata:
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise ValueError("metadata entries must be key/value pairs")
            key, value = pair
            if not isinstance(key, str) or not key.strip():
                raise ValueError("metadata keys must be non-empty")
            if value is not None and not isinstance(value, (str, int, float, bool)):
                raise ValueError("metadata values must be JSON scalars")
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("metadata values must be finite")
            keys.append(key)
        if keys != sorted(keys) or len(keys) != len(set(keys)):
            raise ValueError("metadata keys must be unique and sorted")
        self._components()

    @classmethod
    def capture(cls, current_tick, coordinator, npcs, *, metadata=None,
                consequence_recorder=None, campaign=None, misconduct=None, routines=None,
                routine_executions=None, routine_institutions=None, institutional_politics=None,
                goal_book=None, goal_event_adapter=None, goal_review_decisions=None, identity_decisions=None,
                testimony_inquiries=None, testimony=None, travel=None, presence=None, presence_encounters=None, familiarity=None, relationships=None, emotions=None, stress=None, conditioning=None, psychological_learning_decisions=None, life_history=None, memory_reflections=None, emotional_scars=None, emotional_scar_decisions=None, scar_identity_proposals=None, identity_goal_reviews=None, action_executions=None, action_world_facts=None, action_resources=None, action_replanning=None, action_evaluations=None, experience_transfers=None, goal_lifecycle=None, goal_review_applications=None, goal_commitments=None):
        if not isinstance(coordinator, SimulationTickCoordinator):
            raise TypeError("coordinator must be a SimulationTickCoordinator")
        if not isinstance(npcs, dict):
            raise TypeError("npcs must be a dict keyed by entity ID")
        if coordinator._last_tick is not None and current_tick < coordinator._last_tick:
            raise ValueError("current_tick cannot precede the last processed tick")
        for npc_id, npc in npcs.items():
            if not isinstance(npc_id, str) or not npc_id.strip() or getattr(npc, "entity_id", None) != npc_id:
                raise ValueError("NPC mapping keys must match NPC entity IDs")
        trust = coordinator.conversation_adapter.trust
        beliefs = coordinator.conversation_adapter.beliefs
        if beliefs.trust is not trust:
            raise ValueError("beliefs and conversation adapter must share trust")
        if consequence_recorder is not None:
            if not isinstance(consequence_recorder, SocialConsequenceRecorder):
                raise TypeError("consequence_recorder must be a SocialConsequenceRecorder or None")
            if consequence_recorder.trust is not trust or consequence_recorder.beliefs is not beliefs:
                raise ValueError("consequence recorder must share the checkpoint trust and belief systems")
        if campaign is not None and not isinstance(campaign, LifeItselfCampaign):
            raise TypeError("campaign must be a LifeItselfCampaign or None")
        if routines is not None and not isinstance(routines, RoutineBook):
            raise TypeError("routines must be a RoutineBook or None")
        routines_snapshot = RoutineBookSnapshot.capture(routines) if routines is not None else None
        if routine_executions is not None and not isinstance(routine_executions, RoutineExecutionLedger):
            raise TypeError("routine_executions must be a RoutineExecutionLedger or None")
        if routine_executions is not None and routines is None:
            raise ValueError("routine execution history requires the corresponding RoutineBook")
        execution_snapshot = RoutineExecutionSnapshot.capture(routine_executions) if routine_executions is not None else None
        if routine_institutions is not None and not isinstance(routine_institutions, RoutineInstitutionLedger):
            raise TypeError("routine_institutions must be a RoutineInstitutionLedger or None")
        institution_snapshot = RoutineInstitutionSnapshot.capture(routine_institutions) if routine_institutions is not None else None
        if institutional_politics is not None and not isinstance(institutional_politics, InstitutionalPoliticalLedger):
            raise TypeError("institutional_politics must be an InstitutionalPoliticalLedger or None")
        if goal_book is not None and not isinstance(goal_book, GoalBook):
            raise TypeError("goal_book must be a GoalBook or None")
        if goal_event_adapter is not None:
            if not isinstance(goal_event_adapter, GoalEventAdapter):
                raise TypeError("goal_event_adapter must be a GoalEventAdapter or None")
            if goal_book is None or goal_event_adapter.goals is not goal_book:
                raise ValueError("goal event adapter must share the checkpoint GoalBook")
        goal_snapshot_json = GoalBookSnapshot.capture(goal_book).to_json() if goal_book is not None else None
        goal_replay_json = GoalEventReplaySnapshot.capture(goal_event_adapter).to_json() if goal_event_adapter is not None else None
        if goal_review_decisions is not None and not isinstance(goal_review_decisions, GoalReviewDecisionLedger):
            raise TypeError("goal_review_decisions must be a GoalReviewDecisionLedger or None")
        goal_decisions_snapshot = GoalReviewDecisionSnapshot.capture(goal_review_decisions) if goal_review_decisions is not None else None
        if goal_decisions_snapshot is not None and any(record[7] > current_tick for record in goal_decisions_snapshot.records):
            raise ValueError("goal review decisions cannot occur after the checkpoint tick")
        if goal_decisions_snapshot is not None:
            if goal_book is None:
                raise ValueError("goal review decisions require the corresponding GoalBook")
            known_goals = {goal.goal_id: goal.owner_id for goal in goal_book.goals.values()}
            for record in goal_decisions_snapshot.records:
                if known_goals.get(record[3]) != record[2]:
                    raise ValueError("goal review decision references an unknown goal or owner")
                try:
                    source_event = coordinator.events.get(record[1])
                except KeyError:
                    raise ValueError(f"goal review decision references missing world event: {record[1]}") from None
                if source_event.tick > record[7] or record[2] not in source_event.participants:
                    raise ValueError("goal review decision does not match its source event")
        if identity_decisions is not None and not isinstance(identity_decisions, IdentityDecisionLedger):
            raise TypeError("identity_decisions must be an IdentityDecisionLedger or None")
        identity_snapshot = IdentityDecisionSnapshot.capture(identity_decisions) if identity_decisions is not None else None
        if identity_snapshot is not None:
            unknown_profiles = sorted(
                profile[0] for profile in identity_snapshot.profiles
                if profile[0] not in npcs
            )
            if unknown_profiles:
                raise ValueError(
                    "identity profiles reference NPCs missing from checkpoint: "
                    + ", ".join(unknown_profiles)
                )
            for record in identity_snapshot.decisions:
                if record[6] > current_tick:
                    raise ValueError("identity decisions cannot occur after the checkpoint tick")
                try:
                    source_event = coordinator.events.get(record[1])
                except KeyError:
                    raise ValueError(f"identity decision references missing world event: {record[1]}") from None
                if source_event.tick > record[6]:
                    raise ValueError("identity decision predates its source event")
                present = record[2] in source_event.participants if record[12] == "participant" else record[2] in source_event.witnesses
                if not present:
                    raise ValueError("identity decision role does not match its source event")
        if identity_goal_reviews is not None and not isinstance(identity_goal_reviews, IdentityGoalReviewDecisionLedger):
            raise TypeError("identity_goal_reviews must be an IdentityGoalReviewDecisionLedger or None")
        identity_goal_review_snapshot = IdentityGoalReviewSnapshot.capture(identity_goal_reviews) if identity_goal_reviews is not None else None
        if identity_goal_review_snapshot is not None:
            if goal_book is None or identity_snapshot is None:
                raise ValueError("identity-goal reviews require the corresponding GoalBook and identity decisions")
            identity_by_id = {record[0]: record for record in identity_snapshot.decisions}
            goal_owners = {goal.goal_id: goal.owner_id for goal in goal_book.goals.values()}
            events_by_id = {event.event_id: event for event in coordinator.events.snapshot()}
            for record in identity_goal_review_snapshot.records:
                (decision_id, accepted, decision_tick, _rationale, identity_id, event_id,
                 owner_id, identity_policy_id, axis, delta, goal_id, _policy_id, _action,
                 proposed_tick, _current_category, _proposed_category, _current_priority,
                 _proposed_priority, _current_confidence, _proposed_confidence) = record
                identity = identity_by_id.get(identity_id)
                source = events_by_id.get(event_id)
                if (identity is None or not identity[5] or identity[2] != owner_id
                        or identity[1] != event_id or identity[3] != identity_policy_id
                        or identity[4] != axis or not math.isclose(identity[10], delta, abs_tol=1e-12)
                        or identity[6] > proposed_tick or proposed_tick > decision_tick
                        or decision_tick > current_tick):
                    raise ValueError("identity-goal review does not follow its accepted identity decision")
                if goal_owners.get(goal_id) != owner_id:
                    raise ValueError("identity-goal review references an unknown goal or owner")
                if source is None or source.tick > identity[6]:
                    raise ValueError("identity-goal review references a missing or future source event")
                if (identity[12] == "participant" and owner_id not in source.participants) or (
                        identity[12] == "witness" and owner_id not in source.witnesses):
                    raise ValueError("identity-goal review role does not match its source event")
        if testimony_inquiries is not None and not isinstance(testimony_inquiries, TestimonyInquiryLedger):
            raise TypeError("testimony_inquiries must be a TestimonyInquiryLedger or None")
        inquiry_snapshot = TestimonyInquirySnapshot.capture(testimony_inquiries) if testimony_inquiries is not None else None
        if inquiry_snapshot is not None:
            for inquiry in inquiry_snapshot.restore().inquiries():
                if inquiry.asked_tick > current_tick:
                    raise ValueError("testimony inquiries cannot be asked after the checkpoint tick")
                try:
                    source_event = coordinator.events.get(inquiry.event_id)
                except KeyError:
                    raise ValueError(f"testimony inquiry references missing world event: {inquiry.event_id}") from None
                if source_event.tick > inquiry.asked_tick or inquiry.witness_id not in source_event.witnesses:
                    raise ValueError("testimony inquiry does not match its source event")
            if any(response.answered_tick > current_tick for response in inquiry_snapshot.restore().responses()):
                raise ValueError("testimony responses cannot occur after the checkpoint tick")
        if testimony is not None and not isinstance(testimony, TestimonyLedger):
            raise TypeError("testimony must be a TestimonyLedger or None")
        if testimony is not None:
            for record in testimony.snapshot():
                if record.event_tick > current_tick:
                    raise ValueError("testimony cannot refer to events after the checkpoint tick")
                try:
                    source_event = coordinator.events.get(record.event_id)
                except KeyError:
                    raise ValueError(f"testimony references missing world event: {record.event_id}") from None
                if source_event.tick != record.event_tick or record.witness_id not in source_event.witnesses:
                    raise ValueError("testimony does not match its source event")
        political_snapshot_json = json.dumps(institutional_politics.snapshot(), sort_keys=True, separators=(",", ":"), allow_nan=False) if institutional_politics is not None else None
        if travel is not None and not isinstance(travel, TravelLedger):
            raise TypeError("travel must be a TravelLedger or None")
        travel_snapshot = TravelSnapshot.capture(travel) if travel is not None else None
        if travel_snapshot is not None:
            if any(journey.started_tick > current_tick or (journey.arrived_tick is not None and journey.arrived_tick > current_tick) for journey in travel_snapshot.journeys):
                raise ValueError("travel journeys cannot start or arrive after the checkpoint tick")
            if any(tick > current_tick for tick, _signature, _result in travel_snapshot.ticks):
                raise ValueError("travel tick history cannot occur after the checkpoint tick")
            if any(journey.owner_id not in npcs for journey in travel_snapshot.journeys):
                raise ValueError("travel journeys reference NPCs missing from checkpoint")
            routine_journeys = [journey for journey in travel_snapshot.journeys if journey.routine_id is not None]
            if routine_journeys and routines_snapshot is None:
                raise ValueError("routine-linked travel requires the corresponding RoutineBook")
            if routine_journeys:
                known_routines = {block.routine_id: block for block in routines_snapshot.blocks}
                for journey in routine_journeys:
                    block = known_routines.get(journey.routine_id)
                    if block is None or block.owner_id != journey.owner_id or block.location_id != journey.destination:
                        raise ValueError("routine-linked travel does not match its saved routine block")
        if execution_snapshot is not None:
            known_routines = {block.routine_id for block in routines.snapshot()}
            if any(record.routine_id not in known_routines for record in execution_snapshot.records):
                raise ValueError("routine execution history references an unknown routine")
        if presence is not None and not isinstance(presence, PresenceLedger):
            raise TypeError("presence must be a PresenceLedger or None")
        presence_snapshot = PresenceSnapshot.capture(presence) if presence is not None else None
        if presence_snapshot is not None:
            if any(record.updated_tick > current_tick for record in presence_snapshot.records):
                raise ValueError("NPC presence cannot be updated after the checkpoint tick")
            if any(tick > current_tick for tick, _signature, _records in presence_snapshot.ticks):
                raise ValueError("presence tick history cannot occur after the checkpoint tick")
            presence_owners = {record.owner_id for record in presence_snapshot.records}
            presence_owners.update(record.owner_id for _tick, _signature, records in presence_snapshot.ticks for record in records)
            if any(owner_id not in npcs for owner_id in presence_owners):
                raise ValueError("presence records reference NPCs missing from checkpoint")
        if presence_encounters is not None and not isinstance(presence_encounters, PresenceEncounterLedger):
            raise TypeError("presence_encounters must be a PresenceEncounterLedger or None")
        encounter_snapshot = PresenceEncounterSnapshot.capture(presence_encounters) if presence_encounters is not None else None
        if encounter_snapshot is not None:
            if any(record.tick > current_tick for record in encounter_snapshot.records):
                raise ValueError("NPC encounters cannot occur after the checkpoint tick")
            if any(tick > current_tick for tick, _signature, _records in encounter_snapshot.ticks):
                raise ValueError("encounter replay history cannot occur after the checkpoint tick")
            encounter_owners = {owner for record in encounter_snapshot.records for owner in record.participants}
            if any(owner not in npcs for owner in encounter_owners):
                raise ValueError("encounter records reference NPCs missing from checkpoint")
            if (encounter_snapshot.records or encounter_snapshot.ticks) and presence_snapshot is None:
                raise ValueError("presence encounters require the corresponding presence ledger")
            known_presence = {record.owner_id: record for record in presence_snapshot.records} if presence_snapshot is not None else {}
            for record in encounter_snapshot.records:
                if any(owner not in known_presence for owner in record.participants):
                    raise ValueError("encounter participants require saved physical presence")
                for interaction_id in record.trust_interaction_ids:
                    interaction = trust._interactions.get(interaction_id)
                    if (interaction is None or interaction.observed_tick != record.tick
                            or {interaction.observer_id, interaction.target_id} != set(record.participants)):
                        raise ValueError("encounter trust history does not match its participants")
                if (record.conversation_id is not None
                        and record.conversation_id not in coordinator.conversation_adapter._results):
                    raise ValueError("encounter references a conversation missing from checkpoint replay")
                # Presence is current state; participants may have moved since this historical encounter.
        if familiarity is not None and not isinstance(familiarity, SocialFamiliarityLedger):
            raise TypeError("familiarity must be a SocialFamiliarityLedger or None")
        familiarity_snapshot = SocialFamiliaritySnapshot.capture(familiarity) if familiarity is not None else None
        if familiarity_snapshot is not None:
            if any(item.tick > current_tick for item in familiarity_snapshot.observations):
                raise ValueError("familiarity observations cannot occur after the checkpoint tick")
            if any(item.observer_id not in npcs or item.target_id not in npcs for item in familiarity_snapshot.observations):
                raise ValueError("familiarity observations reference NPCs missing from checkpoint")
            if presence_encounters is None and familiarity_snapshot.observations:
                raise ValueError("familiarity observations require their source encounter ledger")
            known_encounters = {record.encounter_id: record for record in presence_encounters.snapshot()} if presence_encounters is not None else {}
            for item in familiarity_snapshot.observations:
                source = known_encounters.get(item.encounter_id)
                if (source is None or source.tick != item.tick
                        or {item.observer_id, item.target_id} != set(source.participants)):
                    raise ValueError("familiarity observation does not match its source encounter")
        if emotions is not None and not isinstance(emotions, NPCEmotionalEventLedger):
            raise TypeError("emotions must be an NPCEmotionalEventLedger or None")
        emotional_snapshot = EmotionalEventSnapshot.capture(emotions) if emotions is not None else None
        if emotional_snapshot is not None:
            emotional_ledger = emotional_snapshot.restore()
            if emotional_ledger.current_tick > current_tick:
                raise ValueError("emotional state cannot be sampled after the checkpoint tick")
            emotional_npc_ids = set(npcs)
            for state in emotional_ledger.states():
                if state.npc_id not in emotional_npc_ids:
                    raise ValueError("emotional states reference NPCs missing from checkpoint")
            journal_events = {event.event_id: event for event in coordinator.events.snapshot()}
            for source_event in emotional_ledger._events.values():
                authoritative = journal_events.get(source_event.event_id)
                if authoritative != source_event:
                    raise ValueError(
                        "emotional event history does not match the authoritative world journal"
                    )
            for event_id, npc_id, _rule_id in emotional_ledger._applied:
                source_event = journal_events.get(event_id)
                if source_event is None:
                    raise ValueError(f"emotional replay references missing world event: {event_id}")
                if npc_id not in emotional_npc_ids:
                    raise ValueError("emotional replay references NPCs missing from checkpoint")
                if npc_id not in source_event.participants + source_event.witnesses:
                    raise ValueError("emotional replay owner does not belong to its source event")
            if any(event.tick > current_tick for event in emotional_ledger._events.values()):
                raise ValueError("emotional events cannot occur after the checkpoint tick")
        if stress is not None and not isinstance(stress, NPCStressLedger):
            raise TypeError("stress must be an NPCStressLedger or None")
        stress_snapshot = NPCStressSnapshot.capture(stress) if stress is not None else None
        if stress_snapshot is not None:
            stress_ledger = stress_snapshot.restore()
            if stress_ledger.current_tick > current_tick:
                raise ValueError("NPC stress cannot be sampled after the checkpoint tick")
            for owner_id, _value in stress_ledger.snapshot()["stress"].items():
                if owner_id not in npcs:
                    raise ValueError("stress records reference NPCs missing from checkpoint")
            journal_events = {event.event_id: event for event in coordinator.events.snapshot()}
            for record in stress_ledger.records():
                source_event = journal_events.get(record.event_id)
                if source_event is None:
                    raise ValueError(f"stress record references missing world event: {record.event_id}")
                if (record.owner_id not in source_event.participants + source_event.witnesses
                        or source_event.tick > record.tick):
                    raise ValueError("stress record does not match its source world event")
                if record.tick > current_tick:
                    raise ValueError("stress records cannot occur after the checkpoint tick")
        if conditioning is not None and not isinstance(conditioning, NPCConditioningLedger):
            raise TypeError("conditioning must be an NPCConditioningLedger or None")
        conditioning_snapshot = NPCConditioningSnapshot.capture(conditioning) if conditioning is not None else None
        if conditioning_snapshot is not None:
            conditioning_ledger = conditioning_snapshot.restore()
            if conditioning_ledger.current_tick > current_tick:
                raise ValueError("NPC conditioning cannot be sampled after the checkpoint tick")
            for (owner_id, _cue), _value in conditioning_ledger._associations.items():
                if owner_id not in npcs:
                    raise ValueError("conditioning associations reference NPCs missing from checkpoint")
            journal_events = {event.event_id: event for event in coordinator.events.snapshot()}
            for record in conditioning_ledger.records():
                source_event = journal_events.get(record.source_event_id)
                if source_event is None:
                    raise ValueError(f"conditioning record references missing world event: {record.source_event_id}")
                if (record.owner_id not in source_event.participants + source_event.witnesses
                        or source_event.tick > record.tick):
                    raise ValueError("conditioning record does not match its source world event")
                if record.tick > current_tick:
                    raise ValueError("conditioning records cannot occur after the checkpoint tick")
        if psychological_learning_decisions is not None and not isinstance(psychological_learning_decisions, PsychologicalLearningDecisionLedger):
            raise TypeError("psychological_learning_decisions must be a PsychologicalLearningDecisionLedger or None")
        learning_decision_snapshot = PsychologicalLearningDecisionSnapshot.capture(psychological_learning_decisions) if psychological_learning_decisions is not None else None
        if learning_decision_snapshot is not None:
            if conditioning_snapshot is None:
                raise ValueError("psychological learning decisions require the corresponding conditioning ledger")
            conditioning_records = {record.record_id: record for record in conditioning_snapshot.restore().records()}
            journal_events = {event.event_id: event for event in coordinator.events.snapshot()}
            for item in learning_decision_snapshot.decisions:
                decision_id, owner_id, source_event_id, rule_id, cue, accepted, decision_tick = item[:7]
                if owner_id not in npcs or decision_tick > current_tick:
                    raise ValueError("psychological learning decisions reference an unknown NPC or future tick")
                source_event = journal_events.get(source_event_id)
                if source_event is None or source_event.tick > decision_tick or owner_id not in source_event.participants + source_event.witnesses:
                    raise ValueError("psychological learning decision does not match its source world event")
                applied = conditioning_records.get(f"psych-learning:{decision_id}")
                if accepted:
                    if applied is None or (applied.owner_id, applied.source_event_id, applied.cue, applied.tick) != (owner_id, source_event_id, cue, decision_tick):
                        raise ValueError("accepted psychological learning decision is missing its conditioning record")
                elif applied is not None:
                    raise ValueError("rejected psychological learning decision cannot have an applied conditioning record")
        if relationships is not None and not isinstance(relationships, SocialRelationshipLedger):
            raise TypeError("relationships must be a SocialRelationshipLedger or None")
        relationship_snapshot = SocialRelationshipSnapshot.capture(relationships) if relationships is not None else None
        if relationship_snapshot is not None:
            if any(item.tick > current_tick for item in relationship_snapshot.changes):
                raise ValueError("relationship changes cannot occur after the checkpoint tick")
            if any(item.observer_id not in npcs or item.target_id not in npcs for item in relationship_snapshot.changes):
                raise ValueError("relationship changes reference NPCs missing from checkpoint")
            for item in relationship_snapshot.changes:
                try:
                    source_event = coordinator.events.get(item.source_event_id)
                except KeyError:
                    raise ValueError(f"relationship change references missing world event: {item.source_event_id}") from None
                if (source_event.tick > item.tick
                        or item.observer_id not in source_event.participants + source_event.witnesses
                        or item.target_id not in source_event.participants + source_event.witnesses):
                    raise ValueError("relationship change does not match its source world event")
        misconduct_snapshot = None
        if misconduct is not None:
            if not isinstance(misconduct, MisconductReportingSystem):
                raise TypeError("misconduct must be a MisconductReportingSystem or None")
            misconduct_snapshot = MisconductSnapshot.capture(misconduct)
            if any(report.filed_tick > current_tick for report in misconduct_snapshot.reports):
                raise ValueError("misconduct reports cannot be filed after the checkpoint tick")
            if any(decision.tick > current_tick for decision in misconduct_snapshot.decisions):
                raise ValueError("misconduct review decisions cannot occur after the checkpoint tick")
            misconduct_snapshot.restore(coordinator.events)  # validate incident references before saving
        if life_history is not None and not isinstance(life_history, NPCLifeHistory):
            raise TypeError("life_history must be an NPCLifeHistory or None")
        life_history_snapshot = life_history.snapshot() if life_history is not None else None
        if memory_reflections is not None and not isinstance(memory_reflections, MemoryReflectionLedger):
            raise TypeError("memory_reflections must be a MemoryReflectionLedger or None")
        if memory_reflections is not None and life_history is None:
            raise ValueError("memory reflections require the corresponding autobiographical life history")
        if memory_reflections is not None and memory_reflections.history is not life_history:
            raise ValueError("memory reflections must share the checkpoint life history")
        reflection_snapshot = memory_reflections.snapshot() if memory_reflections is not None else None
        if emotional_scar_decisions is not None and not isinstance(emotional_scar_decisions, EmotionalScarDecisionLedger):
            raise TypeError("emotional_scar_decisions must be an EmotionalScarDecisionLedger or None")
        if emotional_scar_decisions is not None:
            if emotional_scar_decisions.current_tick > current_tick:
                raise ValueError("emotional scar decisions cannot occur after the checkpoint tick")
            if emotional_scars is not None and emotional_scars.snapshot() != emotional_scar_decisions.scars.snapshot():
                raise ValueError("emotional scar decisions and supplied scar ledger must share identical state")
            emotional_scars = emotional_scar_decisions.scars
            if life_history is None:
                raise ValueError("emotional scar decisions require the corresponding autobiographical life history")
            known_npcs = set(npcs)
            journal_events = {event.event_id: event for event in coordinator.events.snapshot()}
            known_memories = {memory.memory_id: memory for memory in life_history.memories()}
            for proposal in emotional_scar_decisions.proposals():
                source = journal_events.get(proposal.source_event_id)
                memory = known_memories.get(proposal.source_memory_id)
                if proposal.owner_id not in known_npcs:
                    raise ValueError("emotional scar proposal references an NPC missing from checkpoint")
                if (source is None or source.tick > proposal.proposed_tick
                        or proposal.proposed_tick > current_tick
                        or proposal.owner_id not in source.participants + source.witnesses):
                    raise ValueError("emotional scar proposal does not match its source world event")
                if (memory is None or memory.owner_id != proposal.owner_id
                        or memory.event_id != proposal.source_event_id
                        or memory.tick > proposal.proposed_tick):
                    raise ValueError("emotional scar proposal requires its owner's autobiographical source memory")
            for decision in emotional_scar_decisions.decisions():
                if decision.owner_id not in known_npcs or decision.decision_tick > current_tick:
                    raise ValueError("emotional scar decision references an unknown NPC or future tick")
        scar_snapshot = EmotionalScarSnapshot.capture(emotional_scars) if emotional_scars is not None else None
        scar_decision_snapshot = EmotionalScarDecisionSnapshot.capture(emotional_scar_decisions) if emotional_scar_decisions is not None else None
        if scar_identity_proposals is not None and not isinstance(scar_identity_proposals, ScarIdentityProposalLedger):
            raise TypeError("scar_identity_proposals must be a ScarIdentityProposalLedger or None")
        scar_identity_proposal_snapshot = ScarIdentityProposalSnapshot.capture(scar_identity_proposals) if scar_identity_proposals is not None else None
        if scar_snapshot is not None:
            scar_ledger = scar_snapshot.restore()
            if scar_ledger.current_tick > current_tick:
                raise ValueError("emotional scars cannot be sampled after the checkpoint tick")
            known_npcs = set(npcs)
            journal_events = {event.event_id: event for event in coordinator.events.snapshot()}
            known_memories = {memory.memory_id: memory for memory in life_history.memories()} if life_history is not None else {}
            for scar in scar_ledger.scars():
                source = journal_events.get(scar.source_event_id)
                memory = known_memories.get(scar.source_memory_id)
                if scar.owner_id not in known_npcs:
                    raise ValueError("emotional scar references an NPC missing from checkpoint")
                if source is None or source.tick > scar.created_tick or scar.created_tick > current_tick:
                    raise ValueError("emotional scar does not match its source world event")
                if scar.owner_id not in source.participants + source.witnesses:
                    raise ValueError("emotional scar owner does not belong to its source world event")
                if memory is None or memory.owner_id != scar.owner_id or memory.event_id != scar.source_event_id:
                    raise ValueError("emotional scar requires its owner's autobiographical source memory")
            if any(recovery.tick > current_tick for recovery in scar_ledger.recoveries()):
                raise ValueError("emotional scar recovery cannot occur after the checkpoint tick")
        if scar_identity_proposal_snapshot is not None:
            if scar_snapshot is None or identity_snapshot is None:
                raise ValueError("scar identity proposals require emotional scars and identity decisions")
            scar_by_id = {item.scar_id: item for item in scar_snapshot.restore().scars()}
            for evidence in scar_identity_proposal_snapshot.records:
                proposal = evidence.proposal
                scar = scar_by_id.get(evidence.scar_id)
                source = {event.event_id: event for event in coordinator.events.snapshot()}.get(proposal.event_id)
                if (scar is None or scar.owner_id != proposal.npc_id or scar.source_event_id != proposal.event_id
                        or scar.emotion_axis != evidence.emotion_axis or scar.cue_id != evidence.cue_id
                        or source is None or source.tick > evidence.evaluated_tick
                        or evidence.evaluated_tick > current_tick or evidence.evaluated_tick < scar.created_tick
                        or proposal.evidence_strength != evidence.severity
                        or (proposal.role == "participant" and proposal.npc_id not in source.participants)
                        or (proposal.role == "witness" and proposal.npc_id not in source.witnesses)):
                    raise ValueError("scar identity proposal provenance does not match saved scar and event history")
                if proposal.npc_id not in {profile[0] for profile in identity_snapshot.profiles}:
                    raise ValueError("scar identity proposal references an unknown identity profile")
                matching = [d for d in identity_snapshot.decisions if d[1] == proposal.event_id and d[2] == proposal.npc_id and d[3] == proposal.policy_id]
                if len(matching) > 1:
                    raise ValueError("scar identity proposal has conflicting decision provenance")
                if matching:
                    d = matching[0]
                    if (d[4] != proposal.axis or d[8] != proposal.before or d[9] != proposal.after
                            or d[10] != proposal.delta or d[12] != proposal.role):
                        raise ValueError("identity decision disagrees with its scar-informed proposal")
        if reflection_snapshot is not None:
            reflection_ledger = reflection_snapshot.restore(life_history)
            if any(entry.tick > current_tick or entry.owner_id not in npcs for entry in reflection_ledger.entries()):
                raise ValueError("memory reflections reference an unknown NPC or future tick")
        if life_history_snapshot is not None:
            known_npcs = set(npcs)
            journal_events = {event.event_id: event for event in coordinator.events.snapshot()}
            for memory in life_history.memories():
                if memory.owner_id not in known_npcs or any(x not in known_npcs for x in memory.involved_npc_ids):
                    raise ValueError("autobiographical memory references NPCs missing from checkpoint")
                source = journal_events.get(memory.event_id)
                if (source is None or source.tick > memory.tick or memory.tick > current_tick
                        or memory.owner_id not in source.participants + source.witnesses
                        or any(x not in source.participants + source.witnesses for x in memory.involved_npc_ids)):
                    raise ValueError("autobiographical memory does not match its source world event")
            for action in life_history.actions():
                source = journal_events.get(action.event_id)
                if (action.owner_id not in known_npcs or action.target_id not in known_npcs
                        or action.tick > current_tick or source is None
                        or source.tick > action.tick
                        or action.owner_id not in source.participants + source.witnesses
                        or action.target_id not in source.participants + source.witnesses):
                    raise ValueError("personal history action does not match its source world event")
        action_execution_snapshot = None
        action_world_facts_payload = None
        action_resources_payload = None
        action_replanning_snapshot = None
        action_evaluation_snapshot = None
        if (action_world_facts is None) != (action_resources is None):
            raise ValueError("action_world_facts and action_resources must be supplied together")
        if action_executions is not None and (action_world_facts is None or action_resources is None):
            raise ValueError("action execution checkpoints require world facts and resource balances")
        if action_world_facts is not None:
            if not isinstance(action_world_facts, set) or not isinstance(action_resources, dict):
                raise TypeError("action_world_facts and action_resources must be a set and dict")
            normalized_facts = ActionExecutionLedger._canonical_facts(action_world_facts)
            normalized_resources = ActionExecutionLedger._canonical_resources(action_resources)
            action_world_facts_payload = json.dumps(sorted(normalized_facts), separators=(",", ":"), allow_nan=False)
            action_resources_payload = json.dumps(normalized_resources, sort_keys=True, separators=(",", ":"), allow_nan=False)
        if action_executions is not None:
            if not isinstance(action_executions, ActionExecutionLedger):
                raise TypeError("action_executions must be an ActionExecutionLedger or None")
            if action_executions.events is not coordinator.events:
                raise ValueError("action execution ledger must share the checkpoint world event journal")
            if action_executions.goals is not None and action_executions.goals is not goal_book:
                raise ValueError("action execution ledger must share the checkpoint GoalBook")
            if any(policy.goal_progress for policy in action_executions.policies.values()):
                if goal_book is None or action_executions.goals is not goal_book:
                    raise ValueError("goal-progress action policies require the checkpoint GoalBook to be shared by the execution ledger")
            known_npcs = set(npcs)
            journal = {event.event_id: event for event in coordinator.events.snapshot()}
            action_execution_snapshot = action_executions.to_snapshot()
            for record in action_executions.snapshot():
                event = journal.get(record.event_id)
                if (record.owner_id not in known_npcs or record.tick > current_tick
                        or event is None or event.tick != record.tick
                        or record.owner_id not in event.participants
                        or event.event_type != "npc_action_execution"):
                    raise ValueError("action execution record does not match checkpoint NPCs and event history")
            for active in action_executions.active():
                started = journal.get("action-execution:" + active.execution_id + ":started")
                if (active.owner_id not in known_npcs or active.started_tick > current_tick
                        or active.last_tick > current_tick or started is None
                        or started.tick != active.started_tick
                        or active.owner_id not in started.participants
                        or started.event_type != "npc_action_started"):
                    raise ValueError("active action execution does not match checkpoint NPCs and event history")
                for event_id, event in journal.items():
                    if event_id.startswith("action-execution:" + active.execution_id + ":tick:"):
                        if event.tick > current_tick or event.event_type != "npc_action_progress":
                            raise ValueError("action execution progress event is invalid for checkpoint")
        if action_evaluations is not None:
            if not isinstance(action_evaluations, ActionPlanEvaluationLedger):
                raise TypeError("action_evaluations must be an ActionPlanEvaluationLedger or None")
            if action_executions is None or action_evaluations.executions is not action_executions:
                raise ValueError("action evaluations require the checkpoint action execution ledger")
            if action_evaluations.events is not coordinator.events:
                raise ValueError("action evaluations must share the checkpoint world event journal")
            action_evaluation_snapshot = action_evaluations.to_snapshot()
            raw_evaluations = json.loads(action_evaluation_snapshot.to_json())
            journal = {event.event_id: event for event in coordinator.events.snapshot()}
            records = {record.execution_id: record for record in action_executions.snapshot()}
            for evaluation in raw_evaluations["evaluations"]:
                record = records.get(evaluation["execution_id"])
                event = journal.get(evaluation["evaluation_id"])
                if (record is None or record.owner_id != evaluation["owner_id"]
                        or record.action_id != evaluation["action_id"] or record.tick > current_tick
                        or event is None or event.event_type != "npc_action_evaluated"
                        or event.tick != record.tick or event.participants != (record.owner_id,)
                        or dict(event.attributes).get("execution_id") != record.execution_id
                        or dict(event.attributes).get("action_id") != record.action_id):
                    raise ValueError("action evaluation does not match checkpoint execution and event history")
                evidence_ids = evaluation["evidence_event_ids"]
                if record.event_id not in evidence_ids:
                    raise ValueError("action evaluation omits its terminal execution event")
                for evidence_id in evidence_ids:
                    evidence = journal.get(evidence_id)
                    if (evidence is None or evidence.tick > current_tick
                            or record.owner_id not in evidence.participants
                            or dict(evidence.attributes).get("execution_id") != evaluation["execution_id"]):
                        raise ValueError("action evaluation references missing or mismatched evidence")
            for plan_evaluation in raw_evaluations.get("plan_evaluations", []):
                plan_id = plan_evaluation["plan_id"]
                event = journal.get(f"npc-plan-evaluation:{plan_id}")
                if (event is None or event.event_type != "npc_plan_evaluated"
                        or event.participants != (plan_evaluation["owner_id"],)
                        or event.tick > current_tick
                        or dict(event.attributes).get("plan_id") != plan_id):
                    raise ValueError("aggregate plan evaluation does not match checkpoint event history")
                for evidence_id in plan_evaluation["evidence_event_ids"]:
                    evidence = journal.get(evidence_id)
                    if (evidence is None or evidence.tick > current_tick
                            or plan_evaluation["owner_id"] not in evidence.participants):
                        raise ValueError("aggregate plan evaluation references invalid evidence")
        if action_replanning is not None:
            if not isinstance(action_replanning, NPCActionReplanningCoordinator):
                raise TypeError("action_replanning must be an NPCActionReplanningCoordinator or None")
            if action_executions is None or action_replanning.executions is not action_executions:
                raise ValueError("replanning history requires the checkpoint action execution ledger")
            if action_replanning.events is not coordinator.events:
                raise ValueError("replanning coordinator must share the checkpoint world event journal")
            if action_replanning.evaluations is not action_evaluations:
                raise ValueError("replanning coordinator and checkpoint must share the action evaluation ledger")
            if action_replanning.decisions.goals is not goal_book:
                raise ValueError("replanning coordinator must share the checkpoint GoalBook")
            if action_replanning.experience_transfers is not None and (
                    action_replanning.experience_transfers is not experience_transfers
                    or action_replanning.life_history is not life_history):
                raise ValueError("experience-aware replanning must share the checkpoint life history and transfer ledger")
            action_replanning_snapshot = action_replanning.to_snapshot()
            raw_replanning = json.loads(action_replanning_snapshot.to_json())
            for request in raw_replanning["requests"]:
                event = coordinator.events.get(request["event_id"])
                if (request["owner_id"] not in npcs or request["tick"] > current_tick
                        or event.tick != request["tick"]
                        or request["owner_id"] not in event.participants
                        or event.event_type != "npc_action_replanned"
                        or dict(event.attributes).get("request_id") != request["request_id"]
                        or dict(event.attributes).get("status") != request["status"]):
                    raise ValueError("replanning request does not match checkpoint NPCs and event history")
        experience_transfer_snapshot = None
        if experience_transfers is not None:
            if not isinstance(experience_transfers, NPCExperienceTransferLedger):
                raise TypeError("experience_transfers must be an NPCExperienceTransferLedger or None")
            if life_history is None or experience_transfers.history is not life_history:
                raise ValueError("experience transfers require the checkpoint autobiographical life history")
            if experience_transfers.events is not coordinator.events:
                raise ValueError("experience transfers must share the checkpoint world event journal")
            experience_transfer_snapshot = experience_transfers.snapshot()
            NPCExperienceTransferLedger(coordinator.events, life_history, experience_transfer_snapshot)
            if any(item.transfer_tick > current_tick for item in experience_transfer_snapshot.records):
                raise ValueError("experience transfers cannot occur after the checkpoint tick")
        if goal_review_applications is not None and not isinstance(goal_review_applications, GoalReviewApplicationLedger):
            raise TypeError('goal_review_applications must be a GoalReviewApplicationLedger or None')
        goal_review_applications_snapshot = GoalReviewApplicationSnapshot.capture(goal_review_applications) if goal_review_applications is not None else None
        if goal_review_applications_snapshot is not None:
            if goal_decisions_snapshot is None or goal_snapshot_json is None:
                raise ValueError('goal review applications require the matching decision ledger and GoalBook')
            decisions_by_id = {record[0]: record for record in goal_decisions_snapshot.records}
            goals_by_id = {record[0]: record for record in GoalBookSnapshot.from_json(goal_snapshot_json).records}
            for record in goal_review_applications_snapshot.records:
                decision = decisions_by_id.get(record[0])
                goal = goals_by_id.get(record[1])
                if decision is None or not decision[6]:
                    raise ValueError('goal review application must reference an accepted decision')
                if goal is None or goal[1] != record[2] or decision[3] != record[1] or decision[2] != record[2]:
                    raise ValueError('goal review application references an unknown goal or owner')
                if record[3] > current_tick or decision[7] != record[3]:
                    raise ValueError('goal review application tick does not match its decision or checkpoint')
                if (goal[2], goal[3], goal[8], goal[11]) != (record[5], record[6], record[7], record[8].value):
                    raise ValueError('goal review application result does not match the checkpoint GoalBook')
        goal_lifecycle_snapshot = None
        if goal_lifecycle is not None:
            if not isinstance(goal_lifecycle, GoalLifecycleLedger):
                raise TypeError('goal_lifecycle must be a GoalLifecycleLedger or None')
            if goal_book is None:
                raise ValueError('goal lifecycle history requires the corresponding GoalBook')
            goal_lifecycle_snapshot = GoalLifecycleSnapshot.capture(goal_lifecycle)
            known_goals = {goal.goal_id: goal.owner_id for goal in goal_book.goals.values()}
            if any(record[1] not in known_goals or known_goals[record[1]] != record[2] or record[5] > current_tick for record in goal_lifecycle_snapshot.records):
                raise ValueError('goal lifecycle history references an unknown goal, owner, or future tick')
            latest_status = {record[1]: record[4] for record in goal_lifecycle_snapshot.records}
            if any(record[5] < goal_book.goals[record[1]].created_tick for record in goal_lifecycle_snapshot.records):
                raise ValueError('goal lifecycle event cannot precede goal creation')
            if any(goal_book.goals[goal_id].status.value != status for goal_id, status in latest_status.items()):
                raise ValueError('goal lifecycle status does not match the checkpoint GoalBook')
            journal_ids = {event.event_id for event in coordinator.events.snapshot()}
            if any(evidence_id not in journal_ids for record in goal_lifecycle_snapshot.records for evidence_id in record[7]) and life_history is None:
                raise ValueError('autobiographical lifecycle evidence requires checkpointed life history')
            if life_history is not None:
                known_evidence = {memory.memory_id for memory in life_history.memories()}
                known_evidence.update(event.event_id for event in coordinator.events.snapshot())
                if experience_transfer_snapshot is not None:
                    known_evidence.update(item.transfer_id for item in experience_transfer_snapshot.records)
                if any(evidence_id not in known_evidence for record in goal_lifecycle_snapshot.records for evidence_id in record[7]):
                    raise ValueError('goal lifecycle evidence references an unknown autobiographical memory')

        goal_commitments_snapshot = None
        if goal_commitments is not None:
            if not isinstance(goal_commitments, GoalCommitmentLedger):
                raise TypeError("goal_commitments must be a GoalCommitmentLedger or None")
            if goal_book is None:
                raise ValueError("goal commitments require the corresponding GoalBook")
            goal_commitments_snapshot = GoalCommitmentSnapshot.capture(goal_commitments)
            known_goals = {goal.goal_id: goal.owner_id for goal in goal_book.goals.values()}
            for item in goal_commitments_snapshot.restore().entries():
                if item.tick > current_tick:
                    raise ValueError("goal commitments cannot occur after the checkpoint tick")
                if known_goals.get(item.selected_goal_id) != item.owner_id:
                    raise ValueError("goal commitment references an unknown selected goal or owner")
                if any(known_goals.get(goal_id) != item.owner_id for goal_id in item.deferred_goal_ids):
                    raise ValueError("goal commitment references an unknown deferred goal or owner")
        envelope = SimulationSaveEnvelope.capture(current_tick, coordinator.events)
        return cls(
            current_tick, envelope.to_json(),
            NPCCollectionSnapshot.capture(list(npcs.values())).to_json(),
            SocialTrustSnapshot.capture(trust).to_json(),
            SocialBeliefSnapshot.capture(beliefs).to_json(),
            WorldEventMemoryReplaySnapshot.capture(coordinator.memory_adapter).to_json(),
            SocialConversationReplaySnapshot.capture(coordinator.conversation_adapter).to_json(),
            SimulationTickReplaySnapshot.capture(coordinator).to_json(),
            coordinator.memory_adapter.ticks_per_hour,
            tuple(sorted((metadata or {}).items())),
            SocialConsequenceReplaySnapshot.capture(consequence_recorder).to_json() if consequence_recorder is not None else None,
            campaign.to_json() if campaign is not None else None,
            misconduct_snapshot.to_json() if misconduct_snapshot is not None else None,
            routines_snapshot.to_json() if routines_snapshot is not None else None,
            execution_snapshot.to_json() if execution_snapshot is not None else None,
            institution_snapshot.to_json() if institution_snapshot is not None else None,
            political_snapshot_json,
            goal_snapshot_json,
            goal_replay_json,
            goal_decisions_snapshot.to_json() if goal_decisions_snapshot is not None else None,
            identity_snapshot.to_json() if identity_snapshot is not None else None,
            inquiry_snapshot.to_json() if inquiry_snapshot is not None else None,
            testimony.to_json() if testimony is not None else None,
            travel_snapshot.to_json() if travel_snapshot is not None else None,
            presence_snapshot.to_json() if presence_snapshot is not None else None,
            encounter_snapshot.to_json() if encounter_snapshot is not None else None,
            familiarity_snapshot.to_json() if familiarity_snapshot is not None else None,
            relationship_snapshot.to_json() if relationship_snapshot is not None else None,
            emotional_snapshot.to_json() if emotional_snapshot is not None else None,
            stress_snapshot.to_json() if stress_snapshot is not None else None,
            conditioning_snapshot.to_json() if conditioning_snapshot is not None else None,
            learning_decision_snapshot.to_json() if learning_decision_snapshot is not None else None,
            life_history_snapshot.to_json() if life_history_snapshot is not None else None,
            reflection_snapshot.to_json() if reflection_snapshot is not None else None,
            scar_snapshot.to_json() if scar_snapshot is not None else None,
            scar_decision_snapshot.to_json() if scar_decision_snapshot is not None else None,
            scar_identity_proposal_snapshot.to_json() if scar_identity_proposal_snapshot is not None else None,
            identity_goal_review_snapshot.to_json() if identity_goal_review_snapshot is not None else None,
            action_execution_snapshot.to_json() if action_execution_snapshot is not None else None,
            action_world_facts_payload,
            action_resources_payload,
            action_replanning_snapshot.to_json() if action_replanning_snapshot is not None else None,
            action_evaluation_snapshot.to_json() if action_evaluation_snapshot is not None else None,
            experience_transfer_snapshot.to_json() if experience_transfer_snapshot is not None else None,
            goal_lifecycle_snapshot.to_json() if goal_lifecycle_snapshot is not None else None,
            goal_review_applications_snapshot.to_json() if goal_review_applications_snapshot is not None else None,
            goal_commitments_snapshot.to_json() if goal_commitments_snapshot is not None else None,
        )

    def _components(self):
        envelope = SimulationSaveEnvelope.from_json(self.events_json)
        if envelope.current_tick != self.current_tick:
            raise ValueError("checkpoint clock does not match event envelope")
        components = (
            envelope,
            NPCCollectionSnapshot.from_json(self.npcs_json),
            SocialTrustSnapshot.from_json(self.trust_json),
            SocialBeliefSnapshot.from_json(self.beliefs_json),
            WorldEventMemoryReplaySnapshot.from_json(self.memory_replay_json),
            SocialConversationReplaySnapshot.from_json(self.conversations_json),
            SimulationTickReplaySnapshot.from_json(self.tick_replay_json),
            SocialConsequenceReplaySnapshot.from_json(self.consequence_replay_json) if self.consequence_replay_json is not None else None,
            LifeItselfCampaign.from_json(self.campaign_json) if self.campaign_json is not None else None,
            MisconductSnapshot.from_json(self.misconduct_json) if self.misconduct_json is not None else None,
            RoutineBookSnapshot.from_json(self.routines_json) if self.routines_json is not None else None,
            RoutineExecutionSnapshot.from_json(self.routine_executions_json) if self.routine_executions_json is not None else None,
            RoutineInstitutionSnapshot.from_json(self.routine_institutions_json) if self.routine_institutions_json is not None else None,
            InstitutionalPoliticalLedger.from_snapshot(json.loads(self.institutional_politics_json)) if self.institutional_politics_json is not None else None,
            GoalBookSnapshot.from_json(self.goals_json) if self.goals_json is not None else None,
            GoalEventReplaySnapshot.from_json(self.goal_event_replay_json) if self.goal_event_replay_json is not None else None,
            GoalReviewDecisionSnapshot.from_json(self.goal_review_decisions_json) if self.goal_review_decisions_json is not None else None,
            IdentityDecisionSnapshot.from_json(self.identity_decisions_json) if self.identity_decisions_json is not None else None,
            TestimonyInquirySnapshot.from_json(self.testimony_inquiries_json) if self.testimony_inquiries_json is not None else None,
            TestimonyLedger.from_json(self.testimony_json) if self.testimony_json is not None else None,
            TravelSnapshot.from_json(self.travel_json) if self.travel_json is not None else None,
            PresenceSnapshot.from_json(self.presence_json) if self.presence_json is not None else None,
            PresenceEncounterSnapshot.from_json(self.presence_encounters_json) if self.presence_encounters_json is not None else None,
            SocialFamiliaritySnapshot.from_json(self.familiarity_json) if self.familiarity_json is not None else None,
            SocialRelationshipSnapshot.from_json(self.relationships_json) if self.relationships_json is not None else None,
            EmotionalEventSnapshot.from_json(self.emotions_json) if self.emotions_json is not None else None,
            NPCStressSnapshot.from_json(self.stress_json) if self.stress_json is not None else None,
            NPCConditioningSnapshot.from_json(self.conditioning_json) if self.conditioning_json is not None else None,
            PsychologicalLearningDecisionSnapshot.from_json(self.psychological_learning_decisions_json) if self.psychological_learning_decisions_json is not None else None,
            LifeHistorySnapshot.from_json(self.life_history_json) if self.life_history_json is not None else None,
            MemoryReflectionSnapshot.from_json(self.memory_reflections_json) if self.memory_reflections_json is not None else None,
            EmotionalScarSnapshot.from_json(self.emotional_scars_json) if self.emotional_scars_json is not None else None,
            EmotionalScarDecisionSnapshot.from_json(self.emotional_scar_decisions_json) if self.emotional_scar_decisions_json is not None else None,
            ScarIdentityProposalSnapshot.from_json(self.scar_identity_proposals_json) if self.scar_identity_proposals_json is not None else None,
            IdentityGoalReviewSnapshot.from_json(self.identity_goal_reviews_json) if self.identity_goal_reviews_json is not None else None,
            ActionExecutionSnapshot.from_json(self.action_executions_json) if self.action_executions_json is not None else None,
            json.loads(self.action_world_facts_json) if self.action_world_facts_json is not None else None,
            json.loads(self.action_resources_json) if self.action_resources_json is not None else None,
            NPCReplanningSnapshot.from_json(self.action_replanning_json) if self.action_replanning_json is not None else None,
            ActionEvaluationSnapshot.from_json(self.action_evaluations_json) if self.action_evaluations_json is not None else None,
            ExperienceTransferSnapshot.from_json(self.experience_transfers_json) if self.experience_transfers_json is not None else None,
            GoalLifecycleSnapshot.from_json(self.goal_lifecycle_json) if self.goal_lifecycle_json is not None else None,
            GoalReviewApplicationSnapshot.from_json(self.goal_review_applications_json) if self.goal_review_applications_json is not None else None,
            GoalCommitmentSnapshot.from_json(self.goal_commitments_json) if self.goal_commitments_json is not None else None,
        )
        goals_snapshot, goal_replay, goal_review_decisions = components[14], components[15], components[16]
        identity_decisions = components[17]
        testimony_inquiries = components[18]
        testimony = components[19]
        travel_snapshot = components[20]
        presence_snapshot = components[21]
        encounter_snapshot = components[22]
        familiarity_snapshot = components[23]
        relationship_snapshot = components[24]
        emotional_snapshot = components[25]
        stress_snapshot = components[26]
        conditioning_snapshot = components[27]
        learning_decisions_snapshot = components[28]
        life_history_snapshot = components[29]
        memory_reflections_snapshot = components[30]
        emotional_scars_snapshot = components[31]
        emotional_scar_decisions_snapshot = components[32]
        scar_identity_proposal_snapshot = components[33]
        identity_goal_review_snapshot = components[34]
        action_execution_snapshot = components[35]
        action_world_facts = components[36]
        action_resources = components[37]
        action_replanning_snapshot = components[38]
        action_evaluation_snapshot = components[39]
        experience_transfer_snapshot = components[40]
        goal_lifecycle_snapshot = components[41]
        goal_review_applications_snapshot = components[42]
        goal_commitments_snapshot = components[43]
        if experience_transfer_snapshot is not None:
            if life_history_snapshot is None:
                raise ValueError("experience transfers require checkpointed autobiographical life history")
            history = life_history_snapshot.restore()
            transfer_ledger = NPCExperienceTransferLedger(envelope.restore_event_ledger(), history, experience_transfer_snapshot)
            known_npcs = {npc.entity_id for npc in NPCCollectionSnapshot.from_json(self.npcs_json).restore().values()}
            if any(record.recipient_id not in known_npcs or record.source_npc_id not in known_npcs
                   or record.transfer_tick > self.current_tick
                   for record in transfer_ledger.snapshot().records):
                raise ValueError("experience transfer references an unknown NPC or future tick")
        if action_evaluation_snapshot is not None and action_execution_snapshot is None:
            raise ValueError("action evaluations require checkpointed action execution state")
        if (action_world_facts is None) != (action_resources is None):
            raise ValueError("action world facts and resources must be checkpointed together")
        if action_execution_snapshot is not None and (action_world_facts is None or action_resources is None):
            raise ValueError("action execution state requires checkpointed world facts and resources")
        if action_world_facts is not None:
            ActionExecutionLedger._canonical_facts(action_world_facts)
            ActionExecutionLedger._canonical_resources(action_resources)
        if action_replanning_snapshot is not None and action_execution_snapshot is None:
            raise ValueError("replanning history requires checkpointed action execution state")
        if action_evaluation_snapshot is not None:
            if action_execution_snapshot is None:
                raise ValueError("action evaluations require checkpointed action execution state")
            journal = {event.event_id: event for event in envelope.restore_event_ledger().snapshot()}
            npc_ids = {npc.entity_id for npc in NPCCollectionSnapshot.from_json(self.npcs_json).restore().values()}
            raw_evaluations = json.loads(action_evaluation_snapshot.to_json())
            records = {item["record"]["execution_id"]: item["record"]
                       for item in json.loads(action_execution_snapshot.to_json())["records"]}
            seen = set()
            for evaluation in raw_evaluations["evaluations"]:
                execution_id = evaluation["execution_id"]
                record = records.get(execution_id)
                event = journal.get(evaluation["evaluation_id"])
                if (execution_id in seen or record is None
                        or evaluation["owner_id"] not in npc_ids
                        or record["owner_id"] != evaluation["owner_id"]
                        or record["action_id"] != evaluation["action_id"]
                        or record["tick"] > self.current_tick
                        or event is None or event.tick != record["tick"]
                        or event.event_type != "npc_action_evaluated"
                        or event.participants != (record["owner_id"],)
                        or dict(event.attributes).get("execution_id") != execution_id
                        or dict(event.attributes).get("action_id") != record["action_id"]):
                    raise ValueError("action evaluation does not match checkpoint execution and event history")
                seen.add(execution_id)
                evidence_ids = evaluation["evidence_event_ids"]
                if record["event_id"] not in evidence_ids:
                    raise ValueError("action evaluation omits its terminal execution event")
                for evidence_id in evidence_ids:
                    evidence = journal.get(evidence_id)
                    if (evidence is None or evidence.tick > self.current_tick
                            or record["owner_id"] not in evidence.participants
                            or dict(evidence.attributes).get("execution_id") != execution_id):
                        raise ValueError("action evaluation references missing or mismatched evidence")
            for plan_evaluation in raw_evaluations.get("plan_evaluations", []):
                plan_id = plan_evaluation["plan_id"]
                event = journal.get(f"npc-plan-evaluation:{plan_id}")
                if (event is None or event.event_type != "npc_plan_evaluated"
                        or event.participants != (plan_evaluation["owner_id"],)
                        or event.tick > self.current_tick
                        or dict(event.attributes).get("plan_id") != plan_id):
                    raise ValueError("aggregate plan evaluation does not match checkpoint event history")
                for evidence_id in plan_evaluation["evidence_event_ids"]:
                    evidence = journal.get(evidence_id)
                    if (evidence is None or evidence.tick > self.current_tick
                            or plan_evaluation["owner_id"] not in evidence.participants):
                        raise ValueError("aggregate plan evaluation references invalid evidence")
        if action_replanning_snapshot is not None:
            journal = {event.event_id: event for event in envelope.restore_event_ledger().snapshot()}
            npc_ids = {npc.entity_id for npc in NPCCollectionSnapshot.from_json(self.npcs_json).restore().values()}
            for request in json.loads(action_replanning_snapshot.to_json())["requests"]:
                event = journal.get(request["event_id"])
                if (request["owner_id"] not in npc_ids or request["tick"] > self.current_tick
                        or event is None or event.tick != request["tick"]
                        or request["owner_id"] not in event.participants
                        or event.event_type != "npc_action_replanned"):
                    raise ValueError("replanning request does not match checkpoint NPCs and event history")
        if action_execution_snapshot is not None:
            journal = {event.event_id: event for event in envelope.restore_event_ledger().snapshot()}
            npc_ids = {npc.entity_id for npc in NPCCollectionSnapshot.from_json(self.npcs_json).restore().values()}
            raw_action_state = json.loads(action_execution_snapshot.to_json())
            for item in raw_action_state["records"]:
                record = item["record"]
                event = journal.get(record["event_id"])
                if (record["owner_id"] not in npc_ids or record["tick"] > self.current_tick
                        or event is None or event.tick != record["tick"]
                        or record["owner_id"] not in event.participants
                        or event.event_type != "npc_action_execution"):
                    raise ValueError("action execution record does not match checkpoint NPCs and event history")
            for active in raw_action_state["active"]:
                event_id = "action-execution:" + active["execution_id"] + ":started"
                event = journal.get(event_id)
                if (active["owner_id"] not in npc_ids or active["started_tick"] > self.current_tick
                        or active["last_tick"] > self.current_tick or event is None
                        or event.tick != active["started_tick"]
                        or active["owner_id"] not in event.participants
                        or event.event_type != "npc_action_started"):
                    raise ValueError("active action execution does not match checkpoint NPCs and event history")
                for progress_id, progress_event in journal.items():
                    if progress_id.startswith("action-execution:" + active["execution_id"] + ":tick:"):
                        if progress_event.tick > self.current_tick or progress_event.event_type != "npc_action_progress":
                            raise ValueError("action execution progress event is invalid for checkpoint")
        if identity_goal_review_snapshot is not None:
            if goals_snapshot is None or identity_decisions is None:
                raise ValueError("identity-goal reviews require the corresponding GoalBook and identity decisions")
            identity_by_id = {record[0]: record for record in identity_decisions.decisions}
            goal_owners = {record[0]: record[1] for record in goals_snapshot.records}
            journal = {event.event_id: event for event in envelope.restore_event_ledger().snapshot()}
            for record in identity_goal_review_snapshot.records:
                (decision_id, accepted, decision_tick, _rationale, identity_id, event_id,
                 owner_id, identity_policy_id, axis, delta, goal_id, _policy_id, _action,
                 proposed_tick, _current_category, _proposed_category, _current_priority,
                 _proposed_priority, _current_confidence, _proposed_confidence) = record
                identity = identity_by_id.get(identity_id)
                source = journal.get(event_id)
                if (identity is None or not identity[5] or identity[2] != owner_id
                        or identity[1] != event_id or identity[3] != identity_policy_id
                        or identity[4] != axis or not math.isclose(identity[10], delta, abs_tol=1e-12)
                        or identity[6] > proposed_tick or proposed_tick > decision_tick
                        or decision_tick > self.current_tick):
                    raise ValueError("identity-goal review does not follow its accepted identity decision")
                if goal_owners.get(goal_id) != owner_id:
                    raise ValueError("identity-goal review references an unknown goal or owner")
                if source is None or source.tick > identity[6]:
                    raise ValueError("identity-goal review references a missing or future source event")
                if (identity[12] == "participant" and owner_id not in source.participants) or (
                        identity[12] == "witness" and owner_id not in source.witnesses):
                    raise ValueError("identity-goal review role does not match its source event")
        if scar_identity_proposal_snapshot is not None:
            if emotional_scars_snapshot is None or identity_decisions is None:
                raise ValueError("scar identity proposals require emotional scars and identity decisions")
            scar_by_id = {scar.scar_id: scar for scar in emotional_scars_snapshot.restore().scars()}
            journal = {event.event_id: event for event in envelope.restore_event_ledger().snapshot()}
            for evidence in scar_identity_proposal_snapshot.records:
                proposal = evidence.proposal
                scar = scar_by_id.get(evidence.scar_id)
                source = journal.get(proposal.event_id)
                if (scar is None or scar.owner_id != proposal.npc_id or scar.source_event_id != proposal.event_id
                        or scar.emotion_axis != evidence.emotion_axis or scar.cue_id != evidence.cue_id
                        or source is None or source.tick > evidence.evaluated_tick
                        or evidence.evaluated_tick > self.current_tick or evidence.evaluated_tick < scar.created_tick
                        or proposal.evidence_strength != evidence.severity):
                    raise ValueError("scar identity proposal provenance does not match saved scar and event history")
                if proposal.npc_id not in {profile[0] for profile in identity_decisions.profiles}:
                    raise ValueError("scar identity proposal references an unknown identity profile")
                matches = [d for d in identity_decisions.decisions if d[1] == proposal.event_id
                           and d[2] == proposal.npc_id and d[3] == proposal.policy_id]
                if len(matches) > 1 or (matches and (
                        matches[0][4] != proposal.axis or matches[0][8] != proposal.before
                        or matches[0][9] != proposal.after or matches[0][10] != proposal.delta
                        or matches[0][12] != proposal.role or matches[0][6] < evidence.evaluated_tick)):
                    raise ValueError("identity decision disagrees with its scar-informed proposal")
        if emotional_scar_decisions_snapshot is not None:
            if life_history_snapshot is None or emotional_scars_snapshot is None:
                raise ValueError("emotional scar decisions require autobiographical life history and the corresponding scar ledger")
            decision_ledger = emotional_scar_decisions_snapshot.restore()
            saved_scars = emotional_scars_snapshot.restore()
            if decision_ledger.current_tick > self.current_tick:
                raise ValueError("emotional scar decisions cannot occur after the checkpoint tick")
            if decision_ledger.scars.snapshot() != saved_scars.snapshot():
                raise ValueError("emotional scar decisions disagree with the checkpoint scar ledger")
            npc_ids = {npc.entity_id for npc in NPCCollectionSnapshot.from_json(self.npcs_json).restore().values()}
            journal = {event.event_id: event for event in envelope.restore_event_ledger().snapshot()}
            memories = {memory.memory_id: memory for memory in life_history_snapshot.restore().memories()}
            for proposal in decision_ledger.proposals():
                source = journal.get(proposal.source_event_id)
                memory = memories.get(proposal.source_memory_id)
                if (proposal.owner_id not in npc_ids or source is None
                        or source.tick > proposal.proposed_tick or proposal.proposed_tick > self.current_tick
                        or proposal.owner_id not in source.participants + source.witnesses):
                    raise ValueError("emotional scar proposal does not match saved NPCs and source event")
                if (memory is None or memory.owner_id != proposal.owner_id
                        or memory.event_id != proposal.source_event_id
                        or memory.tick > proposal.proposed_tick):
                    raise ValueError("emotional scar proposal requires its owner's saved autobiographical memory")
            for decision in decision_ledger.decisions():
                if decision.owner_id not in npc_ids or decision.decision_tick > self.current_tick:
                    raise ValueError("emotional scar decisions reference an unknown NPC or future tick")
        if emotional_scars_snapshot is not None:
            if life_history_snapshot is None:
                raise ValueError("emotional scars require the corresponding autobiographical life history")
            scars = emotional_scars_snapshot.restore()
            if scars.current_tick > self.current_tick:
                raise ValueError("emotional scars cannot be sampled after the checkpoint tick")
            npc_ids = {npc.entity_id for npc in NPCCollectionSnapshot.from_json(self.npcs_json).restore().values()}
            journal = {event.event_id: event for event in envelope.restore_event_ledger().snapshot()}
            memories = {memory.memory_id: memory for memory in life_history_snapshot.restore().memories()}
            for scar in scars.scars():
                source = journal.get(scar.source_event_id)
                memory = memories.get(scar.source_memory_id)
                if scar.owner_id not in npc_ids:
                    raise ValueError("emotional scar references an NPC missing from checkpoint")
                if source is None or source.tick > scar.created_tick or scar.created_tick > self.current_tick:
                    raise ValueError("emotional scar does not match its source world event")
                if scar.owner_id not in source.participants + source.witnesses:
                    raise ValueError("emotional scar owner does not belong to its source world event")
                if memory is None or memory.owner_id != scar.owner_id or memory.event_id != scar.source_event_id:
                    raise ValueError("emotional scar requires its owner's autobiographical source memory")
            if any(item.tick > self.current_tick for item in scars.recoveries()):
                raise ValueError("emotional scar recovery cannot occur after the checkpoint tick")
        if memory_reflections_snapshot is not None:
            if life_history_snapshot is None:
                raise ValueError("memory reflections require the corresponding autobiographical life history")
            reflection_ledger = memory_reflections_snapshot.restore(life_history_snapshot.restore())
            npc_ids = {npc.entity_id for npc in NPCCollectionSnapshot.from_json(self.npcs_json).restore().values()}
            if any(entry.tick > self.current_tick or entry.owner_id not in npc_ids for entry in reflection_ledger.entries()):
                raise ValueError("memory reflections reference an unknown NPC or future tick")
        if learning_decisions_snapshot is not None:
            npc_ids = {npc.entity_id for npc in NPCCollectionSnapshot.from_json(self.npcs_json).restore().values()}
            conditioning_records = ({record.record_id: record for record in conditioning_snapshot.restore().records()}
                                   if conditioning_snapshot is not None else {})
            if conditioning_snapshot is None:
                raise ValueError("psychological learning decisions require the corresponding conditioning ledger")
            journal_events = {event.event_id: event for event in envelope.restore_event_ledger().snapshot()}
            for item in learning_decisions_snapshot.decisions:
                decision_id, owner_id, source_event_id, _rule_id, cue, accepted, decision_tick = item[:7]
                if owner_id not in npc_ids or decision_tick > self.current_tick:
                    raise ValueError("psychological learning decisions reference an unknown NPC or future tick")
                source_event = journal_events.get(source_event_id)
                if source_event is None or source_event.tick > decision_tick or owner_id not in source_event.participants + source_event.witnesses:
                    raise ValueError("psychological learning decision does not match its source world event")
                applied = conditioning_records.get(f"psych-learning:{decision_id}")
                if accepted and (applied is None or (applied.owner_id, applied.source_event_id, applied.cue, applied.tick) != (owner_id, source_event_id, cue, decision_tick)):
                    raise ValueError("accepted psychological learning decision is missing its conditioning record")
                if not accepted and applied is not None:
                    raise ValueError("rejected psychological learning decision cannot have an applied conditioning record")
        if presence_snapshot is not None:
            if any(record.updated_tick > self.current_tick for record in presence_snapshot.records):
                raise ValueError("NPC presence cannot be updated after the checkpoint tick")
            if any(tick > self.current_tick for tick, _signature, _records in presence_snapshot.ticks):
                raise ValueError("presence tick history cannot occur after the checkpoint tick")
            npc_ids = {npc.entity_id for npc in NPCCollectionSnapshot.from_json(self.npcs_json).restore().values()}
            presence_owners = {record.owner_id for record in presence_snapshot.records}
            presence_owners.update(record.owner_id for _tick, _signature, records in presence_snapshot.ticks for record in records)
            if any(owner_id not in npc_ids for owner_id in presence_owners):
                raise ValueError("presence records reference NPCs missing from checkpoint")
        if travel_snapshot is not None:
            if any(journey.started_tick > self.current_tick or (journey.arrived_tick is not None and journey.arrived_tick > self.current_tick) for journey in travel_snapshot.journeys):
                raise ValueError("travel journeys cannot start or arrive after the checkpoint tick")
            if any(tick > self.current_tick for tick, _signature, _result in travel_snapshot.ticks):
                raise ValueError("travel tick history cannot occur after the checkpoint tick")
            npc_ids = {npc.entity_id for npc in NPCCollectionSnapshot.from_json(self.npcs_json).restore().values()}
            if any(journey.owner_id not in npc_ids for journey in travel_snapshot.journeys):
                raise ValueError("travel journeys reference NPCs missing from checkpoint")
            routine_journeys = [journey for journey in travel_snapshot.journeys if journey.routine_id is not None]
            if routine_journeys and components[10] is None:
                raise ValueError("routine-linked travel requires the corresponding RoutineBook")
            if routine_journeys:
                known_routines = {block.routine_id: block for block in components[10].blocks}
                for journey in routine_journeys:
                    block = known_routines.get(journey.routine_id)
                    if block is None or block.owner_id != journey.owner_id or block.location_id != journey.destination:
                        raise ValueError("routine-linked travel does not match its saved routine block")
        if testimony_inquiries is not None:
            journal = envelope.restore_event_ledger()
            inquiry_ledger = testimony_inquiries.restore()
            for inquiry in inquiry_ledger.inquiries():
                if inquiry.asked_tick > self.current_tick:
                    raise ValueError("testimony inquiries cannot be asked after the checkpoint tick")
                try:
                    event = journal.get(inquiry.event_id)
                except KeyError:
                    raise ValueError(f"testimony inquiry references missing world event: {inquiry.event_id}") from None
                if event.tick > inquiry.asked_tick or inquiry.witness_id not in event.witnesses:
                    raise ValueError("testimony inquiry does not match its source event")
            if any(response.answered_tick > self.current_tick for response in inquiry_ledger.responses()):
                raise ValueError("testimony responses cannot occur after the checkpoint tick")
        if testimony is not None:
            journal = envelope.restore_event_ledger()
            for record in testimony.snapshot():
                if record.event_tick > self.current_tick:
                    raise ValueError("testimony cannot refer to events after the checkpoint tick")
                try:
                    event = journal.get(record.event_id)
                except KeyError:
                    raise ValueError(f"testimony references missing world event: {record.event_id}") from None
                if event.tick != record.event_tick or record.witness_id not in event.witnesses:
                    raise ValueError("testimony does not match its source event")
        if identity_decisions is not None:
            journal = envelope.restore_event_ledger()
            for record in identity_decisions.decisions:
                if record[6] > self.current_tick:
                    raise ValueError("identity decisions cannot occur after the checkpoint tick")
                try:
                    event = journal.get(record[1])
                except KeyError:
                    raise ValueError(f"identity decision references missing world event: {record[1]}") from None
                if event.tick > record[6]:
                    raise ValueError("identity decision predates its source event")
                present = record[2] in event.participants if record[12] == "participant" else record[2] in event.witnesses
                if not present:
                    raise ValueError("identity decision role does not match its source event")
        if goal_review_decisions is not None and any(record[7] > self.current_tick for record in goal_review_decisions.records):
            raise ValueError("goal review decisions cannot occur after the checkpoint tick")
        if goal_review_decisions is not None:
            if goals_snapshot is None:
                raise ValueError("goal review decisions require the corresponding GoalBook")
            known_goals = {record[0]: record[1] for record in goals_snapshot.records}
            journal = envelope.restore_event_ledger()
            for record in goal_review_decisions.records:
                if known_goals.get(record[3]) != record[2]:
                    raise ValueError("goal review decision references an unknown goal or owner")
                try:
                    source_event = journal.get(record[1])
                except KeyError:
                    raise ValueError(f"goal review decision references missing world event: {record[1]}") from None
                if source_event.tick > record[7] or record[2] not in source_event.participants:
                    raise ValueError("goal review decision does not match its source event")
        if goal_replay is not None and goals_snapshot is None:
            raise ValueError("goal event replay history requires the corresponding GoalBook")
        if goal_replay is not None:
            journal = envelope.restore_event_ledger()
            for event_id, signature in goal_replay.entries:
                try:
                    event = journal.get(event_id)
                except KeyError:
                    raise ValueError(f"goal replay references missing world event: {event_id}") from None
                expected = (event.tick, event.event_type, tuple(event.participants),
                            tuple(event.witnesses), repr(event.attributes))
                if signature != expected:
                    raise ValueError(f"goal replay signature disagrees with world event: {event_id}")
        if encounter_snapshot is not None:
            if any(record.tick > self.current_tick for record in encounter_snapshot.records):
                raise ValueError("NPC encounters cannot occur after the checkpoint tick")
            if any(tick > self.current_tick for tick, _signature, _records in encounter_snapshot.ticks):
                raise ValueError("encounter replay history cannot occur after the checkpoint tick")
            npc_ids = {npc.entity_id for npc in NPCCollectionSnapshot.from_json(self.npcs_json).restore().values()}
            if any(owner not in npc_ids for record in encounter_snapshot.records for owner in record.participants):
                raise ValueError("encounter records reference NPCs missing from checkpoint")
            if (encounter_snapshot.records or encounter_snapshot.ticks) and presence_snapshot is None:
                raise ValueError("presence encounters require the corresponding presence ledger")
            presence_by_owner = {record.owner_id: record for record in presence_snapshot.records} if presence_snapshot is not None else {}
            trust_by_id = {item.interaction_id: item for item in components[2].interactions}
            conversation_ids = {key for key, _signature, _result in components[5].entries}
            for record in encounter_snapshot.records:
                if any(owner not in presence_by_owner for owner in record.participants):
                    raise ValueError("encounter participants require saved physical presence")
                for interaction_id in record.trust_interaction_ids:
                    interaction = trust_by_id.get(interaction_id)
                    if (interaction is None or interaction.observed_tick != record.tick
                            or {interaction.observer_id, interaction.target_id} != set(record.participants)):
                        raise ValueError("encounter trust history does not match its participants")
                if record.conversation_id is not None and record.conversation_id not in conversation_ids:
                    raise ValueError("encounter references a conversation missing from checkpoint replay")
                # Current presence may have advanced beyond the historical encounter.
        if familiarity_snapshot is not None:
            if any(item.tick > self.current_tick for item in familiarity_snapshot.observations):
                raise ValueError("familiarity observations cannot occur after the checkpoint tick")
            npc_ids = {npc.entity_id for npc in NPCCollectionSnapshot.from_json(self.npcs_json).restore().values()}
            if any(item.observer_id not in npc_ids or item.target_id not in npc_ids for item in familiarity_snapshot.observations):
                raise ValueError("familiarity observations reference NPCs missing from checkpoint")
            if familiarity_snapshot.observations and encounter_snapshot is None:
                raise ValueError("familiarity observations require their source encounter ledger")
            known_encounters = {record.encounter_id: record for record in encounter_snapshot.records} if encounter_snapshot is not None else {}
            for item in familiarity_snapshot.observations:
                source = known_encounters.get(item.encounter_id)
                if (source is None or source.tick != item.tick
                        or {item.observer_id, item.target_id} != set(source.participants)):
                    raise ValueError("familiarity observation does not match its source encounter")
        if emotional_snapshot is not None:
            emotional_ledger = emotional_snapshot.restore()
            if emotional_ledger.current_tick > self.current_tick:
                raise ValueError("emotional state cannot be sampled after the checkpoint tick")
            npc_ids = {npc.entity_id for npc in NPCCollectionSnapshot.from_json(self.npcs_json).restore().values()}
            if any(state.npc_id not in npc_ids for state in emotional_ledger.states()):
                raise ValueError("emotional states reference NPCs missing from checkpoint")
            journal = envelope.restore_event_ledger()
            for source_event in emotional_ledger._events.values():
                try:
                    authoritative = journal.get(source_event.event_id)
                except KeyError:
                    raise ValueError(
                        f"emotional history references missing world event: {source_event.event_id}"
                    ) from None
                if authoritative != source_event:
                    raise ValueError("emotional event history disagrees with authoritative world journal")
            for event_id, npc_id, _rule_id in emotional_ledger._applied:
                try:
                    source_event = journal.get(event_id)
                except KeyError:
                    raise ValueError(f"emotional replay references missing world event: {event_id}") from None
                if npc_id not in npc_ids:
                    raise ValueError("emotional replay references NPCs missing from checkpoint")
                if npc_id not in source_event.participants + source_event.witnesses:
                    raise ValueError("emotional replay owner does not belong to its source event")
            if any(event.tick > self.current_tick for event in emotional_ledger._events.values()):
                raise ValueError("emotional events cannot occur after the checkpoint tick")
        if stress_snapshot is not None:
            stress_ledger = stress_snapshot.restore()
            if stress_ledger.current_tick > self.current_tick:
                raise ValueError("NPC stress cannot be sampled after the checkpoint tick")
            npc_ids = {npc.entity_id for npc in NPCCollectionSnapshot.from_json(self.npcs_json).restore().values()}
            if any(owner_id not in npc_ids for owner_id in stress_ledger.snapshot()["stress"]):
                raise ValueError("stress records reference NPCs missing from checkpoint")
            journal = envelope.restore_event_ledger()
            for record in stress_ledger.records():
                try:
                    source_event = journal.get(record.event_id)
                except KeyError:
                    raise ValueError(f"stress record references missing world event: {record.event_id}") from None
                if (record.tick > self.current_tick or source_event.tick > record.tick
                        or record.owner_id not in source_event.participants + source_event.witnesses):
                    raise ValueError("stress record does not match its source world event")
        if relationship_snapshot is not None:
            if any(item.tick > self.current_tick for item in relationship_snapshot.changes):
                raise ValueError("relationship changes cannot occur after the checkpoint tick")
            npc_ids = {npc.entity_id for npc in NPCCollectionSnapshot.from_json(self.npcs_json).restore().values()}
            if any(item.observer_id not in npc_ids or item.target_id not in npc_ids for item in relationship_snapshot.changes):
                raise ValueError("relationship changes reference NPCs missing from checkpoint")
            journal = envelope.restore_event_ledger()
            for item in relationship_snapshot.changes:
                try:
                    source_event = journal.get(item.source_event_id)
                except KeyError:
                    raise ValueError(f"relationship change references missing world event: {item.source_event_id}") from None
                if (source_event.tick > item.tick
                        or item.observer_id not in source_event.participants + source_event.witnesses
                        or item.target_id not in source_event.participants + source_event.witnesses):
                    raise ValueError("relationship change does not match its source world event")
        if conditioning_snapshot is not None:
            conditioning_ledger = conditioning_snapshot.restore()
            if conditioning_ledger.current_tick > self.current_tick:
                raise ValueError("NPC conditioning cannot be sampled after the checkpoint tick")
            known_npcs = {npc.entity_id for npc in NPCCollectionSnapshot.from_json(self.npcs_json).restore().values()}
            if any(owner not in known_npcs for owner, _cue in conditioning_ledger._associations):
                raise ValueError("conditioning associations reference unknown NPCs")
            journal = {event.event_id: event for event in envelope.restore_event_ledger().snapshot()}
            for record in conditioning_ledger.records():
                source = journal.get(record.source_event_id)
                if source is None:
                    raise ValueError(f"conditioning record references missing world event: {record.source_event_id}")
                if (record.owner_id not in source.participants + source.witnesses
                        or source.tick > record.tick or record.tick > self.current_tick):
                    raise ValueError("conditioning record does not match its source world event")
        if life_history_snapshot is not None:
            history = life_history_snapshot.restore()
            npc_ids = {npc.entity_id for npc in NPCCollectionSnapshot.from_json(self.npcs_json).restore().values()}
            journal = {event.event_id: event for event in envelope.restore_event_ledger().snapshot()}
            for memory in history.memories():
                source = journal.get(memory.event_id)
                if (memory.owner_id not in npc_ids or any(x not in npc_ids for x in memory.involved_npc_ids)
                        or source is None or source.tick > memory.tick or memory.tick > self.current_tick
                        or memory.owner_id not in source.participants + source.witnesses
                        or any(x not in source.participants + source.witnesses for x in memory.involved_npc_ids)):
                    raise ValueError("autobiographical memory does not match saved NPCs and source event")
            for action in history.actions():
                source = journal.get(action.event_id)
                if (action.owner_id not in npc_ids or action.target_id not in npc_ids
                        or action.tick > self.current_tick or source is None
                        or source.tick > action.tick
                        or action.owner_id not in source.participants + source.witnesses
                        or action.target_id not in source.participants + source.witnesses):
                    raise ValueError("personal history action does not match saved NPCs and source event")
        if goal_lifecycle_snapshot is not None:
            if goals_snapshot is None:
                raise ValueError('goal lifecycle history requires the corresponding GoalBook')
            known_goals = {record[0]: record[1] for record in goals_snapshot.records}
            if any(record[1] not in known_goals or known_goals[record[1]] != record[2] or record[5] > self.current_tick for record in goal_lifecycle_snapshot.records):
                raise ValueError('goal lifecycle history references an unknown goal, owner, or future tick')
            latest_status = {record[1]: record[4] for record in goal_lifecycle_snapshot.records}
            goal_records = {record[0]: record for record in goals_snapshot.records}
            if any(record[5] < goal_records[record[1]][4] for record in goal_lifecycle_snapshot.records):
                raise ValueError('goal lifecycle event cannot precede goal creation')
            if any(goal_records[goal_id][11] != status for goal_id, status in latest_status.items()):
                raise ValueError('goal lifecycle status does not match the checkpoint GoalBook')
            journal_ids = {event.event_id for event in envelope.restore_event_ledger().snapshot()}
            if any(evidence_id not in journal_ids for record in goal_lifecycle_snapshot.records for evidence_id in record[7]) and life_history_snapshot is None:
                raise ValueError('autobiographical lifecycle evidence requires checkpointed life history')
            if life_history_snapshot is not None:
                known_memory_ids = {record[0] for record in life_history_snapshot.memories}
                known_memory_ids.update(event.event_id for event in envelope.restore_event_ledger().snapshot())
                if experience_transfer_snapshot is not None:
                    known_memory_ids.update(item.transfer_id for item in experience_transfer_snapshot.records)
                if any(evidence_id not in known_memory_ids for record in goal_lifecycle_snapshot.records for evidence_id in record[7]):
                    raise ValueError('goal lifecycle evidence references an unknown autobiographical memory')
        if goal_review_applications_snapshot is not None:
            if goals_snapshot is None or goal_review_decisions is None:
                raise ValueError('goal review applications require the matching decisions and GoalBook')
            decisions_by_id = {record[0]: record for record in goal_review_decisions.records}
            goals_by_id = {record[0]: record for record in goals_snapshot.records}
            for record in goal_review_applications_snapshot.records:
                decision = decisions_by_id.get(record[0])
                goal = goals_by_id.get(record[1])
                if decision is None or not decision[6] or goal is None or goal[1] != record[2]:
                    raise ValueError('goal review application references an unknown or rejected decision')
                if decision[3] != record[1] or decision[2] != record[2] or decision[7] != record[3] or record[3] > self.current_tick:
                    raise ValueError('goal review application does not match its decision')
                if (goal[2], goal[3], goal[8], goal[11]) != (record[5], record[6], record[7], record[8].value):
                    raise ValueError('goal review application result does not match the checkpoint GoalBook')
        if goal_commitments_snapshot is not None:
            if goals_snapshot is None:
                raise ValueError("goal commitments require checkpointed GoalBook state")
            known_goals = {record[0]: record[1] for record in goals_snapshot.records}
            for item in goal_commitments_snapshot.restore().entries():
                if item.tick > self.current_tick:
                    raise ValueError("goal commitments cannot occur after the checkpoint tick")
                if known_goals.get(item.selected_goal_id) != item.owner_id:
                    raise ValueError("goal commitment references an unknown selected goal or owner")
                if any(known_goals.get(goal_id) != item.owner_id for goal_id in item.deferred_goal_ids):
                    raise ValueError("goal commitment references an unknown deferred goal or owner")
        return components

    def to_json(self):
        envelope, npcs, trust, beliefs, memory, conversations, ticks, consequence, campaign, misconduct, routines, routine_executions, routine_institutions, institutional_politics, goals, goal_event_replay, goal_review_decisions, identity_decisions, testimony_inquiries, testimony, travel, presence, presence_encounters, familiarity, relationships, emotions, stress, conditioning, learning_decisions, life_history, memory_reflections, emotional_scars, emotional_scar_decisions, scar_identity_proposals, identity_goal_reviews, action_execution_snapshot, action_world_facts, action_resources, action_replanning_snapshot, action_evaluation_snapshot, experience_transfer_snapshot, goal_lifecycle_snapshot, goal_review_applications_snapshot, goal_commitments_snapshot = self._components()
        payload = {
            "schema_version": self.SCHEMA_VERSION, "current_tick": self.current_tick,
            "events": json.loads(envelope.to_json()), "npcs": json.loads(npcs.to_json()),
            "trust": json.loads(trust.to_json()), "beliefs": json.loads(beliefs.to_json()),
            "memory_replay": json.loads(memory.to_json()),
            "conversations": json.loads(conversations.to_json()),
            "tick_replay": json.loads(ticks.to_json()),
            "ticks_per_hour": self.ticks_per_hour,
            "metadata": [list(pair) for pair in self.metadata],
        }
        if consequence is not None:
            payload["consequence_replay"] = json.loads(consequence.to_json())
        if self.campaign_json is not None:
            payload["campaign"] = json.loads(self.campaign_json)
        if misconduct is not None:
            payload["misconduct"] = json.loads(misconduct.to_json())
        if routines is not None:
            payload["routines"] = json.loads(routines.to_json())
        if routine_executions is not None:
            payload["routine_executions"] = json.loads(routine_executions.to_json())
        if routine_institutions is not None:
            payload["routine_institutions"] = json.loads(routine_institutions.to_json())
        if institutional_politics is not None:
            payload["institutional_politics"] = institutional_politics.snapshot()
        if goals is not None:
            payload["goals"] = json.loads(goals.to_json())
        if goal_event_replay is not None:
            payload["goal_event_replay"] = json.loads(goal_event_replay.to_json())
        if goal_review_decisions is not None:
            payload["goal_review_decisions"] = json.loads(goal_review_decisions.to_json())
        if identity_decisions is not None:
            payload["identity_decisions"] = json.loads(identity_decisions.to_json())
        if identity_goal_reviews is not None:
            payload["identity_goal_reviews"] = json.loads(identity_goal_reviews.to_json())
        if testimony_inquiries is not None:
            payload["testimony_inquiries"] = json.loads(testimony_inquiries.to_json())
        if testimony is not None:
            payload["testimony"] = json.loads(testimony.to_json())
        if travel is not None:
            payload["travel"] = json.loads(travel.to_json())
        if presence is not None:
            payload["presence"] = json.loads(presence.to_json())
        if presence_encounters is not None:
            payload["presence_encounters"] = json.loads(presence_encounters.to_json())
        if familiarity is not None:
            payload["familiarity"] = json.loads(familiarity.to_json())
        if relationships is not None:
            payload["relationships"] = json.loads(relationships.to_json())
        if emotions is not None:
            payload["emotions"] = json.loads(emotions.to_json())
        if stress is not None:
            payload["stress"] = json.loads(stress.to_json())
        if conditioning is not None:
            payload["conditioning"] = json.loads(conditioning.to_json())
        if learning_decisions is not None:
            payload["psychological_learning_decisions"] = json.loads(learning_decisions.to_json())
        if self.psychological_learning_decisions_json is not None:
            payload["psychological_learning_decisions"] = json.loads(self.psychological_learning_decisions_json)
        if life_history is not None:
            payload["life_history"] = json.loads(life_history.to_json())
        if memory_reflections is not None:
            payload["memory_reflections"] = json.loads(memory_reflections.to_json())
        if self.emotional_scars_json is not None:
            payload["emotional_scars"] = json.loads(self.emotional_scars_json)
        if self.emotional_scar_decisions_json is not None:
            payload["emotional_scar_decisions"] = json.loads(self.emotional_scar_decisions_json)
        if scar_identity_proposals is not None:
            payload["scar_identity_proposals"] = json.loads(scar_identity_proposals.to_json())
        if self.action_executions_json is not None:
            payload["action_executions"] = json.loads(self.action_executions_json)
        if self.action_world_facts_json is not None:
            payload["action_world_facts"] = json.loads(self.action_world_facts_json)
            payload["action_resources"] = json.loads(self.action_resources_json)
        if action_replanning_snapshot is not None:
            payload["action_replanning"] = json.loads(action_replanning_snapshot.to_json())
        if action_evaluation_snapshot is not None:
            payload["action_evaluations"] = json.loads(action_evaluation_snapshot.to_json())
        if experience_transfer_snapshot is not None:
            payload["experience_transfers"] = json.loads(experience_transfer_snapshot.to_json())
        if goal_lifecycle_snapshot is not None:
            payload["goal_lifecycle"] = json.loads(goal_lifecycle_snapshot.to_json())
        if goal_review_applications_snapshot is not None:
            payload["goal_review_applications"] = json.loads(goal_review_applications_snapshot.to_json())
        if goal_commitments_snapshot is not None:
            payload["goal_commitments"] = json.loads(goal_commitments_snapshot.to_json())
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_json(cls, payload):
        try:
            raw = json.loads(payload)
            if not isinstance(raw, dict) or raw.get("schema_version") != cls.SCHEMA_VERSION:
                raise ValueError("unsupported world checkpoint schema version")
            nested = lambda key: json.dumps(raw[key], sort_keys=True, separators=(",", ":"), allow_nan=False)
            metadata = tuple(sorted(((item[0], item[1]) for item in raw.get("metadata", ())), key=lambda pair: pair[0]))
            return cls(raw["current_tick"], nested("events"), nested("npcs"), nested("trust"),
                       nested("beliefs"), nested("memory_replay"), nested("conversations"),
                       nested("tick_replay"), raw.get("ticks_per_hour", 1.0), metadata,
                       json.dumps(raw["consequence_replay"], sort_keys=True, separators=(",", ":"), allow_nan=False) if raw.get("consequence_replay") is not None else None,
                       json.dumps(raw["campaign"], sort_keys=True, separators=(",", ":"), allow_nan=False) if raw.get("campaign") is not None else None,
                       json.dumps(raw["misconduct"], sort_keys=True, separators=(",", ":"), allow_nan=False) if raw.get("misconduct") is not None else None,
                       json.dumps(raw["routines"], sort_keys=True, separators=(",", ":"), allow_nan=False) if raw.get("routines") is not None else None,
                       json.dumps(raw["routine_executions"], sort_keys=True, separators=(",", ":"), allow_nan=False) if raw.get("routine_executions") is not None else None,
                       json.dumps(raw["routine_institutions"], sort_keys=True, separators=(",", ":"), allow_nan=False) if raw.get("routine_institutions") is not None else None,
                       json.dumps(raw["institutional_politics"], sort_keys=True, separators=(",", ":"), allow_nan=False) if raw.get("institutional_politics") is not None else None,
                       json.dumps(raw["goals"], sort_keys=True, separators=(",", ":"), allow_nan=False) if raw.get("goals") is not None else None,
                       json.dumps(raw["goal_event_replay"], sort_keys=True, separators=(",", ":"), allow_nan=False) if raw.get("goal_event_replay") is not None else None,
                       json.dumps(raw["goal_review_decisions"], sort_keys=True, separators=(",", ":"), allow_nan=False) if raw.get("goal_review_decisions") is not None else None,
                       json.dumps(raw["identity_decisions"], sort_keys=True, separators=(",", ":"), allow_nan=False) if raw.get("identity_decisions") is not None else None,
                       json.dumps(raw["testimony_inquiries"], sort_keys=True, separators=(",", ":"), allow_nan=False) if raw.get("testimony_inquiries") is not None else None,
                       json.dumps(raw["testimony"], sort_keys=True, separators=(",", ":"), allow_nan=False) if raw.get("testimony") is not None else None,
                       json.dumps(raw["travel"], sort_keys=True, separators=(",", ":"), allow_nan=False) if raw.get("travel") is not None else None,
                       json.dumps(raw["presence"], sort_keys=True, separators=(",", ":"), allow_nan=False) if raw.get("presence") is not None else None,
                       json.dumps(raw["presence_encounters"], sort_keys=True, separators=(",", ":"), allow_nan=False) if raw.get("presence_encounters") is not None else None,
                       json.dumps(raw["familiarity"], sort_keys=True, separators=(",", ":"), allow_nan=False) if raw.get("familiarity") is not None else None,
                       json.dumps(raw["relationships"], sort_keys=True, separators=(",", ":"), allow_nan=False) if raw.get("relationships") is not None else None,
                       json.dumps(raw["emotions"], sort_keys=True, separators=(",", ":"), allow_nan=False) if raw.get("emotions") is not None else None,
                       json.dumps(raw["stress"], sort_keys=True, separators=(",", ":"), allow_nan=False) if raw.get("stress") is not None else None,
                       json.dumps(raw["conditioning"], sort_keys=True, separators=(",", ":"), allow_nan=False) if raw.get("conditioning") is not None else None,
                       json.dumps(raw["psychological_learning_decisions"], sort_keys=True, separators=(",", ":"), allow_nan=False) if raw.get("psychological_learning_decisions") is not None else None,
                       json.dumps(raw["life_history"], sort_keys=True, separators=(",", ":"), allow_nan=False) if raw.get("life_history") is not None else None,
                       json.dumps(raw["memory_reflections"], sort_keys=True, separators=(",", ":"), allow_nan=False) if raw.get("memory_reflections") is not None else None,
                       json.dumps(raw["emotional_scars"], sort_keys=True, separators=(",", ":"), allow_nan=False) if raw.get("emotional_scars") is not None else None,
                       json.dumps(raw["emotional_scar_decisions"], sort_keys=True, separators=(",", ":"), allow_nan=False) if raw.get("emotional_scar_decisions") is not None else None,
                       json.dumps(raw["scar_identity_proposals"], sort_keys=True, separators=(",", ":"), allow_nan=False) if raw.get("scar_identity_proposals") is not None else None,
                       json.dumps(raw["identity_goal_reviews"], sort_keys=True, separators=(",", ":"), allow_nan=False) if raw.get("identity_goal_reviews") is not None else None,
                       json.dumps(raw["action_executions"], sort_keys=True, separators=(",", ":"), allow_nan=False) if raw.get("action_executions") is not None else None,
                       json.dumps(raw["action_world_facts"], sort_keys=True, separators=(",", ":"), allow_nan=False) if raw.get("action_world_facts") is not None else None,
                       json.dumps(raw["action_resources"], sort_keys=True, separators=(",", ":"), allow_nan=False) if raw.get("action_resources") is not None else None,
                       json.dumps(raw["action_replanning"], sort_keys=True, separators=(",", ":"), allow_nan=False) if raw.get("action_replanning") is not None else None,
                       json.dumps(raw["action_evaluations"], sort_keys=True, separators=(",", ":"), allow_nan=False) if raw.get("action_evaluations") is not None else None,
                       json.dumps(raw["experience_transfers"], sort_keys=True, separators=(",", ":"), allow_nan=False) if raw.get("experience_transfers") is not None else None,
                       json.dumps(raw["goal_lifecycle"], sort_keys=True, separators=(",", ":"), allow_nan=False) if raw.get("goal_lifecycle") is not None else None,
                       json.dumps(raw["goal_review_applications"], sort_keys=True, separators=(",", ":"), allow_nan=False) if raw.get("goal_review_applications") is not None else None,
                       json.dumps(raw["goal_commitments"], sort_keys=True, separators=(",", ":"), allow_nan=False) if raw.get("goal_commitments") is not None else None)
        except ValueError:
            raise
        except (TypeError, KeyError, IndexError, json.JSONDecodeError) as exc:
            raise ValueError("invalid simulation world checkpoint") from exc

    def restore(self):
        envelope, npc_snapshot, trust_snapshot, belief_snapshot, memory_snapshot, conversation_snapshot, tick_snapshot, consequence_snapshot, campaign, misconduct_snapshot, routine_snapshot, execution_snapshot, institution_snapshot, institutional_politics, goals_snapshot, goal_event_replay, goal_review_decisions_snapshot, identity_decisions_snapshot, testimony_inquiries_snapshot, testimony_snapshot, travel_snapshot, presence_snapshot, encounter_snapshot, familiarity_snapshot, relationship_snapshot, emotional_snapshot, stress_snapshot, conditioning_snapshot, learning_decisions_snapshot, life_history_snapshot, memory_reflections_snapshot, emotional_scars_snapshot, emotional_scar_decisions_snapshot, scar_identity_proposal_snapshot, identity_goal_review_snapshot, action_execution_snapshot, action_world_facts, action_resources, action_replanning_snapshot, action_evaluation_snapshot, experience_transfer_snapshot, goal_lifecycle_snapshot, goal_review_applications_snapshot, goal_commitments_snapshot = self._components()
        events = envelope.restore_event_ledger()
        npcs = npc_snapshot.restore()
        trust = trust_snapshot.restore()
        beliefs = belief_snapshot.restore(trust)
        memory = WorldEventMemoryAdapter(events, ticks_per_hour=self.ticks_per_hour)
        memory_snapshot.restore(memory, npcs)
        conversations = SocialConversationAdapter(trust, beliefs)
        conversation_snapshot.restore(conversations)
        coordinator = SimulationTickCoordinator(events, memory, conversations)
        tick_snapshot.restore(coordinator)
        consequence_recorder = SocialConsequenceRecorder(trust, beliefs) if consequence_snapshot is not None else None
        if consequence_snapshot is not None:
            consequence_snapshot.restore(consequence_recorder)
        misconduct = misconduct_snapshot.restore(events) if misconduct_snapshot is not None else None
        if misconduct is not None:
            if any(report.filed_tick > self.current_tick for report in misconduct.snapshot()[0]):
                raise ValueError("misconduct reports cannot be after the checkpoint tick")
            if any(decision.tick > self.current_tick for decision in misconduct.snapshot()[1]):
                raise ValueError("misconduct decisions cannot be after the checkpoint tick")
        routines = routine_snapshot.restore() if routine_snapshot is not None else None
        routine_executions = execution_snapshot.restore() if execution_snapshot is not None else None
        if routine_executions is not None:
            if routines is None:
                raise ValueError("routine execution history requires a routine schedule")
            known_routines = {block.routine_id for block in routines.snapshot()}
            if any(record.routine_id not in known_routines for record in routine_executions.snapshot()):
                raise ValueError("routine execution history references an unknown routine")
        routine_institutions = institution_snapshot.restore() if institution_snapshot is not None else None
        goals = goals_snapshot.restore() if goals_snapshot is not None else None
        goal_review_decisions = goal_review_decisions_snapshot.restore() if goal_review_decisions_snapshot is not None else None
        identity_decisions = identity_decisions_snapshot.restore() if identity_decisions_snapshot is not None else None
        testimony_inquiries = testimony_inquiries_snapshot.restore() if testimony_inquiries_snapshot is not None else None
        testimony = testimony_snapshot if testimony_snapshot is not None else None
        travel = travel_snapshot.restore() if travel_snapshot is not None else None
        presence = presence_snapshot.restore() if presence_snapshot is not None else None
        presence_encounters = encounter_snapshot.restore() if encounter_snapshot is not None else None
        familiarity = familiarity_snapshot.restore() if familiarity_snapshot is not None else None
        relationship_snapshot = SocialRelationshipSnapshot.from_json(self.relationships_json) if self.relationships_json is not None else None
        relationships = relationship_snapshot.restore() if relationship_snapshot is not None else None
        emotions = emotional_snapshot.restore() if emotional_snapshot is not None else None
        stress = stress_snapshot.restore() if stress_snapshot is not None else None
        conditioning = conditioning_snapshot.restore() if conditioning_snapshot is not None else None
        psychological_learning_decisions = learning_decisions_snapshot.restore() if learning_decisions_snapshot is not None else None
        life_history = life_history_snapshot.restore() if life_history_snapshot is not None else None
        memory_reflections = memory_reflections_snapshot.restore(life_history) if memory_reflections_snapshot is not None else None
        emotional_scars = emotional_scars_snapshot.restore() if emotional_scars_snapshot is not None else None
        emotional_scar_decisions = emotional_scar_decisions_snapshot.restore() if emotional_scar_decisions_snapshot is not None else None
        scar_identity_proposals = ScarIdentityProposalLedger.from_snapshot(scar_identity_proposal_snapshot) if scar_identity_proposal_snapshot is not None else None
        identity_goal_reviews = identity_goal_review_snapshot.restore() if identity_goal_review_snapshot is not None else None
        experience_transfers = (NPCExperienceTransferLedger(events, life_history, experience_transfer_snapshot)
                                if experience_transfer_snapshot is not None else None)
        goal_lifecycle = goal_lifecycle_snapshot.restore() if goal_lifecycle_snapshot is not None else None
        return RestoredSimulation(self.current_tick, events, npcs, trust, beliefs,
                                  memory, conversations, coordinator, self.metadata,
                                  consequence_recorder, campaign, misconduct, routines, routine_executions,
                                  routine_institutions, institutional_politics, goals, goal_event_replay,
                                  goal_review_decisions, identity_decisions, testimony_inquiries, testimony, travel, presence, presence_encounters, familiarity, relationships, emotions, stress, conditioning, psychological_learning_decisions, life_history, memory_reflections, emotional_scars, emotional_scar_decisions, scar_identity_proposals, identity_goal_reviews, action_execution_snapshot, set(action_world_facts) if action_world_facts is not None else None, dict(action_resources) if action_resources is not None else None, action_replanning_snapshot, action_evaluation_snapshot, experience_transfers,
                                  goal_lifecycle, goal_review_applications_snapshot.restore() if goal_review_applications_snapshot is not None else None,
                                  goal_commitments_snapshot.restore() if goal_commitments_snapshot is not None else None)
