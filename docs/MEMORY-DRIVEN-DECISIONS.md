# Memory-Driven Decision Influence

MemoryDecisionInfluenceAdapter converts recalled autobiographical memories into bounded, owner-specific choice-appraisal contributions.

## Explicit association

Each MemoryChoiceAssociation links one owner-owned memory to one candidate choice and supplies signed sensitivity in [-1, 1]. Positive sensitivity increases that choice's score when the memory is recalled; negative sensitivity decreases it. The engine does not infer a universal reaction from memory tags, emotional impact, or event severity.

## Evaluation

Only memories present in the current MemoryRecallResult can contribute. Each contribution is recall score multiplied by authored sensitivity. Multiple recalled memories associated with one choice accumulate, then the aggregate is proportionally bounded to [-1, 1] so the memory subsystem cannot overwhelm other appraisal inputs. Output preserves per-memory provenance.

The result is read-only and can be passed into IntegratedPsychologicalDecisionAdapter. It does not execute a choice, mutate a memory, change personality, or guarantee behavior.

Tests: tests/test_memory_decisions.py.
