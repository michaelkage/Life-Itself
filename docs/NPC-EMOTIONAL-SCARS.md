# Long-Term Emotional Scars and Recovery

An EmotionalScar is a persistent, owner-specific imprint linked to both an authoritative source event and the owner's autobiographical memory. It records an emotion axis, an exact trigger cue, an initial severity, and a per-tick retention factor.

Severity is derived rather than destructively edited. Between recovery actions it decays as:

    severity(t + n) = severity(t) * retained_per_tick ** n

A retention factor close to 1 represents a slowly healing scar. Recovery is explicit: a caller records a named action, tick, and bounded severity reduction. Recovery never deletes the scar or its source memory. The ledger rejects recovery amounts greater than the remaining severity and preserves each action as append-only history.

Evaluation accepts exact observed cue IDs and exposure values. A matching scar contributes current severity multiplied by cue exposure to its configured emotion axis. Contributions retain scar, event, and memory provenance; axis totals are capped at 1.0. No semantic cue inference occurs.

NPCEmotionalScarLedger is deterministic and owner-scoped. Duplicate scar and recovery IDs are idempotent only when their full content matches. Conflicting reuse, duplicate source-event/owner/axis/cue scars, backward time, unknown scars, and cross-owner recovery are rejected.

EmotionalScarSnapshot stores canonical version-1 JSON and validates the complete history on restore. `EmotionalScarFormationAdapter` can turn a sufficiently strong `EmotionalMemoryResponse` into an evidence-grounded proposal. It derives source event and memory IDs from the owner's actual autobiographical record, and a stable proposal key makes repeated appraisal deterministic. Proposals do not create scars. The owner must explicitly accept or reject each proposal through `EmotionalScarDecisionLedger`; rejection remains in the decision history and changes no scar state. Acceptance creates the persistent scar once. Decision snapshots preserve proposals, accepted and rejected decisions, scars, and recovery history. The composite world checkpoint currently persists the scar ledger; decision-ledger checkpoint integration is a separate follow-on.

This is a simulation abstraction, not a clinical diagnosis or a claim that real trauma follows one universal decay curve.

Tests: tests/test_emotional_scars.py.
