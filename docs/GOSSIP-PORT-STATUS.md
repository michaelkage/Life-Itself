# Gossip and rumour propagation port status

This branch ports the engine-independent Python gossip reference into the C++ core.

## Behaviour covered

- A memory at or above the telephone threshold (0.6) retains the target identity.
- Below 0.6, retelling drops identity but preserves the physical description.
- Attributed memories at or below 0.05 are not transmitted; unattributed memories at or below 0.01 are not transmitted.
- Corroboration merges descriptions, combines retention, and removes attribution when reported target IDs conflict.
- NPC conversations transfer rumours and update a matching listener memory rather than blindly overwriting the final memory in the list.
- Police pursue identification when attribution and retention are sufficient, stop/search when jacket confidence is high, and otherwise log insufficient detail.

## Validation added

- C++ regression coverage for attribution/floor boundaries, identity conflict, description sharpening, memory targeting, and all three police response outcomes.
- Python regression coverage for preserving unrelated listener memories during corroboration.
- GitHub Actions workflow runs the Python unittest suite and the CMake/CTest C++ suite on the feature branch and pull requests to main.

## Current limitation

The tests are committed but have not been observed passing in a completed CI run yet. Do not treat the port as verified until the workflow reports success.
