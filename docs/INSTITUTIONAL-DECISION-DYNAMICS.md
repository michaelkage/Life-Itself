# Institutional decision dynamics

`simreality/institutional_dynamics.py` adds a deterministic, inspectable model of why two institutions—or two employees inside one institution—may respond differently to the same situation.

## Inputs

- **Institutional profile:** leader identity, weighted leadership priorities, accountability, political pressure, budget pressure, and staffing pressure.
- **Department state:** department priorities, remaining budget, available staff, and institutional influence.
- **Employee profile:** integrity, ambition, loyalty to leadership, favouritism, and explicit signed bias-cue weights.
- **Decision options:** department, resource costs, priority tags, evidence strength and minimum threshold, requester influence, public visibility, transparency, personal advantage, and named bias cues.

All weights and traits are explicit inputs. This first slice does not infer prejudice from a person's identity or invent hidden motives.

## Evaluation

`InstitutionalDecisionEvaluator.evaluate(...)` is pure and deterministic. It:

1. Marks an option infeasible when the department lacks budget or staff, or when its minimum evidence threshold is not met.
2. Scores alignment with both leadership and department priorities.
3. Accounts for current resource pressure, evidence, accountability, public visibility, transparency, employee ambition and integrity, loyalty, favouritism, and explicitly configured bias cues.
4. Returns per-axis contributions and blockers, sorted with feasible options first and stable score/ID tie-breaking.

Bias weights may be positive or negative. For example, an employee can favour a cue associated with a connected requester while penalising a cue associated with an outsider. Those cues must be supplied by the simulation; the evaluator does not decide which groups deserve treatment.

## Deliberate boundaries

- A score is not a moral verdict, a factual finding, or an action.
- The evaluator does not spend money, assign staff, change policy, execute corruption, or alter a person's rights.
- Department rivalry is represented initially through different department priority weights and influence, not through a simulated negotiation between departments.
- Budgets and staffing are supplied as current state; this module does not yet generate or redistribute them.
- Evidence thresholds are explicit policy gates. A caller may configure no minimum threshold, but should not treat influence or bias as evidence.
- The result is one component for an NPC decision-maker to consider alongside goals, beliefs, personality, and world events.

This is a first institutional dynamics slice, not a complete organization simulator.
