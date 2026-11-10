# Personality-Conditioned Emotional Appraisal

PersonalityEmotionAdapter connects a cue-triggered emotional memory response to an NPC's durable identity profile. It applies only explicit PersonalityEmotionRule mappings from a signed personality trait to a named emotion axis.

For each memory contribution, the modifier is clamp(trait value × rule coefficient × trait sensitivity, -1, 1). The adjusted contribution is the source intensity multiplied by (1 + modifier), then clamped to [0, 1]. A positive modifier amplifies the response; a negative modifier attenuates it. A modifier of -1 suppresses that contribution completely. Unmapped emotion axes pass through unchanged. When multiple traits map to one emotion axis, their adjusted contributions are summed and the axis total is capped at 1.

The result preserves memory and association provenance, trait value, authored coefficient, sensitivity, and applied modifier. Duplicate mappings for the same personality/emotion pair are rejected.

This is a read-only appraisal stage. It does not mutate personality, autobiographical memory, the source emotional response, or the emotional event ledger. It does not infer cues, select behavior, or guarantee outward expression. A caller may explicitly pass the conditioned intensity snapshot into the existing emotional-state update pipeline.

Personality profiles and rules are authored configuration; durable identity traits continue to be persisted by the existing identity decision system. The output is a derived snapshot and need not be persisted independently if its inputs and simulation tick can be reproduced.

Tests: tests/test_personality_emotion.py.
