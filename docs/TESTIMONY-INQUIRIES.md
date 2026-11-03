# Investigator inquiries and witness responses

`TestimonyInquiryLedger` stores explicit questions and responses with stable
IDs. Identical replay is idempotent; conflicting responses cannot overwrite
history; responses cannot predate their questions. Both questions and responses
round-trip through canonical versioned JSON.

`TestimonyInquiryAdapter.ask` turns one caller-selected
`TestimonyFollowUp` proposal into a persisted inquiry. The investigator
supplies the inquiry ID and tick. The adapter never chooses a proposal, contacts
a witness, or invents a response; reusing an inquiry ID with different content
is rejected by the ledger.

Answered inquiries can be materialized as ordinary `TestimonyRecord` instances
and appended to the existing testimony ledger, so analysis and belief adapters
continue to use one testimony pipeline. Refusals are retained in inquiry history
but do not fabricate a factual testimony detail.
