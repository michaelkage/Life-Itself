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


## Save-state snapshot

`TestimonyInquirySnapshot` wraps the ledger in its own versioned canonical
JSON envelope. Capture, serialize, parse, and restore preserve unanswered
questions, answers, refusals, and stable IDs. The snapshot validates canonical
encoding and delegates ledger invariants to the existing inquiry codec.


## World checkpoint integration

The optional `testimony_inquiries` argument to
`SimulationWorldCheckpoint.capture` embeds inquiry and response history in the
composite world save. Restoring a checkpoint returns the ledger as
`RestoredSimulation.testimony_inquiries`; omitting the argument preserves
backward-compatible checkpoints with no inquiry section.

Checkpoint validation rejects inquiries or responses dated after the world
clock, missing source events, inquiries asked before their source event, and
witness IDs that are not recorded witnesses for the source event. This keeps
investigation history tied to the authoritative event journal.


## Materialization adapter

`TestimonyMaterializationAdapter.materialize` appends an answered inquiry to a
caller-provided `TestimonyLedger` using a caller-provided stable testimony ID and
recording hour. Repeating the same materialization is idempotent through the
ledger's existing ID semantics; reusing that ID for different record content is
rejected. Unanswered inquiries and refusals remain in the inquiry history and
produce no testimony record. The adapter does not choose inquiries, answer
questions, or infer witness facts.


## End-to-end inquiry pipeline

`InquiryInvestigationPipeline.process` materializes an answered inquiry, analyzes
all testimony for that event, and applies the resulting corroboration or
contradiction evidence to the caller-selected observer's `SocialBeliefSystem`.
The caller supplies inquiry/testimony IDs, recording hour, observer ID, and
observed tick. Existing replay-safe ledgers and evidence IDs make repeated
processing safe; refusals create neither testimony nor belief claims. The
pipeline never chooses a witness answer or resolves conflicting accounts into
one objective truth.
