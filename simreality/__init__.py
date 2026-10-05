"""Simulation core for the Simulated Reality Engine.

Three sub-engines, pure Python, no engine dependency:

    decay      -- exponential memory decay with correct sign handling
    gossip     -- rumour mutation through social contact
    ecosystem  -- desperation index and behavioural status flips

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
]