# Population execution loop

`PopulationExecutionLoop` is the first population-level orchestration layer
above `SimulationTickCoordinator`. It composes the existing event-memory,
conversation and routine execution systems without duplicating their domain
logic.

## Tick phases

1. Capture and validate a stable, sorted NPC roster for the request.
2. Validate the selected routine-owner slice, disruption IDs and required
   outcome samples for all routine blocks active at the supplied minute.
3. Advance active multi-tick actions against checkpointable owner-scoped action
   facts/resources, then evaluate explicit `NPCDecisionContext` inputs in stable
   owner-ID order.
4. Revalidate and dispatch the first action step for each actionable decision.
   An owner with an active action or one completed earlier in the same tick is
   not dispatched again.
5. Advance travel and synchronize presence, then resolve evidence-backed
   encounters before event-memory and conversation processing.
6. Resolve due routines, apply configured economic effects for action completions,
   add explicit household obligations and settle requested obligations.
7. Return immutable phase outputs, including action dispatches and action
   advancement records.

Routine owners default to the full roster. A caller may pass `owner_ids` to
execute a deterministic subset, enabling an external population manager to
spread routine work across bounded slices. The result records the full roster
snapshot; it does not imply that all NPCs had a routine due in that slice.

## Replay and failure semantics

The loop rejects conflicting replay inputs and returns the original successful
result for identical in-memory replay. The underlying subsystems retain their
own replay ledgers. When a `PopulationTickTransactionCoordinator` is supplied,
the loop executes inside its durable prepare/commit boundary. All mutated
subsystems must be registered; the participant factory covers NPC state, world
events, social memory/conversations/trust/beliefs, routines, travel, presence,
encounters, action ledger and goals, action facts/resources, economics and
household obligations when configured. On failure, registered participants are
restored and derived per-tick caches are discarded. Without that coordinator,
the loop remains component-replay-safe but is not globally atomic.

## Intentional non-goals

The loop does not synthesize world facts, desired goal facts, event witnesses,
proximity, conversations, disruptions, travel routes or random samples. The caller must supply actual
observations and deterministic outcome samples. The loop dispatches and advances symbolic actions only when an
`NPCActionDispatchAdapter`, `ActionExecutionLedger` and `ActionWorldState` are
configured. It does not infer physical movement, world facts, resources or
real-world side effects.

## Example

```python
from simreality import (
    PopulationExecutionLoop,
    RoutineBook,
    RoutineExecutionLedger,
)

loop = PopulationExecutionLoop(coordinator, routine_book, routine_ledger)
result = loop.run_tick(
    tick=12,
    minute_of_day=500,
    npcs=npcs,
    event_ids=("event-at-tick-12",),
    conversations=(ConversationIntent("chat-12", "listener", "speaker"),),
    outcome_samples={"work-shift-12": 0.35},
)
```

Regression coverage: `tests/test_population_execution.py`.


## Spatial partitioning and population LOD

`PopulationSpatialScheduler` consumes a `PresenceLedger` plus an explicit
importance score for every scheduled owner. It partitions owners by their
authoritative symbolic current location (including the current route node for
travelling NPCs), then assigns FULL, STANDARD, BACKGROUND or DORMANT detail
under deterministic global budgets. Equal scores break by owner ID. It rejects
missing presence and conflicting tick replays rather than inventing a location.

The scheduler returns stable cell/LOD slices and the selected/deferred owner
sets. Pass `selected_owner_ids` to `PopulationExecutionLoop.run_tick` as
`owner_ids` to bound routine execution. LOD is a scheduling decision only:
the caller remains responsible for selecting which subsystems run at each
detail tier.

## Validated action dispatch

`ActionWorldState` owns per-owner mutable fact sets and resource dictionaries
and exposes a versioned JSON checkpoint. Restore mutates existing nested sets
and dictionaries in place, preserving references held by action systems. The
transaction participant factory can register it as `action_world_state`.

`NPCActionDispatchAdapter` dispatches the first plan step after live
precondition/resource validation. Existing active actions advance once per
population tick; multi-tick policies retain reservations until completion or
interruption. An owner cannot start a second action while one is active, nor
restart the same action in the tick in which it completes. Completion mutates
world facts/resources, records the world event and applies configured goal
progress through `ActionExecutionLedger`. The population loop exposes action
advancement and dispatch records and sends newly completed actions to the
economic adapter in the same tick.

Both adapters are deterministic and reject conflicting same-tick replay.
Neither adapter creates coordinates, travel budgets, social encounters,
economic balances or world facts.


## Travel and presence integration

When a `TravelTickAdapter` and `PresenceTickAdapter` are supplied together,
`PopulationExecutionLoop.run_tick` now requires explicit owner travel budgets.
It advances the travel ledger, materializes arrival/presence world events, and
synchronizes the authoritative presence ledger before the social/event-memory
phase. The returned `PopulationTickResult` includes the travel result and
presence records. Closed edges and time multipliers are explicit tick inputs
and participate in population replay signatures.

Encounter creation remains evidence-gated: callers must supply explicit
opportunity evidence to `PresenceSocialAdapter`. Merely sharing a district or
route node does not create a social encounter.

## Subsystem LOD policies

`PopulationLODPolicy` resolves which subsystems are due at a given tick for
each LOD tier. The default policy keeps travel active at every tier, reduces
social, memory, economy and decision cadence for background NPCs, and disables
those high-detail systems for dormant NPCs. These are execution-policy
decisions, not silent changes to simulation facts. The scheduler returns the
tier for each owner; the runtime integrator must consult `due_subsystems`
before invoking each subsystem.

## Household economics

`EconomicLedger` provides owner-scoped accounts and replay-safe, balanced
double-entry transfers. `HouseholdLedger` records explicit obligations and
settles them through that same ledger. `EconomicActionAdapter` applies a
configured account transfer only for a completed `ActionExecution`; it does
not infer wages, purchases, prices, inventory quantities, or obligations from
action names. Configure policies with real account IDs and explicit amounts.
The ledger supports canonical JSON snapshots for persistence. Multiple configured
transfers may be applied atomically for one action (for example, gross wages and
payroll withholding); debit totals are preflighted before any transfer is posted.
`HouseholdActionAdapter` can also create deterministic obligations from completed
actions with explicit household/account IDs, amounts and due-tick offsets. The
population transaction factory checkpoints both adapter replay indexes alongside
the economic and household ledgers.

## Transaction boundary status

A durable transaction is available when explicitly configured. It is opt-in
and only protects state represented by registered participants. Use
`build_population_transaction_participants` with the same live roster,
coordinator, ledgers and adapters used by the loop; include `action_ledger` and
`action_world_state` when action dispatch is enabled. External mutable objects
not registered as participants are outside the rollback guarantee. The local
JSON journal uses atomic replacement and fsync, but multi-process locking and a
production shared-storage backend remain outstanding.


Explicit encounter evidence can also be passed as
`PresenceEncounterIntent` values when a shared `PresenceSocialAdapter` is
configured. The loop synchronizes travel-derived presence first, then asks the
adapter to validate the supplied opportunity against both NPCs' current
physical location. Valid encounter events are included in the same tick's
selected event IDs, allowing the social memory phase to process them. A false
opportunity creates no encounter. This remains caller-evidence-driven; the
loop does not infer line of sight, attention, or social intent.


## Durable whole-tick transaction boundary

`PopulationTickTransactionCoordinator` provides the enclosing transaction boundary for population execution. Configure it on `PopulationExecutionLoop` and register a `TransactionParticipant` for every mutable subsystem that can participate in the tick.

The loop validates participant coverage at construction. The required names are `npcs`, `world_events`, `event_memory`, `social_conversations`, `social_beliefs`, `social_trust`, `routine_book`, and `routine_executions`; configured travel/presence add `travel` and `presence`, encounter integration adds `encounters`, economic action effects add `economics` and `economic_actions`, and household settlement adds `households`. Supplying completed action execution records additionally requires `action_executions`.

A participant supplies two operations:
- `capture() -> str`: return a complete canonical JSON checkpoint of domain state and replay/idempotency indexes.
- `restore(checkpoint_json)`: restore exactly that checkpoint.

The participant set must include, when configured: the NPC collection (including memories and mutable beliefs), world event ledger, event-memory adapter, social conversation adapter and belief/trust ledgers, travel ledger, presence ledger, encounter ledger, routine book/execution ledger, action execution ledger, economic ledger/action adapter, and household ledger. Shared state must be represented once or restored in an order that preserves shared object identity. Checkpoint callbacks should use each subsystem's versioned save-state codec rather than serializing arbitrary object internals.

The coordinator writes and fsyncs a `prepared` journal record before invoking the tick. On success it captures all post-tick participant checkpoints and the canonical result payload, then atomically replaces and fsyncs the journal with `committed`. On an exception it restores participants in reverse registration order and durably marks the transaction aborted. On startup it restores the pre-tick checkpoints for interrupted `prepared` records, and restores post-tick checkpoints for committed records.

A committed replay verifies the durable request signature, restores the committed post-state, and invokes the population operation again. Component replay indexes must therefore be included in participant checkpoints so this second invocation reconstructs the original typed result without applying effects twice. Conflicting requests for an already journaled tick are rejected.

`PopulationTickResult` now carries economic transfers and household settlements when explicit completed action executions and settlement IDs are supplied. These effects run inside the same operation callback and therefore share the same rollback/commit boundary provided the economic and household ledgers are registered as transaction participants.

The transaction coordinator is opt-in for compatibility. A loop without a configured coordinator retains its previous component-level guarantees only; it must not be described as whole-tick atomic. The journal is a local durable file and assumes a single writer process. Multi-process execution requires an external transactional store or an exclusive process lock. Schema migrations must be versioned before changing the journal format.


### Concrete checkpoint participant registration

Use `build_population_transaction_participants(...)` to bind the existing versioned save-state codecs to live objects. It creates participants for NPC state, world events, event-memory replay, social conversation replay, social trust, social beliefs, routine definitions and routine execution history; optional travel/presence, encounters, economics, economic-action replay, household obligations and action execution history are included when their live adapters are supplied. If the action ledger is connected to a `GoalBook`, the builder also registers `action_goals` so action-driven goal progress is rolled back with the execution record.

The builder restores mutable ledgers in place, preserving references held by adapters. Register order is intentional: world events precede action execution restoration, social trust precedes social beliefs, and economics precedes economic-action replay restoration. The NPC mapping and its instances must remain stable for the coordinator lifetime; changing the roster between durable ticks is rejected during restore.

The NPC checkpoint currently follows `NPCCollectionSnapshot` schema version 1 and therefore covers the core NPC model fields and witnessed memories represented by that codec. Any newly introduced mutable NPC field must be added to that codec before it can be claimed as transactionally protected. External mutable stores, planner/goal state, and other runtime-owned state must have their own participant before whole-tick atomicity can be claimed for them.


The outer transaction wrapper also discards the current tick's in-memory orchestration replay entries when rollback occurs. This is essential: otherwise `SimulationTickCoordinator` could return a cached result after its underlying participant state had been restored to pre-tick state, silently skipping the effects on retry. The action execution participant is available through the checkpoint builder; pass the live `ActionExecutionLedger` when action execution state is part of the population transaction. Its world-event ledger must be the same object used by the population coordinator.
