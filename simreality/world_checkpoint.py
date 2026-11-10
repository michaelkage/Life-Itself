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
                testimony_inquiries=None, testimony=None, travel=None, presence=None, presence_encounters=None, familiarity=None, relationships=None):
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
        return components

    def to_json(self):
        envelope, npcs, trust, beliefs, memory, conversations, ticks, consequence, campaign, misconduct, routines, routine_executions, routine_institutions, institutional_politics, goals, goal_event_replay, goal_review_decisions, identity_decisions, testimony_inquiries, testimony, travel, presence, presence_encounters, familiarity, relationships = self._components()
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
                       json.dumps(raw["relationships"], sort_keys=True, separators=(",", ":"), allow_nan=False) if raw.get("relationships") is not None else None)
        except ValueError:
            raise
        except (TypeError, KeyError, IndexError, json.JSONDecodeError) as exc:
            raise ValueError("invalid simulation world checkpoint") from exc

    def restore(self):
        envelope, npc_snapshot, trust_snapshot, belief_snapshot, memory_snapshot, conversation_snapshot, tick_snapshot, consequence_snapshot, campaign, misconduct_snapshot, routine_snapshot, execution_snapshot, institution_snapshot, institutional_politics, goals_snapshot, goal_event_replay, goal_review_decisions_snapshot, identity_decisions_snapshot, testimony_inquiries_snapshot, testimony_snapshot, travel_snapshot, presence_snapshot, encounter_snapshot, familiarity_snapshot = self._components()
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
        return RestoredSimulation(self.current_tick, events, npcs, trust, beliefs,
                                  memory, conversations, coordinator, self.metadata,
                                  consequence_recorder, campaign, misconduct, routines, routine_executions,
                                  routine_institutions, institutional_politics, goals, goal_event_replay,
                                  goal_review_decisions, identity_decisions, testimony_inquiries, testimony, travel, presence, presence_encounters, familiarity, relationships)
