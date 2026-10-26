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
