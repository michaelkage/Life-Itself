# NPC stress checkpoint integration

`SimulationWorldCheckpoint.capture(..., stress=ledger)` optionally stores the
canonical stress snapshot. Restored worlds expose it as
`RestoredSimulation.stress`.

The checkpoint validates stress owners against the NPC roster, verifies every
stressor record against the authoritative world event journal, confirms the
NPC was a participant or witness, and rejects records or ledger ticks later
than the checkpoint clock. Older checkpoints without a stress section remain
valid and restore `stress=None`.

The codec is schema-versioned and canonical. Coping profiles remain authored
configuration and should be reattached by the simulation setup after loading;
the saved ledger preserves accumulated values and stressor replay history.

Tests: `tests/test_emotional_stress_checkpoint.py`.
