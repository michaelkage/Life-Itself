# NPC Social Conversations

`SocialConversationAdapter` connects an actual memory transfer through the existing
gossip conversation system to the listener's observer-specific belief ledger.

## Contract

- The caller supplies a stable conversation ID, listener, speaker, simulation tick,
  and optional district. The adapter does not choose who meets or talks.
- Memory transfer uses the existing `gossip.converse` behavior; this is not a
  second gossip implementation.
- Each transferred rumour is recorded as evidence for the listener. The listener's
  trust in the speaker is sampled when the rumour is observed.
- Rumour claims preserve attribution boundaries. If the rumour has lost its target
  ID, its claim key is event/action-level and does not name a suspect.
- Identical replay of the same conversation ID and inputs returns the stored result.
  Reusing the ID with different participants, tick, district, or speaker-memory
  content raises `ValueError`.
- Results are read-only records; `snapshot()` returns results sorted by conversation ID.
- This adapter does not establish objective truth or infer a universal moral meaning.

## Example

```python
from simreality import SocialBeliefSystem, SocialConversationAdapter, SocialTrustLedger

trust = SocialTrustLedger()
beliefs = SocialBeliefSystem(trust)
conversations = SocialConversationAdapter(trust, beliefs)
result = conversations.converse(
    "market-chat-001", listener=shopkeeper, speaker=guard,
    observed_tick=120, district_id="market",
)
```

Tests: `tests/test_social_conversations.py`.
