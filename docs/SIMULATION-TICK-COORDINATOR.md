# Deterministic Simulation Tick Coordinator

`SimulationTickCoordinator` establishes a stable order for two existing systems:
world-event-to-witness-memory materialization and NPC-to-NPC conversation transfer.

## Tick contract

1. The caller supplies the integer tick, an NPC mapping, event IDs that occurred
   at that exact tick, and any conversation intents to run.
2. Every selected event is validated against the authoritative event ledger.
   Every listed witness must be present in the supplied NPC mapping.
3. Memories are materialized for witnesses in sorted event/witness order.
4. Conversations run in sorted conversation-ID order, after memory creation.
5. Identical replay of a processed tick returns its original result without
   repeating mutations. Different inputs for the same tick are rejected.
6. A new tick must be greater than the last processed tick. Tick history is
   returned chronologically by `snapshot()`.

## Deliberate boundaries

The coordinator does not decide which events occur, who can see an event, who
meets whom, or what an NPC intends. Those inputs remain explicit. It does not
advance weather, decay every NPC's memories, schedule autonomous activities, or
infer moral meaning. This makes it a small ordering layer rather than a second
simulation engine.

The coordinator is an in-memory runtime component. Its `snapshot()` exposes
completed tick results, but it does not yet restore its own internal replay
index from serialized data; durable save/load should serialize the request ledger
and adapter state as part of a future world snapshot format.

## Example

```python
from simreality import (
    ConversationIntent,
    SimulationTickCoordinator,
    SocialBeliefSystem,
    SocialConversationAdapter,
    SocialTrustLedger,
    WorldEventLedger,
    WorldEventMemoryAdapter,
)

events = WorldEventLedger()
trust = SocialTrustLedger()
beliefs = SocialBeliefSystem(trust)
conversation_adapter = SocialConversationAdapter(trust, beliefs)
memory_adapter = WorldEventMemoryAdapter(events)
ticks = SimulationTickCoordinator(events, memory_adapter, conversation_adapter)

result = ticks.step(
    12,
    npcs,
    event_ids=("event-at-tick-12",),
    conversations=(ConversationIntent("chat-12", "listener", "speaker"),),
)
```

Regression coverage: `tests/test_simulation_tick.py`.
