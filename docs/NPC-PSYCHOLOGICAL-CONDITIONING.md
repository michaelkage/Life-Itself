# NPC psychological conditioning and associative learning

This system gives NPCs persistent, individual associations between explicitly
named cues and experienced outcomes. It is not a diagnosis or a universal
trauma model. The simulation supplies the cue, outcome, intensity, source event,
and learning mode; the ledger records exactly that interpretation.

## Learning

Each NPC has a `ConditioningProfile` with independent learning, extinction,
and spontaneous-recovery rates. Associations are owner-scoped and bounded
between -1 and +1.

- Positive associations produce an approach signal.
- Negative associations produce an avoidance signal.
- Zero produces a neutral signal.
- Reinforcement moves an association toward the supplied outcome.
- Extinction moves it toward neutral without automatically reversing it.
- Spontaneous recovery gradually weakens association magnitude toward neutral.

The same cue can mean different things to different NPCs. One NPC may associate
a raised voice with danger while another associates it with familiar coaching.
No association is shared unless an integration explicitly copies evidence.

## Replay and persistence

Every learning record has a stable record ID and source world-event ID.
Replaying the same record is idempotent; conflicting record reuse and duplicate
source-event/cue learning for one NPC are rejected. Snapshots use canonical JSON
and preserve current associations, learning history, and per-NPC decay clocks so
one NPC's update never advances another NPC's recovery clock. Conditioning can
also be passed as `conditioning=...` to `SimulationWorldCheckpoint.capture`;
restored worlds expose `RestoredSimulation.conditioning`. The composite checkpoint
validates each learning record against the authoritative event journal and NPC roster.

## Behavioral integration boundary

`NPCConditioningLedger.assess(owner_id, cue)` returns an approach/avoid/neutral
signal and bounded response strength. It does not select actions, change goals,
alter routines, or force an NPC to confront or avoid a cue. Decision systems
may combine it with values, current stress, relationships, obligations, and
context. Authored profiles are configuration; association history is state.

Tests: `tests/test_npc_conditioning.py`.
