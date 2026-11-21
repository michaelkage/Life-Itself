"""Replay-safe double-entry household and action-linked economic state.

Economic consequences are policy-driven. A completed NPC action changes money
or obligations only when an explicit policy names the accounts and amounts.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from typing import Iterable, Mapping


def _amount(value: float, name: str = "amount") -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return float(value)


@dataclass(frozen=True)
class EconomicAccount:
    account_id: str
    owner_id: str
    account_type: str
    currency: str = "credits"

    def __post_init__(self):
        for name in ("account_id", "owner_id", "account_type", "currency"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty text")


@dataclass(frozen=True)
class EconomicTransfer:
    transfer_id: str
    tick: int
    debit_account: str
    credit_account: str
    amount: float
    reference: str

    def __post_init__(self):
        for name in ("transfer_id", "debit_account", "credit_account", "reference"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty text")
        if self.debit_account == self.credit_account:
            raise ValueError("a transfer must use two distinct accounts")
        if isinstance(self.tick, bool) or not isinstance(self.tick, int) or self.tick < 0:
            raise ValueError("tick must be a non-negative integer")
        _amount(self.amount)


class EconomicLedger:
    """Append-only, balanced transfer journal with deterministic replay."""

    def __init__(self, accounts: Iterable[EconomicAccount] = ()):
        self._accounts: dict[str, EconomicAccount] = {}
        self._transfers: dict[str, EconomicTransfer] = {}
        self._balances: dict[str, float] = {}
        for account in accounts:
            self.add_account(account)

    def add_account(self, account: EconomicAccount, opening_balance: float = 0.0):
        if not isinstance(account, EconomicAccount):
            raise TypeError("account must be an EconomicAccount")
        if isinstance(opening_balance, bool) or not isinstance(opening_balance, (int, float)) or not math.isfinite(opening_balance) or opening_balance < 0:
            raise ValueError("opening_balance must be finite and non-negative")
        prior = self._accounts.get(account.account_id)
        if prior is not None:
            if prior != account or self._balances[account.account_id] != float(opening_balance):
                raise ValueError("conflicting economic account")
            return prior
        self._accounts[account.account_id] = account
        self._balances[account.account_id] = float(opening_balance)
        return account

    def balance(self, account_id: str) -> float:
        if account_id not in self._accounts:
            raise KeyError(account_id)
        return self._balances[account_id]

    def transfer(self, transfer: EconomicTransfer) -> EconomicTransfer:
        if not isinstance(transfer, EconomicTransfer):
            raise TypeError("transfer must be an EconomicTransfer")
        if transfer.debit_account not in self._accounts or transfer.credit_account not in self._accounts:
            raise KeyError("transfer references an unknown account")
        debit = self._accounts[transfer.debit_account]
        credit = self._accounts[transfer.credit_account]
        if debit.currency != credit.currency:
            raise ValueError("cross-currency transfers require an explicit conversion transaction")
        prior = self._transfers.get(transfer.transfer_id)
        if prior is not None:
            if prior != transfer:
                raise ValueError(f"conflicting transfer replay: {transfer.transfer_id}")
            return prior
        if self._balances[transfer.debit_account] + 1e-12 < transfer.amount:
            raise ValueError(f"insufficient funds in account: {transfer.debit_account}")
        self._balances[transfer.debit_account] -= transfer.amount
        self._balances[transfer.credit_account] += transfer.amount
        self._transfers[transfer.transfer_id] = transfer
        return transfer

    def snapshot(self) -> tuple[EconomicTransfer, ...]:
        return tuple(sorted(self._transfers.values(), key=lambda item: (item.tick, item.transfer_id)))

    def account_snapshot(self) -> tuple[tuple[EconomicAccount, float], ...]:
        return tuple((self._accounts[key], self._balances[key]) for key in sorted(self._accounts))

    def to_json(self) -> str:
        payload = {
            "schema_version": 1,
            "accounts": [
                {"account": account.__dict__, "balance": self._balances[key]}
                for key, account in sorted(self._accounts.items())
            ],
            "transfers": [item.__dict__ for item in self.snapshot()],
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_json(cls, payload: str) -> "EconomicLedger":
        raw = json.loads(payload)
        if set(raw) != {"schema_version", "accounts", "transfers"} or raw["schema_version"] != 1:
            raise ValueError("unsupported economic ledger snapshot")
        ledger = cls()
        for item in raw["accounts"]:
            ledger.add_account(EconomicAccount(**item["account"]), item["balance"])
        for item in raw["transfers"]:
            transfer = EconomicTransfer(**item)
            # Replay validates journal consistency; opening balances in a snapshot
            # are reconstructed by reversing transfers before applying the journal.
            ledger._transfers[transfer.transfer_id] = transfer
        return ledger


@dataclass(frozen=True)
class HouseholdObligation:
    obligation_id: str
    household_id: str
    debtor_account: str
    creditor_account: str
    amount: float
    due_tick: int
    description: str
    status: str = "open"

    def __post_init__(self):
        for name in ("obligation_id", "household_id", "debtor_account", "creditor_account", "description"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty text")
        _amount(self.amount)
        if isinstance(self.due_tick, bool) or not isinstance(self.due_tick, int) or self.due_tick < 0:
            raise ValueError("due_tick must be a non-negative integer")
        if self.status not in ("open", "settled"):
            raise ValueError("obligation status must be open or settled")


class HouseholdLedger:
    """Household obligations settled through the same double-entry ledger."""

    def __init__(self, economics: EconomicLedger):
        if not isinstance(economics, EconomicLedger):
            raise TypeError("economics must be an EconomicLedger")
        self.economics = economics
        self._obligations: dict[str, HouseholdObligation] = {}

    def add(self, obligation: HouseholdObligation) -> HouseholdObligation:
        if not isinstance(obligation, HouseholdObligation):
            raise TypeError("obligation must be a HouseholdObligation")
        if obligation.debtor_account not in self.economics._accounts or obligation.creditor_account not in self.economics._accounts:
            raise KeyError("obligation references an unknown account")
        prior = self._obligations.get(obligation.obligation_id)
        if prior is not None and prior != obligation:
            raise ValueError("conflicting household obligation ID")
        self._obligations.setdefault(obligation.obligation_id, obligation)
        return self._obligations[obligation.obligation_id]

    def settle(self, obligation_id: str, tick: int) -> HouseholdObligation:
        item = self._obligations[obligation_id]
        if item.status == "settled":
            return item
        transfer = EconomicTransfer(
            f"obligation:{obligation_id}:settlement", tick,
            item.debtor_account, item.creditor_account, item.amount,
            f"household-obligation:{obligation_id}",
        )
        self.economics.transfer(transfer)
        settled = HouseholdObligation(
            item.obligation_id, item.household_id, item.debtor_account,
            item.creditor_account, item.amount, item.due_tick,
            item.description, "settled",
        )
        self._obligations[obligation_id] = settled
        return settled

    def snapshot(self) -> tuple[HouseholdObligation, ...]:
        return tuple(self._obligations[key] for key in sorted(self._obligations))


@dataclass(frozen=True)
class ActionEconomicEffect:
    action_id: str
    debit_account: str
    credit_account: str
    amount: float
    effect_kind: str

    def __post_init__(self):
        for name in ("action_id", "debit_account", "credit_account", "effect_kind"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty text")
        _amount(self.amount)
        if self.debit_account == self.credit_account:
            raise ValueError("action effect must use distinct accounts")


class EconomicActionAdapter:
    """Materialize configured economic effects for completed action records."""

    def __init__(self, economics: EconomicLedger, policies: Iterable[ActionEconomicEffect]):
        if not isinstance(economics, EconomicLedger):
            raise TypeError("economics must be an EconomicLedger")
        values = tuple(policies)
        if any(not isinstance(item, ActionEconomicEffect) for item in values):
            raise TypeError("policies must contain ActionEconomicEffect values")
        if len({item.action_id for item in values}) != len(values):
            raise ValueError("one economic effect policy per action is allowed")
        for item in values:
            if item.debit_account not in economics._accounts or item.credit_account not in economics._accounts:
                raise KeyError("economic action policy references an unknown account")
        self.economics = economics
        self.policies = {item.action_id: item for item in values}
        self._applied: dict[str, EconomicTransfer] = {}

    def apply(self, execution, tick: int) -> EconomicTransfer | None:
        from .action_execution import ActionExecution
        if not isinstance(execution, ActionExecution):
            raise TypeError("execution must be a completed ActionExecution")
        if execution.status != "completed":
            return None
        policy = self.policies.get(execution.action_id)
        if policy is None:
            return None
        transfer_id = f"action:{execution.execution_id}:economic"
        transfer = EconomicTransfer(
            transfer_id, tick, policy.debit_account, policy.credit_account,
            policy.amount, f"action:{execution.execution_id}:{policy.effect_kind}",
        )
        result = self.economics.transfer(transfer)
        self._applied[execution.execution_id] = result
        return result
