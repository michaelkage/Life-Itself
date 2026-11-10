# Integrated belief- and conditioning-aware NPC decisions

`IntegratedPsychologicalDecisionAdapter` combines three distinct inputs
for one observer:

1. Stable personal values and bias weights from `NPCValueProfile`.
2. Current social-belief confidence from `SocialBeliefSystem`, applied only
   through caller-authored claim-to-value and claim-to-bias mappings.
3. Learned cue associations from `NPCConditioningLedger`, scaled by
   authored cue sensitivity and explicit option exposure.

For each candidate, `IntegratedChoiceResult` retains the full
`BeliefAwareResult`, per-cue conditioning contributions, and final score.
The final score is the belief-aware appraisal score plus the sum of conditioned
cue contributions. Ranking is deterministic, with choice ID as the tie-breaker.

The adapter does not infer what a claim or cue means, decide whether a belief is
true, update learning, or execute a choice. Missing claims and missing cue
sensitivities are errors rather than silently invented information. Both the
belief system and conditioning ledger remain unchanged during ranking.

Tests: `tests/test_integrated_decisions.py`.
