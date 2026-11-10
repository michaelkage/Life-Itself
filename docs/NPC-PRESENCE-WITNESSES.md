# Presence-aware witness eligibility

`PresenceWitnessAdapter` is the physical-presence gate between the world and
witness-memory systems. It reads an event's explicit `location_id` attribute
and checks each candidate against the authoritative `PresenceLedger`.

A candidate is eligible only when all three conditions hold:

1. The NPC has a recorded presence state.
2. The NPC is `at_location` at the event's location (travelling, blocked, and
   unreachable NPCs are excluded).
3. The world driver explicitly marks an observation opportunity for that NPC.

The opportunity map is deliberately supplied by the caller. It can later be
derived from line of sight, hearing, obstructions, attention, distance, indoor
layout, or other world geometry. This adapter does not guess those facts.
Co-location alone does not make somebody a witness.

The result is a canonical, sorted assessment with an eligibility reason for
every candidate. It does not mutate the authoritative event or add witnesses.
The world driver can use `eligible_witnesses` when constructing the event's
original witness list; `WorldEventMemoryAdapter` then materializes memories
only for those explicitly recorded witnesses.

Regression coverage: `tests/test_presence_witnesses.py`.
