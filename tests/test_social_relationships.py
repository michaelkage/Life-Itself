import json
import unittest

from simreality.social_relationships import (
    RELATIONSHIP_FACETS, RelationshipChange, SocialRelationshipLedger,
    SocialRelationshipSnapshot,
)


def change(change_id, observer="a", target="b", facet="warmth", delta=0.4,
           tick=1, event="event-1", tag=""):
    return RelationshipChange(change_id, event, observer, target, tick, facet, delta, tag)


class SocialRelationshipTests(unittest.TestCase):
    def test_facets_coexist_without_collapsing_to_one_moral_score(self):
        ledger = SocialRelationshipLedger((
            change("warm", facet="warmth", delta=0.8),
            change("resent", facet="resentment", delta=0.7),
            change("fear", facet="fear", delta=0.3),
        ))
        state = ledger.relationship("a", "b")
        self.assertAlmostEqual(state.value("warmth"), 0.8)
        self.assertAlmostEqual(state.value("resentment"), 0.7)
        self.assertAlmostEqual(state.value("fear"), 0.3)
        self.assertEqual(len(state.facets), len(RELATIONSHIP_FACETS))

    def test_relationships_are_directional(self):
        ledger = SocialRelationshipLedger((
            change("a-b", "a", "b", "respect", 0.9),
            change("b-a", "b", "a", "respect", 0.1),
        ))
        self.assertAlmostEqual(ledger.relationship("a", "b").value("respect"), 0.9)
        self.assertAlmostEqual(ledger.relationship("b", "a").value("respect"), 0.1)

    def test_explicit_changes_are_bounded_and_can_recede(self):
        ledger = SocialRelationshipLedger((
            change("up", delta=0.9),
            change("more", delta=0.8, tick=2),
            change("down", delta=-0.6, tick=3),
        ))
        self.assertAlmostEqual(ledger.relationship("a", "b").value("warmth"), 0.4)
        self.assertAlmostEqual(ledger.relationship("a", "b", through_tick=2).value("warmth"), 1.0)

    def test_replay_is_idempotent_and_conflicts_rejected(self):
        ledger = SocialRelationshipLedger()
        item = change("stable")
        self.assertEqual(ledger.add(item), item)
        self.assertEqual(ledger.add(item), item)
        with self.assertRaisesRegex(ValueError, "reused"):
            ledger.add(change("stable", delta=0.5))
        self.assertEqual(len(ledger.snapshot()), 1)

    def test_invalid_facet_delta_and_self_relationship_rejected(self):
        with self.assertRaises(ValueError):
            change("bad", facet="goodness")
        with self.assertRaises(ValueError):
            change("bad", delta=1.1)
        with self.assertRaises(ValueError):
            change("bad", observer="a", target="a")

    def test_snapshot_round_trip_is_canonical(self):
        ledger = SocialRelationshipLedger((
            change("z", facet="respect", delta=0.6),
            change("a", facet="resentment", delta=0.2, tick=2),
        ))
        snapshot = SocialRelationshipSnapshot.capture(ledger)
        payload = snapshot.to_json()
        restored = SocialRelationshipSnapshot.from_json(payload).restore()
        self.assertEqual(restored.snapshot(), ledger.snapshot())
        self.assertEqual(SocialRelationshipSnapshot.capture(restored).to_json(), payload)

    def test_snapshot_rejects_noncanonical_payload(self):
        payload = json.dumps({"schema_version": 1, "changes": []}, indent=2)
        with self.assertRaisesRegex(ValueError, "canonical"):
            SocialRelationshipSnapshot.from_json(payload)


if __name__ == "__main__":
    unittest.main()
