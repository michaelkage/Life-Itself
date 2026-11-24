# Atomic world tick pipeline

`SimulationWorldTickPipeline` is the engine-independent integration boundary for
systems that already own authoritative travel, physical presence, encounters,
and social-event processing.

## Phase order

A call to `step(tick, npcs, ...)` executes these phases in order:

1. **Travel advancement** — `TravelTickAdapter.advance` consumes explicit
   per-owner budgets and explicit road closures/time multipliers. Optional
   rerouting requires the caller to provide a `PersonalRoutePlanner`.
2. **Presence synchronization** — `PresenceTickAdapter.synchronize` derives
   current location or in-transit edge progress from the resulting travel ledger.
3. **Confirmed encounters** — sorted `PresenceEncounterIntent` values are
   evaluated against the newly synchronized physical-presence ledger. An
   opportunity must be explicitly confirmed; co-location alone is not an
   encounter. Dialogue and bilateral trust effects remain opt-in.
4. **Social processing** — the existing `SimulationTickCoordinator` materializes
   memories for selected/current-tick witnessed events, then processes explicit
   `ConversationIntent` values in canonical order.

The pipeline does not infer routes, budgets, visibility, attention, intent,
dialogue, or trust policy. Those remain world-driver decisions.

## Atomicity and replay

Before the first phase, the pipeline captures the authoritative event journal,
travel/presence/encounter ledgers, social adapter replay indexes, trust/belief
state, affected NPC memories, and coordinator replay state. If any phase raises,
all captured state is restored before the exception is propagated. The same
tick and same request signature returns the original result; a conflicting
same-tick request or an out-of-order new tick is rejected.

The lower-level component snapshots remain the durable persistence format.
Construct a pipeline around the restored component adapters after loading a
`SimulationWorldCheckpoint`; the pipeline's in-process request cache is an
execution optimization, not a replacement for component replay history.

## Example

```python
result = pipeline.step(
    tick,
    npcs,
    travel_budgets={"npc-17": 1.25},
    closed_edge_ids=("road-closed-4",),
    encounter_intents=(
        PresenceEncounterIntent(
            encounter_id=f"encounter:{tick}:npc-17:npc-22",
            first_id="npc-17",
            second_id="npc-22",
            opportunity=True,
        ),
    ),
)
```

The returned `WorldTickPipelineResult` contains the travel result, presence
updates, confirmed encounter results, and the social tick result.

## Regression coverage

Run:

```bash
python -m pytest -q tests/test_world_tick_pipeline.py
python -m pytest -q
```
