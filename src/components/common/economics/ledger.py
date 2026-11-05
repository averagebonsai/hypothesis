"""Multi-asset resource tracking and exact conservation ledger."""

from math import isfinite
from typing import Self

from pydantic import Field, model_validator

from simulation_core.types import FrozenModel


class InsufficientResourceError(ValueError):
    """Raised when an operation would violate non-negativity constraints."""


def _validate_amount(amount: float) -> None:
    if not isfinite(amount) or amount < 0:
        raise ValueError("Amount must be a finite non-negative number")


class ResourceLedger(FrozenModel):
    """Immutable, multi-asset ledger tracking actor balances and transfers with exact conservation."""

    balances: dict[str, dict[str, float]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_finite_balances(self) -> Self:
        for actor_id, assets in self.balances.items():
            for asset, balance in assets.items():
                if not isfinite(balance):
                    raise ValueError(f"Balance for {actor_id}:{asset} must be finite")
        return self

    def get_balance(self, actor_id: str, asset: str) -> float:
        return self.balances.get(actor_id, {}).get(asset, 0.0)

    def actor_balances(self, actor_id: str) -> dict[str, float]:
        return dict(self.balances.get(actor_id, {}))

    def has_budget(self, actor_id: str, asset: str, amount: float) -> bool:
        _validate_amount(amount)
        return self.get_balance(actor_id, asset) >= amount

    def total_resource(self, asset: str) -> float:
        return sum(assets.get(asset, 0.0) for assets in self.balances.values())

    def credit(self, actor_id: str, asset: str, amount: float) -> "ResourceLedger":
        _validate_amount(amount)
        updated = {k: dict(v) for k, v in self.balances.items()}
        current = updated.setdefault(actor_id, {}).get(asset, 0.0)
        updated[actor_id][asset] = current + amount
        return ResourceLedger(balances=updated)

    def debit(
        self, actor_id: str, asset: str, amount: float, *, allow_negative: bool = False
    ) -> "ResourceLedger":
        _validate_amount(amount)
        current = self.get_balance(actor_id, asset)
        if not allow_negative and current < amount:
            raise InsufficientResourceError(
                f"Actor {actor_id} has insufficient {asset}: required {amount}, available {current}"
            )
        updated = {k: dict(v) for k, v in self.balances.items()}
        updated.setdefault(actor_id, {})[asset] = current - amount
        return ResourceLedger(balances=updated)

    def transfer(
        self,
        sender_id: str,
        receiver_id: str,
        asset: str,
        amount: float,
        *,
        allow_negative: bool = False,
    ) -> "ResourceLedger":
        _validate_amount(amount)
        if sender_id == receiver_id:
            return self
        total_before = self.total_resource(asset)
        debited = self.debit(sender_id, asset, amount, allow_negative=allow_negative)
        credited = debited.credit(receiver_id, asset, amount)
        total_after = credited.total_resource(asset)
        if abs(total_after - total_before) > 1e-9:
            raise RuntimeError("Transfer violated resource conservation")
        return credited
