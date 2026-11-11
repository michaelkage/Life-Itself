import json
import unittest

from simreality import (
    ActionTag, NPC, ConversationIntent, SocialBeliefSystem,
    ObservedClaim, SocialConsequenceRecorder, SocialConversationAdapter, SocialTrustLedger, SimulationTickCoordinator,
    SimulationWorldCheckpoint, WitnessedSocialEvent, WorldEventLedger, WorldEventMemoryAdapter,
    LifeItselfCampaign, LifeState, MisconductReport, MisconductReportingSystem,
    MisconductType, ReviewDecision, ReviewOutcome, RoutineBlock, RoutineBook,
    RoutineDisruption, DisruptionKind, RoutineExecutionLedger,
    RoutineInstitutionLedger, InstitutionalPoliticalLedger,
    GoalBook, NPCGoal, GoalEventAdapter, GoalProgressPolicy,
    GoalReviewAction, GoalReviewEvaluator, GoalReviewPolicy,
    GoalReviewDecision, GoalReviewDecisionLedger,
    GoalReviewApplicationAdapter, GoalReviewApplicationLedger,
    NPCIdentityProfile, IdentityChangeProposal, IdentityDecisionLedger,
    TestimonyInquiry, TestimonyInquiryLedger, TestimonyResponse,
    TestimonyLedger, TestimonyRecord, TestimonyDetail,
    InquiryInvestigationPipeline, RouteEdge, PersonalRoutePlanner,
    TravelTickAdapter, PresenceLedger, AutobiographicalMemory, NPCLifeHistory,
    MemoryReinterpretation, MemoryReflectionLedger,
    EmotionalScar, NPCEmotionalScarLedger,
    EmotionalScarProposal, EmotionalScarDecision, EmotionalScarDecisionLedger,
    IdentityGoalAction, IdentityGoalAlignmentAdapter, IdentityGoalAlignmentPolicy,
    IdentityGoalReviewDecision, IdentityGoalReviewDecisionLedger,
    ActionExecutionLedger, ActionExecutionPolicy,
    ActionPlanEvaluationLedger,
)
from simreality.npc_goal_emergence import GoalLifecycleLedger
from simreality.goals import GoalStatus
from simreality.presence_encounters import PresenceEncounter, PresenceEncounterLedger, PresenceSocialAdapter
from simreality.goals import GoalStatus
from simreality.social_familiarity import PresenceFamiliarityAdapter, SocialFamiliarityLedger
from simreality.emotional_events import EmotionalEventRule, NPCEmotionalEventLedger
from simreality.psychological_conditioning import ConditioningProfile, NPCConditioningLedger
from simreality.psychological_interpretation import LearningProposal
from simreality.psychological_learning_decisions import PsychologicalLearningDecisionLedger
from simreality.planning import DeterministicPlanner, PlanningAction
from simreality.npc_experience_transfer import NPCExperienceTransferLedger


class SimulationWorldCheckpointTests(unittest.TestCase):
    def make_simulation(self):
        events = WorldEventLedger((
            WorldEventLedger.make_event(
                "event-1", 3, "incident",
                participants=("speaker", "subject"), witnesses=("speaker", "listener"),
                attributes={
                    "action_tag": ActionTag.CRIME_THEFT.value,
                    "target_entity_id": "subject",
                    "memory_impact": 0.9,
                },
            ),
        ))
        npcs = {"speaker": NPC("speaker"), "listener": NPC("listener")}
        trust = SocialTrustLedger({("listener", "speaker"): 0.9})
        beliefs = SocialBeliefSystem(trust)
        memory = WorldEventMemoryAdapter(events, ticks_per_hour=2.0)
        conversations = SocialConversationAdapter(trust, beliefs)
        coordinator = SimulationTickCoordinator(events, memory, conversations)
        consequences = SocialConsequenceRecorder(trust, beliefs)
        consequences.record(WitnessedSocialEvent(
            "event-social-1", "listener", "speaker", 3, -1, 0.4,
            (ObservedClaim("claim-1", 1, 0.7),),
        ))
        intent = ConversationIntent("chat-3", "listener", "speaker")
        coordinator.step(3, npcs, event_ids=("event-1",), conversations=(intent,))
        return coordinator, npcs, consequences


    def test_checkpoint_round_trip_persists_goal_review_applications(self):
        coordinator, npcs, _ = self.make_simulation()
        goals = GoalBook()
        goals.add(NPCGoal("career", "speaker", "career", 5.0, confidence=0.7))
        policy = GoalReviewPolicy(
            "career-review", "incident", "career",
            GoalReviewAction.REPRIORITIZE, priority_delta=-1.0,
            confidence_delta=-0.1,
        )
        proposal = GoalReviewEvaluator(goals, (policy,)).assess(
            (coordinator.events.get("event-1"),)
        )[0]
        decisions = GoalReviewDecisionLedger((
            GoalReviewDecision.from_proposal(
                "decision-career", proposal, accepted=True, decision_tick=4,
                rationale="The setback changed my priorities",
            ),
        ))
        applications = GoalReviewApplicationLedger()
        GoalReviewApplicationAdapter.apply(
            decisions.get("decision-career"), goals, applications,
        )
        checkpoint = SimulationWorldCheckpoint.capture(
            4, coordinator, npcs, goal_book=goals,
            goal_review_decisions=decisions,
            goal_review_applications=applications,
        )
        restored = SimulationWorldCheckpoint.from_json(checkpoint.to_json()).restore()
        self.assertEqual(restored.goal_review_applications.entries(), applications.entries())
        self.assertEqual(restored.goals.goals["career"].priority, 4.0)

    def test_checkpoint_round_trip_persists_physical_presence(self):
        coordinator, npcs, _ = self.make_simulation()
        presence = PresenceLedger()
        presence.place("speaker", "courthouse", 2)
        presence.place("listener", "street", 3)
        checkpoint = SimulationWorldCheckpoint.capture(
            4, coordinator, npcs, presence=presence,
        )
        restored = SimulationWorldCheckpoint.from_json(checkpoint.to_json()).restore()
        self.assertIsNotNone(restored.presence)
        self.assertEqual(restored.presence.occupants("courthouse"), ("speaker",))
        self.assertEqual(restored.presence.occupants("street"), ("listener",))

    def test_checkpoint_rejects_presence_for_unknown_npc(self):
        coordinator, npcs, _ = self.make_simulation()
        presence = PresenceLedger()
        presence.place("missing-npc", "street", 1)
        with self.assertRaisesRegex(ValueError, "missing from checkpoint"):
            SimulationWorldCheckpoint.capture(
                4, coordinator, npcs, presence=presence,
            )

    def test_checkpoint_round_trip_persists_psychological_learning_decisions(self):
        coordinator, npcs, _ = self.make_simulation()
        conditioning = NPCConditioningLedger()
        profile = ConditioningProfile("speaker", learning_rate=0.5)
        proposal = LearningProposal("speaker", "event-1", 3, "rule-trust",
                                    "authority", 1.0, 1.0, "reinforce", "trusted authority")
        decisions = PsychologicalLearningDecisionLedger()
        decisions.decide("learning-1", proposal, accepted=True, decision_tick=4,
                         conditioning=conditioning, profile=profile,
                         rationale="This authority helped me")
        checkpoint = SimulationWorldCheckpoint.capture(
            4, coordinator, npcs, conditioning=conditioning,
            psychological_learning_decisions=decisions,
        )
        restored = SimulationWorldCheckpoint.from_json(checkpoint.to_json()).restore()
        self.assertIsNotNone(restored.psychological_learning_decisions)
        self.assertEqual(restored.psychological_learning_decisions.entries(), decisions.entries())
        self.assertEqual(restored.conditioning.association_for("speaker", "authority"), 0.5)
        replay = restored.psychological_learning_decisions.decide(
            "learning-1", proposal, accepted=True, decision_tick=4,
            conditioning=restored.conditioning, profile=profile,
            rationale="This authority helped me",
        )
        self.assertEqual(replay.decision_id, "learning-1")
        self.assertEqual(len(restored.conditioning.records()), 1)

    def test_checkpoint_round_trip_persists_autobiographical_history_and_repair_choices(self):
        coordinator, npcs, _ = self.make_simulation()
        history = NPCLifeHistory()
        history.record(AutobiographicalMemory(
            "memory-1", "speaker", "event-1", 3, ("listener",),
            "The witness refused to help me", 0.8, -0.1,
            turning_point=True, tags=("betrayal",),
        ))
        history.act("forgive-1", "speaker", "listener", "event-1",
                    action="forgive", tick=4, rationale="I choose to let go")
        checkpoint = SimulationWorldCheckpoint.capture(
            4, coordinator, npcs, life_history=history,
        )
        restored = SimulationWorldCheckpoint.from_json(checkpoint.to_json()).restore()
        self.assertIsNotNone(restored.life_history)
        self.assertEqual(restored.life_history.snapshot().to_json(), history.snapshot().to_json())
        state = restored.life_history.relationship_history("speaker", "listener", "event-1")
        self.assertTrue(state["forgiven"])
        self.assertFalse(state["reconciled"])
        self.assertEqual(restored.life_history.memories("speaker")[0].interpretation,
                         "The witness refused to help me")

    def test_checkpoint_rejects_autobiographical_history_with_unknown_source_event(self):
        coordinator, npcs, _ = self.make_simulation()
        history = NPCLifeHistory()
        history.record(AutobiographicalMemory(
            "memory-1", "speaker", "missing-event", 3, ("listener",),
            "An event I remember", 0.5, 0.0,
        ))
        with self.assertRaisesRegex(ValueError, "source world event"):
            SimulationWorldCheckpoint.capture(4, coordinator, npcs, life_history=history)

    def test_round_trip_restores_dependencies_and_idempotent_tick_replay(self):
        coordinator, npcs, consequences = self.make_simulation()
        payload = SimulationWorldCheckpoint.capture(
            4, coordinator, npcs, metadata={"world": "alpha", "seed": 42},
            consequence_recorder=consequences,
        ).to_json()

        restored_checkpoint = SimulationWorldCheckpoint.from_json(payload)
        restored = restored_checkpoint.restore()
        self.assertEqual(restored.current_tick, 4)
        self.assertEqual(restored.metadata, (("seed", 42), ("world", "alpha")))
        self.assertEqual(restored.memory_adapter.ticks_per_hour, 2.0)
        self.assertIsNotNone(restored.consequence_recorder)
        before_consequence_trust = restored.trust.snapshot()
        replayed_consequence = restored.consequence_recorder.record(WitnessedSocialEvent(
            "event-social-1", "listener", "speaker", 3, -1, 0.4,
            (ObservedClaim("claim-1", 1, 0.7),),
        ))
        self.assertEqual(replayed_consequence.event_id, "event-social-1")
        self.assertEqual(restored.trust.snapshot(), before_consequence_trust)

        before = list(restored.npcs["speaker"].memories)
        result = restored.coordinator.step(
            3, restored.npcs, event_ids=("event-1",),
            conversations=(ConversationIntent("chat-3", "listener", "speaker"),),
        )
        self.assertEqual(restored.npcs["speaker"].memories, before)
        self.assertEqual(len(restored.npcs["speaker"].memories), 1)
        self.assertEqual(result.tick, 3)
        self.assertEqual(
            SimulationWorldCheckpoint.capture(
                4, restored.coordinator, restored.npcs,
                metadata=dict(restored.metadata),
                consequence_recorder=restored.consequence_recorder,
            ).to_json(),
            payload,
        )


    def test_identity_decisions_round_trip_and_event_replay_remains_idempotent(self):
        coordinator, npcs, _ = self.make_simulation()
        profile = NPCIdentityProfile("speaker", {"trust": 0.2}, {"trust": 1.0})
        proposal = IdentityChangeProposal(
            "event-1", "speaker", "incident-policy", "trust",
            0.2, 0.25, 0.05, 1.0, "participant", 0.05,
        )
        identity = IdentityDecisionLedger((profile,))
        identity.decide(
            "identity-decision-1", proposal, accepted=True,
            decision_tick=4, rationale="The NPC accepts the experience",
        )
        payload = SimulationWorldCheckpoint.capture(
            4, coordinator, npcs, identity_decisions=identity,
        ).to_json()
        restored = SimulationWorldCheckpoint.from_json(payload).restore()
        self.assertEqual(restored.identity_decisions.traits_for("speaker")["trust"], 0.25)
        self.assertEqual(len(restored.identity_decisions.entries()), 1)
        restored.identity_decisions.record(restored.identity_decisions.entries()[0])
        self.assertEqual(restored.identity_decisions.traits_for("speaker")["trust"], 0.25)
        self.assertEqual(
            SimulationWorldCheckpoint.capture(
                4, restored.coordinator, restored.npcs,
                identity_decisions=restored.identity_decisions,
            ).to_json(),
            payload,
        )

    def test_identity_checkpoint_rejects_profiles_outside_npc_roster(self):
        coordinator, npcs, _ = self.make_simulation()
        identity = IdentityDecisionLedger((
            NPCIdentityProfile("unregistered-npc", {"trust": 0.2}),
        ))
        with self.assertRaisesRegex(ValueError, "missing from checkpoint"):
            SimulationWorldCheckpoint.capture(
                4, coordinator, npcs, identity_decisions=identity,
            )

    def test_identity_decision_checkpoint_rejects_missing_source_event(self):
        coordinator, npcs, _ = self.make_simulation()
        profile = NPCIdentityProfile("speaker", {"trust": 0.2})
        proposal = IdentityChangeProposal(
            "missing-event", "speaker", "policy", "trust",
            0.2, 0.25, 0.05, 1.0, "participant", 0.05,
        )
        identity = IdentityDecisionLedger((profile,))
        identity.decide("decision", proposal, accepted=True, decision_tick=4, rationale="test")
        with self.assertRaises(ValueError):
            SimulationWorldCheckpoint.capture(4, coordinator, npcs, identity_decisions=identity)

    def test_testimony_inquiries_round_trip_in_world_checkpoint(self):
        coordinator, npcs, _ = self.make_simulation()
        inquiries = TestimonyInquiryLedger()
        inquiries.append_inquiry(TestimonyInquiry(
            "inquiry-1", "event-1", "speaker", "observed_action", 3,
        ))
        inquiries.append_response(TestimonyResponse(
            "inquiry-1", 4, True, "saw the incident", 0.85,
        ))
        payload = SimulationWorldCheckpoint.capture(
            4, coordinator, npcs, testimony_inquiries=inquiries,
        ).to_json()

        restored = SimulationWorldCheckpoint.from_json(payload).restore()
        self.assertIsNotNone(restored.testimony_inquiries)
        self.assertEqual(restored.testimony_inquiries.inquiries(), inquiries.inquiries())
        self.assertEqual(restored.testimony_inquiries.responses(), inquiries.responses())
        self.assertEqual(
            SimulationWorldCheckpoint.capture(
                4, restored.coordinator, restored.npcs,
                testimony_inquiries=restored.testimony_inquiries,
            ).to_json(),
            payload,
        )

    def test_testimony_inquiries_are_optional_and_future_records_rejected(self):
        coordinator, npcs, _ = self.make_simulation()
        payload = SimulationWorldCheckpoint.capture(4, coordinator, npcs).to_json()
        self.assertNotIn('"testimony_inquiries"', payload)
        self.assertIsNone(SimulationWorldCheckpoint.from_json(payload).restore().testimony_inquiries)

        inquiries = TestimonyInquiryLedger((
            TestimonyInquiry("future", "event-1", "speaker", "observed_action", 5),
        ))
        with self.assertRaises(ValueError):
            SimulationWorldCheckpoint.capture(
                4, coordinator, npcs, testimony_inquiries=inquiries,
            )

    def test_testimony_inquiry_checkpoint_rejects_non_witness(self):
        coordinator, npcs, _ = self.make_simulation()
        inquiries = TestimonyInquiryLedger((
            TestimonyInquiry("not-witness", "event-1", "listener", "observed_action", 3),
        ))
        with self.assertRaises(ValueError):
            SimulationWorldCheckpoint.capture(
                4, coordinator, npcs, testimony_inquiries=inquiries,
            )


    def test_inquiry_testimony_and_beliefs_survive_checkpoint_replay(self):
        coordinator, npcs, _ = self.make_simulation()
        inquiries = TestimonyInquiryLedger((
            TestimonyInquiry("checkpoint-q", "event-1", "speaker", "coat", 3),
        ))
        inquiries.append_response(TestimonyResponse(
            "checkpoint-q", 4, True, "green", 0.9,
        ))
        testimony = TestimonyLedger((
            TestimonyRecord(
                "listener-account", "event-1", "listener", 3, 1.0, 0.0,
                (TestimonyDetail("listener-coat", "coat", "black", 0.8),), (),
            ),
        ))
        pipeline = InquiryInvestigationPipeline()
        pipeline.process(
            inquiries, testimony, coordinator.conversation_adapter.beliefs,
            "checkpoint-q", "speaker-account", 2.0, "listener", 4,
        )

        payload = SimulationWorldCheckpoint.capture(
            4, coordinator, npcs,
            testimony_inquiries=inquiries, testimony=testimony,
        ).to_json()
        restored = SimulationWorldCheckpoint.from_json(payload).restore()
        self.assertEqual(restored.testimony_inquiries.to_json(), inquiries.to_json())
        self.assertEqual(restored.testimony.to_json(), testimony.to_json())

        before_beliefs = restored.beliefs.snapshot()
        replay = pipeline.process(
            restored.testimony_inquiries, restored.testimony, restored.beliefs,
            "checkpoint-q", "speaker-account", 2.0, "listener", 4,
        )
        self.assertEqual(replay.materialized.testimony_id, "speaker-account")
        self.assertEqual(restored.beliefs.snapshot(), before_beliefs)
        self.assertEqual(
            SimulationWorldCheckpoint.capture(
                4, restored.coordinator, restored.npcs,
                testimony_inquiries=restored.testimony_inquiries,
                testimony=restored.testimony,
            ).to_json(),
            payload,
        )

    def test_testimony_ledger_round_trips_and_rejects_non_witness(self):
        coordinator, npcs, _ = self.make_simulation()
        testimony = TestimonyLedger((
            TestimonyRecord(
                "testimony-1", "event-1", "speaker", 3, 1.5, 0.01,
                (TestimonyDetail("detail-1", "observed_action", "saw it", 0.9),),
                (),
            ),
        ))
        payload = SimulationWorldCheckpoint.capture(
            4, coordinator, npcs, testimony=testimony,
        ).to_json()
        restored = SimulationWorldCheckpoint.from_json(payload).restore()
        self.assertEqual(restored.testimony.snapshot(), testimony.snapshot())
        self.assertEqual(
            SimulationWorldCheckpoint.capture(
                4, restored.coordinator, restored.npcs,
                testimony=restored.testimony,
            ).to_json(),
            payload,
        )

        invalid = TestimonyLedger((
            TestimonyRecord(
                "testimony-invalid", "event-1", "listener", 3, 1.5, 0.01, (), (),
            ),
        ))
        with self.assertRaises(ValueError):
            SimulationWorldCheckpoint.capture(4, coordinator, npcs, testimony=invalid)

    def test_consequence_section_is_optional(self):
        coordinator, npcs, _ = self.make_simulation()
        payload = SimulationWorldCheckpoint.capture(4, coordinator, npcs).to_json()
        self.assertNotIn("consequence_replay", payload)
        restored = SimulationWorldCheckpoint.from_json(payload).restore()
        self.assertIsNone(restored.consequence_recorder)

    def test_consequence_recorder_must_share_checkpoint_ledgers(self):
        coordinator, npcs, _ = self.make_simulation()
        unrelated_trust = SocialTrustLedger()
        unrelated_beliefs = SocialBeliefSystem(unrelated_trust)
        unrelated_recorder = SocialConsequenceRecorder(unrelated_trust, unrelated_beliefs)
        with self.assertRaises(ValueError):
            SimulationWorldCheckpoint.capture(
                4, coordinator, npcs, consequence_recorder=unrelated_recorder,
            )

    def test_unknown_schema_rejected(self):
        with self.assertRaises(ValueError):
            SimulationWorldCheckpoint.from_json('{"schema_version":99}')

    def test_invalid_clock_or_metadata_rejected(self):
        coordinator, npcs, _ = self.make_simulation()
        with self.assertRaises(ValueError):
            SimulationWorldCheckpoint.capture(-1, coordinator, npcs)
        with self.assertRaises(ValueError):
            SimulationWorldCheckpoint.capture(
                4, coordinator, npcs, metadata={"not-finite": float("nan")},
            )


    def test_checkpoint_rejects_event_replay_reference_to_missing_event(self):
        coordinator, npcs, _ = self.make_simulation()
        payload = json.loads(SimulationWorldCheckpoint.capture(4, coordinator, npcs).to_json())
        payload["tick_replay"]["entries"][0]["event_ids"] = ["missing-event"]
        checkpoint = SimulationWorldCheckpoint.from_json(json.dumps(payload))
        with self.assertRaises((ValueError, KeyError)):
            checkpoint.restore()

    def test_checkpoint_rejects_clock_that_disagrees_with_event_envelope(self):
        coordinator, npcs, _ = self.make_simulation()
        payload = json.loads(SimulationWorldCheckpoint.capture(4, coordinator, npcs).to_json())
        payload["events"]["current_tick"] = 5
        with self.assertRaises(ValueError):
            SimulationWorldCheckpoint.from_json(json.dumps(payload))

    def test_checkpoint_rejects_memory_replay_for_non_witness(self):
        coordinator, npcs, _ = self.make_simulation()
        payload = json.loads(SimulationWorldCheckpoint.capture(4, coordinator, npcs).to_json())
        payload["memory_replay"]["entries"][0]["witness_id"] = "listener"
        with self.assertRaises(ValueError):
            SimulationWorldCheckpoint.from_json(json.dumps(payload))

    def test_checkpoint_json_is_canonical_after_whitespace_and_key_reordering(self):
        coordinator, npcs, consequences = self.make_simulation()
        checkpoint = SimulationWorldCheckpoint.capture(
            4, coordinator, npcs, metadata={"world": "alpha", "seed": 42},
            consequence_recorder=consequences,
        )
        parsed = json.loads(checkpoint.to_json())
        reformatted = json.dumps(parsed, indent=2, sort_keys=False)
        self.assertEqual(
            SimulationWorldCheckpoint.from_json(reformatted).to_json(),
            checkpoint.to_json(),
        )


    def test_campaign_lifecycle_round_trips_inside_world_checkpoint(self):
        coordinator, npcs, _ = self.make_simulation()
        campaign = LifeItselfCampaign()
        campaign.begin_first_life("first-life")
        campaign.active_world.money["first-life"] = 75.0
        campaign.record_death("illness")
        campaign.continue_as_ghost()
        payload = SimulationWorldCheckpoint.capture(
            4, coordinator, npcs, campaign=campaign,
        ).to_json()

        restored = SimulationWorldCheckpoint.from_json(payload).restore()
        self.assertIsNotNone(restored.campaign)
        self.assertEqual(restored.campaign.active_world.life.state, LifeState.GHOST)
        self.assertEqual(restored.campaign.active_world.life.death_cause, "illness")
        self.assertEqual(restored.campaign.active_world.money["first-life"], 75.0)

        restored.campaign.start_fresh_world("second-life")
        self.assertEqual(restored.campaign.active_world.life.character_id, "second-life")
        self.assertEqual(len(restored.campaign.archived_worlds), 1)
        self.assertEqual(
            restored.campaign.visit_archive(restored.campaign.archived_worlds[0].archive_id)
            .money["first-life"],
            75.0,
        )

    def test_campaign_section_is_optional_and_invalid_campaign_is_rejected(self):
        coordinator, npcs, _ = self.make_simulation()
        payload = SimulationWorldCheckpoint.capture(4, coordinator, npcs).to_json()
        self.assertNotIn('"campaign"', payload)
        altered = json.loads(payload)
        altered["campaign"] = {"schema_version": 99}
        with self.assertRaises(ValueError):
            SimulationWorldCheckpoint.from_json(json.dumps(altered))


    def test_misconduct_history_round_trips_and_validates_world_incidents(self):
        coordinator, npcs, _ = self.make_simulation()
        report = MisconductReport(
            "report-1", 4, "listener", "speaker", "police-east",
            MisconductType.CORRUPTION, ("event-1",),
            "A concern was raised about the incident.", False,
        )
        decision = ReviewDecision(
            "review-1", "report-1", 4, "reviewer-1",
            ReviewOutcome.UNDER_REVIEW, ("dispatch-record-1",),
            "The available records are being reviewed.",
        )
        reporting = MisconductReportingSystem((report,), (decision,))
        payload = SimulationWorldCheckpoint.capture(
            4, coordinator, npcs, misconduct=reporting,
        ).to_json()
        restored = SimulationWorldCheckpoint.from_json(payload).restore()
        self.assertIsNotNone(restored.misconduct)
        self.assertEqual(restored.misconduct.snapshot(), reporting.snapshot())
        self.assertEqual(restored.misconduct.status("report-1").outcome, ReviewOutcome.UNDER_REVIEW)
        self.assertEqual(
            SimulationWorldCheckpoint.capture(
                4, restored.coordinator, restored.npcs, misconduct=restored.misconduct,
            ).to_json(),
            payload,
        )

    def test_misconduct_section_is_optional_and_missing_incident_is_rejected(self):
        coordinator, npcs, _ = self.make_simulation()
        payload = SimulationWorldCheckpoint.capture(4, coordinator, npcs).to_json()
        self.assertNotIn('"misconduct"', payload)
        self.assertIsNone(SimulationWorldCheckpoint.from_json(payload).restore().misconduct)

        report = MisconductReport(
            "report-2", 4, "listener", "speaker", "police-east",
            MisconductType.NEGLECT_OF_DUTY, ("missing-event",),
            "An incident reference that is not in the world journal.", False,
        )
        reporting = MisconductReportingSystem((report,))
        with self.assertRaisesRegex(ValueError, "missing world events"):
            SimulationWorldCheckpoint.capture(4, coordinator, npcs, misconduct=reporting)

    def test_checkpoint_rejects_misconduct_decisions_from_the_future(self):
        coordinator, npcs, _ = self.make_simulation()
        report = MisconductReport(
            "report-future", 4, "listener", "speaker", "police-east",
            MisconductType.CORRUPTION, ("event-1",), "Report description.", False,
        )
        decision = ReviewDecision(
            "decision-future", "report-future", 5, "reviewer-1",
            ReviewOutcome.UNDER_REVIEW, (), "Review has not occurred yet.",
        )
        reporting = MisconductReportingSystem((report,), (decision,))
        with self.assertRaisesRegex(ValueError, "after the checkpoint tick"):
            SimulationWorldCheckpoint.capture(4, coordinator, npcs, misconduct=reporting)


    def test_routine_schedules_round_trip_in_world_checkpoint(self):
        coordinator, npcs, _ = self.make_simulation()
        routines = RoutineBook((
            RoutineBlock(
                "shift-1", "speaker", "work", "shop-1", 480, 960,
                priority=0.9, flexibility_minutes=15,
                fallback_activity="call manager", fallback_location_id="home-1",
            ),
        ))
        payload = SimulationWorldCheckpoint.capture(
            4, coordinator, npcs, routines=routines,
        ).to_json()
        restored = SimulationWorldCheckpoint.from_json(payload).restore()
        self.assertEqual(restored.routines.snapshot(), routines.snapshot())
        self.assertEqual(restored.routines.for_period("speaker", 500)[0].activity, "work")
        self.assertEqual(
            SimulationWorldCheckpoint.capture(
                4, restored.coordinator, restored.npcs, routines=restored.routines,
            ).to_json(),
            payload,
        )

    def test_routine_checkpoint_section_is_optional(self):
        coordinator, npcs, _ = self.make_simulation()
        payload = SimulationWorldCheckpoint.capture(4, coordinator, npcs).to_json()
        self.assertNotIn('"routines"', payload)
        self.assertIsNone(SimulationWorldCheckpoint.from_json(payload).restore().routines)


    def test_routine_execution_history_round_trips_and_replays_idempotently(self):
        coordinator, npcs, _ = self.make_simulation()
        block = RoutineBlock("shift-exec", "speaker", "work", "shop-1", 480, 960,
                             flexibility_minutes=10, fallback_activity="call manager",
                             fallback_location_id="home-1")
        routines = RoutineBook((block,))
        executions = RoutineExecutionLedger()
        disruption = RoutineDisruption("traffic-a", "speaker", DisruptionKind.TRAFFIC,
                                       1.0, 480, 600, delay_minutes=25)
        original = executions.execute("attendance-1", routines, block, 500,
                                      (disruption,), outcome_sample=0.1)
        payload = SimulationWorldCheckpoint.capture(
            4, coordinator, npcs, routines=routines, routine_executions=executions,
        ).to_json()
        restored = SimulationWorldCheckpoint.from_json(payload).restore()
        self.assertEqual(restored.routine_executions.get("attendance-1"), original)
        replay = restored.routine_executions.execute(
            "attendance-1", restored.routines, block, 500, (disruption,), outcome_sample=0.1,
        )
        self.assertEqual(replay, original)
        self.assertEqual(
            SimulationWorldCheckpoint.capture(
                4, restored.coordinator, restored.npcs,
                routines=restored.routines, routine_executions=restored.routine_executions,
            ).to_json(),
            payload,
        )

    def test_routine_execution_history_requires_matching_schedule(self):
        coordinator, npcs, _ = self.make_simulation()
        block = RoutineBlock("shift-exec", "speaker", "work", "shop-1", 480, 960)
        routines = RoutineBook((block,))
        executions = RoutineExecutionLedger()
        executions.execute("attendance-1", routines, block, 500)
        with self.assertRaisesRegex(ValueError, "requires the corresponding RoutineBook"):
            SimulationWorldCheckpoint.capture(4, coordinator, npcs, routine_executions=executions)


    def test_institutional_records_round_trip_inside_world_checkpoint(self):
        coordinator, npcs, _ = self.make_simulation()
        institutions = RoutineInstitutionLedger()
        event = WorldEventLedger.make_event(
            "late-record-1", 4, "workplace_late_arrival",
            participants=("speaker",),
            attributes={"location_id": "shop-1", "delay_minutes": 12},
        )
        institutions.apply((event,))
        coordinator.events.append(event)
        payload = SimulationWorldCheckpoint.capture(
            4, coordinator, npcs, routine_institutions=institutions,
        ).to_json()
        restored = SimulationWorldCheckpoint.from_json(payload).restore()
        self.assertEqual(restored.routine_institutions.snapshot(), institutions.snapshot())
        self.assertEqual(restored.routine_institutions.apply((event,)), ())
        self.assertEqual(
            SimulationWorldCheckpoint.capture(
                4, restored.coordinator, restored.npcs,
                routine_institutions=restored.routine_institutions,
            ).to_json(),
            payload,
        )

    def test_institutional_checkpoint_section_is_optional(self):
        coordinator, npcs, _ = self.make_simulation()
        payload = SimulationWorldCheckpoint.capture(4, coordinator, npcs).to_json()
        self.assertNotIn('"routine_institutions"', payload)
        self.assertIsNone(
            SimulationWorldCheckpoint.from_json(payload).restore().routine_institutions
        )


    def test_institutional_political_history_round_trips_in_world_checkpoint(self):
        coordinator, npcs, _ = self.make_simulation()
        politics = InstitutionalPoliticalLedger(
            "city_hall",
            initial_influence=(("planning", 0.4),),
            leadership_priorities=(("housing", 0.3),),
        )
        from simreality import InstitutionalPoliticalEvent
        politics.append(InstitutionalPoliticalEvent(
            "coalition-formed", "city_hall", 2, "planning",
            influence_delta=0.15, other_department_id="transport",
            relationship_delta=0.6, priority_tag="housing",
            leadership_priority_delta=0.2, rationale="joint housing plan",
        ))
        payload = SimulationWorldCheckpoint.capture(
            4, coordinator, npcs, institutional_politics=politics,
        ).to_json()
        restored = SimulationWorldCheckpoint.from_json(payload).restore()
        self.assertIsNotNone(restored.institutional_politics)
        self.assertEqual(restored.institutional_politics.state(), politics.state())
        self.assertEqual(
            SimulationWorldCheckpoint.capture(
                4, restored.coordinator, restored.npcs,
                institutional_politics=restored.institutional_politics,
            ).to_json(),
            payload,
        )

    def test_institutional_political_history_is_optional(self):
        coordinator, npcs, _ = self.make_simulation()
        payload = SimulationWorldCheckpoint.capture(4, coordinator, npcs).to_json()
        self.assertNotIn("institutional_politics", json.loads(payload))
        restored = SimulationWorldCheckpoint.from_json(payload).restore()
        self.assertIsNone(restored.institutional_politics)


    def test_goal_book_and_event_replay_round_trip_in_world_checkpoint(self):
        coordinator, npcs, _ = self.make_simulation()
        goals = GoalBook()
        goals.add(NPCGoal("goal-1", "speaker", "civic", 0.8, progress=0.25))
        adapter = GoalEventAdapter(goals, (
            GoalProgressPolicy("policy-1", "incident", "civic", 0.2),
        ))
        updates = adapter.apply(coordinator.events.snapshot())
        self.assertEqual(len(updates), 1)
        self.assertAlmostEqual(goals.goals["goal-1"].progress, 0.45)

        payload = SimulationWorldCheckpoint.capture(
            4, coordinator, npcs, goal_book=goals, goal_event_adapter=adapter,
        ).to_json()
        restored = SimulationWorldCheckpoint.from_json(payload).restore()
        self.assertEqual(restored.goals.snapshot(), goals.snapshot())
        self.assertIsNotNone(restored.goal_event_replay)

        restored_adapter = GoalEventAdapter(restored.goals, (
            GoalProgressPolicy("policy-1", "incident", "civic", 0.2),
        ))
        restored.goal_event_replay.restore(restored_adapter)
        self.assertEqual(restored_adapter.apply(restored.events.snapshot()), ())
        self.assertAlmostEqual(restored.goals.goals["goal-1"].progress, 0.45)
        self.assertEqual(
            SimulationWorldCheckpoint.capture(
                4, restored.coordinator, restored.npcs,
                goal_book=restored.goals, goal_event_adapter=restored_adapter,
            ).to_json(),
            payload,
        )

    def test_goal_checkpoint_sections_are_optional_and_replay_requires_goals(self):
        coordinator, npcs, _ = self.make_simulation()
        payload = SimulationWorldCheckpoint.capture(4, coordinator, npcs).to_json()
        self.assertNotIn('"goals"', payload)
        self.assertNotIn('"goal_event_replay"', payload)
        restored = SimulationWorldCheckpoint.from_json(payload).restore()
        self.assertIsNone(restored.goals)
        self.assertIsNone(restored.goal_event_replay)

        altered = json.loads(payload)
        altered["goal_event_replay"] = {
            "schema_version": 1,
            "entries": [["event-1", [3, "incident", ["speaker", "subject"],
                                     ["speaker"], repr((("action_tag", "crime_theft"),
                                                        ("memory_impact", 0.9),
                                                        ("target_entity_id", "subject")))]]],
        }
        with self.assertRaisesRegex(ValueError, "requires the corresponding GoalBook"):
            SimulationWorldCheckpoint.from_json(json.dumps(altered))

    def test_goal_replay_checkpoint_rejects_missing_or_changed_world_events(self):
        coordinator, npcs, _ = self.make_simulation()
        goals = GoalBook()
        goals.add(NPCGoal("goal-2", "speaker", "civic", 0.5))
        adapter = GoalEventAdapter(goals, (
            GoalProgressPolicy("policy-1", "incident", "civic", 0.1),
        ))
        adapter.apply(coordinator.events.snapshot())
        payload = json.loads(SimulationWorldCheckpoint.capture(
            4, coordinator, npcs, goal_book=goals, goal_event_adapter=adapter,
        ).to_json())
        payload["goal_event_replay"]["entries"][0][0] = "missing-event"
        with self.assertRaisesRegex(ValueError, "references missing world event"):
            SimulationWorldCheckpoint.from_json(json.dumps(payload))

    def test_goal_review_decisions_round_trip_in_world_checkpoint(self):
        coordinator, npcs, _ = self.make_simulation()
        goals = GoalBook()
        goals.add(NPCGoal("goal-review-1", "speaker", "career", 5.0, confidence=0.8))
        evaluator = GoalReviewEvaluator(goals, (
            GoalReviewPolicy(
                "career-setback", "incident", "career",
                GoalReviewAction.REPRIORITIZE, priority_delta=-1.0,
            ),
        ))
        proposal = evaluator.assess(coordinator.events.snapshot())[0]
        decisions = GoalReviewDecisionLedger((
            GoalReviewDecision.from_proposal(
                "decision-1", proposal, accepted=True, decision_tick=4,
                rationale="The NPC chooses to lower this ambition's priority.",
            ),
        ))
        payload = SimulationWorldCheckpoint.capture(
            4, coordinator, npcs, goal_book=goals,
            goal_review_decisions=decisions,
        ).to_json()
        restored = SimulationWorldCheckpoint.from_json(payload).restore()
        self.assertIsNotNone(restored.goal_review_decisions)
        self.assertEqual(restored.goal_review_decisions.entries(), decisions.entries())
        self.assertEqual(
            SimulationWorldCheckpoint.capture(
                4, restored.coordinator, restored.npcs, goal_book=restored.goals,
                goal_review_decisions=restored.goal_review_decisions,
            ).to_json(),
            payload,
        )

    def test_goal_review_decisions_are_optional_and_future_decisions_rejected(self):
        coordinator, npcs, _ = self.make_simulation()
        payload = SimulationWorldCheckpoint.capture(4, coordinator, npcs).to_json()
        self.assertNotIn("goal_review_decisions", json.loads(payload))
        self.assertIsNone(
            SimulationWorldCheckpoint.from_json(payload).restore().goal_review_decisions
        )

        goals = GoalBook()
        goals.add(NPCGoal("goal-review-2", "speaker", "career", 2.0))
        proposal = GoalReviewEvaluator(goals, (
            GoalReviewPolicy("persist", "incident", "career", GoalReviewAction.PERSIST),
        )).assess(coordinator.events.snapshot())[0]
        decisions = GoalReviewDecisionLedger((
            GoalReviewDecision.from_proposal(
                "future-decision", proposal, accepted=False, decision_tick=5,
                rationale="The NPC declines the suggestion.",
            ),
        ))
        with self.assertRaisesRegex(ValueError, "after the checkpoint tick"):
            SimulationWorldCheckpoint.capture(
                4, coordinator, npcs, goal_book=goals,
                goal_review_decisions=decisions,
            )

    def test_goal_event_adapter_must_share_checkpoint_goal_book(self):
        coordinator, npcs, _ = self.make_simulation()
        goals = GoalBook()
        other_goals = GoalBook()
        adapter = GoalEventAdapter(other_goals, ())
        with self.assertRaisesRegex(ValueError, "must share"):
            SimulationWorldCheckpoint.capture(
                4, coordinator, npcs, goal_book=goals, goal_event_adapter=adapter,
            )



    def test_presence_encounters_round_trip_in_world_checkpoint(self):
        coordinator, npcs, _ = self.make_simulation()
        presence = PresenceLedger()
        presence.place("speaker", "cafe", 4)
        presence.place("listener", "cafe", 4)
        adapter = PresenceSocialAdapter(presence)
        adapter.encounter(
            "encounter-checkpoint", "speaker", "listener", 4,
            opportunity=True, events=coordinator.events, conversation=True,
            conversation_id="conversation-checkpoint", listener=npcs["listener"],
            speaker=npcs["speaker"], conversation_adapter=coordinator.conversation_adapter,
            trust=coordinator.conversation_adapter.trust,
            trust_directions=(1, -1), trust_strength=0.25,
        )
        familiarity_adapter = PresenceFamiliarityAdapter(adapter.ledger)
        familiarity_adapter.observe_encounter(
            "encounter-checkpoint",
            {("speaker", "listener"): 0.8, ("listener", "speaker"): 0.3},
        )
        payload = SimulationWorldCheckpoint.capture(
            4, coordinator, npcs, presence=presence,
            presence_encounters=adapter.ledger,
            familiarity=familiarity_adapter.ledger,
        ).to_json()
        restored = SimulationWorldCheckpoint.from_json(payload).restore()
        self.assertIsNotNone(restored.presence_encounters)
        self.assertEqual(restored.presence_encounters.snapshot(), adapter.ledger.snapshot())
        self.assertEqual(restored.presence_encounters.tick_snapshot(), adapter.ledger.tick_snapshot())
        self.assertIsNotNone(restored.familiarity)
        self.assertEqual(restored.familiarity.snapshot(), familiarity_adapter.ledger.snapshot())
        self.assertAlmostEqual(restored.familiarity.familiarity("speaker", "listener"), 0.8)
        recognition = restored.familiarity.assess_recognition(
            "speaker", "listener", identity_cue_available=True, threshold=0.7,
        )
        self.assertTrue(recognition.recognized)
        self.assertEqual(
            SimulationWorldCheckpoint.capture(
                4, restored.coordinator, restored.npcs, presence=restored.presence,
                presence_encounters=restored.presence_encounters,
                familiarity=restored.familiarity,
            ).to_json(),
            payload,
        )

    def test_presence_encounter_checkpoint_rejects_missing_presence(self):
        coordinator, npcs, _ = self.make_simulation()
        ledger = PresenceEncounterLedger()
        ledger._record(4, "signature", PresenceEncounter(
            "missing-presence", 4, "cafe", ("listener", "speaker")
        ))
        with self.assertRaisesRegex(ValueError, "corresponding presence ledger"):
            SimulationWorldCheckpoint.capture(
                4, coordinator, npcs, presence_encounters=ledger,
            )

    def test_in_progress_travel_round_trips_in_composite_checkpoint(self):
        coordinator, npcs, _ = self.make_simulation()
        edges = (RouteEdge("street-a", "home", "crossroads", 3),
                 RouteEdge("street-b", "crossroads", "office", 4))
        planner = PersonalRoutePlanner(edges)
        travel_adapter = TravelTickAdapter(edges)
        travel_adapter.start("commute-speaker", "speaker",
                             planner.plan("speaker", "home", "office"), 4)
        travel_adapter.advance(5, {"speaker": 1})
        payload = SimulationWorldCheckpoint.capture(
            5, coordinator, npcs, travel=travel_adapter.ledger,
        ).to_json()
        restored = SimulationWorldCheckpoint.from_json(payload).restore()
        self.assertIsNotNone(restored.travel)
        self.assertEqual(restored.travel.get("commute-speaker").edge_progress, 1)
        self.assertEqual(
            SimulationWorldCheckpoint.capture(5, restored.coordinator, restored.npcs,
                                              travel=restored.travel).to_json(),
            payload,
        )
        resumed = TravelTickAdapter(edges, restored.travel)
        result = resumed.advance(6, {"speaker": 2})
        self.assertEqual(result.journeys[0].current_location, "crossroads")
        self.assertEqual(result.journeys[0].edge_progress, 0)

    def test_travel_checkpoint_rejects_unknown_npc_and_future_tick(self):
        coordinator, npcs, _ = self.make_simulation()
        edges = (RouteEdge("road", "home", "office", 3),)
        adapter = TravelTickAdapter(edges)
        adapter.start("unknown-owner-trip", "ghost", PersonalRoutePlanner(edges).plan("ghost", "home", "office"), 4)
        with self.assertRaisesRegex(ValueError, "missing from checkpoint"):
            SimulationWorldCheckpoint.capture(4, coordinator, npcs, travel=adapter.ledger)
        adapter2 = TravelTickAdapter(edges)
        adapter2.start("future-trip", "speaker", PersonalRoutePlanner(edges).plan("speaker", "home", "office"), 5)
        with self.assertRaisesRegex(ValueError, "after the checkpoint tick"):
            SimulationWorldCheckpoint.capture(4, coordinator, npcs, travel=adapter2.ledger)

    def test_routine_linked_travel_requires_and_validates_saved_routine_book(self):
        coordinator, npcs, _ = self.make_simulation()
        edges = (RouteEdge("commute", "home", "office", 2),)
        planner = PersonalRoutePlanner(edges)
        adapter = TravelTickAdapter(edges)
        adapter.start("routine:4:work-shift", "speaker",
                      planner.plan("speaker", "home", "office"), 4,
                      routine_id="work-shift")
        routines = RoutineBook((
            RoutineBlock("work-shift", "speaker", "work", "office", 540, 600),
        ))
        with self.assertRaisesRegex(ValueError, "requires the corresponding RoutineBook"):
            SimulationWorldCheckpoint.capture(4, coordinator, npcs, travel=adapter.ledger)
        payload = SimulationWorldCheckpoint.capture(
            4, coordinator, npcs, routines=routines, travel=adapter.ledger,
        ).to_json()
        restored = SimulationWorldCheckpoint.from_json(payload).restore()
        self.assertEqual(restored.travel.get("routine:4:work-shift").routine_id, "work-shift")
        wrong_routine = RoutineBook((
            RoutineBlock("work-shift", "listener", "work", "office", 540, 600),
        ))
        with self.assertRaisesRegex(ValueError, "does not match its saved routine"):
            SimulationWorldCheckpoint.capture(
                4, coordinator, npcs, routines=wrong_routine, travel=adapter.ledger,
            )


    def test_relationship_facets_round_trip_and_validate_source_event(self):
        from simreality import RelationshipChange, SocialRelationshipLedger
        coordinator, npcs, _ = self.make_simulation()
        relationships = SocialRelationshipLedger((
            RelationshipChange("warmth-1", "event-1", "speaker", "listener",
                               3, "warmth", 0.8, "protected-me"),
            RelationshipChange("resentment-1", "event-1", "speaker", "listener",
                               3, "resentment", 0.6, "betrayed-me"),
            RelationshipChange("respect-1", "event-1", "listener", "speaker",
                               3, "respect", 0.4, "stood-ground"),
        ))
        payload = SimulationWorldCheckpoint.capture(
            4, coordinator, npcs, relationships=relationships,
        ).to_json()
        restored = SimulationWorldCheckpoint.from_json(payload).restore()
        self.assertEqual(restored.relationships.snapshot(), relationships.snapshot())
        self.assertAlmostEqual(
            restored.relationships.relationship("speaker", "listener").value("warmth"), 0.8,
        )
        self.assertAlmostEqual(
            restored.relationships.relationship("speaker", "listener").value("resentment"), 0.6,
        )
        self.assertAlmostEqual(
            restored.relationships.relationship("listener", "speaker").value("respect"), 0.4,
        )
        self.assertEqual(
            SimulationWorldCheckpoint.capture(
                4, restored.coordinator, restored.npcs,
                relationships=restored.relationships,
            ).to_json(),
            payload,
        )

    def test_relationship_checkpoint_rejects_missing_or_nonparticipant_source(self):
        from simreality import RelationshipChange, SocialRelationshipLedger
        coordinator, npcs, _ = self.make_simulation()
        missing = SocialRelationshipLedger((
            RelationshipChange("missing-source", "no-event", "speaker", "listener",
                               3, "warmth", 0.2),
        ))
        with self.assertRaisesRegex(ValueError, "missing world event"):
            SimulationWorldCheckpoint.capture(4, coordinator, npcs, relationships=missing)
        unrelated = SocialRelationshipLedger((
            RelationshipChange("unrelated-source", "event-1", "listener", "speaker",
                               2, "warmth", 0.2),
        ))
        # The source event occurs at tick 3, so a claimed change at tick 2 predates it.
        self.assertEqual(len(unrelated.snapshot()), 1)
        with self.assertRaisesRegex(ValueError, "does not match its source world event"):
            SimulationWorldCheckpoint.capture(
                4, coordinator, npcs, relationships=unrelated,
            )


    def test_emotional_state_round_trips_with_world_event_provenance(self):
        coordinator, npcs, _ = self.make_simulation()
        emotions = NPCEmotionalEventLedger()
        emotions.advance(
            4, coordinator.events.snapshot(),
            event_rules=(
                EmotionalEventRule("incident-grief", "incident", "witness", "grief", 0.7),
                EmotionalEventRule("incident-anger", "incident", "witness", "anger", 0.3),
            ),
        )
        payload = SimulationWorldCheckpoint.capture(
            4, coordinator, npcs, emotions=emotions,
        ).to_json()
        restored = SimulationWorldCheckpoint.from_json(payload).restore()
        self.assertIsNotNone(restored.emotions)
        self.assertEqual(restored.emotions.snapshot(), emotions.snapshot())
        self.assertAlmostEqual(restored.emotions.state_for("listener").intensities["grief"], 0.7)
        self.assertAlmostEqual(restored.emotions.state_for("speaker").intensities["anger"], 0.3)
        self.assertEqual(
            SimulationWorldCheckpoint.capture(
                4, restored.coordinator, restored.npcs, emotions=restored.emotions,
            ).to_json(),
            payload,
        )

    def test_emotional_checkpoint_rejects_unknown_npc_state(self):
        coordinator, npcs, _ = self.make_simulation()
        from simreality.identity_context import NPCEmotionalState
        emotions = NPCEmotionalEventLedger({
            "missing-npc": NPCEmotionalState("missing-npc", 4, {"anger": 0.5}),
        }, current_tick=4)
        with self.assertRaisesRegex(ValueError, "missing from checkpoint"):
            SimulationWorldCheckpoint.capture(4, coordinator, npcs, emotions=emotions)

    def test_emotional_checkpoint_rejects_event_not_in_authoritative_journal(self):
        coordinator, npcs, _ = self.make_simulation()
        emotions = NPCEmotionalEventLedger()
        invented = WorldEventLedger.make_event(
            "invented-emotion-source", 3, "incident", participants=("speaker",),
        )
        emotions.advance(
            4, (invented,),
            event_rules=(EmotionalEventRule("anger", "incident", "participant", "anger", 0.4),),
        )
        with self.assertRaisesRegex(ValueError, "authoritative world journal"):
            SimulationWorldCheckpoint.capture(4, coordinator, npcs, emotions=emotions)

    def test_emotional_checkpoint_section_is_optional(self):
        coordinator, npcs, _ = self.make_simulation()
        payload = SimulationWorldCheckpoint.capture(4, coordinator, npcs).to_json()
        self.assertNotIn('"emotions"', payload)
        self.assertIsNone(SimulationWorldCheckpoint.from_json(payload).restore().emotions)


    def test_checkpoint_round_trip_persists_memory_reflections(self):
        coordinator, npcs, _ = self.make_simulation()
        history = NPCLifeHistory()
        history.record(AutobiographicalMemory(
            "memory-reflect-1", "speaker", "event-1", 3, ("listener",),
            "The witness abandoned me", 0.8, -0.2,
        ))
        reflections = MemoryReflectionLedger(history)
        reflections.record(MemoryReinterpretation(
            "reflection-1", "speaker", "memory-reflect-1", 4,
            "The witness abandoned me",
            "The witness may have been afraid",
            "I learned more about what happened",
        ))
        checkpoint = SimulationWorldCheckpoint.capture(
            4, coordinator, npcs, life_history=history,
            memory_reflections=reflections,
        )
        payload = checkpoint.to_json()
        restored = SimulationWorldCheckpoint.from_json(payload).restore()
        self.assertIsNotNone(restored.memory_reflections)
        self.assertEqual(restored.memory_reflections.entries(), reflections.entries())
        self.assertEqual(
            restored.memory_reflections.current_interpretation("speaker", "memory-reflect-1"),
            "The witness may have been afraid",
        )
        self.assertEqual(
            restored.life_history.memories("speaker")[0].interpretation,
            "The witness abandoned me",
        )
        self.assertEqual(
            SimulationWorldCheckpoint.capture(
                4, restored.coordinator, restored.npcs,
                life_history=restored.life_history,
                memory_reflections=restored.memory_reflections,
            ).to_json(),
            payload,
        )

    def test_checkpoint_rejects_memory_reflections_without_matching_life_history(self):
        coordinator, npcs, _ = self.make_simulation()
        history = NPCLifeHistory()
        history.record(AutobiographicalMemory(
            "memory-reflect-2", "speaker", "event-1", 3, ("listener",),
            "The witness abandoned me", 0.8, -0.2,
        ))
        reflections = MemoryReflectionLedger(history)
        with self.assertRaisesRegex(ValueError, "require the corresponding"):
            SimulationWorldCheckpoint.capture(
                4, coordinator, npcs, memory_reflections=reflections,
            )

    def test_checkpoint_rejects_reflection_after_checkpoint_tick(self):
        coordinator, npcs, _ = self.make_simulation()
        history = NPCLifeHistory()
        history.record(AutobiographicalMemory(
            "memory-reflect-3", "speaker", "event-1", 3, ("listener",),
            "The witness abandoned me", 0.8, -0.2,
        ))
        reflections = MemoryReflectionLedger(history)
        reflections.record(MemoryReinterpretation(
            "reflection-3", "speaker", "memory-reflect-3", 5,
            "The witness abandoned me", "I understand it differently",
            "Later reflection",
        ))
        with self.assertRaisesRegex(ValueError, "future tick"):
            SimulationWorldCheckpoint.capture(
                4, coordinator, npcs, life_history=history,
                memory_reflections=reflections,
            )

    def test_checkpoint_round_trip_persists_emotional_scars_and_recovery(self):
        coordinator, npcs, _ = self.make_simulation()
        history = NPCLifeHistory()
        history.record(AutobiographicalMemory(
            "scar-memory-1", "speaker", "event-1", 3, ("listener",),
            "The incident left a lasting fear", 0.9, -0.2,
            turning_point=True, tags=("fear",),
        ))
        scars = NPCEmotionalScarLedger()
        scars.add_scar(EmotionalScar(
            "scar-1", "speaker", "event-1", "scar-memory-1",
            4, "fear", "crowded-room", 0.8, 0.999,
        ))
        scars.recover(
            recovery_id="recovery-1", scar_id="scar-1", owner_id="speaker",
            tick=4, amount=0.1, method="supportive_contact",
        )
        payload = SimulationWorldCheckpoint.capture(
            4, coordinator, npcs, life_history=history, emotional_scars=scars,
        ).to_json()
        restored = SimulationWorldCheckpoint.from_json(payload).restore()
        self.assertIsNotNone(restored.emotional_scars)
        self.assertEqual(restored.emotional_scars.scars(), scars.scars())
        self.assertEqual(restored.emotional_scars.recoveries(), scars.recoveries())
        self.assertAlmostEqual(restored.emotional_scars.severity_for("scar-1", 4), 0.7)
        response = restored.emotional_scars.evaluate(
            "speaker", {"crowded-room": 1.0}, 4,
        )
        self.assertAlmostEqual(dict(response.intensities)["fear"], 0.7)
        self.assertEqual(
            SimulationWorldCheckpoint.capture(
                4, restored.coordinator, restored.npcs,
                life_history=restored.life_history,
                emotional_scars=restored.emotional_scars,
            ).to_json(),
            payload,
        )

    def test_checkpoint_rejects_emotional_scars_without_source_history(self):
        coordinator, npcs, _ = self.make_simulation()
        scars = NPCEmotionalScarLedger()
        scars.add_scar(EmotionalScar(
            "scar-no-history", "speaker", "event-1", "missing-memory",
            4, "fear", "crowded-room", 0.8,
        ))
        with self.assertRaisesRegex(ValueError, "autobiographical life history"):
            SimulationWorldCheckpoint.capture(
                4, coordinator, npcs, emotional_scars=scars,
            )

    def test_checkpoint_rejects_emotional_scar_with_mismatched_memory(self):
        coordinator, npcs, _ = self.make_simulation()
        history = NPCLifeHistory()
        history.record(AutobiographicalMemory(
            "memory-other", "listener", "event-1", 3, ("speaker",),
            "A different observer's memory", 0.5, 0.0,
        ))
        scars = NPCEmotionalScarLedger()
        scars.add_scar(EmotionalScar(
            "scar-wrong-owner", "speaker", "event-1", "memory-other",
            4, "fear", "crowded-room", 0.8,
        ))
        with self.assertRaisesRegex(ValueError, "autobiographical source memory"):
            SimulationWorldCheckpoint.capture(
                4, coordinator, npcs, life_history=history, emotional_scars=scars,
            )

    def test_emotional_scar_acceptance_and_rejection_survive_world_checkpoint(self):
        coordinator, npcs, _ = self.make_simulation()
        history = NPCLifeHistory()
        history.record(AutobiographicalMemory(
            "scar-decision-memory", "speaker", "event-1", 3, ("listener",),
            "The incident was frightening", 0.9, -0.2,
            turning_point=True, tags=("fear",),
        ))
        decisions = EmotionalScarDecisionLedger()
        accepted = EmotionalScarProposal(
            "proposal-accepted", "speaker", "event-1", "scar-decision-memory",
            4, "fear", "crowded-room", 0.8, 0.999,
        )
        rejected = EmotionalScarProposal(
            "proposal-rejected", "speaker", "event-1", "scar-decision-memory",
            4, "anger", "raised-voice", 0.6, 0.999,
        )
        decisions.add_proposal(accepted)
        decisions.add_proposal(rejected)
        decisions.decide(EmotionalScarDecision(
            "decision-accepted", accepted.proposal_id, "speaker", 4, True,
            "This experience still affects me",
        ))
        decisions.decide(EmotionalScarDecision(
            "decision-rejected", rejected.proposal_id, "speaker", 4, False,
            "I do not identify with this reaction",
        ))
        payload = SimulationWorldCheckpoint.capture(
            4, coordinator, npcs, life_history=history,
            emotional_scar_decisions=decisions,
        ).to_json()
        restored = SimulationWorldCheckpoint.from_json(payload).restore()
        self.assertEqual(restored.emotional_scar_decisions.proposals(), decisions.proposals())
        self.assertEqual(restored.emotional_scar_decisions.decisions(), decisions.decisions())
        self.assertEqual(restored.emotional_scar_decisions.scars.snapshot(), decisions.scars.snapshot())
        self.assertEqual(len(restored.emotional_scar_decisions.scars.scars()), 1)
        self.assertEqual(
            SimulationWorldCheckpoint.capture(
                4, restored.coordinator, restored.npcs,
                life_history=restored.life_history,
                emotional_scar_decisions=restored.emotional_scar_decisions,
            ).to_json(),
            payload,
        )

    def test_checkpoint_rejects_rejected_scar_proposal_without_matching_memory(self):
        coordinator, npcs, _ = self.make_simulation()
        history = NPCLifeHistory()
        history.record(AutobiographicalMemory(
            "other-owner-memory", "listener", "event-1", 3, ("speaker",),
            "Only the listener remembers this", 0.7, 0.0,
        ))
        decisions = EmotionalScarDecisionLedger()
        proposal = EmotionalScarProposal(
            "proposal-invalid", "speaker", "event-1", "other-owner-memory",
            4, "fear", "crowded-room", 0.5,
        )
        decisions.add_proposal(proposal)
        decisions.decide(EmotionalScarDecision(
            "decision-invalid", proposal.proposal_id, "speaker", 4, False,
            "Rejected",
        ))
        with self.assertRaisesRegex(ValueError, "autobiographical source memory"):
            SimulationWorldCheckpoint.capture(
                4, coordinator, npcs, life_history=history,
                emotional_scar_decisions=decisions,
            )


    def test_checkpoint_round_trips_scar_identity_proposals_and_decision_chain(self):
        from simreality import (
            EmotionalScarIdentityAdapter, ScarIdentityPolicy,
            ScarIdentityProposalLedger,
        )
        coordinator, npcs, _ = self.make_simulation()
        history = NPCLifeHistory()
        history.record(AutobiographicalMemory(
            "identity-scar-memory", "speaker", "event-1", 3, ("listener",),
            "The incident left a lasting fear", 0.9, -0.2,
            turning_point=True, tags=("fear",),
        ))
        scars = NPCEmotionalScarLedger()
        scars.add_scar(EmotionalScar(
            "identity-scar-1", "speaker", "event-1", "identity-scar-memory",
            4, "fear", "crowded-room", 0.8,
        ))
        identities = IdentityDecisionLedger((
            NPCIdentityProfile("speaker", {"trust": 0.1}),
            NPCIdentityProfile("listener", {"trust": 0.0}),
        ))
        policy = ScarIdentityPolicy(
            "fear-to-trust", "fear", "crowded-room", "trust",
            delta_per_severity=-0.05, maximum_delta=0.05,
        )
        evidence = EmotionalScarIdentityAdapter.propose_evidence(
            scars, identities, coordinator.events, (policy,), 4,
        )
        self.assertEqual(len(evidence), 1)
        proposals = ScarIdentityProposalLedger()
        proposals.record_many(evidence)
        identities.decide(
            "identity-scar-decision-1", evidence[0].proposal,
            accepted=True, decision_tick=4,
            rationale="I choose to become more cautious",
        )
        payload = SimulationWorldCheckpoint.capture(
            4, coordinator, npcs, life_history=history, emotional_scars=scars,
            identity_decisions=identities, scar_identity_proposals=proposals,
        ).to_json()
        restored = SimulationWorldCheckpoint.from_json(payload).restore()
        self.assertEqual(restored.scar_identity_proposals.entries(), evidence)
        self.assertEqual(restored.identity_decisions.traits_for("speaker")["trust"],
                         evidence[0].proposal.after)
        self.assertEqual(
            SimulationWorldCheckpoint.capture(
                4, restored.coordinator, restored.npcs,
                life_history=restored.life_history,
                emotional_scars=restored.emotional_scars,
                identity_decisions=restored.identity_decisions,
                scar_identity_proposals=restored.scar_identity_proposals,
            ).to_json(),
            payload,
        )

    def test_emotional_scars_remain_optional_in_legacy_checkpoints(self):
        coordinator, npcs, _ = self.make_simulation()
        payload = SimulationWorldCheckpoint.capture(4, coordinator, npcs).to_json()
        self.assertNotIn('"emotional_scars"', payload)
        self.assertIsNone(SimulationWorldCheckpoint.from_json(payload).restore().emotional_scars)



    def test_identity_goal_reviews_round_trip_with_identity_provenance_and_once_only_application(self):
        coordinator, npcs, _ = self.make_simulation()
        goals = GoalBook()
        goals.add(NPCGoal("career-goal", "speaker", "career", 5.0, confidence=0.6))
        identity = IdentityDecisionLedger((NPCIdentityProfile("speaker", {"ambition": 0.0}),))
        proposal = IdentityChangeProposal("event-1", "speaker", "identity-policy", "ambition", 0.0, 0.3, 0.3, 0.8, "participant", 0.1)
        identity.decide("identity-accepted", proposal, accepted=True, decision_tick=4, rationale="I accept this change")
        adapter = IdentityGoalAlignmentAdapter(goals, (IdentityGoalAlignmentPolicy("career-alignment", "ambition", "career", IdentityGoalAction.REPRIORITIZE, minimum_abs_delta=0.1, priority_delta=1.5),))
        review_proposal, = adapter.assess(identity.entries(), current_tick=4)
        reviews = IdentityGoalReviewDecisionLedger((IdentityGoalReviewDecision("goal-review-1", review_proposal, True, 5, "This goal matters more to me now"),))
        self.assertTrue(reviews.apply_accepted("goal-review-1", goals))
        payload = SimulationWorldCheckpoint.capture(5, coordinator, npcs, goal_book=goals, identity_decisions=identity, identity_goal_reviews=reviews).to_json()
        restored = SimulationWorldCheckpoint.from_json(payload).restore()
        self.assertEqual(restored.goals.goals["career-goal"].priority, 6.5)
        self.assertEqual(restored.identity_goal_reviews.entries(), reviews.entries())
        self.assertFalse(restored.identity_goal_reviews.apply_accepted("goal-review-1", restored.goals))
        self.assertEqual(SimulationWorldCheckpoint.capture(5, restored.coordinator, restored.npcs, goal_book=restored.goals, identity_decisions=restored.identity_decisions, identity_goal_reviews=restored.identity_goal_reviews).to_json(), payload)

    def test_checkpoint_rejects_identity_goal_review_without_accepted_identity_source(self):
        coordinator, npcs, _ = self.make_simulation()
        goals = GoalBook()
        goals.add(NPCGoal("career-goal", "speaker", "career", 5.0))
        identity = IdentityDecisionLedger((NPCIdentityProfile("speaker", {"ambition": 0.0}),))
        proposal = IdentityChangeProposal("event-1", "speaker", "identity-policy", "ambition", 0.0, 0.3, 0.3, 0.8, "participant", 0.1)
        identity.decide("identity-rejected", proposal, accepted=False, decision_tick=4, rationale="This is not me")
        from simreality.identity_goal_alignment import IdentityGoalReviewProposal
        forged = IdentityGoalReviewProposal("identity-rejected", "event-1", "speaker", "identity-policy", "ambition", 0.3, "career-goal", "career-alignment", IdentityGoalAction.REPRIORITIZE, 4, "career", "career", 5.0, 6.0, 0.5, 0.5)
        reviews = IdentityGoalReviewDecisionLedger((IdentityGoalReviewDecision("forged-review", forged, True, 5, "forged"),))
        with self.assertRaisesRegex(ValueError, "accepted identity decision"):
            SimulationWorldCheckpoint.capture(5, coordinator, npcs, goal_book=goals, identity_decisions=identity, identity_goal_reviews=reviews)
    def test_action_execution_and_world_resources_restore_atomically(self):
        coordinator, npcs, _ = self.make_simulation()
        planner = DeterministicPlanner((
            PlanningAction("collect-grain", frozenset({"at-field"}),
                           frozenset({"has-grain"})),
        ))
        policies = (ActionExecutionPolicy("collect-grain", (("energy", 2.0),),
                                          duration_ticks=2),)
        ledger = ActionExecutionLedger(planner, policies, coordinator.events)
        facts, resources = {"at-field"}, {"energy": 5.0}
        ledger.start("collect-1", "speaker", 4, "collect-grain", facts, resources,
                     plan_actions=("collect-grain",))
        ledger.advance("collect-1", 5, facts, resources)
        payload = SimulationWorldCheckpoint.capture(
            5, coordinator, npcs, action_executions=ledger,
            action_world_facts=facts, action_resources=resources,
        ).to_json()
        restored = SimulationWorldCheckpoint.from_json(payload).restore()
        self.assertEqual(restored.action_world_facts, {"at-field"})
        self.assertEqual(restored.action_resources, {"energy": 5.0})
        resumed = restored.restore_action_execution_ledger(planner, policies)
        self.assertEqual(resumed.active("collect-1").progress_ticks, 1)
        self.assertEqual(
            SimulationWorldCheckpoint.capture(
                5, restored.coordinator, restored.npcs, action_executions=resumed,
                action_world_facts=restored.action_world_facts,
                action_resources=restored.action_resources,
            ).to_json(),
            payload,
        )
        result = resumed.advance("collect-1", 6, restored.action_world_facts,
                                 restored.action_resources)
        self.assertEqual(result.status, "completed")
        self.assertEqual(restored.action_world_facts, {"at-field", "has-grain"})
        self.assertEqual(restored.action_resources, {"energy": 3.0})


    def test_replanning_history_restores_with_action_checkpoint(self):
        from simreality.action_execution import ActionExecutionLedger, ActionExecutionPolicy
        from simreality.npc_action_replanning import NPCActionReplanningCoordinator
        from simreality.npc_autonomy import NPCDecisionCycle
        from simreality.planning import DeterministicPlanner, PlanningAction

        coordinator, npcs, _ = self.make_simulation()
        goals = GoalBook()
        goals.add(NPCGoal("food-goal", "speaker", "survival", 8.0))
        planner = DeterministicPlanner((
            PlanningAction("get-food", frozenset({"at-market"}), frozenset({"has-food"})),
        ))
        policies = (ActionExecutionPolicy("get-food"),)
        ledger = ActionExecutionLedger(planner, policies, coordinator.events, goals)
        decisions = NPCDecisionCycle(goals, planner)
        replanning = NPCActionReplanningCoordinator(decisions, ledger)
        facts, resources = {"at-market"}, {"cash": 3.0}
        goal_facts = {"food-goal": {"has-food"}}
        first = replanning.replan(
            "speaker", 4, facts, resources, goal_facts, reason="food needed",
        )
        self.assertEqual(first.status, "started")
        payload = SimulationWorldCheckpoint.capture(
            4, coordinator, npcs, goal_book=goals,
            action_executions=ledger, action_world_facts=facts,
            action_resources=resources, action_replanning=replanning,
        ).to_json()

        restored = SimulationWorldCheckpoint.from_json(payload).restore()
        restored_ledger = restored.restore_action_execution_ledger(planner, policies)
        restored_decisions = NPCDecisionCycle(restored.goals, planner)
        restored_replanning = restored.restore_action_replanning_coordinator(
            restored_decisions, restored_ledger,
        )
        repeated = restored_replanning.replan(
            "speaker", 4, facts, resources, goal_facts, reason="food needed",
        )
        self.assertEqual(repeated, first)
        self.assertEqual(len(restored_ledger.active()), 1)
        self.assertEqual(
            SimulationWorldCheckpoint.capture(
                4, restored.coordinator, restored.npcs, goal_book=restored.goals,
                action_executions=restored_ledger, action_world_facts=restored.action_world_facts,
                action_resources=restored.action_resources, action_replanning=restored_replanning,
            ).to_json(),
            payload,
        )


    def test_action_evaluation_history_and_learning_restore_atomically(self):
        from simreality.npc_action_replanning import NPCActionReplanningCoordinator
        from simreality.npc_autonomy import NPCDecisionCycle

        coordinator, npcs, _ = self.make_simulation()
        goals = GoalBook()
        goals.add(NPCGoal("food-goal", "speaker", "survival", 8.0))
        planner = DeterministicPlanner((
            PlanningAction("get-food", frozenset({"at-market"}), frozenset({"has-food"})),
        ))
        policies = (ActionExecutionPolicy("get-food"),)
        executions = ActionExecutionLedger(planner, policies, coordinator.events, goals)
        evaluations = ActionPlanEvaluationLedger(executions, learning_min_samples=1)
        decisions = NPCDecisionCycle(goals, planner)
        replanning = NPCActionReplanningCoordinator(
            decisions, executions, coordinator.events, evaluations,
        )
        facts, resources = {"at-market"}, {"cash": 3.0}
        goal_facts = {"food-goal": {"has-food"}}
        planned = replanning.replan(
            "speaker", 4, facts, resources, goal_facts, reason="food needed",
        )
        progression = replanning.advance(
            planned.execution_id, 5, facts, resources, goal_facts,
        )
        self.assertIsNotNone(progression.evaluation)
        self.assertIsNotNone(progression.plan_evaluation)
        payload = SimulationWorldCheckpoint.capture(
            5, coordinator, npcs, goal_book=goals,
            action_executions=executions, action_world_facts=facts,
            action_resources=resources, action_replanning=replanning,
            action_evaluations=evaluations,
        ).to_json()

        restored = SimulationWorldCheckpoint.from_json(payload).restore()
        restored_executions = restored.restore_action_execution_ledger(planner, policies)
        restored_evaluations = restored.restore_action_evaluation_ledger(restored_executions)
        restored_decisions = NPCDecisionCycle(restored.goals, planner)
        restored_replanning = restored.restore_action_replanning_coordinator(
            restored_decisions, restored_executions, restored_evaluations,
        )
        self.assertEqual(restored_evaluations.to_snapshot(), evaluations.to_snapshot())
        self.assertEqual(restored_evaluations.plan_history, evaluations.plan_history)
        self.assertEqual(restored_evaluations.reliability("get-food"), evaluations.reliability("get-food"))
        self.assertIs(restored_replanning.evaluations, restored_evaluations)
        self.assertEqual(
            SimulationWorldCheckpoint.capture(
                5, restored.coordinator, restored.npcs, goal_book=restored.goals,
                action_executions=restored_executions,
                action_world_facts=restored.action_world_facts,
                action_resources=restored.action_resources,
                action_replanning=restored_replanning,
                action_evaluations=restored_evaluations,
            ).to_json(),
            payload,
        )

    def test_action_checkpoint_requires_atomic_facts_and_resources(self):
        coordinator, npcs, _ = self.make_simulation()
        planner = DeterministicPlanner((
            PlanningAction("collect-grain", frozenset({"at-field"}),
                           frozenset({"has-grain"})),
        ))
        ledger = ActionExecutionLedger(planner, (), coordinator.events)
        with self.assertRaisesRegex(ValueError, "require world facts and resource balances"):
            SimulationWorldCheckpoint.capture(
                4, coordinator, npcs, action_executions=ledger,
            )

    def test_action_checkpoint_rejects_execution_after_checkpoint_tick(self):
        coordinator, npcs, _ = self.make_simulation()
        planner = DeterministicPlanner((
            PlanningAction("collect-grain", frozenset({"at-field"}),
                           frozenset({"has-grain"})),
        ))
        ledger = ActionExecutionLedger(planner, (), coordinator.events)
        facts, resources = {"at-field"}, {}
        ledger.start("future-action", "speaker", 5, "collect-grain", facts, resources,
                     plan_actions=("collect-grain",))
        with self.assertRaisesRegex(ValueError, "active action execution"):
            SimulationWorldCheckpoint.capture(
                4, coordinator, npcs, action_executions=ledger,
                action_world_facts=facts, action_resources=resources,
            )


if __name__ == "__main__":
    unittest.main()


    def test_checkpoint_round_trip_persists_reported_npc_experiences(self):
        coordinator, npcs, _ = self.make_simulation()
        coordinator.events.append(WorldEventLedger.make_event(
            "chat-transfer", 4, "conversation",
            participants=("speaker", "listener"),
        ))
        history = NPCLifeHistory((AutobiographicalMemory(
            "speaker-memory", "speaker", "event-1", 3, ("listener",),
            "I experienced the incident first-hand", 0.7, 0.2,
        ),))
        transfers = NPCExperienceTransferLedger(coordinator.events, history)
        transfers.transfer("share-1", "listener", "speaker", "speaker-memory",
                           "chat-transfer", confidence=0.75)
        checkpoint = SimulationWorldCheckpoint.capture(
            4, coordinator, npcs, life_history=history,
            experience_transfers=transfers,
        )
        restored = SimulationWorldCheckpoint.from_json(checkpoint.to_json()).restore()
        self.assertIsNotNone(restored.experience_transfers)
        self.assertEqual(restored.experience_transfers.received_by("listener"),
                         transfers.received_by("listener"))
        self.assertEqual(
            SimulationWorldCheckpoint.capture(
                4, restored.coordinator, restored.npcs,
                life_history=restored.life_history,
                experience_transfers=restored.experience_transfers,
            ).to_json(),
            checkpoint.to_json(),
        )

    def test_checkpoint_rejects_experience_transfers_without_shared_life_history(self):
        coordinator, npcs, _ = self.make_simulation()
        coordinator.events.append(WorldEventLedger.make_event(
            "chat-transfer", 4, "conversation",
            participants=("speaker", "listener"),
        ))
        history = NPCLifeHistory((AutobiographicalMemory(
            "speaker-memory", "speaker", "event-1", 3, ("listener",),
            "I experienced the incident first-hand", 0.7, 0.2,
        ),))
        transfers = NPCExperienceTransferLedger(coordinator.events, history)
        transfers.transfer("share-1", "listener", "speaker", "speaker-memory",
                           "chat-transfer", confidence=0.75)
        with self.assertRaisesRegex(ValueError, "require the checkpoint autobiographical life history"):
            SimulationWorldCheckpoint.capture(
                4, coordinator, npcs, experience_transfers=transfers,
            )

    def test_goal_lifecycle_round_trips_with_goal_book_and_preserves_reopen_history(self):
        coordinator, npcs, _ = self.make_simulation()
        goals = GoalBook()
        goal = NPCGoal("goal-1", "speaker", "safety", 4.0)
        goals.add(goal)
        history = NPCLifeHistory((AutobiographicalMemory(
            "goal-memory", "speaker", "event-1", 3, ("listener",),
            "A turning point", 0.8, 0.2, turning_point=True,
            tags=("goal:safety",),
        ),))
        lifecycle = GoalLifecycleLedger()
        lifecycle.record(goal, 3, "adopted", evidence_ids=("goal-memory",))
        lifecycle.transition(
            goals, "goal-1", GoalStatus.ABANDONED, 4, "immediate danger passed",
        )
        lifecycle.transition(
            goals, "goal-1", GoalStatus.ACTIVE, 5, "new threat emerged",
        )
        payload = SimulationWorldCheckpoint.capture(
            5, coordinator, npcs, goal_book=goals, goal_lifecycle=lifecycle,
            life_history=history,
        ).to_json()
        restored = SimulationWorldCheckpoint.from_json(payload).restore()
        self.assertIsNotNone(restored.goal_lifecycle)
        self.assertEqual(restored.goal_lifecycle.snapshot(), lifecycle.snapshot())
        self.assertEqual(restored.goals.goals["goal-1"].status.value, "active")
        self.assertEqual(
            SimulationWorldCheckpoint.capture(
                5, restored.coordinator, restored.npcs,
                goal_book=restored.goals, goal_lifecycle=restored.goal_lifecycle,
                life_history=restored.life_history,
            ).to_json(),
            payload,
        )

    def test_goal_lifecycle_checkpoint_rejects_unknown_goal(self):
        coordinator, npcs, _ = self.make_simulation()
        goals = GoalBook()
        from simreality.npc_goal_emergence import GoalLifecycleEvent
        lifecycle = GoalLifecycleLedger((
            GoalLifecycleEvent("life-1", "missing", "speaker", None,
                               "active", 3, "adopted"),
        ))
        with self.assertRaisesRegex(ValueError, "unknown goal"):
            SimulationWorldCheckpoint.capture(
                4, coordinator, npcs, goal_book=goals, goal_lifecycle=lifecycle,
            )
