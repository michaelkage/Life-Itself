# NPC Identity Evolution

This module proposes gradual, individual-specific changes to long-term NPC traits.

## Model

- `NPCIdentityProfile` stores configurable trait axes in [-1, 1], such as social trust, risk tolerance, curiosity, independence, ambition, or institutional confidence. Per-axis sensitivities in [0, 2] allow the same event to affect different NPCs differently.
- `IdentityChangePolicy` maps a world-event type to a signed trait shift. A policy can use an event attribute as an evidence-strength value, set a minimum strength, cap its per-event effect, and include or exclude witnesses.
- `IdentityEvolutionEvaluator` returns proposals in deterministic order. It never mutates profiles. Trait values remain bounded and each event's effect is capped.

## Design boundary

The system does not assign objective good/bad labels, infer personality from an event name, or conflate temporary emotion with long-term identity. Repeated experiences accumulate only when a higher-level simulation component explicitly accepts and applies proposals. This keeps identity change inspectable and compatible with morally ambiguous choices.

## Emotional scar evidence

`EmotionalScarIdentityAdapter` maps an already accepted, still-active emotional scar into a bounded identity-change proposal. A `ScarIdentityPolicy` must explicitly match the scar's emotion axis and exact cue ID to an identity trait axis, and supplies the signed per-severity effect, minimum remaining severity, maximum change, and witness eligibility.

The adapter samples scar severity after natural decay and recorded recovery, checks that the source event exists and that the NPC was a participant or eligible witness, and uses the NPC's current identity profile and axis sensitivity. Each scar receives a distinct derived policy key so multiple accepted scars from one event can be considered independently. Missing profiles, source events, or trait axes are neutral and produce no proposal.

This is proposal generation only. It does not mutate the identity ledger. The NPC must still explicitly accept or reject the proposal through `IdentityDecisionLedger`; rejection remains history and leaves the trait unchanged. An accepted scar therefore never automatically changes personality or identity.

Example:

```python
policy = ScarIdentityPolicy(
    "fear-to-trust", "fear", "crowded-room", "social_trust",
    delta_per_severity=-0.05, minimum_severity=0.2,
)
proposals = EmotionalScarIdentityAdapter.propose(
    scar_ledger, identity_ledger, world_events, (policy,), tick=120,
)
# Each proposal still requires an explicit NPC decision.
```

The adapter lives in `simreality/emotional_scar_identity.py`. Tests: `tests/test_identity_decisions.py`.
