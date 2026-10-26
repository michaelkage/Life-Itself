# Deterministic NPC Planning — First Implementation Slice

**Status:** implemented in the engine-independent Python reference layer. Execution against the live world, save/load integration, and C++ parity remain future work.

## Purpose

The goal system chooses what matters to an NPC. This planner answers a narrower question: given explicit current facts, a desired set of facts, and a catalog of possible actions, what is the lowest-cost valid action sequence?

## Contract

- `PlanningAction` declares stable action ID, preconditions, facts to add/remove, and a positive integer cost.
- `DeterministicPlanner` searches the declared state space with uniform action costs per edge and a least-total-cost priority queue.
- `PlanResult` returns success, ordered action IDs, total cost, number of expanded states, and a reason.
- Action IDs provide stable tie-breaking when plans have equal cost.
- Search is bounded by `max_expansions`; it never silently runs without a limit.
- The planner only reasons over supplied facts and declared effects. It does not infer facts, execute actions, or mutate NPCs/world state.
- A caller must revalidate preconditions before executing each action because the live world can change after planning.

## Limitations

This is a finite symbolic planner, not a full utility or behavior-tree system. It does not yet model continuous quantities, probabilistic outcomes, partial observability, resource accounting beyond action costs, action duration, interruption, or multi-agent coordination. Positive integer costs make search costs well-defined; the expansion budget protects against state explosion.

## Regression coverage

`tests/test_planning.py` covers least-cost selection, stable tie-breaking, preconditions, add/delete effects, already-satisfied goals, unsolvable states, budget exhaustion, and invalid action definitions.
