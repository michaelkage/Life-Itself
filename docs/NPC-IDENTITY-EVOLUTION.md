# NPC Identity Evolution

This module proposes gradual, individual-specific changes to long-term NPC traits.

## Model

- `NPCIdentityProfile` stores configurable trait axes in [-1, 1], such as social trust, risk tolerance, curiosity, independence, ambition, or institutional confidence. Per-axis sensitivities in [0, 2] allow the same event to affect different NPCs differently.
- `IdentityChangePolicy` maps a world-event type to a signed trait shift. A policy can use an event attribute as an evidence-strength value, set a minimum strength, cap its per-event effect, and include or exclude witnesses.
- `IdentityEvolutionEvaluator` returns proposals in deterministic order. It never mutates profiles. Trait values remain bounded and each event's effect is capped.

## Design boundary

The system does not assign objective good/bad labels, infer personality from an event name, or conflate temporary emotion with long-term identity. Repeated experiences accumulate only when a higher-level simulation component explicitly accepts and applies proposals. This keeps identity change inspectable and compatible with morally ambiguous choices.

## Current limitation

The proposal layer is not yet connected to a persistent identity state or an acceptance ledger. Those are separate integration steps; a proposal alone does not mean an NPC has changed.
