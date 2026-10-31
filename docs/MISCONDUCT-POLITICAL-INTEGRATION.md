# Misconduct-to-politics integration

`simreality/misconduct_politics.py` connects the existing append-only
`MisconductReportingSystem` to institutional political history without
collapsing a report into a verdict.

## Explicit department mapping

A report identifies a person, not an organisational department. The caller must
supply `department_id` when asking `MisconductPoliticalBridge` to assess a
report status. The bridge never guesses an employee's department.

## Separate events for filing and review

The bridge emits one outcome for the original report with finding status
`alleged`, followed by one outcome for every review decision in its history.
Review outcomes map as follows:

| Review outcome | Political finding status |
| --- | --- |
| filed | alleged |
| under review | under_review |
| substantiated | substantiated |
| not substantiated | not_substantiated |
| insufficient evidence | insufficient_evidence |
| dismissed | dismissed |

Each review decision remains a separate dated event. If a later review changes
the finding, policy can define a separate effect for that later status; prior
history is not rewritten. No political effect occurs unless an exact
misconduct-type/finding-status rule exists in the supplied
`InstitutionalOutcomePolicy`.

The bridge retains incident IDs and review evidence IDs as provenance labels.
It does not independently verify those records or determine the correctness of
the review decision.

## Replay

Report and review outcomes use stable IDs derived from their source report or
decision IDs. The outcome adapter signs the input and matching policy rule;
the political ledger makes exact replay idempotent and rejects conflicting
reuse. Tests: `tests/test_misconduct_politics.py`.
