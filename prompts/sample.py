from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

FirmId = str

class MarketExperiment(ABC):
    """Rules of one economic experiment."""

    firms: tuple[FirmId, ...]

    @abstractmethod
    def reset(self) -> dict[str, Any]:
        ...

    @abstractmethod
    def active_firms(self, state: dict[str, Any]) -> tuple[FirmId, ...]:
        """Firms choosing now.

        Multiple firms means simultaneous moves.
        One firm means sequential moves.
        """
        ...

    @abstractmethod
    def observe(self, state: dict[str, Any], firm: FirmId) -> dict[str, Any]:
        """Information visible to this firm."""
        ...

    @abstractmethod
    def validate_action(
        self, state: dict[str, Any], firm: FirmId, action: float
    ) -> float:
        ...

    @abstractmethod
    def apply_actions(
        self, state: dict[str, Any], actions: dict[FirmId, float]
    ) -> dict[str, Any]:
        """Record actions, advance phase, and settle market when appropriate."""
        ...

    @abstractmethod
    def is_done(self, state: dict[str, Any]) -> bool:
        ...


class Policy(ABC):
    @abstractmethod
    def choose(self, observation: dict[str, Any]) -> float:
        ...


def run_experiment(
    experiment: MarketExperiment,
    policies: dict[FirmId, Policy],
) -> dict[str, Any]:
    state = experiment.reset()

    while not experiment.is_done(state):
        active = experiment.active_firms(state)

        # All firms in the same stage observe the same pre-action state.
        actions = {
            firm: experiment.validate_action(
                state,
                firm,
                policies[firm].choose(experiment.observe(state, firm)),
            )
            for firm in active
        }

        state = experiment.apply_actions(state, actions)

    return state

###

@dataclass
class BertrandConfig:
    firms: tuple[FirmId, ...] = ("A", "B")
    marginal_cost: dict[FirmId, float] = field(
        default_factory=lambda: {"A": 10.0, "B": 10.0}
    )
    price_bounds: tuple[float, float] = (0.0, 50.0)
    market_size: int = 100
    reservation_price: float = 40.0
    rounds: int = 20


class BertrandExperiment(MarketExperiment):
    def __init__(self, config: BertrandConfig):
        self.config = config
        self.firms = config.firms

    def reset(self):
        return {
            "round": 1,
            "phase": "pricing",
            "prices": {},
            "history": [],
        }

    def active_firms(self, state):
        return self.firms  # simultaneous

    def observe(self, state, firm):
        return {
            "round": state["round"],
            "action_type": "price",
            "price_bounds": self.config.price_bounds,
            "marginal_cost": self.config.marginal_cost[firm],
            "past_outcomes": state["history"],
        }

    def validate_action(self, state, firm, action):
        low, high = self.config.price_bounds
        return min(max(float(action), low), high)

    def apply_actions(self, state, actions):
        prices = actions
        lowest_price = min(prices.values())

        demand = self.config.market_size if lowest_price <= self.config.reservation_price else 0
        winners = [firm for firm, price in prices.items() if price == lowest_price]

        quantities = {
            firm: demand / len(winners) if firm in winners else 0
            for firm in self.firms
        }
        profits = {
            firm: (prices[firm] - self.config.marginal_cost[firm]) * quantities[firm]
            for firm in self.firms
        }

        state["history"].append({
            "round": state["round"],
            "prices": prices,
            "quantities": quantities,
            "profits": profits,
        })
        state["round"] += 1
        return state

    def is_done(self, state):
        return state["round"] > self.config.rounds

### 

@dataclass
class StackelbergConfig:
    leader: FirmId = "Leader"
    follower: FirmId = "Follower"
    demand_intercept: float = 100.0  # P(Q) = a - bQ
    demand_slope: float = 1.0
    marginal_cost: dict[FirmId, float] = field(
        default_factory=lambda: {"Leader": 20.0, "Follower": 20.0}
    )
    rounds: int = 1


class StackelbergExperiment(MarketExperiment):
    def __init__(self, config: StackelbergConfig):
        self.config = config
        self.firms = (config.leader, config.follower)
        self.max_quantity = config.demand_intercept / config.demand_slope

    def reset(self):
        return {
            "round": 1,
            "phase": "leader_moves",
            "leader_quantity": None,
            "history": [],
        }

    def active_firms(self, state):
        if state["phase"] == "leader_moves":
            return (self.config.leader,)
        if state["phase"] == "follower_moves":
            return (self.config.follower,)
        return ()

    def observe(self, state, firm):
        observation = {
            "round": state["round"],
            "action_type": "quantity",
            "quantity_bounds": (0.0, self.max_quantity),
            "marginal_cost": self.config.marginal_cost[firm],
            "inverse_demand": {
                "intercept": self.config.demand_intercept,
                "slope": self.config.demand_slope,
            },
        }

        # The crucial Stackelberg information difference:
        if firm == self.config.follower:
            observation["leader_quantity"] = state["leader_quantity"]

        return observation

    def validate_action(self, state, firm, action):
        return min(max(float(action), 0.0), self.max_quantity)

    def apply_actions(self, state, actions):
        if state["phase"] == "leader_moves":
            state["leader_quantity"] = actions[self.config.leader]
            state["phase"] = "follower_moves"
            return state

        follower_quantity = actions[self.config.follower]
        leader_quantity = state["leader_quantity"]
        total_quantity = leader_quantity + follower_quantity

        price = max(
            0.0,
            self.config.demand_intercept
            - self.config.demand_slope * total_quantity,
        )

        quantities = {
            self.config.leader: leader_quantity,
            self.config.follower: follower_quantity,
        }
        profits = {
            firm: (price - self.config.marginal_cost[firm]) * quantity
            for firm, quantity in quantities.items()
        }

        state["history"].append({
            "round": state["round"],
            "quantities": quantities,
            "market_price": price,
            "profits": profits,
        })

        state["round"] += 1
        state["phase"] = "leader_moves"
        state["leader_quantity"] = None
        return state

    def is_done(self, state):
        return state["round"] > self.config.rounds