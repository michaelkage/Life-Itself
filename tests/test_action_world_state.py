"""Action world-state validation and in-place checkpoint restoration tests."""
import unittest

from simreality.action_world_state import ActionWorldState


class ActionWorldStateTests(unittest.TestCase):
    def test_checkpoint_restore_preserves_nested_live_container_identity(self):
        facts = {"available"}
        resources = {"energy": 7.5}
        state = ActionWorldState({"npc-a": facts}, {"npc-a": resources})
        payload = state.to_json()
        facts.add("mutated")
        resources["energy"] = 1.0
        state.restore_json(payload)
        self.assertIs(state.world_facts_by_owner["npc-a"], facts)
        self.assertIs(state.resources_by_owner["npc-a"], resources)
        self.assertEqual(facts, {"available"})
        self.assertEqual(resources, {"energy": 7.5})

    def test_rejects_mismatched_owner_rosters(self):
        with self.assertRaisesRegex(ValueError, "same owners"):
            ActionWorldState({"npc-a": set()}, {})

    def test_rejects_non_finite_resource_balances(self):
        with self.assertRaisesRegex(ValueError, "finite and non-negative"):
            ActionWorldState({"npc-a": set()}, {"npc-a": {"energy": float("nan")}})

    def test_restore_rejects_duplicate_owner_records(self):
        state = ActionWorldState()
        with self.assertRaisesRegex(ValueError, "duplicate action world-state owner"):
            state.restore_json(
                '{"owners":[{"owner_id":"npc-a","resources":[],"world_facts":[]},'
                '{"owner_id":"npc-a","resources":[],"world_facts":[]}],"schema_version":1}'
            )


if __name__ == "__main__":
    unittest.main()
