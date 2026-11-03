# Testimony belief queries

`TestimonyBeliefQueryAdapter` provides a read-only query for an NPC's belief
about a particular event attribute and reported value. It uses the same stable
claim ID convention as `TestimonyBeliefAdapter`.

Unknown claims return `known=False` and `confidence=None`; no neutral prior is
invented. Known confidence remains a subjective observer state, not a truth
judgment. The convenience `believes` property returns true at confidence >= 0.65,
false at <= 0.35, and unknown in between. Dialogue can use this to select
follow-up questions or wording without asserting the account is objectively true.

Queries do not mutate beliefs, trust, testimony, or evidence.