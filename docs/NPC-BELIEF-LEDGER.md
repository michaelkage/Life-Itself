# NPC Belief Ledger

## Purpose

`simreality/beliefs.py` tracks how an NPC's confidence in an explicit claim changes
when it receives supporting or contradictory evidence. It complements choice
appraisal: beliefs describe what the NPC thinks may be true; appraisal describes
how that NPC evaluates possible choices.

## Evidence model

Each evidence record includes a stable evidence ID, claim ID, source ID, direction
(+1 support, -1 contradiction), strength, source reliability, and observation tick.
Strength and reliability are separate, explicit inputs in [0, 1].

Starting from a prior confidence (default 0.5 for unknown claims), each item moves
confidence toward 1 for support or 0 for contradiction by a fraction equal to
strength multiplied by source reliability. Evidence is replayed in canonical
(tick, evidence ID) order. The same evidence ID is idempotent when content matches
and rejected when its content differs.

## Boundaries and limitations

- This is a deterministic evidence ledger, not an oracle for objective truth.
- Source reliability must be supplied by the simulation; this module does not
  infer trustworthiness or decide whether a witness is biased.
- It does not change relationships, value weights, goals, or world state.
- The update is a transparent bounded heuristic, not a calibrated Bayesian posterior.
- Snapshot output is stable and suitable for serialization by a caller.

## Example

```python
from simreality.beliefs import BeliefLedger, Evidence

beliefs = BeliefLedger({"witness-saw-theft": 0.5})
beliefs.add(Evidence(
    evidence_id="interview-18",
    claim_id="witness-saw-theft",
    source_id="witness-4",
    direction=1,
    strength=0.8,
    source_reliability=0.7,
    observed_tick=120,
))
print(beliefs.get("witness-saw-theft"))
```

The same evidence can change different NPCs' beliefs differently in a later layer
by assigning NPC-specific priors and source reliability. This module keeps that
choice explicit rather than silently imposing a universal trust model.
