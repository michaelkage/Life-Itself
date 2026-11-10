# NPC psychological learning decisions

Event interpretation produces proposals, not facts and not automatic learning. The PsychologicalLearningDecisionLedger adds the explicit decision stage.

## Accept or reject

Call decide with a proposal, a stable decision ID, the decision tick, the owner's ConditioningProfile, and the shared NPCConditioningLedger.

- **Accept:** applies the proposal as one conditioning record at the decision tick. The original event tick remains provenance; learning never travels backward in simulation time.
- **Reject:** records the decision and rationale without changing the conditioning ledger.
- **Replay:** an identical decision ID and payload returns the existing decision. Reusing an ID with different content, or deciding the same event/owner/rule proposal twice, is rejected.
- **Conflicting experiences:** a later proposal from a different event may reinforce an opposing outcome for the same cue. The existing conditioning learning rate gradually shifts the association rather than rewriting history.

Accepted conditioning uses the stable record ID psych-learning:<decision_id>. On save/load, persist both the conditioning ledger and PsychologicalLearningDecisionSnapshot; restore the decision snapshot before accepting further decisions. This keeps the accepted/rejected history and applied associations aligned. A replayed decision is not applied again.

The ledger does not infer whether a proposal is true, force an NPC to accept it, or automatically generate a decision. The simulation or authored NPC policy must supply the decision and rationale.

Tests: tests/test_psychological_learning_decisions.py.
