# Institutional response options

`simreality/institutional_response.py` adds a pure mapping layer between an
`InstitutionalReviewAssessment` and the options an institution makes available.

## Options, not automatic outcomes

An institution defines a complete response catalog for all four review levels.
For example, a workplace can offer a private check-in and ask about barriers at
the check-in level; a formal review can offer fact-finding, a schedule review,
and a chance to request an accommodation. The options are policy-specific and
are returned in stable configured order.

The planner does not select an option, execute it, alter a person's job or
appointment, or imply that a review level proves misconduct. Even an urgent
review only presents the institution's configured options. A separate NPC or
institutional decision-maker must choose what to do. If an option is enacted,
the simulation should record that as a separate world event with its own
evidence and consequences.

Supportive options are explicitly tagged, making it possible for downstream
decision systems to distinguish support from process-oriented actions without
assuming that one category is always appropriate.

See `tests/test_institutional_response.py` for coverage.
