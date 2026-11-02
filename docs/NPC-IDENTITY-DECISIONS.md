# NPC identity decisions and persistence

Identity evolution is a two-stage process. `IdentityEvolutionEvaluator` produces deterministic proposals from configured event policies; it does not mutate an NPC. `IdentityDecisionLedger` records the NPC's explicit acceptance or rejection.

## Decision semantics

- A decision records the source event, NPC, policy, trait axis, before/proposed values, evidence strength, role, decision tick, rationale, and acceptance.
- An accepted decision applies the proposed trait value to the ledger's durable identity state.
- A rejected decision remains in the append-only history and leaves the trait unchanged.
- A proposal is identified by `(event_id, npc_id, policy_id)`; it can receive only one decision.
- Repeating the exact same decision ID and content is idempotent. Reusing an ID with different content, or deciding the same proposal again, is rejected.
- Accepted values must continue from the current trait value. This prevents an old proposal from overwriting later identity evolution.

## Saving and replay

`IdentityDecisionSnapshot` stores the initial profile state, sensitivity values, and ordered decision history. Restore rebuilds the current traits by replaying accepted decisions, then verifies the rebuilt state against the saved state. This means accepted changes survive save/close/reopen while rejected decisions remain available as history.

`SimulationWorldCheckpoint.capture(..., identity_decisions=ledger)` includes this snapshot in the composite checkpoint. Restore exposes it as `RestoredSimulation.identity_decisions`. Checkpoint validation requires every decision's source event to exist, precede the decision, match the recorded participant/witness role, and not occur after the checkpoint tick.

The identity ledger is deliberately separate from the general NPC entity model for now. Systems that need an NPC's current identity should read `ledger.traits_for(npc_id)`; the evaluator can be constructed from `ledger.profiles()` when reassessing future events. This keeps the change explicit and prevents silent mutation by event replay.
