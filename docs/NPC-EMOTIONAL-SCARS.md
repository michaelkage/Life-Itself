# Long-Term Emotional Scars and Recovery

An EmotionalScar is a persistent, owner-specific imprint linked to both an authoritative source event and the owner's autobiographical memory. It records an emotion axis, an exact trigger cue, an initial severity, and a per-tick retention factor.

Severity is derived rather than destructively edited. Between recovery actions it decays as:

    severity(t + n) = severity(t) * retained_per_tick ** n

A retention factor close to 1 represents a slowly healing scar. Recovery is explicit: a caller records a named action, tick, and bounded severity reduction. Recovery never deletes the scar or its source memory. The ledger rejects recovery amounts greater than the remaining severity and preserves each action as append-only history.

Evaluation accepts exact observed cue IDs and exposure values. A matching scar contributes current severity multiplied by cue exposure to its configured emotion axis. Contributions retain scar, event, and memory provenance; axis totals are capped at 1.0. No semantic cue inference occurs.

NPCEmotionalScarLedger is deterministic and owner-scoped. Duplicate scar and recovery IDs are idempotent only when their full content matches. Conflicting reuse, duplicate source-event/owner/axis/cue scars, backward time, unknown scars, and cross-owner recovery are rejected.

EmotionalScarSnapshot stores canonical version-1 JSON and validates the complete history on restore. This is a component-level persistence codec; composite world-checkpoint integration and automatic scar creation policies remain future work. The caller must validate source event and memory ownership against the authoritative world and life-history ledgers.

This is a simulation abstraction, not a clinical diagnosis or a claim that real trauma follows one universal decay curve.

Tests: tests/test_emotional_scars.py.
