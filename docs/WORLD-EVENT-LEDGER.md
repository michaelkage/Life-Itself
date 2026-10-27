# Deterministic World Event Ledger

## Purpose

`simreality/world_events.py` introduces a shared, append-only record of what the
simulation says happened. It is separate from what an NPC believes happened:
a single world event may have many witnesses, and each witness can later develop
different trust, memories, rumours, or conclusions.

## Event record

A `WorldEvent` contains:

- `event_id`: stable, caller-assigned identity.
- `tick`: non-negative simulation tick; no wall-clock timestamp is required.
- `event_type`: a domain label such as `conversation`, `theft`, `arrest`, or
  `medical_emergency`.
- `participants`: ordered character IDs whose roles matter to the event.
- `witnesses`: character IDs who observed it, kept separately from participants.
- `attributes`: sorted immutable scalar key/value pairs for explicit details.

Use `WorldEventLedger.make_event(...)` to canonicalize witness and attribute order.
Participant order is preserved because the order may encode roles.

## Determinism and replay

- Identical event ID/content is idempotent.
- Reusing an event ID for different content is rejected.
- Batch insertion validates the entire batch before changing the ledger.
- Snapshots and queries are ordered by `(tick, event_id)`, not arrival order.
- Tick-range filters are inclusive; queries can also filter by participant,
  witness, and event type.
- `from_snapshot` reconstructs the ledger and checks event identity consistency.
- No real-time timestamps, random IDs, or implicit moral labels are generated.

## Scope boundary

This ledger is an authoritative journal, not a rules engine. It does not decide
who was close enough to witness an event, what an event means, or how an NPC reacts.
The next integration step is to let explicit event consumers derive social
consequences, legal evidence, memory entries, and goals without mutating the
historical event record itself.

## Example

```python
from simreality.world_events import WorldEventLedger

events = WorldEventLedger()
event = events.make_event(
    "market-incident-14",
    tick=240,
    event_type="threat",
    participants=("resident-8", "shopkeeper-3"),
    witnesses=("guard-2", "neighbour-5"),
    attributes={"location": "market-square", "severity": 0.7},
)
events.append(event)
witnessed = events.query(witness_id="guard-2")
```
