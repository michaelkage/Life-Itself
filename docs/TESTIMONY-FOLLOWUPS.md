# Testimony follow-up planning

`TestimonyFollowUpPlanner` creates a deterministic, read-only shortlist of
witness/details to clarify. Contradictory accounts are included; corroborated
details can also appear when the observer has not formed a confident belief.

Priority is the product of testimony confidence and belief uncertainty. Unknown
beliefs and confidence near 0.5 are maximally unresolved; confident belief
reduces priority. This ranks investigative attention, not witness credibility or
objective truth. A minimum-priority threshold can filter the result.

The planner does not alter testimony, trust, beliefs, or the world. A caller
decides whether to ask a proposed question and records any resulting answer as a
new testimony record.
