# NPC Strategy Beliefs and Explicit Learning

`NPCStrategyBeliefLedger` builds owner-specific reliability beliefs from immutable terminal `NPCPlanEvaluation` records.

## Observation rules

- Only `completed` and `failed` terminal evaluations can produce strategy observations.
- A `replanned` result is neutral: interruption or replacement is not evidence that a strategy failed.
- A completed plan with missing expected goal facts is a failure observation.
- Zero-confidence evaluations are excluded because the outcome was not adequately observed.
- Strategy identity is a deterministic digest of the goal and ordered action sequence.
- Context is an explicit caller-supplied key. Evidence is never pooled across NPCs, goals, strategies, or contexts.
- Reflection IDs may be attached as explanatory provenance, but counterfactuals never count as actual outcomes.

## Evidence aggregation

`StrategyLearningRule` defines a minimum sample count, a Beta prior, and a minimum posterior movement before a proposal is emitted. Evaluation confidence weights each observation. The posterior is a reliability estimate, not certainty or a truth claim. A single failure cannot permanently blacklist a route.

`NPCStrategyBeliefLedger.assess` returns a deterministic proposal only after enough comparable observations create a meaningful shift from the prior. A proposal is bound to the exact observation set and is rejected if new evidence makes it stale before the NPC decides.

## NPC agency

`decide(proposal, accepted=..., decision_tick=..., rationale=...)` records an explicit accept or reject choice. Rejection remains in history without changing the effective belief. An accepted later proposal can revise an earlier accepted belief; no historical observation or decision is overwritten.

`plan_reliabilities(owner_id, context_key)` exports only the latest accepted beliefs in the exact `(goal_id, action_sequence) -> confidence` mapping already consumed by `DeterministicPlanner` and `NPCDecisionCycle`. The planner applies its existing bounded risk premium. Strategy learning does not change authored action costs.

## Persistence

`StrategyBeliefSnapshot` stores immutable observations and decisions. `SimulationWorldCheckpoint.capture(..., strategy_beliefs=...)` persists this optional component and validates owners, ticks, plan evaluations, action sequences, and source event provenance. The corresponding `RestoredSimulation.strategy_beliefs` is restored without changing older checkpoint payloads.

Tests: `tests/test_npc_strategy_beliefs.py` and `tests/test_world_checkpoint.py`.