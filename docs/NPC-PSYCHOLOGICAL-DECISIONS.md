# Conditioning-aware NPC decision appraisal

This module connects explicit associative learning to candidate-choice appraisal.
An NPC's learned associations can influence what they consider attractive or
aversive without directly commanding an action.

## Authored inputs

Each `ConditionedDecisionProfile` belongs to one NPC and defines a signed
sensitivity for each cue. The decision caller supplies cue exposure per candidate
choice. Exposure is bounded from zero to one and represents the caller's
contextual estimate that the option would involve that cue.

For each cue:

`conditioned contribution = learned association × exposure × cue sensitivity`

The learned association is owner-specific and bounded [-1, 1]. Sensitivity may
also be positive or negative: an NPC can find a learned warning motivating,
or deliberately seek a situation they associate with safety or reassurance.

## Ranking and boundaries

`PsychologicalDecisionAdapter.rank` adds these contributions to the existing
value-based appraisal, then sorts by total score with stable choice-ID tie
breaking. Results retain the base score and per-cue contributions for
inspection.

The adapter is deterministic and read-only. It does not infer which cues an
option contains, alter memories, change beliefs, or execute the preferred
choice. The caller must supply candidate options and explicit cue exposures.
Different NPCs can therefore rank the same options differently from their
individual histories and authored sensitivities.

This adapter uses the existing persisted conditioning ledger; it introduces no
new checkpoint section. Decision profiles and option exposure mappings are
authored/runtime inputs and should be reconstructed by world setup.

Tests: `tests/test_psychological_decisions.py`.
