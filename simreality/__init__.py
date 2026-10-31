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
