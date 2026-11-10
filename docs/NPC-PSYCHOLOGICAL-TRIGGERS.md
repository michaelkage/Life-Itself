# Context-sensitive psychological triggers

This module activates learned associations only when an explicitly observed cue
and authored context conditions match an NPC-specific trigger definition.

## Trigger definitions

A `PsychologicalTrigger` identifies:
- its owner NPC
- a canonical learned cue
- optional literal aliases for the cue
- context tags that must all be present
- context tags that must not be present

The caller supplies observed cues and context tags. No geometry, hearing,
attention, identity, intent, or threat is inferred. For example, an NPC may
associate raised voices with avoidance specifically in a workplace, while an
explicit trusted-friend context can block that trigger.

## Output and decision boundary

`PsychologicalTriggerAdapter.evaluate` returns sorted activation records with
the matching cue, satisfied context, and the NPC's conditioned response.
Associations remain owner-specific: the same cue may produce avoidance for one
NPC and approach for another.

Evaluation is deterministic and read-only. It does not execute a reaction,
change trust, rewrite memory, or select an action. Decision systems can combine
the activation with current stress, beliefs, goals, obligations, and other
contextual evidence.

Trigger definitions are authored configuration and should be supplied again
after loading. The learned associations and their event history are persisted
by `NPCConditioningSnapshot` and the composite world checkpoint.

Tests: `tests/test_psychological_triggers.py`.
