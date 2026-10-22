"""Simulation core for the Simulated Reality Engine.

Engine-independent simulation services, with Python as a reference layer for
portable C++ systems. Nothing here may depend on Unreal objects or the game
thread; keeping that boundary honest makes the systems testable in CI.
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
from .information import ClaimResult, InformationClaim, InformationKind, InformationLedger
from . import districts, fixers, justice, reputation, trauma

__all__ = [
    "ActionTag", "AgeBand", "Description", "District", "NPC", "NPCMemory",
    "TELEPHONE_THRESHOLD", "TraumaLevel", "Weather", "LAMBDA_BASE",
    "decay_constant", "retention_after", "sweep", "visibility_modifier",
    "BehaviourDecision", "IllegalBranch", "desperation_index", "evaluate",
    "apply_district_pressure", "Conversation", "Rumour", "converse",
    "police_response", "retell", "ClaimResult", "InformationClaim",
    "InformationKind", "InformationLedger", "districts", "fixers", "justice",
    "reputation", "trauma",
]

# Persistent health, social obligations, and finite campaign-life lifecycle.
from .health_life import (
    CampaignLife, CharacterHealth, HealthCondition, LifeState, PersistentWorld,
    SocialObligation, WorldArchive,
)

__all__ += [
    "CampaignLife", "CharacterHealth", "HealthCondition", "LifeState",
    "PersistentWorld", "SocialObligation", "WorldArchive",
]

from .campaign import ArchivedTimeline, LifeItselfCampaign

__all__ += ["ArchivedTimeline", "LifeItselfCampaign"]

# Daily medical, economic, relationship, bereavement and ghost decision services.
from .life_simulation import (
    DailyLifeRecord, GhostDecision, GhostWindow, LifeSimulation, PersonProfile,
    RecoveryEstimate, ResponsibilityOutcome, ResponsibilityResolution, Treatment,
)

__all__ += [
    "DailyLifeRecord", "GhostDecision", "GhostWindow", "LifeSimulation",
    "PersonProfile", "RecoveryEstimate", "ResponsibilityOutcome",
    "ResponsibilityResolution", "Treatment",
]
