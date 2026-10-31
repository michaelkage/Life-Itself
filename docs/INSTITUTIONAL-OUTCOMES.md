# Institutional outcome dynamics

`simreality/institutional_outcomes.py` translates explicit institutional
outcomes into the existing event-sourced political ledger. It is a policy
adapter, not an automatic truth detector or story generator.

## Outcome inputs

An `InstitutionalOutcome` identifies:

- the institution, period, outcome type, and affected department;
- an explicit finding status;
- an optional related department for alliance/rivalry effects;
- an optional leadership priority tag; and
- zero or more evidence IDs supplied by the caller.

Supported finding-status labels are `alleged`, `corroborated`,
`substantiated`, `not_substantiated`, `insufficient_evidence`,
`confirmed`, `retracted`. These labels are classifications supplied by the
simulation's review process; this adapter does not decide whether evidence is
authentic or sufficient.

## Policy-controlled effects

An `InstitutionalOutcomePolicy` contains exact-match rules keyed by
(`outcome_type`, `finding_status`). A rule can change:

- the affected department's influence;
- the signed relationship between that department and an explicitly named
  related department; and
- a leadership priority, when a priority tag is supplied.

There is no implicit penalty for an allegation. If no matching rule exists,
the resulting political event has zero effect. Designers can therefore make an
allegation trigger an inquiry without treating it as proof, give a substantiated
finding a consequence, or define a different response when a complaint is
not substantiated or retracted.

Example outcome types include `project_success`, `scandal`,
`public_complaint`, and `leadership_change`; these are ordinary explicit
labels rather than hard-coded special cases. Leadership changes only affect
the modeled state when a policy rule says how influence, relationships, or
priorities should shift.

## Replay and persistence

The adapter creates an `InstitutionalPoliticalEvent` with ID
`outcome:<outcome_id>`. Its rationale contains a SHA-256 signature of the
complete outcome and matched policy rule. Repeating the same assessment is
idempotent through the political ledger; reusing an outcome ID with changed
outcome or policy inputs is rejected by the ledger's conflicting-ID check.
The existing political ledger snapshot and optional world-checkpoint section
therefore preserve committed effects without a second persistence format.

## Boundaries

Evidence IDs are retained as provenance labels but are not resolved against an
evidence registry here. A separate review process must set the finding status.
The adapter does not automatically create investigations, dismiss employees,
appoint leaders, allocate budgets, or execute projects. It only emits the
political effects explicitly configured by the policy. Tests:
`tests/test_institutional_outcomes.py`.
