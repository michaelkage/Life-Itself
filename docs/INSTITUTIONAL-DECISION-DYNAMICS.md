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


## Department resource competition

`simreality/institutional_resources.py` adds a deterministic allocation-planning phase. Departments submit one request per period for budget and staff. The allocator ranks requests using four explicit score components: alignment with leadership priorities, service impact, urgency, and department influence. The policy controls the weight of each component.

The allocator processes requests in descending score order with department ID as a stable tie-break. Each department receives the same fulfilment ratio for its requested budget and staff, limited by the remaining pools. This means a shortage can produce partial fulfilment, and no allocation can exceed the institution's total budget or staff pool. A request may ask for budget only or staff only.

The returned plan includes each score contribution, allocation ratio, allocated amount, and unmet request. It is a proposal only: it does not mutate `DepartmentState`, spend money, hire staff, or alter future periods. The simulation must explicitly commit a plan before updating department resources. This first version uses priority-ordered rationing rather than negotiation or a proportional/fair-share formula; influence is a configured pressure, not proof that a department's request is more deserving.
