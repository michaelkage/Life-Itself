# Population execution loop

`PopulationExecutionLoop` is the first population-level orchestration layer
above `SimulationTickCoordinator`. It composes the existing event-memory,
conversation and routine execution systems without duplicating their domain
logic.

## Tick phases

1. Capture and validate a stable, sorted NPC roster for the request.
2. Validate the selected routine-owner slice, disruption IDs and required
   outcome samples for all routine blocks active at the supplied minute.
3. Run the event-memory and conversation phase through
   `SimulationTickCoordinator.step`.
4. Resolve due routines through `SimulationTickCoordinator.execute_routines`
   and the existing `RoutineTickAdapter` / `RoutineExecutionLedger`.
5. If an `NPCDecisionCycle` is configured, evaluate only the NPCs with explicit
   `NPCDecisionContext` inputs in stable owner-ID order. These are read-only
   proposals; no plan action is dispatched.
6. Return an immutable result containing decisions, the social phase, routine
   executions and roster IDs.

Routine owners default to the full roster. A caller may pass `owner_ids` to
execute a deterministic subset, enabling an external population manager to
spread routine work across bounded slices. The result records the full roster
snapshot; it does not imply that all NPCs had a routine due in that slice.

## Replay and failure semantics

The loop rejects conflicting replay inputs and returns the original successful
result for identical in-memory replay. The underlying social and routine phases
also have their own replay ledgers.

This composition is deliberately **phase-atomic, not globally atomic**. The
coordinator commits event memory/conversations before the routine ledger is
updated. Routine inputs are preflighted before that commit; if an unexpected
routine-ledger failure occurs afterward, the social phase remains committed.
Retrying the exact same tick inputs reuses the coordinator's result and retries
the routine phase. A durable whole-world transaction still belongs in the
world checkpoint/transaction boundary.

## Intentional non-goals

The loop does not synthesize world facts, desired goal facts, event witnesses,
proximity, conversations, disruptions, travel routes or random samples. The caller must supply actual
observations and deterministic outcome samples. Decision proposals are connected to the loop, but it does not yet execute
symbolic NPC plans or dispatch physical actions; those remain separate
integration work.

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

`NPCActionDispatchAdapter` converts actionable `NPCDecision` proposals into
the first active action in each plan. It requires live, owner-scoped mutable
world-fact and resource maps. `ActionExecutionLedger.start` rechecks action
preconditions and unreserved resource costs before creating an active
execution and journal event. Missing state, stale preconditions and insufficient
resources reject dispatch. Only one plan step is started per NPC per tick;
subsequent steps require fresh live validation. Non-actionable or already
satisfied decisions are explicitly reported as not dispatched.

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
The ledger supports canonical JSON snapshots for persistence.

## Transaction boundary status

Travel, presence, social, routine, action, and economic ledgers retain their
existing component-level replay and checkpoint behavior. Population orchestration
now orders travel/presence before social work, but it does **not yet provide a
single rollback transaction across all these ledgers and mutable NPC state**.
A failure after a committed travel or social phase can therefore leave earlier
phases committed. Whole-tick atomicity remains an explicit outstanding task;
do not treat per-component replay as a substitute for it.
