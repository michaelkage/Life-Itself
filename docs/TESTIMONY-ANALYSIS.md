# Witness testimony analysis

`TestimonyAnalyzer` compares stored accounts for one event without changing
the objective event journal, witness recall, or testimony ledger.

- Accounts are grouped by event and detail attribute key.
- Two distinct witnesses stating equal values produce corroboration.
- Different values for the same attribute produce a contradiction candidate.
- Missing/omitted details are unknown and do not count as disagreement.
- Repeated accounts from the same witness are not compared against one another.
- Each match reports both account IDs and confidence decayed to the inquiry hour.
- Confidence decay affects evidentiary strength metadata, not whether values differ.
- Output ordering is canonical and independent of ledger insertion order.

This is a deterministic comparison layer, not an adjudicator: it does not decide
which witness is truthful, infer unstated facts, or automatically alter NPC beliefs.
