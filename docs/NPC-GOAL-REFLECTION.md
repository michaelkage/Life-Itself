# NPC Goal Reflection and Counterfactual Reasoning

`NPCGoalReflectiveReasoner` adds a read-only reflection pass after a terminal `NPCPlanEvaluation`. It preserves the original plan, action records, and world events. It does not change a goal, rewrite autobiographical memory, commit a new plan, or claim that a plausible cause is proven.

## Evidence-bounded causal attribution

A `GoalReflectionRule` maps exact action-deviation flags and exact world-event types to four candidate causes:
- `own_decision`: a mapped execution deviation associated with the NPC's own plan.
- `insufficient_resources`: only when the caller supplies a measured `(resource, required, available)` shortfall.
- `another_npc`: only when a mapped event includes a participant other than the reflecting NPC.
- `changed_circumstances`: an explicitly mapped authoritative event type.

No cause is inferred from free-form memory prose. Missing evidence and future evidence are rejected. Unmapped event types have no causal effect. If no rule matches, the result is `undetermined` rather than a fabricated explanation. These are supported attributions under authored rules, not statistical proof of causality.

## Counterfactual plan comparison

`GoalReflectionAlternative` defines a named alternative by excluding a canonical set of action IDs. The reasoner runs the existing deterministic planner against the supplied current facts and goal facts using the remaining authored actions. It reports route feasibility, action sequence, cost, and cost delta against the evaluated plan's declared action costs.

Counterfactuals are hypothetical planning results, not historical events and not proof that the alternative would have succeeded in the original world. The caller supplies the live fact snapshot and an explicit maximum number of alternatives; each search remains bounded by the planner expansion budget.

## Persistence and agency

The reflection is a deterministic derived projection. Persist the authoritative source ledgers and rebuild it after restore. It never silently updates beliefs or goals. A later integration may feed accepted reflection results into authored memory or arbitration policies, but this layer itself only explains and compares.

Tests: `tests/test_npc_goal_reflection.py`.