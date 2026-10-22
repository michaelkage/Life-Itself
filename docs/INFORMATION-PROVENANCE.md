# Information Provenance Ledger

## Purpose

The information layer must distinguish the world's underlying events from claims made about those events. NPCs may report accurately, misremember details, infer causes, repeat a rumour, or issue a correction. The ledger records that history without deciding truth on behalf of the world.

The first portable implementation lives in:
- `cpp/include/simreality/Information.h`
- `cpp/src/Information.cpp`
- `cpp/tests/InformationTests.cpp`

## Claim fields

Each claim has:
- A stable claim ID
- A subject key and proposition key
- A root evidence ID identifying the original evidence lineage
- An optional parent claim ID
- Source and recipient entity IDs
- An integer creation tick
- Confidence in the range [0, 1]
- A relay hop count
- A claim kind: observation, report, inference, or correction

The proposition key is a stable domain key, not free-form dialogue. Generated dialogue may describe a claim, but must not determine its identity or mutate authoritative state.

## Provenance rules

1. Claim IDs are unique within a ledger.
2. Root claims have no parent and a hop count of zero.
3. A child is recorded only after its parent.
4. A relay must preserve its root evidence ID.
5. A relay's source must be the parent claim's recipient.
6. Ticks cannot move backwards along a claim lineage.
7. A child hop count is exactly its parent's hop count plus one.
8. Confidence and transmission fidelity must be finite values in [0, 1].
9. Corrections are new claims. They do not erase or rewrite the claim being corrected.
10. Independent evidence is counted by distinct root evidence IDs, not by the number of retellings.

## What this does not yet do

This is an engine-independent provenance primitive, not a complete media or belief system. It does not yet:
- Decide whether a proposition is objectively true
- Automatically update NPC beliefs
- Model news organizations, private channels, access control, or publication incentives
- Persist the ledger in world snapshots
- Replace the existing gossip/rumour implementation
- Guarantee that two differently named root IDs truly represent independent evidence; evidence identity must be assigned by the event/evidence creation layer

These are deliberate boundaries. Integration should come after the primitive's semantics and tests are stable.

## Test command

From the repository root:

```bash
cmake -S cpp -B build
cmake --build build --parallel 2
ctest --test-dir build --output-on-failure
```

The dedicated CTest target checks relay lineage, confidence attenuation, duplicate rejection, invalid parentage, time ordering, and the distinction between repeated reports and separate evidence roots.
