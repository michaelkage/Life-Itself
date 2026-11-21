import unittest

from simreality.action_execution import ActionExecution
from simreality.household_economy import (
    ActionEconomicEffect, EconomicAccount, EconomicActionAdapter,
    EconomicLedger, EconomicTransfer, HouseholdLedger, HouseholdObligation,
)


class HouseholdEconomyTests(unittest.TestCase):
    def setUp(self):
        self.economics = EconomicLedger((
            EconomicAccount("employer", "business-1", "business_cash"),
            EconomicAccount("worker", "npc-1", "wallet"),
            EconomicAccount("rent", "landlord-1", "receivable"),
            EconomicAccount("home", "household-1", "household_cash"),
        ))
        self.economics._balances["employer"] = 100.0
        self.economics._balances["home"] = 40.0

    def test_double_entry_transfer_is_replay_safe_and_balanced(self):
        transfer = EconomicTransfer("wage-1", 1, "employer", "worker", 25, "payroll")
        self.economics.transfer(transfer)
        self.assertEqual(self.economics.balance("employer"), 75.0)
        self.assertEqual(self.economics.balance("worker"), 25.0)
        self.assertEqual(self.economics.transfer(transfer), transfer)
        self.assertEqual(len(self.economics.snapshot()), 1)
        with self.assertRaisesRegex(ValueError, "conflicting transfer replay"):
            self.economics.transfer(EconomicTransfer("wage-1", 1, "employer", "worker", 20, "payroll"))

    def test_insufficient_funds_and_currency_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError, "insufficient funds"):
            self.economics.transfer(EconomicTransfer("bad", 1, "worker", "rent", 1, "rent"))
        self.economics.add_account(EconomicAccount("foreign", "x", "cash", "tokens"))
        with self.assertRaisesRegex(ValueError, "cross-currency"):
            self.economics.transfer(EconomicTransfer("fx", 1, "employer", "foreign", 1, "unsupported"))

    def test_household_obligation_settlement_posts_transfer_once(self):
        household = HouseholdLedger(self.economics)
        obligation = HouseholdObligation("rent-apr", "household-1", "home", "rent", 30, 4, "monthly rent")
        household.add(obligation)
        settled = household.settle("rent-apr", 4)
        self.assertEqual(settled.status, "settled")
        self.assertEqual(self.economics.balance("home"), 10.0)
        self.assertEqual(self.economics.balance("rent"), 30.0)
        self.assertEqual(household.settle("rent-apr", 4), settled)
        self.assertEqual(len(self.economics.snapshot()), 1)

    def test_completed_action_applies_explicit_wage_effect(self):
        adapter = EconomicActionAdapter(
            self.economics,
            (ActionEconomicEffect("work_shift", "employer", "worker", 15, "wage"),),
        )
        execution = ActionExecution(
            "exec-1", "npc-1", 2, "work_shift", "completed", "done",
            ("ready",), ("paid",), (("energy", 5.0),), (("energy", 3.0),),
            "event-1",
        )
        result = adapter.apply(execution, 2)
        self.assertEqual(result.amount, 15.0)
        self.assertEqual(self.economics.balance("worker"), 15.0)
        self.assertEqual(adapter.apply(execution, 2), result)
        self.assertEqual(len(self.economics.snapshot()), 1)

    def test_noncompleted_action_has_no_economic_effect(self):
        adapter = EconomicActionAdapter(
            self.economics,
            (ActionEconomicEffect("work_shift", "employer", "worker", 15, "wage"),),
        )
        execution = ActionExecution(
            "exec-2", "npc-1", 2, "work_shift", "interrupted", "cancelled",
            ("ready",), ("ready",), (), (), "event-2",
        )
        self.assertIsNone(adapter.apply(execution, 2))
        self.assertEqual(self.economics.balance("worker"), 0.0)

    def test_json_round_trip_preserves_balances_and_journal(self):
        self.economics.transfer(EconomicTransfer("wage", 1, "employer", "worker", 12, "payroll"))
        restored = EconomicLedger.from_json(self.economics.to_json())
        self.assertEqual(restored.account_snapshot(), self.economics.account_snapshot())
        self.assertEqual(restored.snapshot(), self.economics.snapshot())


if __name__ == "__main__":
    unittest.main()
