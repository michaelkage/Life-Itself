# Institutional lobbying and coalitions

`simreality/institutional_lobbying.py` adds an explicit political action layer
on top of the institutional political-history ledger.

## How it works

A department submits a `PoliticalLobbyRequest` describing a requested change to
a leadership priority. The request includes public-service impact, evidence,
transparency, urgency, public visibility, personal advantage, and departments
that explicitly support or oppose it.

`InstitutionalLobbyEvaluator` reads the current ledger state and produces a
transparent assessment:

- The department's accumulated influence affects its reach.
- Existing positive relationships strengthen named supporters.
- Existing negative relationships amplify the effect of named opponents.
- Service impact and evidence strengthen a request.
- Accountability makes transparency more important and personal advantage more costly.
- Public visibility matters only when the institution's political-pressure setting gives it weight.

A configured `PoliticalLobbyPolicy` supplies the weights and approval/defer
thresholds. The evaluator returns approved, deferred, or rejected; it does not
silently enact a request.

## Committing outcomes

Call `InstitutionalLobbyEvaluator.commit(ledger, assessments)` to append the
resulting events to the existing `InstitutionalPoliticalLedger`. Approved
requests change the named leadership priority and modestly increase the
requesting department's influence. Rejected requests modestly reduce influence.
Deferred requests leave both unchanged. The event IDs are derived from request
IDs, so committing the same assessment again is idempotent and conflicting
reuse is rejected by the ledger.

Batch assessments are all calculated against the same pre-resolution state and
returned in stable request-ID order. This avoids one department gaining an
unintended advantage merely because its request was processed first.

## Boundaries

This is a policy-driven simulation model, not a claim that real institutions
always behave this way. It does not invent supporters, infer motives from
identity, or automatically create alliances. NPCs or other simulation systems
must explicitly choose to lobby and name their coalition positions. It does not
yet model private negotiation dialogue, leadership succession, or the complete
resource-allocation cycle. Committed events are preserved by the existing
institutional political ledger and its world-checkpoint integration.
