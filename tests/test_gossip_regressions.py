"""Regression tests for gossip transfer edge cases not covered by the original suite."""

import unittest

from simreality import ActionTag, Description, NPC, NPCMemory, Rumour, converse


def memory(target, retention=0.9):
    return NPCMemory(
        witness_id="witness",
        target_entity_id=target,
        initial_impact=1.0,
        retention=retention,
        timestamp_hour=12.0,
        action_tag=ActionTag.CRIME_THEFT,
        description=Description(
            height_m=1.8,
            jacket_colour_weights={"black": 0.8},
        ),
    )


class TestGossipMemoryTargeting(unittest.TestCase):
    def test_conflicting_identity_reports_remove_attribution(self):
        first = Rumour(
            action_tag=ActionTag.CRIME_THEFT.value,
            target_entity_id="target-a",
            description=Description(height_m=1.8, height_uncertainty_m=0.3),
            retention=0.9,
            district_id="D1",
        )
        second = Rumour(
            action_tag=ActionTag.CRIME_THEFT.value,
            target_entity_id="target-b",
            description=Description(height_m=1.82, height_uncertainty_m=0.3),
            retention=0.8,
            district_id="D1",
        )

        combined = first.corroborate(second)

        self.assertIsNone(combined.target_entity_id)
        self.assertEqual(combined.corroborations, 2)
        self.assertLess(combined.description.height_uncertainty_m, 0.3)

    def test_corroboration_does_not_replace_unrelated_last_memory(self):
        listener = NPC(entity_id="listener")
        listener.memories = [
            memory("target"),
            memory("unrelated-target"),
        ]
        speaker = NPC(entity_id="speaker")
        speaker.memories = [memory("target")]

        converse(listener, speaker, "D1")

        self.assertEqual(len(listener.memories), 2)
        self.assertEqual(listener.memories[0].target_entity_id, "target")
        self.assertEqual(listener.memories[1].target_entity_id, "unrelated-target")
        self.assertEqual(listener.memories[1].description.height_m, 1.8)


if __name__ == "__main__":
    unittest.main()
