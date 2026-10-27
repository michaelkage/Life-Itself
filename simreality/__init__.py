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
