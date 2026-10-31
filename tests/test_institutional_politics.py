import unittest

from simreality.institutional_politics import (
    InstitutionalPoliticalEvent,
    InstitutionalPoliticalLedger,
)


class InstitutionalPoliticalLedgerTests(unittest.TestCase):
    def event(self, event_id, **kwargs):
        defaults = dict(
            institution_id="city_hall",
            period_index=1,
            department_id="planning",
            influence_delta=0.1,
            rationale="public project delivery",
        )
        defaults.update(kwargs)
        return InstitutionalPoliticalEvent(event_id, **defaults)

    def test_department_influence_and_priorities_evolve(self):
        ledger = InstitutionalPoliticalLedger(
            "city_hall",
            initial_influence=(("planning", 0.4),),
            leadership_priorities=(("housing", 0.3),),
        )
        ledger.append(self.event(
            "lobby-1", influence_delta=0.2,
            priority_tag="housing", leadership_priority_delta=0.25,
        ))
        state = ledger.state()
        self.assertEqual(dict(state.department_influence)["planning"], 0.6)
        self.assertEqual(dict(state.leadership_priorities)["housing"], 0.55)

    def test_relationships_are_symmetric_and_signed(self):
        ledger = InstitutionalPoliticalLedger("city_hall")
        ledger.append(self.event(
            "alliance", department_id="planning",
            other_department_id="transport", relationship_delta=0.6,
            influence_delta=0.0,
        ))
        ledger.append(self.event(
            "dispute", department_id="transport",
            other_department_id="planning", relationship_delta=-0.2,
            influence_delta=0.0, period_index=2,
        ))
        self.assertEqual(ledger.state().department_relationships,
                         (("planning", "transport", 0.39999999999999997),))

    def test_append_order_does_not_change_replayed_state(self):
        events = (
            self.event("b", period_index=2, influence_delta=-0.1),
            self.event("a", period_index=1, influence_delta=0.2),
        )
        first = InstitutionalPoliticalLedger("city_hall")
        second = InstitutionalPoliticalLedger("city_hall")
        first.append_many(events)
        second.append_many(tuple(reversed(events)))
        self.assertEqual(first.state(), second.state())

    def test_identical_event_retry_is_idempotent(self):
        ledger = InstitutionalPoliticalLedger("city_hall")
        event = self.event("once")
        ledger.append(event)
        before = ledger.state()
        ledger.append(event)
        self.assertEqual(ledger.state(), before)
        self.assertEqual(len(ledger.events), 1)

    def test_conflicting_event_id_is_rejected(self):
        ledger = InstitutionalPoliticalLedger("city_hall")
        ledger.append(self.event("same"))
        with self.assertRaises(ValueError):
            ledger.append(self.event("same", influence_delta=0.2))

    def test_snapshot_round_trip_preserves_history_and_state(self):
        ledger = InstitutionalPoliticalLedger(
            "city_hall", initial_influence=(("planning", 0.4),),
            leadership_priorities=(("housing", 0.3),),
        )
        ledger.append(self.event(
            "coalition", other_department_id="transport",
            relationship_delta=0.5, priority_tag="housing",
            leadership_priority_delta=0.1,
        ))
        restored = InstitutionalPoliticalLedger.from_snapshot(ledger.snapshot())
        self.assertEqual(restored.state(), ledger.state())
        self.assertEqual(restored.events, ledger.events)

    def test_rejects_cross_institution_events_and_bad_relationships(self):
        ledger = InstitutionalPoliticalLedger("city_hall")
        with self.assertRaises(ValueError):
            ledger.append(self.event("foreign", institution_id="court"))
        with self.assertRaises(ValueError):
            self.event("self", other_department_id="planning", relationship_delta=0.2)
        with self.assertRaises(ValueError):
            self.event("orphan", priority_tag=None, leadership_priority_delta=0.2)

    def test_effects_are_clamped_to_valid_ranges(self):
        ledger = InstitutionalPoliticalLedger(
            "city_hall", initial_influence=(("planning", 0.9),),
        )
        ledger.append(self.event("boost", influence_delta=0.5))
        self.assertEqual(dict(ledger.state().department_influence)["planning"], 1.0)


if __name__ == "__main__":
    unittest.main()
