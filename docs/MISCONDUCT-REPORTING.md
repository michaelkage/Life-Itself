# Misconduct Reporting and Institutional Accountability

**Status:** Engine-independent reporting core and canonical persistence are implemented. Reports can be included in the composite world checkpoint, with incident references validated against the authoritative event ledger. No automatic misconduct detection or policing simulation is implied.

## Purpose

The simulation can represent discrimination, racial discrimination, corruption, abuse of authority, neglect of duty, bribery, and favouritism as reportable conduct. This module records an allegation and its subsequent review without declaring guilt merely because a report exists.

## Records

- `MisconductReport`: report ID, filing tick, subject, institution, allegation category, incident references, description, and optional reporter identity. Anonymous reports must not store a reporter ID.
- `ReviewDecision`: reviewer, tick, outcome, evidence references, and rationale.
- `ReportStatus`: the original report, current status, latest decision, and complete decision history.

Outcomes distinguish filed, under review, substantiated, not substantiated, insufficient evidence, and dismissed. Filing is not a finding. “Insufficient evidence” is not the same as a proven false allegation.

## Deterministic behavior

Report and decision IDs are idempotent when reused with identical content and rejected when reused with conflicting content. Decisions must reference an existing report and cannot predate it; decision history cannot move backward in time. Batch insertion validates before mutation.

The module does not infer misconduct from race, neighbourhood, job title, report volume, or an NPC's reputation. It does not decide guilt, automatically punish anyone, or assume reviewers are unbiased. Those are separate simulation systems requiring explicit evidence, institutional rules, incentives, and possible corruption within the review process itself.

## Next integration work

1. Add institutional policy, investigation capacity, conflicts of interest, evidence tampering, whistleblower protection, and appeal records.
2. Model enforcement and public service allocation as stateful resource decisions. Differences between neighbourhoods should emerge from budget, staffing, influence, prejudice, corruption, priorities, and recorded decisions—not a hard-coded rule that poor areas deserve less protection.
3. Provide a player-facing report action and clear status history once the game UI exists.

## Regression coverage

`tests/test_misconduct.py` covers allegation-versus-finding, review history, anonymous reporting, distinct evidence outcomes, conflicting IDs, unknown references, and time ordering. `tests/test_misconduct_save_state.py` covers canonical JSON, complete review-history round trips, schema validation, and missing world-event references. `tests/test_world_checkpoint.py` covers optional checkpoint integration and round-trip replay.
