# Observer-specific NPC event interpretation

The authoritative world-event journal records what happened. It does not decide
what every NPC thinks happened. This module provides authored interpretation
rules that can turn witnessed facts into individual learning proposals.

## Individual interpretation

Each `NPCInterpretationProfile` belongs to one NPC and contains rules matching
an exact event type plus optional exact attribute constraints. A matched rule
supplies a learned cue, signed outcome, intensity, and learning mode.

Different NPCs can interpret the same event differently. One may interpret a
raised voice as a warning; another may interpret the same meeting as evidence
that management is enforcing fair standards. These interpretations are
subjective rules, not changes to the underlying event.

Only listed participants and witnesses receive proposals. This checks journal
membership, not whether an NPC noticed, understood, or remembered the event;
the caller remains responsible for supplying appropriate observation records.

## Proposal boundary

`NPCEventInterpreter.interpret` returns deterministic `LearningProposal`
values. It does not mutate the conditioning ledger. The simulation can review,
filter, or reject a proposal before explicitly applying it through
`NPCConditioningLedger.learn`. Stable source event IDs support replay
protection at the learning ledger.

Profiles are authored configuration and should be restored by world setup.
Proposals are transient; accepted learning records and associations are saved
through the conditioning checkpoint integration.

Tests: `tests/test_npc_event_interpretation.py`.
