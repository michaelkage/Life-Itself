# Persistent NPC Routines — First Implementation Slice

**Status:** Python reference implementation includes canonical schedule persistence, an idempotent execution ledger, a deterministic tick adapter, and an explicit routine-execution phase on `SimulationTickCoordinator`. Callers run the ordinary world tick first, then call `execute_routines` for that latest tick with a schedule, ledger, minute, disruptions, and outcome samples. Schedules and execution history can be included in `SimulationWorldCheckpoint`. This is an explicit two-phase API, not an automatic routine call inside `step`; callers must pass the same ledger into checkpoint capture. NPC memory associations still need to be translated into explicit disruptions. Route simulation and C++ runtime integration remain pending.

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
