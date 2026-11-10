# NPC familiarity and recognition

`SocialFamiliarityLedger` records directed exposure: how familiar one NPC is
with another. Every confirmed encounter is bilateral, but exposure strengths
are independently supplied for each direction. A distracted NPC and an
attentive NPC can therefore leave the same meeting with different familiarity.

Repeated exposures compound as `1 - product(1 - strength)`. The ledger also
supports historical queries through a tick and stable observation IDs for
idempotent replay. It is deliberately separate from `SocialTrustLedger`:
familiarity does not imply trust, affection, agreement, or moral approval.

`PresenceFamiliarityAdapter.observe_encounter` accepts an existing encounter
ID and requires exactly two directional exposure strengths. It cannot create
familiarity from mere co-location or an unconfirmed encounter.

Recognition is assessed separately. The caller must provide an explicit
`identity_cue_available` signal (for example, a clear face, known voice, or
distinctive identifying feature) and a threshold. Without an identity cue,
even a highly familiar NPC does not automatically identify someone. The
assessment returns the familiarity value and a reason.

`SocialFamiliaritySnapshot` stores the complete directional observation
history in canonical JSON. Composite world-checkpoint integration keeps the
history alongside its source encounter records.

Tests: `tests/test_social_familiarity.py`.
