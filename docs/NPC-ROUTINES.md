# Persistent NPC Routines — First Implementation Slice

**Status:** Python reference implementation includes canonical schedule persistence, an idempotent execution ledger, a deterministic tick adapter, and an explicit routine-execution phase on `SimulationTickCoordinator`. Callers run the ordinary world tick first, then call `execute_routines` for that latest tick with a schedule, ledger, minute, disruptions, and outcome samples. Schedules and execution history can be included in `SimulationWorldCheckpoint`. This is an explicit two-phase API, not an automatic routine call inside `step`; callers must pass the same ledger into checkpoint capture. NPC memory associations still need to be translated into explicit disruptions. Route planning and deterministic graph-based travel progression now have a Python reference implementation; composite checkpoint integration and C++ runtime integration remain pending.

## Design contract

A routine is an intention, not a teleport command. `RoutineBlock` says what an NPC planned to do, where, and during which part of a day. It does not prove they arrived or that the destination is available. The resolver returns a separate `RoutineResolution` describing intended and actual activity/location, outcome, delay, and the disruption records considered.

The module is engine-independent and does not read wall-clock time or global random state. Uncertain outcomes use an explicit `outcome_sample` supplied by the caller's seeded simulation stream. Reusing the same block, minute, disruptions, and sample yields the same result. Disruptions are processed in stable ID order.

## First-class disruptions

`RoutineDisruption` can represent traffic, weather, alarm/phone failure, low motivation, unexpected events, illness, location avoidance, or a social obligation. A disruption can cause a delay, redirect an NPC to a fallback activity/location, or cause the planned activity to be missed. The caller supplies severity and timing; the module does not fabricate weather, traffic, phone state, or emergencies.

Examples:
- A dead phone battery means an alarm does not ring; the NPC wakes late and may call work, arrive late, or miss the shift.
- Bad traffic makes an NPC late. A sufficiently long delay can cause a missed appointment or a fallback.
- A storm can change a work shift into work-from-home if the NPC/job scenario supports it.
- After an assault or accident at a street, an NPC's retained memory can be translated into a location-avoidance disruption. Avoidance is a personal response, not a global road closure.
- A low-motivation day can cause a delay or fallback without making every NPC unreliable.

## Uncertainty and fairness

The outcome is not encoded as a public percentage forecast. The caller draws a sample from the simulation's deterministic random stream; the resolver compares that sample to each relevant disruption's severity. A stable seed makes a replay identical, while different seeds can produce different histories. No option is guaranteed by the routine alone. Scenario rules should still preserve ordinary baseline functionality: a shop may usually have stock, but stock is state and may run out; a business can open late if its owner is delayed.

The `RoutineBookSnapshot` codec persists intended routine blocks and validates schema, canonical ordering, and overlap constraints. `RoutineExecutionLedger` records a caller-named execution ID, minute, complete disruption inputs, outcome sample, and exact resolution. Reusing the same execution ID and inputs is idempotent; reusing it with conflicting inputs or outcomes is rejected. `RoutineExecutionSnapshot` canonically persists this history, and `SimulationWorldCheckpoint` can store both the schedule and execution ledger. Checkpoint capture requires the execution records to reference routine IDs in that schedule. The ledger is currently standalone: it is not automatically invoked by the world tick coordinator, and it does not generate disruptions from NPC memories on its own. This first slice is intentionally modest. It does not yet simulate routes, calculate traffic from vehicles, derive disruption probability from a phone's battery, generate schedules for every citizen, or execute movement. Those require world state and an integrated scheduler.

## API sketch

```python
from simreality.routines import RoutineBook, RoutineBlock

book = RoutineBook([
    RoutineBlock("shift-12", "npc-12", "work", "bakery", 8 * 60, 16 * 60)
])
block = book.for_period("npc-12", 9 * 60)[0]
resolution = book.resolve(block, 9 * 60, disruptions, outcome_sample=seeded_sample)
```

## Regression coverage

`tests/test_routine_save_state.py` covers canonical schedule JSON round trips and rejects malformed, overlapping, or non-canonical schedules. `tests/test_routine_execution.py` covers idempotent executions, conflicting ID reuse, deterministic input ordering, and exact outcome persistence. `tests/test_world_checkpoint.py` covers optional schedule and execution-history integration. `tests/test_routines.py` covers non-guaranteed attendance, alarm/phone failure, traffic, weather, low motivation, location avoidance, stable replay under reordered inputs, overlap validation, and NPC-independent routines.


## Personal memory-driven avoidance

`MemoryRoutineAdapter` is the first bridge from existing NPC memories to routine disruptions. It requires an explicit `MemoryLocationAssociation`: the memory index, location, optional alternate location, and association scale. This explicit link is necessary because the current `NPCMemory` record contains the witnessed target and action but does not contain a location. The adapter never infers a location from a crime tag, identity, or neighbourhood.

For a linked memory, its current retention is multiplied by the association scale. Associations below the caller's threshold do not contribute. Multiple linked memories at the same location compound deterministically into one `LOCATION_AVOIDANCE` disruption, with a stable ID and optional alternative location. Different NPC memory retention can therefore produce different outcomes for the same location. The rule is a transparent simulation heuristic, not a claim that all people respond to frightening events in the same way.

The caller still supplies the time window and decides when the resulting disruption is relevant. This adapter does not autonomously discover where an event happened, modify the routine schedule, generate random samples, or route around a real road graph. For save/load replay, persist the explicit associations and pass the derived disruptions into `RoutineExecutionLedger`; the execution ledger preserves the exact disruption inputs and resolved result.


## Explicit routine tick adapter

`RoutineTickAdapter.execute_due` bridges schedule definitions to the execution ledger for one caller-supplied tick ID and minute of day. It selects active blocks in stable routine-ID order, filters the explicit disruption list to each routine owner's NPC, and requires a caller-supplied outcome sample for every active routine. Execution IDs are formed from the tick ID and routine ID, so retries with the same inputs return the stored record and conflicting inputs are rejected by the ledger.

This is a composable adapter, not yet an automatic extension of `SimulationTickCoordinator`. The world-tick caller remains responsible for providing the tick ID, simulation minute, disruption events, and deterministic samples from its own seeded stream. No wall clock, global random generator, travel graph, or inferred event is introduced. An optional owner filter supports bounded updates; all active routines for selected owners must still have explicit samples.


## Coordinator integration boundary

After `SimulationTickCoordinator.step(tick, ...)` completes, the caller can run
`coordinator.execute_routines(tick, minute_of_day, book, ledger, ...)`. It only
accepts the latest completed world tick, preventing routine outcomes from being
inserted into an older part of the timeline after later ticks have run. It
returns the ledger's canonical `RoutineExecution` records. Execution IDs use
`{tick}:{routine_id}`; repeated calls with identical inputs reuse stored
results, and conflicting requests are rejected.

This is deliberately a named phase rather than silently running routines in
`step`: simulation time-of-day, disruption generation, and seeded outcome
samples belong to the world driver. Persist the same `RoutineBook` and
`RoutineExecutionLedger` in `SimulationWorldCheckpoint` alongside coordinator
history. The checkpoint preserves routine execution results; the routine phase
is not yet represented as a separate field in `SimulationTickResult`, so the
world driver should treat its returned execution tuple as part of its tick
record. Full atomic checkpointing across concurrent component updates remains
outside this implementation slice.


## Routine outcomes on the shared world timeline

`RoutineWorldEventAdapter` materializes each resolved execution as a canonical
`routine_execution` event at an explicit world tick. The event records the
owner, intended and actual activity/location, outcome, delay, reason, and
disruption IDs. Other adapters can then consume it through the existing world
event journal, including witness-memory and social interpretation systems.

Witnesses are never inferred from the routine itself: the world driver may pass
a per-execution witness list only when visibility or hearing has been established
by other world state. The adapter does not move NPCs, decide whether a manager
reacts, change workplace state, or create secondary consequences. Replaying the
same execution at the same tick is idempotent; reusing its event ID at a
different tick conflicts and is rejected. Regression coverage is in
`tests/test_routine_world_events.py`.


## Explicit routine consequences

`RoutineConsequenceAdapter` applies location/activity-specific `RoutineImpactPolicy`
rules to routine events already in the world journal. A configured workplace may
emit a late-arrival event only when delay exceeds its tolerance; a configured
appointment provider may emit a missed-appointment event. Policies can disable
either effect, and no policy means no consequence is invented. This is a
transparent rule layer, not a complete employer, clinic, or relationship AI.
Consequence IDs are derived from the source event and policy, so identical
retries are idempotent. Tests live in `tests/test_routine_consequences.py`.


## Persistent institution-facing records

`RoutineInstitutionLedger` accumulates explicit `workplace_late_arrival` and
`appointment_missed` consequence events into per-person, per-institution
records. It tracks late-arrival count, missed-appointment count, total recorded
delay, and the last event tick. Records are separate for each institution and
person, and reapplying the same event does not double-count it.

This is a first persistence-in-memory layer, not yet a checkpoint codec or a
complete employment/healthcare model. It does not terminate employment, cancel
future appointments, alter wages, or infer intent. The world driver must use
the established event types and explicitly decide how these records affect
future institutional decisions. Tests are in
`tests/test_routine_institution_ledger.py`.


The institutional ledger also has a standalone canonical JSON codec,
`RoutineInstitutionSnapshot`. It preserves both accumulated records and the
processed-event signatures needed to keep retries from double-counting after
restoration. It can be captured and restored independently. Composite
`SimulationWorldCheckpoint` integration remains a separate task, so callers
must currently include this snapshot alongside their world checkpoint.


### Composite world-checkpoint integration

`SimulationWorldCheckpoint.capture(..., routine_institutions=ledger)` now
includes institutional records in the canonical world checkpoint. Restoring
returns the ledger as `RestoredSimulation.routine_institutions`; its processed
event signatures are preserved, so reapplying an already recorded consequence
does not increment counts again. The section is optional for worlds that do
not use institution-facing records.


## Persistent memory/location associations

`MemoryLocationAssociationBook` stores explicit links from one NPC's memory index to a location, optional alternative location, and avoidance scale. Links are owner-scoped: two NPCs may use the same association ID without sharing memories or responses. Duplicate IDs for the same owner are rejected, and removal is owner-scoped and idempotent.

`MemoryLocationAssociationSnapshot` provides canonical versioned JSON persistence for these links. Capture the association book alongside the NPC memory snapshot, restore both, then call `MemoryRoutineAdapter.derive_avoidance` with `book.for_owner(npc.entity_id)`. This preserves the explicit association across save/load; it does not infer locations, create memories, or automatically schedule disruptions. The existing routine execution ledger continues to preserve the exact derived disruption used for each execution.

Regression coverage: `tests/test_memory_routine_save_state.py`.


## Personal memory-aware route selection

`PersonalRoutePlanner` evaluates an explicit `RouteEdge` graph with deterministic lowest-cost path selection. Callers pass the requesting NPC's `RoutineAvoidanceProfile` values, produced by `MemoryRoutineAdapter.derive_profiles` using that NPC's restored `MemoryLocationAssociationBook.for_owner(owner_id)` entries. Matching owner/location profiles add a configurable cost penalty to routes entering those locations. Profiles belonging to other NPCs are ignored, so a remembered incident does not globally close a street or force every citizen to detour.

`RoutePlan` returns the selected location sequence, base travel cost, adjusted cost, and the avoided locations that influenced the selected path. Equal-cost paths are resolved lexicographically and do not depend on edge insertion order. Each RoutePlan also retains the exact selected edge IDs, so parallel roads remain unambiguous when the travel adapter starts or reroutes a journey. An unreachable destination returns an empty path; the planner does not invent roads, travel times, or location links. This is a graph-level path-choice layer; traffic multipliers, dynamic road closures, vehicle movement, and route execution are supplied by the travel tick adapter and world driver.

Regression coverage: `tests/test_route_planning.py`.


## Deterministic travel execution

TravelTickAdapter turns a found RoutePlan into an owner-scoped TravelJourney. Each consecutive location pair is bound to an explicit RouteEdge; missing segments are rejected rather than silently invented. The world driver advances journeys with a per-owner budget expressed in the same abstract time-cost units as edge travel costs. Partial edge progress is retained between ticks, and a budget can carry across multiple edges.

Road conditions are explicit inputs to each tick. closed_edge_ids pauses a journey at the affected edge and marks it blocked; the caller can reopen it after conditions change. time_multipliers scale the time required by an edge, allowing traffic or temporary delays to affect journey duration without changing the underlying route. Progress is stored in base edge-cost units, so changing a multiplier between ticks does not corrupt partial progress.

An arrival is recorded once in the shared event journal as npc_arrived, with the journey ID, owner, origin, destination, and elapsed travel cost. Tick requests are idempotent: repeating the same tick and inputs returns its stored result, while conflicting inputs for an already processed tick are rejected. A caller must supply a budget for each NPC that should move; absent budgets mean no progress.

TravelSnapshot stores each journey's current edge, partial progress, elapsed cost, status, and the per-tick replay history in canonical versioned JSON. It can restore a journey mid-edge and preserve replay behavior across a save/load cycle. TravelSnapshot is also included as an optional section in SimulationWorldCheckpoint. Capture validates that journey owners exist in the saved NPC roster and that journey and tick-history timestamps do not exceed the checkpoint tick. Restoring the world checkpoint returns the TravelLedger on RestoredSimulation.travel, preserving partial edge progress and replay history. The route graph itself remains world configuration and must be supplied again when constructing TravelTickAdapter. When replan_blocked is enabled and a journey is stopped at a junction (zero progress on its next edge), the adapter can ask PersonalRoutePlanner for a replacement path that excludes the currently closed edges. The request can include owner-scoped memory avoidance profiles, so a detour can reflect that NPC's own experiences. If no path exists, the journey becomes unreachable and is reconsidered on later ticks when re-planning remains enabled. A closure encountered partway through an edge does not teleport the NPC back to the junction: it remains blocked until that edge can be traversed or the world driver resolves the situation. Route graph changes and condition inputs remain explicit world-driver data; the adapter does not invent roads or coordinates. Regression coverage is in tests/test_travel.py.


## Routine destinations and travel

`RoutineTravelAdapter.start_due` connects the active `RoutineBook` schedule to
the route and travel systems. At an explicitly supplied simulation tick and
minute-of-day, the world driver supplies each active NPC's current location,
the route planner, road closures, optional owner-scoped memory avoidance
profiles, and (when desired) an explicit `departure_lead_minutes` window so
commutes can begin before the routine's scheduled start. Travel time is not
guessed from wall-clock minutes; the world driver controls the lead window and
per-tick travel budget. The adapter starts a persistent journey toward the routine's
`location_id` and records the originating `routine_id` on the journey.

The adapter does not teleport NPCs or execute the scheduled activity before
arrival. Arrival is materialized as the existing `npc_arrived` world event;
its attributes include the routine ID, allowing a later routine-resolution
step to act on the correct schedule block. If the NPC is already at the
destination, is travelling for another purpose, or has no available route,
the adapter returns an explicit status rather than silently creating a
conflicting journey. Repeating the same tick/routine request reuses the
existing journey ID.

Routine associations are part of schema version 2 of `TravelSnapshot`; schema
version 1 snapshots remain readable. Because the snapshot is included in
`SimulationWorldCheckpoint`, a routine-linked journey must be checkpointed with
the matching `RoutineBook` (routine ID, owner, and destination are validated).
A commute in progress therefore retains its routine purpose after save/load. Regression coverage is in
`tests/test_routine_travel.py`.


## Arrival-gated routine execution

`RoutineArrivalAdapter` is the hand-off from completed travel to scheduled
activity. It scans only journeys whose status is `arrived` and which carry a
`routine_id`; the journey owner and destination must still match the saved
routine block. An NPC who arrives before the scheduled start waits at the
destination and no execution record is created. Arrival during the block
executes the activity, with lateness consuming the block's explicit flexibility
window. Arrival after the block ends is recorded as missed, or redirected only
when that routine defines an explicit fallback. A late arrival beyond the
flexibility window follows the same fallback/missed rule.

Execution IDs are derived from the journey, routine, and processing tick.
A same-tick retry must reproduce the exact request and result; a later tick
recognizes the journey's prior execution and cannot execute that activity again.
The existing `RoutineExecutionSnapshot` and
`SimulationWorldCheckpoint` persist those records; the arrived journey itself
is already retained by `TravelSnapshot`. Optionally pass a
`RoutineWorldEventAdapter` to materialize the resolved activity as a
`routine_execution` event on the shared timeline. The world driver remains
responsible for supplying the simulation minute, disruptions, deterministic
outcome samples, and any later activity-specific consequences.

Regression coverage: `tests/test_routine_arrival.py`.


## Authoritative physical NPC presence

`PresenceLedger` stores each NPC's current symbolic location or their exact
in-transit road edge and fractional progress. The world driver explicitly
places NPCs at their initial locations with `place(owner_id, location_id, tick)`;
no starting location is guessed. `PresenceTickAdapter.synchronize` derives
updates from the latest journey in `TravelLedger`, so old completed journeys
cannot pull an NPC back to an earlier destination. An NPC travelling, blocked,
or unreachable is not counted as occupying a building or street node;
`occupants(location_id)` returns only NPCs physically at that location.
Optional `npc_presence_updated` events provide a shared timeline hook for
witness visibility, social encounters, workplace attendance, and other systems.

Presence tick replay is deterministic and rejects conflicting same-tick travel
state. `PresenceSnapshot` persists current locations, active edge progress,
and replay history. `SimulationWorldCheckpoint.capture(..., presence=ledger)`
includes this state and validates NPC ownership and checkpoint timestamps;
restoration exposes it as `RestoredSimulation.presence`. Location IDs remain
symbolic graph nodes: actual world coordinates, animation, collision, and
continuous spatial interpolation require an explicit world geometry layer and
are not fabricated by this module.

Regression coverage: `tests/test_presence.py` and
`tests/test_world_checkpoint.py`.
