# Belief-Aware NPC Choice Appraisal

## Purpose

`simreality/belief_appraisal.py` connects the evidence ledger to value-relative
choice appraisal without hiding the connection. Beliefs affect a choice only
when the simulation explicitly maps a claim to a value axis or bias cue.

## Rule

For claim confidence (c), the signed belief signal is (2c - 1). A caller-defined
coefficient (w), constrained to [-1, 1], contributes (w(2c - 1)) to a named
value impact or bias cue. The adjusted option is then scored by the existing
`NPCAppraiser`.

- Confidence 0.5 is neutral.
- Confidence 1 contributes the coefficient.
- Confidence 0 contributes its negative.
- Multiple claims are applied in sorted claim/axis order.
- Every claim-level adjustment is returned for inspection.
- Missing claim IDs raise `KeyError`; the layer does not silently invent a prior.

## Boundaries

This is an explicit integration seam, not an automatic psychology model. The caller
must decide what a claim means for an option and which value or bias it affects.
It does not infer truth, update evidence, mutate the ledger, or declare choices
morally good or bad. It also does not alter source reliability or relationships.
