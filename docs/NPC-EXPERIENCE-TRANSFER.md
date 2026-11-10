# NPC strategic experience transfer

The experience-transfer ledger adds a provenance-preserving channel for sharing a specific autobiographical experience.

A transfer requires a source-owned autobiographical memory, its original event in the authoritative journal with the source recorded as participant or witness, and a later communication event whose participants include both source and recipient. Confidence is supplied by the caller; the ledger does not infer that a report is true.

The recipient receives a reported-experience record, not an autobiographical memory. The record retains source memory ID, original event ID, source role, original tick, communication event ID, transfer tick, account, and confidence. Hearsay therefore cannot silently become first-person experience.

Transfer IDs are idempotent; conflicting reuse is rejected. The same source memory cannot be resent to the same recipient in the same communication under another ID. Canonical component snapshots preserve the records, and restoration revalidates the full source and communication chain.

The retrieval helper is read-only and does not mutate recipient beliefs, personal memories, plans, or historical action evaluations. Replanning can optionally consume the same history and transfer ledgers to guide future action proposals through explicit action tags and outcome tags.


## Strategic retrieval

`strategic_experience_evidence(history, transfers, owner_id, current_tick, limit=100)`
returns a stable, bounded decision-time view of evidence available to an NPC. It excludes future-dated memories and reports and preserves the source class:

| Source class | Base influence |
| --- | ---: |
| Personal participation | 1.00 |
| Witnessed event | 0.60 |
| Reported account | 0.35 × transfer confidence |

These are conservative evidence weights, not truth probabilities. Report confidence remains separately visible. Retrieval is read-only: it does not rewrite memories, beliefs, or historical plan evaluations. The helper is an evidence interface; automatic injection into a particular planner policy remains a separate integration step.


## Composite world checkpoint

Pass the same autobiographical history and event-journal-backed transfer ledger to checkpoint capture:

```python
checkpoint = SimulationWorldCheckpoint.capture(
    current_tick, coordinator, npcs,
    life_history=history,
    experience_transfers=transfers,
)
restored = SimulationWorldCheckpoint.from_json(
    checkpoint.to_json()
).restore()
restored_transfers = restored.experience_transfers
```

The checkpoint stores the transfer snapshot as an optional component, preserving compatibility with older payloads that omit it. Capture and restore both revalidate the source memory, original event, source/recipient identities, communication event, chronology, and NPC membership. Experience transfers require the same life-history instance and world-event journal as the checkpoint. Restore reconstructs the transfer ledger only after restoring the event journal and autobiographical history.


## Tagged action guidance

A planner action may declare exact-match `experience_tags`. An autobiographical memory influences that action only when its tags include one of those exact values and exactly one explicit outcome marker: `outcome:success` or `outcome:failure`. Untagged, unrelated, or outcome-ambiguous memories do not influence action costs. The projection deduplicates repeated accounts of the same original event and retains the strongest available source for that action.

Pass both shared ledgers when constructing the replanning coordinator:

```python
replanning = NPCActionReplanningCoordinator(
    decisions, executions, events,
    life_history=history,
    experience_transfers=transfers,
)
```

Personal evidence has the strongest influence, witnessed evidence is weaker, and reported evidence is additionally discounted by its transfer confidence. The resulting bounded estimate adjusts proposal costs; it is not treated as a world fact or proof of success. Existing execution-derived reliability remains primary when both sources are available. Each resulting `NPCDecision` retains the evidence IDs used, and replanning snapshots preserve that attribution. Historical evaluations and completed executions are not rewritten.
