# Information Provenance Ledger

## Purpose

The information layer must distinguish the world's underlying events from claims made about those events. NPCs may report accurately, misremember details, infer causes, repeat a rumour, or issue a correction. The ledger records that history without deciding truth on behalf of the world.

The portable implementations live in:
- `cpp/include/simreality/Information.h`
- `cpp/src/Information.cpp`
- `cpp/tests/InformationTests.cpp`
- `simreality/information.py`
- `tests/test_information_provenance.py`

The Python implementation is a reference implementation of the C++ ledger's validation and lineage rules. Both are intentionally engine-independent.

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
11. The evidence-strength query combines distinct roots with a bounded noisy-OR estimate; each root contributes only its strongest recorded confidence, so retelling cannot amplify it.

## What this does not yet do

This is an engine-independent provenance primitive, not a complete media or belief system. It does not yet:
- Decide whether a proposition is objectively true
- Model news organizations, private channels, access control, or publication incentives
- Automatically update NPC beliefs from claims
- Replace the existing gossip/rumour implementation
- Guarantee that two differently named root IDs truly represent independent evidence; evidence identity must be assigned by the event/evidence creation layer

The ledger exposes both a distinct-root count and a bounded evidence-strength estimate, including a recipient-scoped query so an NPC only uses claims that reached them. The estimate is a support signal, not an objective-truth score, and depends on root IDs being assigned correctly. Conflicting proposition keys remain separate; the ledger does not decide which account is true. The ledger is owned by `SimulationWorld` and included in version 11 C++ snapshots. Older versions 5–10 remain readable and restore with an empty ledger. `record_witnessed_action` creates an observation claim for each witness, and conversations relay matching claims when the speaker has a recorded parent claim. In the current C++ belief-update path, recipient-scoped evidence can modestly adjust an NPC's confidence alongside existing personality and relationship interpretation; it does not force belief revision or resolve conflicting accounts. If no matching evidence has reached an NPC, this evidence adjustment is skipped.

## Tests

Python and C++ regression tests include lineage preservation, confidence attenuation, duplicate and invalid-parent rejection, invalid confidence/fidelity, monotonic ticks, append-only corrections, recipient-scoped evidence, conflicting proposition keys, and the distinction between repeated reports and separate evidence roots.

From the repository root, run the Python suite using the project's existing test command. The C++ target can be run with:

```bash
cmake -S cpp -B build
cmake --build build --parallel 2
ctest --test-dir build --output-on-failure
```
