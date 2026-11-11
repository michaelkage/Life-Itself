# NPC Intention Arbitration and Commitment

GoalArbitrationEvaluator resolves competition between currently actionable ambitions. It combines the existing GoalBook priority/deadline/confidence/progress score with explicit per-goal mappings for unmet needs, transient emotion, personal value alignment, and resource costs.

## Decision model

- GoalArbitrationRule is authored configuration. No goal meaning or value alignment is inferred.
- Need deficits and emotional intensities use [0, 1]. Value alignment uses [-1, 1].
- The existing GoalBook score is normalized to [0, 1]. Need, emotion, and value contributions are each bounded to ±0.20; authored importance contributes up to ±0.10. The final score is clamped to [0, 1].
- A goal is resource-feasible only when every declared cost is covered by the supplied current resource balance. Costs are evaluated per candidate because only one ambition is selected at a time.
- Dependency-blocked and otherwise non-actionable goals are excluded. Feasible candidates sort before infeasible ones, then by score, base score, and stable goal ID.

## Commitment and temporary sacrifice

GoalCommitmentAdapter.commit is an explicit decision boundary. It validates the assessment against the complete owner-specific GoalBook snapshot, then records one selected goal and all competing actionable goals as deferred. It does not change priority, progress, confidence, status, or lifecycle history. Deferred goals remain active and can win a later arbitration when needs, feelings, values, deadlines, or resources change.

GoalCommitmentLedger is append-only, replay-safe, and enforces at most one commitment per NPC per tick. A different commitment for the same owner and tick is rejected. The same assessment replays idempotently. This prevents two contradictory goal commitments from being accepted for the same decision tick.

## Persistence

GoalCommitmentSnapshot provides canonical JSON capture/restore and validates IDs, per-owner tick uniqueness, and canonical encoding. It is an independent component snapshot; it does not yet add a field to SimulationWorldCheckpoint. Callers that need world-level atomic saves should persist this component alongside the world checkpoint until integrated checkpoint support is added.

## Boundaries

Arbitration does not start actions. Pass the selected goal to the existing decision/replanning pipeline after commitment. Resource checks at arbitration are a snapshot; the action executor must still revalidate live resources and reservations before execution. A commitment is a focus decision, not an irrevocable lock: a later tick may select a different still-active goal.
