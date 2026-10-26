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
1. Every claim must identify a non-empty source and recipient; a claim without a recipient cannot represent knowledge delivered to an actor.
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

`InformationLedger::lineage_for_claim(claim_id)` returns a copied, source-to-recipient chain in oldest-first order; an unknown claim or incomplete chain returns an empty result. This is for investigation and explanation: it exposes how a claim travelled, but does not declare the claim true or make repeated relays independent evidence.

`InformationLedger::claims_received_by(recipient_entity_id)` returns copied claims that were delivered to that recipient, ordered by creation tick and then claim ID for deterministic presentation. An empty recipient ID returns no claims. This lets an investigation begin from what a specific NPC actually received, rather than accidentally querying world-wide information. `InformationLedger::investigation_for(recipient_entity_id)` packages each received claim with its copied source-to-recipient lineage in the same deterministic order. Conflicting proposition keys remain separate entries; unknown or empty recipients produce an empty packet. The packet is an investigation view, not a verdict, and does not expose claims that were never delivered to the recipient.

`InformationLedger::investigation_groups_for(recipient_entity_id)` organizes that packet by subject and proposition key in deterministic lexical order. Each group includes the received entries, the count of distinct evidence roots among those entries, and the bounded evidence-strength estimate computed only from claims delivered to that recipient. Multiple retellings from one root count once; competing proposition keys remain separate groups and are not ranked as true or false. The group deliberately does not blend source reliability, NPC loyalty, compassion, skepticism, or moral judgment into evidence strength: those are separate interpretation signals owned by the belief/personality layer. This keeps "how much independent support reached this NPC" distinct from "how much this NPC trusts the source" and "whether this NPC approves of the action."

## Decision score explanations

The C++ decision layer also exposes `explain_moral_choice(npc, option)`. It returns the normalized NPC value and scenario-option value used for each of the seven score factors, each factor's weighted contribution, and the total score. The existing `evaluate_moral_choice` uses the same breakdown, so the explanation total is computed by the same deterministic formula rather than by a separate approximation. Factor order is stable: urgency, people helped, fairness, safety, freedom, loyalty, and personal cost.

This is an explanation of how a supplied option scores under the NPC's current value priorities. It is not a historical record of a decision, does not capture which information the NPC had at an earlier time, and does not classify the selected option as objectively good or bad. Relationship values and evidence provenance are intentionally not presented as score factors because this scoring function does not currently use them. A later historical decision-context API should capture those inputs at the time of choice rather than reconstructing them from current world state.

## Current NPC decision context

`SimulationWorld::decision_context_for(npc_id, options, target_id)` joins a present-time investigation view with the NPC's current directed relationship values and the score explanation for each supplied moral-choice option. The result includes the simulation hour at which the query was made. Option explanations use the same deterministic factor breakdown as `evaluate_moral_choice`; their order matches the caller-supplied option order. Missing NPC IDs produce an empty context rather than invented knowledge or score factors.

This API is deliberately named and documented as a **current** context query. It does not claim that current relationships or beliefs were the ones available when an earlier choice occurred. Historical decision-time context is not yet recorded by the moral-choice resolver; a future historical record must capture the relevant evidence, relationships, value factors, option scores, and chosen option at the moment of resolution, then persist those records for deterministic replay. Empty investigation sections mean no matching records are available, not that the NPC had evidence against a proposition.

## What this does not yet do

This is an engine-independent provenance primitive, not a complete media or belief system. It does not yet:
- Decide whether a proposition is objectively true
- Model news organizations, private channels, access control, or publication incentives
- Automatically update NPC beliefs from claims
- Replace the existing gossip/rumour implementation
- Guarantee that two differently named root IDs truly represent independent evidence; evidence identity must be assigned by the event/evidence creation layer

The ledger exposes both a distinct-root count and a bounded evidence-strength estimate, including a recipient-scoped query so an NPC only uses claims that reached them. The estimate is a support signal, not an objective-truth score, and depends on root IDs being assigned correctly. Conflicting proposition keys remain separate; the ledger does not decide which account is true. The ledger is owned by `SimulationWorld` and included in version 14 C++ snapshots. NPC belief revisions are stored as an append-only history with prior/new confidence, reason, source, simulation time, and the interpretation factors that influenced the revised account (source reliability, loyalty, compassion, skepticism, and visible evidence strength). Older versions 5–13 remain readable; snapshots before version 11 restore with an empty ledger, and snapshots before version 12 restore with empty belief-revision histories. Version 12 histories load with neutral defaults for interpretation factors. `record_witnessed_action` creates an observation claim for each witness, and conversations relay matching claims when the speaker has a recorded parent claim. In the current C++ belief-update path, recipient-scoped evidence can modestly adjust an NPC's confidence alongside existing personality and relationship interpretation; it does not force belief revision or resolve conflicting accounts. If no matching evidence has reached an NPC, this evidence adjustment is skipped. `SimulationWorld::belief_history_for(npc_id, target_id)` returns a read-only copy of an NPC's revision history in chronological order, optionally filtered to a target; an empty target ID means no target filter. `belief_explanations_for` wraps each revision with its signed confidence delta (`revised_confidence - previous_confidence`) for UI/debugging use. The delta describes a change in the NPC's confidence only; it is not an objective-truth or morality score. `beliefs_about_event(npc_id, target_id, event_timestamp_hour)` returns all beliefs the NPC holds about a target at the exact event time, including incompatible action accounts. Results have a stable canonical order for deterministic presentation, not a confidence-based ranking. Missing NPCs, empty target IDs, and non-finite event times return no results. `belief_account_explanations_for` pairs each current account with only those revision explanations matching its target, action interpretation, and event timestamp. Revision entries remain chronological; an account is still returned when no matching revisions exist. This is a read-only explanation of the NPC's interpretation history, not an assertion about objective truth. `SimulationWorld::investigation_view_for(npc_id, target_id)` joins the recipient's received investigation groups with their current belief accounts and chronological belief explanations. The optional target filter matches information subject keys and belief target IDs. The sections remain separate: claims include evidence lineage, current beliefs may conflict, and revision explanations retain confidence deltas plus the recorded source-reliability, loyalty, compassion, skepticism, and evidence factors. The `belief_accounts` section additionally pairs each current account with only revisions matching that account's target, action interpretation, and event timestamp, so callers do not need to reimplement this join and a competing account's history is not accidentally shown as an explanation for it. Revisions also preserve the IDs of recipient-visible claims and distinct root-evidence IDs available at the time of the change. `BeliefRevisionExplanation::evidence_claims` resolves each saved claim ID against the current ledger and, when found, includes the claim record and its complete source-to-recipient relay lineage. If a saved ID cannot be resolved, the entry remains present with `resolved == false` and its requested ID intact rather than disappearing silently. The revision's `evidence_root_ids` remain available separately, including roots whose claim records may no longer be resolvable. These are provenance links to relevant incoming evidence, not proof that one claim alone caused the confidence change; older snapshots load with empty provenance-link lists. Stable ordering is for reproducible presentation only. Empty sections mean there are no matching records in this view; they must not be interpreted as evidence that a proposition is false.

## Tests

Python and C++ regression tests include lineage preservation, confidence attenuation, duplicate and invalid-parent rejection, invalid confidence/fidelity, monotonic ticks, append-only corrections, recipient-scoped evidence, conflicting proposition keys, and the distinction between repeated reports and separate evidence roots.

From the repository root, run the Python suite using the project's existing test command. The C++ target can be run with:

```bash
cmake -S cpp -B build
cmake --build build --parallel 2
ctest --test-dir build --output-on-failure
```
