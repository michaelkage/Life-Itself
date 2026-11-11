"""Simulation core for the Simulated Reality Engine.

Seven sub-engines, pure Python, no engine dependency:

    decay      -- exponential memory decay with correct sign handling
    gossip     -- rumour mutation through social contact
    ecosystem  -- desperation index and behavioural status flips
    districts  -- macro dynamics over time, city scars with hysteresis
    trauma     -- personal stress accumulation and behavioural tiers
    justice    -- evidence, charges, plea bargaining
    fixers     -- reputation, willingness, betrayal, the district network
    reputation -- local standing derived from evidence

Engine-independent on purpose. This is the layer that runs on the background
thread behind Unreal's render loop; nothing in it may touch a UObject, a UWorld,
or a game thread. Keeping that boundary honest is what makes it testable now and
portable to C++ later.
"""

from .model import (
    ActionTag,
    AgeBand,
    Description,
    District,
    NPC,
    NPCMemory,
    TELEPHONE_THRESHOLD,
    TraumaLevel,
    Weather,
)
from .decay import LAMBDA_BASE, decay_constant, retention_after, sweep, visibility_modifier
from .ecosystem import (
    BehaviourDecision,
    IllegalBranch,
    desperation_index,
    evaluate,
    apply_district_pressure,
)
from .gossip import Conversation, Rumour, converse, police_response, retell
from . import districts, fixers, justice, reputation, trauma

__all__ = [
    "ActionTag",
    "AgeBand",
    "Description",
    "District",
    "NPC",
    "NPCMemory",
    "TELEPHONE_THRESHOLD",
    "TraumaLevel",
    "Weather",
    "LAMBDA_BASE",
    "decay_constant",
    "retention_after",
    "sweep",
    "visibility_modifier",
    "BehaviourDecision",
    "IllegalBranch",
    "desperation_index",
    "evaluate",
    "apply_district_pressure",
    "Conversation",
    "Rumour",
    "converse",
    "police_response",
    "retell",
    "districts",
    "fixers",
    "justice",
    "reputation",
    "trauma",
]

# Persistent health, social obligations, and finite campaign-life lifecycle.
from .health_life import (
    CampaignLife,
    CharacterHealth,
    HealthCondition,
    LifeState,
    PersistentWorld,
    SocialObligation,
    WorldArchive,
)

__all__ += [
    "CampaignLife",
    "CharacterHealth",
    "HealthCondition",
    "LifeState",
    "PersistentWorld",
    "SocialObligation",
    "WorldArchive",
]

from .campaign import ArchivedTimeline, LifeItselfCampaign

__all__ += ["ArchivedTimeline", "LifeItselfCampaign"]


# Daily medical, economic, relationship, bereavement and ghost decision services.
from .life_simulation import (
    DailyLifeRecord,
    GhostDecision,
    GhostWindow,
    LifeSimulation,
    PersonProfile,
    RecoveryEstimate,
    ResponsibilityOutcome,
    ResponsibilityResolution,
    Treatment,
)

__all__ += [
    "DailyLifeRecord", "GhostDecision", "GhostWindow", "LifeSimulation",
    "PersonProfile", "RecoveryEstimate", "ResponsibilityOutcome",
    "ResponsibilityResolution", "Treatment",
]


# Deterministic intention tracking, prerequisite resolution, and bounded goal selection.
from .goals import GoalBook, GoalEvaluation, GoalStatus, NPCGoal

__all__ += ["GoalBook", "GoalEvaluation", "GoalStatus", "NPCGoal"]


# Bounded deterministic symbolic planner for NPC action sequences.
from .planning import DeterministicPlanner, PlanResult, PlanningAction

__all__ += ["DeterministicPlanner", "PlanResult", "PlanningAction"]


# Integrated, read-only NPC goal selection and symbolic planning decision cycle.
from .npc_autonomy import NPCDecision, NPCDecisionCycle

__all__ += ["NPCDecision", "NPCDecisionCycle"]


# Transparent, deterministic appraisal of NPC choices using individual values and bias cues.
from .appraisal import AppraisalResult, ChoiceOption, NPCAppraiser, NPCValueProfile

__all__ += ["AppraisalResult", "ChoiceOption", "NPCAppraiser", "NPCValueProfile"]


# Deterministic evidence tracking for NPC claims and confidence.
from .beliefs import BeliefLedger, BeliefState, Evidence

__all__ += ["BeliefLedger", "BeliefState", "Evidence"]


# Explicit integration between evidence confidence and value-relative NPC appraisal.
from .belief_appraisal import BeliefAwareAppraiser, BeliefAwareResult

__all__ += ["BeliefAwareAppraiser", "BeliefAwareResult"]


# Observer-specific social trust from deterministic interaction history.
from .social_trust import SocialInteraction, SocialTrustLedger, SocialTrustState

__all__ += ["SocialInteraction", "SocialTrustLedger", "SocialTrustState"]

from .social_beliefs import SocialBeliefSystem
__all__ += ["SocialBeliefSystem"]

# Read-only choice ranking using one NPC's social beliefs and value profile.
from .social_decisions import SocialBeliefDecisionAdapter, SocialDecisionResult
__all__ += ["SocialBeliefDecisionAdapter", "SocialDecisionResult"]


# Witnessed actions that update observer-specific trust and beliefs.
from .social_consequences import (
    ObservedClaim, SocialConsequenceRecorder, SocialConsequenceResult,
    WitnessedSocialEvent,
)
__all__ += [
    "ObservedClaim", "SocialConsequenceRecorder", "SocialConsequenceResult",
    "WitnessedSocialEvent",
]


# Shared deterministic journal of authoritative world events.
from .world_events import WorldEvent, WorldEventLedger
__all__ += ["WorldEvent", "WorldEventLedger"]


# Validate and route per-witness interpretations from the shared world journal.
from .world_event_social import WorldEventSocialAdapter
__all__ += ["WorldEventSocialAdapter"]


# Event-to-memory bridge for explicit witnesses.
from .world_event_memory import WorldEventMemoryAdapter
__all__ += ["WorldEventMemoryAdapter"]


# Deterministic decay snapshots and rumour preparation from NPC-owned memories.
from .memory_rumours import MemoryRumourAdapter, MemoryRumourSnapshot
__all__ += ["MemoryRumourAdapter", "MemoryRumourSnapshot"]


# Actual NPC conversation transfer and trust-weighted belief updates.
from .social_conversations import ConversationBeliefResult, SocialConversationAdapter
__all__ += ["ConversationBeliefResult", "SocialConversationAdapter"]


# Stable tick ordering for explicit event-memory and NPC-conversation work.
from .simulation_tick import ConversationIntent, SimulationTickCoordinator, SimulationTickResult
__all__ += ["ConversationIntent", "SimulationTickCoordinator", "SimulationTickResult"]


# Versioned JSON envelope for simulation clock and authoritative event history.
from .save_state import SimulationSaveEnvelope
__all__ += ["SimulationSaveEnvelope"]


# Versioned NPC identity and witnessed-memory snapshots.
from .npc_save_state import NPCCollectionSnapshot, NPCStateSnapshot
__all__ += ["NPCCollectionSnapshot", "NPCStateSnapshot"]

# Trust priors and interaction history for deterministic relationship restoration.
from .npc_save_state import SocialTrustSnapshot
__all__ += ["SocialTrustSnapshot"]

# Versioned persistence for evidence history and observer-specific beliefs.
from .social_belief_save_state import BeliefLedgerSnapshot, SocialBeliefSnapshot
__all__ += ["BeliefLedgerSnapshot", "SocialBeliefSnapshot"]


# Replay-index persistence for witness-memory materialization.
from .adapter_replay_state import WorldEventMemoryReplaySnapshot
__all__ += ["WorldEventMemoryReplaySnapshot"]


# Versioned replay indexes for social conversations and witnessed consequences.
from .social_replay_save_state import SocialConversationReplaySnapshot, SocialConsequenceReplaySnapshot
__all__ += ["SocialConversationReplaySnapshot", "SocialConsequenceReplaySnapshot"]


# Coordinator request/result replay persistence; dependent adapters restore first.
from .tick_replay_save_state import SimulationTickReplaySnapshot
__all__ += ["SimulationTickReplaySnapshot"]


# Composite canonical checkpoint for the integrated simulation pipeline.
from .world_checkpoint import RestoredSimulation, SimulationWorldCheckpoint
__all__ += ["RestoredSimulation", "SimulationWorldCheckpoint"]


# Goal intentions can raise matching daily routine priority within explicit life budgets.
from .goal_life import (
    GoalLifeAdapter, GoalLifeAssessment, GoalLifeContext,
    GoalRoutinePolicy, GoalRoutineProposal,
)
__all__ += [
    "GoalLifeAdapter", "GoalLifeAssessment", "GoalLifeContext",
    "GoalRoutinePolicy", "GoalRoutineProposal",
]


# Disruption-aware, deterministic NPC routine resolution.
from .routines import (
    DisruptionKind, RoutineBlock, RoutineBook, RoutineDisruption,
    RoutineOutcome, RoutineResolution,
)
__all__ += [
    "DisruptionKind", "RoutineBlock", "RoutineBook", "RoutineDisruption",
    "RoutineOutcome", "RoutineResolution",
]


# Evidence-aware reporting and review history for institutional misconduct.
from .misconduct import (
    MisconductReport, MisconductReportingSystem, MisconductType,
    ReportStatus, ReviewDecision, ReviewOutcome,
)
__all__ += [
    "MisconductReport", "MisconductReportingSystem", "MisconductType",
    "ReportStatus", "ReviewDecision", "ReviewOutcome",
]


# Canonical persistence for misconduct reports and review history.
from .misconduct_save_state import MisconductSnapshot
__all__ += ["MisconductSnapshot"]


# Canonical persistence for planned NPC routine schedules.
from .routine_save_state import RoutineBookSnapshot
__all__ += ["RoutineBookSnapshot"]


# Idempotent execution history and canonical persistence for NPC routines.
from .routine_execution import RoutineExecution, RoutineExecutionLedger
from .routine_execution_save_state import RoutineExecutionSnapshot
__all__ += ["RoutineExecution", "RoutineExecutionLedger", "RoutineExecutionSnapshot"]


# Personal, deterministic routine avoidance from explicitly location-linked memories.
from .memory_routines import (
    MemoryLocationAssociation, MemoryRoutineAdapter, RoutineAvoidanceProfile,
)
__all__ += ["MemoryLocationAssociation", "MemoryRoutineAdapter", "RoutineAvoidanceProfile"]

# Owner-scoped persistence for explicit memory/location associations.
from .memory_location_book import MemoryLocationAssociationBook
from .memory_routine_save_state import MemoryLocationAssociationSnapshot
__all__ += ["MemoryLocationAssociationBook", "MemoryLocationAssociationSnapshot"]

# Deterministic route selection with NPC-specific memory avoidance costs.
from .route_planning import PersonalRoutePlanner, RouteEdge, RoutePlan
__all__ += ["PersonalRoutePlanner", "RouteEdge", "RoutePlan"]


# Deterministic bridge from schedule definitions to tick-level executions.
from .routine_tick import RoutineTickAdapter
__all__ += ["RoutineTickAdapter"]


# Materialize explicit routine outcomes in the authoritative world event journal.
from .routine_world_events import RoutineWorldEventAdapter
__all__ += ["RoutineWorldEventAdapter"]


# Explicit policy-driven effects of routine outcomes.
from .routine_consequences import RoutineConsequenceAdapter, RoutineImpactPolicy
__all__ += ["RoutineConsequenceAdapter", "RoutineImpactPolicy"]


from .routine_institution_ledger import InstitutionalRecord, RoutineInstitutionLedger
__all__ += ["InstitutionalRecord", "RoutineInstitutionLedger"]

from .routine_institution_save_state import RoutineInstitutionSnapshot
__all__ += ["RoutineInstitutionSnapshot"]


# Transparent, context-aware institutional review recommendations.
from .institutional_review import (
    ContextAdjustment, InstitutionalReviewAssessment, InstitutionalReviewEvaluator,
    InstitutionalReviewPolicy, ReviewContribution, ReviewLevel,
)
__all__ += [
    "ContextAdjustment", "InstitutionalReviewAssessment", "InstitutionalReviewEvaluator",
    "InstitutionalReviewPolicy", "ReviewContribution", "ReviewLevel",
]


# Institution-specific response options; planning never executes an action.
from .institutional_response import (
    InstitutionalResponseOption, InstitutionalResponsePlan,
    InstitutionalResponsePlanner, InstitutionalResponsePolicy,
)
__all__ += [
    "InstitutionalResponseOption", "InstitutionalResponsePlan",
    "InstitutionalResponsePlanner", "InstitutionalResponsePolicy",
]


# Leadership, resource pressure, departmental priorities, and employee bias in institutional choices.
from .institutional_dynamics import (
    DepartmentState, InstitutionalDecisionEvaluator, InstitutionalDecisionOption,
    InstitutionalDecisionResult, InstitutionalEmployee, InstitutionalOptionAssessment,
    InstitutionalProfile, InstitutionalScoreContribution,
)
__all__ += [
    "DepartmentState", "InstitutionalDecisionEvaluator", "InstitutionalDecisionOption",
    "InstitutionalDecisionResult", "InstitutionalEmployee", "InstitutionalOptionAssessment",
    "InstitutionalProfile", "InstitutionalScoreContribution",
]


# Deterministic competition for institutional budgets and staffing.
from .institutional_resources import (
    DepartmentAllocation, DepartmentResourceRequest, InstitutionalResourceAllocator,
    ResourceAllocationPlan, ResourceAllocationPolicy,
)
__all__ += [
    "DepartmentAllocation", "DepartmentResourceRequest", "InstitutionalResourceAllocator",
    "ResourceAllocationPlan", "ResourceAllocationPolicy",
]


# Event-sourced departmental alliances, rivalries, lobbying effects, and influence.
from .institutional_politics import (
    InstitutionalPoliticalEvent, InstitutionalPoliticalLedger,
    InstitutionalPoliticalState,
)
__all__ += [
    "InstitutionalPoliticalEvent", "InstitutionalPoliticalLedger",
    "InstitutionalPoliticalState",
]


# Coalition-aware lobbying and transparent institutional political outcomes.
from .institutional_lobbying import (
    InstitutionalLobbyEvaluator, PoliticalLobbyAssessment,
    PoliticalLobbyPolicy, PoliticalLobbyRequest,
)
__all__ += [
    "InstitutionalLobbyEvaluator", "PoliticalLobbyAssessment",
    "PoliticalLobbyPolicy", "PoliticalLobbyRequest",
]


# Policy-driven effects of explicit institutional outcomes and review findings.
from .institutional_outcomes import (
    InstitutionalOutcome, InstitutionalOutcomeAdapter,
    InstitutionalOutcomeAssessment, InstitutionalOutcomePolicy,
    InstitutionalOutcomeRule,
)
__all__ += [
    "InstitutionalOutcome", "InstitutionalOutcomeAdapter",
    "InstitutionalOutcomeAssessment", "InstitutionalOutcomePolicy",
    "InstitutionalOutcomeRule",
]


# Connect append-only misconduct findings to institutional political history.
from .misconduct_politics import MisconductPoliticalBridge
__all__ += ["MisconductPoliticalBridge"]


# Evidence-based, read-only proposals to reassess NPC intentions after events.
from .goal_review import GoalReviewAction, GoalReviewEvaluator, GoalReviewPolicy, GoalReviewProposal
__all__ += ["GoalReviewAction", "GoalReviewEvaluator", "GoalReviewPolicy", "GoalReviewProposal"]


# Accepted emotional scars can inform, but never automatically change, identity proposals.
from .emotional_scar_identity import (
    EmotionalScarIdentityAdapter, ScarIdentityPolicy,
)
__all__ += ["EmotionalScarIdentityAdapter", "ScarIdentityPolicy"]


# Append-only NPC decisions on goal reassessment proposals, with canonical persistence.
from .goal_review_decisions import GoalReviewDecision, GoalReviewDecisionLedger
from .goal_review_decisions_save_state import GoalReviewDecisionSnapshot
__all__ += ["GoalReviewDecision", "GoalReviewDecisionLedger", "GoalReviewDecisionSnapshot"]


# Explicit world-event evidence can advance matching active NPC goals.
from .goal_events import GoalEventAdapter, GoalProgressPolicy, GoalProgressUpdate
__all__ += ["GoalEventAdapter", "GoalProgressPolicy", "GoalProgressUpdate"]


# Canonical component snapshots for NPC goals and goal-event replay protection.
from .goal_save_state import GoalBookSnapshot
from .goal_events_save_state import GoalEventReplaySnapshot
__all__ += ["GoalBookSnapshot", "GoalEventReplaySnapshot"]


# Gradual, individual-specific NPC identity evolution proposals.
from .identity_evolution import IdentityChangePolicy, IdentityChangeProposal, IdentityEvolutionEvaluator, NPCIdentityProfile
__all__ += ["IdentityChangePolicy", "IdentityChangeProposal", "IdentityEvolutionEvaluator", "NPCIdentityProfile"]


# Explicit, replay-safe NPC identity decisions and durable accepted trait changes.
from .identity_decisions import IdentityChangeDecision, IdentityDecisionLedger
from .identity_decisions_save_state import IdentityDecisionSnapshot
__all__ += ["IdentityChangeDecision", "IdentityDecisionLedger", "IdentityDecisionSnapshot"]


# Cognitive biases and temporary emotional-state appraisal remain separate from personality.
from .identity_context import (
    ContextualIdentityChange, IdentityCognitiveBiasRule, IdentityCognitiveContextInterpreter,
    IdentityEmotionRule, NPCCognitiveBiasProfile, NPCEmotionalState,
)
__all__ += [
    "ContextualIdentityChange", "IdentityCognitiveBiasRule", "IdentityCognitiveContextInterpreter",
    "IdentityEmotionRule", "NPCCognitiveBiasProfile", "NPCEmotionalState",
]


# Belief-conditioned interpretation remains separate from explicit acceptance.
from .identity_interpretation import (
    IdentityBeliefInterpreter, IdentityInterpretationRule, IdentityMemoryAssociation,
    IdentityRelationshipAssociation, IdentityPersonalityRule, NPCIdentityPersonality,
    NPCIdentityValues, IdentityValueRule,
    InterpretedIdentityChange,
)
__all__ += [
    "IdentityBeliefInterpreter", "IdentityInterpretationRule", "IdentityMemoryAssociation",
    "IdentityRelationshipAssociation", "IdentityPersonalityRule", "NPCIdentityPersonality",
    "NPCIdentityValues", "IdentityValueRule",
    "InterpretedIdentityChange",
]


# Event-driven transient emotion changes with deterministic decay and replay safety.
from .emotional_events import (
    EmotionalDecayRule, EmotionalEventRule, EmotionalRelationshipRule,
    EmotionalMemoryRule, NPCEmotionalEventLedger,
)
__all__ += ["EmotionalDecayRule", "EmotionalEventRule", "EmotionalRelationshipRule", "EmotionalMemoryRule", "NPCEmotionalEventLedger"]


# Deterministic observer-specific recall projections from immutable world events.
from .witness_recall import (
    RecallDetail, RecalledDetail, WitnessRecall, WitnessRecallAdapter,
    WitnessRecallProfile,
)
__all__ += [
    "RecallDetail", "RecalledDetail", "WitnessRecall", "WitnessRecallAdapter",
    "WitnessRecallProfile",
]

from .testimony import TestimonyDetail, TestimonyLedger, TestimonyRecord
__all__ += ["TestimonyDetail", "TestimonyLedger", "TestimonyRecord"]


# Deterministic comparison of independently recorded witness testimony.
from .testimony_analysis import InvestigationReport, TestimonyAnalyzer, TestimonyMatch
__all__ += ["InvestigationReport", "TestimonyAnalyzer", "TestimonyMatch"]


# Explicit conversion of investigation findings into observer-specific belief evidence.
from .testimony_beliefs import TestimonyBeliefAdapter, TestimonyEvidencePolicy, TestimonyEvidenceBatch
__all__ += ["TestimonyBeliefAdapter", "TestimonyEvidencePolicy", "TestimonyEvidenceBatch"]


# Read-only dialogue and investigation queries over observer-specific testimony beliefs.
from .testimony_belief_queries import TestimonyBeliefQuery, TestimonyBeliefQueryAdapter
__all__ += ["TestimonyBeliefQuery", "TestimonyBeliefQueryAdapter"]


# Read-only dialogue and investigation queries over observer-specific testimony beliefs.
from .testimony_belief_queries import TestimonyBeliefQuery, TestimonyBeliefQueryAdapter
__all__ += ["TestimonyBeliefQuery", "TestimonyBeliefQueryAdapter"]

# Deterministic follow-up proposals for uncertain or conflicting testimony.
from .testimony_followups import TestimonyFollowUp, TestimonyFollowUpPlan, TestimonyFollowUpPlanner
__all__ += ["TestimonyFollowUp", "TestimonyFollowUpPlan", "TestimonyFollowUpPlanner"]


# Replay-safe investigator inquiries and explicit witness responses.
from .testimony_inquiries import TestimonyInquiry, TestimonyInquiryLedger, TestimonyResponse
__all__ += ["TestimonyInquiry", "TestimonyInquiryLedger", "TestimonyResponse"]


# Caller-selected investigation proposals become durable questions.
from .testimony_inquiry_adapter import TestimonyInquiryAdapter
__all__ += ["TestimonyInquiryAdapter"]


# Canonical persistence for investigator inquiry and response history.
from .testimony_inquiry_save_state import TestimonyInquirySnapshot
__all__ += ["TestimonyInquirySnapshot"]


# Replay-safe bridge from answered inquiries into the shared testimony ledger.
from .testimony_materialization import TestimonyMaterializationAdapter
__all__ += ["TestimonyMaterializationAdapter"]


# Explicit inquiry-answer pipeline into testimony analysis and observer beliefs.
from .testimony_pipeline import InquiryInvestigationPipeline, InquiryInvestigationResult
__all__ += ["InquiryInvestigationPipeline", "InquiryInvestigationResult"]


# Deterministic NPC travel progression and canonical journey persistence.
from .travel import TravelJourney, TravelLedger, TravelTickAdapter, TravelTickResult
from .travel_save_state import TravelSnapshot
__all__ += ["TravelJourney", "TravelLedger", "TravelTickAdapter", "TravelTickResult", "TravelSnapshot"]


# Schedule-to-travel bridge for NPC routine destinations.
from .routine_travel import RoutineTravelAdapter, RoutineTravelRequest
__all__ += ["RoutineTravelAdapter", "RoutineTravelRequest"]


# Execute routine activities only after their routine-linked travel has arrived.
from .routine_arrival import RoutineArrivalAdapter, RoutineArrivalResult
__all__ += ["RoutineArrivalAdapter", "RoutineArrivalResult"]


# Authoritative location and road-edge presence, synchronized from travel.
from .presence import NPCPresence, PresenceLedger, PresenceTickAdapter
from .presence_save_state import PresenceSnapshot
__all__ += ["NPCPresence", "PresenceLedger", "PresenceTickAdapter", "PresenceSnapshot"]


# Presence-gated social encounters and their canonical replay persistence.
from .presence_encounters import PresenceEncounter, PresenceEncounterResult, PresenceEncounterLedger, PresenceSocialAdapter
from .presence_encounter_save_state import PresenceEncounterSnapshot
__all__ += ["PresenceEncounter", "PresenceEncounterResult", "PresenceEncounterLedger", "PresenceSocialAdapter", "PresenceEncounterSnapshot"]


# Physical presence and explicit observation opportunities gate witness eligibility.
from .presence_witnesses import PresenceWitnessAssessment, PresenceWitnessResolution, PresenceWitnessAdapter
__all__ += ["PresenceWitnessAssessment", "PresenceWitnessResolution", "PresenceWitnessAdapter"]


# Directional familiarity is derived from explicit exposure during confirmed encounters.
from .social_familiarity import (FamiliarityObservation, RecognitionAssessment,
                                 SocialFamiliarityLedger, PresenceFamiliarityAdapter,
                                 SocialFamiliaritySnapshot)
__all__ += ["FamiliarityObservation", "RecognitionAssessment", "SocialFamiliarityLedger",
            "PresenceFamiliarityAdapter", "SocialFamiliaritySnapshot"]


# Directional relationship facets with event-linked evidence and independent persistence.
from .social_relationships import (
    RELATIONSHIP_FACETS, RelationshipChange, RelationshipState,
    SocialRelationshipLedger, SocialRelationshipSnapshot,
)
__all__ += [
    "RELATIONSHIP_FACETS", "RelationshipChange", "RelationshipState",
    "SocialRelationshipLedger", "SocialRelationshipSnapshot",
]


# Observer-specific value, bias, and belief interpretation into relationship changes.
from .relationship_interpretation import (
    RelationshipInterpretationProfile, RelationshipInterpretationResult,
    NPCRelationshipInterpreter,
)
__all__ += [
    "RelationshipInterpretationProfile", "RelationshipInterpretationResult",
    "NPCRelationshipInterpreter",
]


# Canonical component persistence for transient NPC emotional event state.
from .emotional_events_save_state import EmotionalEventSnapshot
__all__ += ["EmotionalEventSnapshot"]


# Separate felt emotion, outward expression, and explicit decision influence.
from .emotional_regulation import (
    EmotionalDecisionAdapter, EmotionalDecisionInfluence, EmotionalDecisionRule,
    EmotionalExpression, EmotionalExpressionAdapter, EmotionalRegulationProfile,
)
__all__ += [
    "EmotionalDecisionAdapter", "EmotionalDecisionInfluence", "EmotionalDecisionRule",
    "EmotionalExpression", "EmotionalExpressionAdapter", "EmotionalRegulationProfile",
]


# Individual coping strategies, accumulated stress, exhaustion, and recovery.
from .emotional_stress import (
    CopingProfile, NPCStressLedger, StressAssessment, StressRecord,
)
__all__ += ["CopingProfile", "NPCStressLedger", "NPCStressSnapshot", "StressAssessment", "StressRecord"]

from .emotional_stress_save_state import NPCStressSnapshot
__all__ += ["NPCStressSnapshot"]


# Individualized, read-only behavioral effects of accumulated stress.
from .stress_adaptation import (
    CHANNELS as STRESS_ADAPTATION_CHANNELS, StressAdaptationProfile,
    StressBehaviorAdapter, StressBehaviorSignal,
)
__all__ += ["STRESS_ADAPTATION_CHANNELS", "StressAdaptationProfile", "StressBehaviorAdapter", "StressBehaviorSignal"]


# Event-sourced, owner-specific associative learning and conditioning persistence.
from .psychological_conditioning import (
    ConditionedResponse, ConditioningProfile, ConditioningRecord,
    NPCConditioningLedger, NPCConditioningSnapshot,
)
__all__ += [
    "ConditionedResponse", "ConditioningProfile", "ConditioningRecord",
    "NPCConditioningLedger", "NPCConditioningSnapshot",
]


# Explicit, context-sensitive activation of owner-specific learned associations.
from .psychological_triggers import (
    PsychologicalTrigger, PsychologicalTriggerAdapter, TriggerActivation,
)
__all__ += [
    "PsychologicalTrigger", "PsychologicalTriggerAdapter", "TriggerActivation",
]


# Observer-specific interpretation proposals from immutable world events.
from .psychological_interpretation import (
    EventInterpretationRule, LearningProposal, NPCEventInterpreter,
    NPCInterpretationProfile,
)
__all__ += [
    "EventInterpretationRule", "LearningProposal", "NPCEventInterpreter",
    "NPCInterpretationProfile",
]


# Read-only choice appraisal informed by owner-specific learned associations.
from .psychological_decisions import (
    ConditionedChoiceResult, ConditionedDecisionProfile,
    ConditionedDecisionResult, PsychologicalDecisionAdapter,
)
__all__ += [
    "ConditionedChoiceResult", "ConditionedDecisionProfile",
    "ConditionedDecisionResult", "PsychologicalDecisionAdapter",
]


# Explicit acceptance or rejection of observer-specific psychological learning.
from .psychological_learning_decisions import (
    PsychologicalLearningDecision, PsychologicalLearningDecisionLedger,
    PsychologicalLearningDecisionSnapshot,
)
__all__ += [
    "PsychologicalLearningDecision", "PsychologicalLearningDecisionLedger",
    "PsychologicalLearningDecisionSnapshot",
]


# Integrated social-belief and associative-conditioning choice appraisal.
from .integrated_decisions import (
    IntegratedChoiceResult, IntegratedDecisionResult,
    IntegratedPsychologicalDecisionAdapter,
)
__all__ += ["IntegratedChoiceResult", "IntegratedDecisionResult", "IntegratedPsychologicalDecisionAdapter"]


# Explicit, owner-specific cognitive dissonance and response history.
from .cognitive_dissonance import (
    CognitiveDissonanceLedger, CognitiveDissonanceSnapshot,
    DissonanceDecision, DissonanceInput,
)
__all__ += ["CognitiveDissonanceLedger", "CognitiveDissonanceSnapshot", "DissonanceDecision", "DissonanceInput"]


# Repeated unresolved dissonance can propose gradual identity change; acceptance stays explicit.
from .dissonance_identity import (
    DissonanceIdentityAssessment, DissonanceIdentityBridge, DissonanceIdentityRule,
)
__all__ += ["DissonanceIdentityAssessment", "DissonanceIdentityBridge", "DissonanceIdentityRule"]


# Observer-owned autobiographical history, forgiveness, and separate reconciliation.
from .npc_life_history import (
    AutobiographicalMemory, LifeHistorySnapshot, NPCLifeHistory, PersonalHistoryAction,
)
__all__ += ["AutobiographicalMemory", "LifeHistorySnapshot", "NPCLifeHistory", "PersonalHistoryAction"]


# Observer-specific autobiographical memory formation from witnessed world events.
from .npc_memory_formation import (
    AutobiographicalMemoryProfile, AutobiographicalMemoryRule,
    NPCAutobiographicalMemoryAdapter,
)
__all__ += [
    "AutobiographicalMemoryProfile", "AutobiographicalMemoryRule",
    "NPCAutobiographicalMemoryAdapter",
]


# Owner-scoped, cue-driven retrieval of autobiographical memories.
from .npc_memory_recall import (
    MemoryRecallProfile, MemoryRecallResult, MemoryRecallRule,
    NPCMemoryRecallAdapter, RecalledMemory,
)
__all__ += [
    "MemoryRecallProfile", "MemoryRecallResult", "MemoryRecallRule",
    "NPCMemoryRecallAdapter", "RecalledMemory",
]


# Append-only reinterpretation history over immutable autobiographical memories.
from .npc_memory_reflection import (
    MemoryReflectionLedger, MemoryReflectionSnapshot, MemoryReinterpretation,
)
__all__ += [
    "MemoryReflectionLedger", "MemoryReflectionSnapshot", "MemoryReinterpretation",
]

# Memory-grounded personality adaptation proposals; explicit identity decisions remain required.
from .personality_adaptation import (
    PersonalityAdaptationAdapter, PersonalityAdaptationAssessment,
    PersonalityAdaptationRule, PersonalityMemoryContribution,
)
__all__ += [
    "PersonalityAdaptationAdapter", "PersonalityAdaptationAssessment",
    "PersonalityAdaptationRule", "PersonalityMemoryContribution",
]

# Cue-triggered, memory-grounded emotional responses with explicit provenance.
from .emotional_memory import (
    EmotionalMemoryAdapter, EmotionalMemoryAssociation,
    EmotionalMemoryContribution, EmotionalMemoryProfile, EmotionalMemoryResponse,
)
__all__ += [
    "EmotionalMemoryAdapter", "EmotionalMemoryAssociation",
    "EmotionalMemoryContribution", "EmotionalMemoryProfile",
    "EmotionalMemoryResponse",
]

# Bounded, owner-specific influence of recalled autobiographical memories on choices.
from .memory_decisions import (
    MemoryChoiceAssociation, MemoryDecisionInfluence,
    MemoryDecisionInfluenceAdapter, MemoryDecisionProfile,
)
__all__ += [
    "MemoryChoiceAssociation", "MemoryDecisionInfluence",
    "MemoryDecisionInfluenceAdapter", "MemoryDecisionProfile",
]


# Personality-conditioned appraisal of cue-triggered emotional memories.
from .personality_emotion import (
    PersonalityConditionedEmotion, PersonalityEmotionAdapter,
    PersonalityEmotionContribution, PersonalityEmotionRule,
)
__all__ += [
    "PersonalityConditionedEmotion", "PersonalityEmotionAdapter",
    "PersonalityEmotionContribution", "PersonalityEmotionRule",
]


# Persistent, cue-triggered emotional scars with explicit recovery history.
from .emotional_scars import (
    EmotionalScar, EmotionalScarContribution, EmotionalScarResponse,
    NPCEmotionalScarLedger, ScarRecoveryRecord,
)
from .emotional_scars_save_state import EmotionalScarSnapshot
__all__ += [
    "EmotionalScar", "EmotionalScarContribution", "EmotionalScarResponse",
    "NPCEmotionalScarLedger", "ScarRecoveryRecord", "EmotionalScarSnapshot",
]


# Evidence-grounded scar proposals require explicit NPC acceptance or rejection.
from .emotional_scar_formation import (
    EmotionalScarDecision, EmotionalScarDecisionLedger, EmotionalScarDecisionSnapshot,
    EmotionalScarFormationAdapter, EmotionalScarFormationPolicy, EmotionalScarProposal,
)
__all__ += [
    "EmotionalScarDecision", "EmotionalScarDecisionLedger", "EmotionalScarDecisionSnapshot",
    "EmotionalScarFormationAdapter", "EmotionalScarFormationPolicy", "EmotionalScarProposal",
]


# Durable provenance for scar-informed identity proposals.
from .scar_identity_proposals import (
    ScarIdentityProposalEvidence, ScarIdentityProposalLedger, ScarIdentityProposalSnapshot,
)
__all__ += ["ScarIdentityProposalEvidence", "ScarIdentityProposalLedger", "ScarIdentityProposalSnapshot"]


# Scar-informed identity proposals remain read-only and require explicit decisions.
from .emotional_scar_identity import EmotionalScarIdentityAdapter, ScarIdentityPolicy
__all__ += ["EmotionalScarIdentityAdapter", "ScarIdentityPolicy"]


# Read-only join of experience, scar, proposal, NPC decision, and identity outcome.
from .identity_evolution_audit import IdentityEvolutionAuditRecord, IdentityEvolutionAuditTrail
__all__ += ["IdentityEvolutionAuditRecord", "IdentityEvolutionAuditTrail"]


# Accepted identity changes can prompt a separate, explicit NPC goal review.
from .identity_goal_alignment import (
    IdentityGoalAction, IdentityGoalAlignmentAdapter, IdentityGoalAlignmentPolicy,
    IdentityGoalReviewDecision, IdentityGoalReviewDecisionLedger,
    IdentityGoalReviewProposal, IdentityGoalReviewSnapshot,
)
__all__ += [
    "IdentityGoalAction", "IdentityGoalAlignmentAdapter", "IdentityGoalAlignmentPolicy",
    "IdentityGoalReviewDecision", "IdentityGoalReviewDecisionLedger",
    "IdentityGoalReviewProposal", "IdentityGoalReviewSnapshot",
]


# Replay-safe execution of one planned NPC action against live facts and resources.
from .action_execution import (ActionExecution, ActionExecutionLedger, ActionExecutionPolicy, ActionExecutionSnapshot, ActiveActionExecution)
__all__ += ["ActionExecution", "ActionExecutionLedger", "ActionExecutionPolicy", "ActionExecutionSnapshot", "ActiveActionExecution"]


# Explicit goal-aware action replanning over the persistent execution ledger.
from .npc_action_replanning import (NPCActionProgression, NPCActionReplanningCoordinator, NPCReplanningResult, NPCReplanningSnapshot)
__all__ += ["NPCActionProgression", "NPCActionReplanningCoordinator", "NPCReplanningResult", "NPCReplanningSnapshot"]


# Evidence-grounded NPC action outcome evaluation and bounded reliability learning.
from .action_evaluation import (
    ActionEvaluationSnapshot, ActionPlanEvaluationLedger, NPCActionEvaluation,
    NPCPlanEvaluation,
)
__all__ += ["ActionEvaluationSnapshot", "ActionPlanEvaluationLedger", "NPCActionEvaluation", "NPCPlanEvaluation"]


# Deterministic, evidence-grounded autonomous goal proposals and append-only lifecycle.
from .npc_goal_emergence import (
    GoalEmergenceRule, GoalLifecycleEvent, GoalLifecycleLedger,
    GoalTemplate, NPCGoalEmergence, NPCGoalProposal,
)
from .goal_lifecycle_save_state import GoalLifecycleSnapshot
__all__ += [
    "GoalEmergenceRule", "GoalLifecycleEvent", "GoalLifecycleLedger",
    "GoalLifecycleSnapshot", "GoalTemplate", "NPCGoalEmergence",
    "NPCGoalProposal",
]


# Accepted goal-review proposals are applied explicitly with stale-state checks and replay protection.
from .goal_review_application import (
    GoalReviewApplication, GoalReviewApplicationAdapter, GoalReviewApplicationLedger,
)
from .goal_review_application_save_state import GoalReviewApplicationSnapshot
__all__ += [
    "GoalReviewApplication", "GoalReviewApplicationAdapter",
    "GoalReviewApplicationLedger", "GoalReviewApplicationSnapshot",
]


# Reconsider abandoned goals only after explicit need and circumstance recovery evidence.
from .goal_recovery import (
    GoalRecoveryAdapter, GoalRecoveryEvaluator, GoalRecoveryProgression,
    GoalRecoveryProposal, GoalRecoveryReplanningAdapter, GoalRecoveryRule,
)
__all__ += [
    "GoalRecoveryAdapter", "GoalRecoveryEvaluator", "GoalRecoveryProgression",
    "GoalRecoveryProposal", "GoalRecoveryReplanningAdapter", "GoalRecoveryRule",
]


from .goal_execution_health import (GoalExecutionHealthEvaluator, GoalExecutionHealthProposal, GoalExecutionHealthRule)
__all__ += ["GoalExecutionHealthEvaluator", "GoalExecutionHealthProposal", "GoalExecutionHealthRule"]


# Explicitly adopt evidence-backed alternative intentions without overwriting the source goal.
from .goal_alternatives import (GoalAlternativeAdapter, GoalAlternativeEvaluator, GoalAlternativeProposal, GoalIntentionAssessment, GoalIntentionEvaluator)
__all__ += ["GoalAlternativeAdapter", "GoalAlternativeEvaluator", "GoalAlternativeProposal", "GoalIntentionAssessment", "GoalIntentionEvaluator"]


# Deterministic arbitration and explicit temporary commitment between active NPC goals.
from .goal_arbitration import (
    GoalArbitrationAssessment, GoalArbitrationCandidate, GoalArbitrationEvaluator,
    GoalArbitrationRule, GoalCommitment, GoalCommitmentAdapter, GoalCommitmentLedger,
)
from .goal_arbitration_save_state import GoalCommitmentSnapshot
__all__ += [
    "GoalArbitrationAssessment", "GoalArbitrationCandidate",
    "GoalArbitrationEvaluator", "GoalArbitrationRule", "GoalCommitment",
    "GoalCommitmentAdapter", "GoalCommitmentLedger", "GoalCommitmentSnapshot",
]


# Fresh goal reassessment with bounded incumbent-focus continuity.
from .goal_intention_continuity import GoalContinuityResult, GoalIntentionContinuityAdapter
__all__ += ["GoalContinuityResult", "GoalIntentionContinuityAdapter"]


# Resume interrupted NPC plans from their persisted execution cursor.
from .npc_action_replanning import NPCActionResumeResult
__all__ += ["NPCActionResumeResult"]


# Provenance-linked autobiographical memory for persistent NPC intentions.
from .goal_intention_memory import (
    GoalIntentionMemory, GoalIntentionMemoryAdapter,
    GoalIntentionMemoryLedger, GoalIntentionMemorySnapshot,
)
__all__ += [
    "GoalIntentionMemory", "GoalIntentionMemoryAdapter",
    "GoalIntentionMemoryLedger", "GoalIntentionMemorySnapshot",
]

from .goal_intention_recall import (
    GoalIntentionRecall, GoalIntentionRecallAdapter,
    GoalIntentionRecallEvidence, GoalIntentionRecallRule,
    GoalIntentionStrategicEvidence,
)
__all__ += [
    "GoalIntentionRecall", "GoalIntentionRecallAdapter",
    "GoalIntentionRecallEvidence", "GoalIntentionRecallRule",
    "GoalIntentionStrategicEvidence",
]
