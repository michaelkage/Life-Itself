# Context-aware institutional review

`simreality/institutional_review.py` is a deterministic, read-only decision layer
on top of `RoutineInstitutionLedger`. It converts explicit accumulated records
into one of four configurable review levels: no review, check-in, formal review,
or urgent review.

## What it does and does not mean

A level is a recommendation to examine a situation, **not** a verdict, diagnosis,
employment decision, or automatic punishment. The evaluator does not change
institutional records, fire an NPC, cancel an appointment, alter wages, or infer
the reason behind an absence.

The policy explicitly weights recorded late arrivals, missed appointments, and
total recorded delay. Total delay contribution is capped. Optional
`ContextAdjustment` inputs can raise or lower the score for named, explained
context such as a documented transit disruption, illness, a care obligation,
clear prior notice, or ignored contact attempts. The simulation caller is
responsible for establishing whether a signal is actually supported; merely
naming an adjustment is not evidence.

Every component of the score is returned as a stable, inspectable contribution.
Context signals are sorted by stable ID, duplicate IDs are rejected, and
reordering inputs does not change the result. A negative adjustment cannot push
the final score below zero, but it does not erase the underlying history.

## Example

```python
from simreality.institutional_review import (
    ContextAdjustment, InstitutionalReviewEvaluator, InstitutionalReviewPolicy,
)
from simreality.routine_institution_ledger import InstitutionalRecord

policy = InstitutionalReviewPolicy("workplace-standard")
evaluator = InstitutionalReviewEvaluator(policy)
record = InstitutionalRecord("bakery", "npc-17", late_arrivals=3, total_delay_minutes=95)
assessment = evaluator.assess(record, (
    ContextAdjustment("transit", -1.5, "Verified transit disruption affected the shift."),
))
print(assessment.level, assessment.score, assessment.contributions)
```

The same person can receive different assessments from different institutions
because each institution supplies its own policy. This is an explicit rules
model, not a universal morality score or a claim that the institution is fair.
Regression coverage is in `tests/test_institutional_review.py`.
