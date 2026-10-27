# NPC Choice Appraisal

## Purpose

`simreality/appraisal.py` lets the same event or hard choice be interpreted
differently by different NPCs. The caller supplies each option's predicted impacts
on named values (for example, loyalty, security, fairness, reputation, or autonomy)
and cues that may trigger a modeled bias (for example, authority or familiarity).

## Scoring

For each option, the appraiser sums the products of the NPC's value weights and
the option's matching impacts, then adds the products of bias weights and matching
bias cues. Missing dimensions contribute zero. Results include per-axis
contributions, so a decision can be explained and debugged.

The score is a relative preference estimate—not a probability, fact, or universal
moral verdict. The system deliberately has no built-in "good" or "bad" axis. Two
NPCs can rank the same options differently because their priorities and biases differ.

## Determinism and boundaries

- Axes are evaluated in sorted order; equal scores break ties by choice ID.
- Values must be finite numbers in [-1, 1]. Duplicate choice IDs are rejected.
- The appraiser is pure: it does not mutate NPC profiles, options, relationships,
  goals, or the world.
- This layer does not invent consequences or infer what an option means. The
  simulation supplies impacts and bias cues based on its own evidence and context.
- The score is not a confidence estimate. Uncertainty about evidence should be
  modeled separately rather than hidden inside this arithmetic.

## Example

```python
from simreality.appraisal import ChoiceOption, NPCAppraiser, NPCValueProfile

profile = NPCValueProfile(
    "witness-12",
    value_weights={"loyalty": 0.9, "security": 0.4, "fairness": 0.6},
    bias_weights={"authority": -0.5},
)
choices = [
    ChoiceOption("stay_silent", {"loyalty": 0.8, "security": -0.2}),
    ChoiceOption("tell_police", {"loyalty": -0.4, "security": 0.7},
                 {"authority": 0.5}),
]
for result in NPCAppraiser.rank(profile, choices):
    print(result.choice_id, result.score, result.value_contributions,
          result.bias_contributions)
```

This makes moral ambiguity a consequence of conflicting values and perceptions,
not a hard-coded morality meter.
