# NPC Social Trust Ledger

`simreality/social_trust.py` models trust separately for each observer-target pair. One NPC can trust a person while another distrusts the same person.

Each interaction has a stable ID, observer, target, direction, strength, tick, and context. Trust starts from a pair-specific prior or 0.5. A positive interaction moves trust toward 1; a negative interaction moves it toward 0, by a fraction equal to strength. Events replay in `(observed_tick, interaction_id)` order. Identical duplicate IDs are idempotent; conflicting reuse is rejected.

`SocialTrustState.source_reliability` exposes trust as an optional input to belief updates. This is an explicit modeling choice, not objective witness accuracy. A separate policy may account for expertise, incentives, familiarity, or context.

Boundaries:

- Trust does not decay merely because time passes.
- The caller supplies an interaction's direction and strength.
- The ledger does not automatically change global reputation, goals, or world state.
- Snapshots and event replay are deterministic.
