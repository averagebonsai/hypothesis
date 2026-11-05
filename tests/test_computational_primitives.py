"""Unit tests for the modular computational primitives."""

import pytest

from components.common.communication import (
    DirectMessagePayload,
    Message,
    PublicBroadcastPayload,
    route_message,
)
from components.common.economics import (
    ConstituentSegment,
    InsufficientResourceError,
    PopulationSystem,
    ResourceLedger,
    economic_efficiency,
    gini_coefficient,
    herfindahl_index,
    social_welfare,
    unilateral_regret,
)
from components.common.math import (
    SeededSampler,
    optimal_bipartite_matching,
    priority_rationing,
    proportional_rationing,
    solve_linear_program,
)
from components.common.topology import NetworkEdge, NetworkTopology
from simulation_core.types import PrivateState


def test_resource_ledger_credits_debits_and_conserves_transfers():
    ledger = ResourceLedger()
    assert ledger.get_balance("alice", "cash") == 0.0

    # Credit
    ledger = ledger.credit("alice", "cash", 100.0)
    ledger = ledger.credit("alice", "tokens", 50.0)
    assert ledger.get_balance("alice", "cash") == 100.0
    assert ledger.get_balance("alice", "tokens") == 50.0
    assert ledger.total_resource("cash") == 100.0

    # Debit with balance check
    ledger = ledger.debit("alice", "cash", 40.0)
    assert ledger.get_balance("alice", "cash") == 60.0

    # Insufficient funds raises error
    with pytest.raises(InsufficientResourceError):
        ledger.debit("alice", "cash", 100.0)

    # Allowed negative debit
    ledger_neg = ledger.debit("alice", "cash", 100.0, allow_negative=True)
    assert ledger_neg.get_balance("alice", "cash") == -40.0

    # Transfer with strict conservation
    ledger = ledger.transfer("alice", "bob", "cash", 25.0)
    assert ledger.get_balance("alice", "cash") == 35.0
    assert ledger.get_balance("bob", "cash") == 25.0
    assert ledger.total_resource("cash") == 60.0

    # Self-transfer is a no-op
    unchanged = ledger.transfer("alice", "alice", "cash", 10.0)
    assert unchanged.get_balance("alice", "cash") == 35.0


def test_delayed_queue_drains_items_at_scheduled_ticks():
    from components.common.scheduling import DelayedQueue

    queue = DelayedQueue()
    assert queue.is_empty

    # Schedule item 1 for tick 3, item 2 for tick 5
    queue, item1 = queue.enqueue(
        "supplier", "manufacturer", {"units": 100}, current_tick=1, delay_ticks=2
    )
    queue, item2 = queue.enqueue(
        "supplier", "distributor", {"units": 50}, current_tick=1, delay_ticks=4
    )
    assert len(queue.items) == 2
    assert not queue.is_empty
    assert len(queue.pending_for("manufacturer")) == 1

    # At tick 2: nothing due
    queue, due_tick2 = queue.drain_due(2)
    assert len(due_tick2) == 0
    assert len(queue.items) == 2

    # At tick 3: item1 due
    queue, due_tick3 = queue.drain_due(3)
    assert len(due_tick3) == 1
    assert due_tick3[0].item_id == item1.item_id
    assert len(queue.items) == 1

    # At tick 5: item2 due
    queue, due_tick5 = queue.drain_due(5)
    assert len(due_tick5) == 1
    assert due_tick5[0].item_id == item2.item_id
    assert queue.is_empty


def test_communication_routing_guarantees_privacy_and_zero_leakage():
    public_facts: dict = {}
    private_states = {
        "alice": PrivateState(facts={}, memory={}),
        "bob": PrivateState(facts={}, memory={}),
        "carol": PrivateState(facts={}, memory={}),
    }

    # Action payload models validate successfully
    direct_payload = DirectMessagePayload(recipient_id="bob", content="Hello Bob", data={"bid": 10})
    assert direct_payload.recipient_id == "bob"
    broadcast_payload = PublicBroadcastPayload(content="Hello world", topic="announcement")
    assert broadcast_payload.content == "Hello world"

    # 1. Direct message from Alice to Bob
    direct_msg = Message(
        sender_id="alice",
        recipient_id="bob",
        content="Secret offer: 42",
        tick=1,
    )
    public_facts, private_states = route_message(direct_msg, public_facts, private_states)

    # Bob receives it in private inbox
    assert len(private_states["bob"].facts["inbox"]) == 1
    assert private_states["bob"].facts["inbox"][0]["content"] == "Secret offer: 42"

    # Alice has it in private outbox
    assert len(private_states["alice"].facts["outbox"]) == 1

    # Carol and Public facts have ZERO knowledge
    assert "inbox" not in private_states["carol"].facts
    assert "broadcasts" not in public_facts

    # 2. Public broadcast from Carol
    broadcast_msg = Message(
        sender_id="carol",
        recipient_id=None,
        content="Market is open",
        tick=2,
    )
    public_facts, private_states = route_message(broadcast_msg, public_facts, private_states)
    assert len(public_facts["broadcasts"]) == 1
    assert public_facts["broadcasts"][0]["content"] == "Market is open"


def test_seeded_sampler_reproducibility():
    sampler1 = SeededSampler(base_seed=42)
    sampler2 = SeededSampler(base_seed=42)
    sampler_diff = SeededSampler(base_seed=99)

    # Identical draws given same base_seed, tick, domain_key
    val1 = sampler1.uniform(tick=1, domain_key="weather_temp", low=10.0, high=30.0)
    val2 = sampler2.uniform(tick=1, domain_key="weather_temp", low=10.0, high=30.0)
    val_diff = sampler_diff.uniform(tick=1, domain_key="weather_temp", low=10.0, high=30.0)

    assert val1 == val2
    assert val1 != val_diff

    # Normal distribution
    norm1 = sampler1.normal(tick=2, domain_key="demand_shock", mean=100.0, std=15.0)
    norm2 = sampler2.normal(tick=2, domain_key="demand_shock", mean=100.0, std=15.0)
    assert norm1 == norm2

    # Weighted choice
    options = ("A", "B", "C")
    choice1 = sampler1.choice(tick=3, domain_key="category", options=options, weights=(0.1, 0.8, 0.1))
    choice2 = sampler2.choice(tick=3, domain_key="category", options=options, weights=(0.1, 0.8, 0.1))
    assert choice1 == choice2


def test_network_topology_paths_and_connectivity():
    edges = (
        NetworkEdge(source="A", target="B", weight=2.0),
        NetworkEdge(source="B", target="C", weight=3.0),
        NetworkEdge(source="C", target="D", weight=1.0),
        NetworkEdge(source="A", target="D", weight=10.0),
    )
    topology = NetworkTopology(nodes=("A", "B", "C", "D", "E"), edges=edges)

    assert topology.neighbors("B") == ("A", "C")
    assert topology.degree("B") == 2
    assert topology.has_edge("A", "B")
    assert topology.has_edge("B", "A")  # bidirectional default

    # Shortest path: A -> B -> C -> D = 2 + 3 + 1 = 6 (vs direct A-D which is 10)
    path = topology.shortest_path("A", "D")
    assert path == ("A", "B", "C", "D")
    assert topology.shortest_path_distance("A", "D") == 6.0

    # Disconnected node E
    assert not topology.are_connected("A", "E")
    assert topology.shortest_path("A", "E") is None


def test_allocation_proportional_and_priority_rationing():
    demands = {"firm_1": 60.0, "firm_2": 40.0}

    # Capacity sufficient
    alloc_unconstrained = proportional_rationing(demands, total_capacity=150.0)
    assert alloc_unconstrained == {"firm_1": 60.0, "firm_2": 40.0}

    # Capacity constrained: exactly 50 total capacity, split 60:40 -> 30.0 and 20.0
    alloc_constrained = proportional_rationing(demands, total_capacity=50.0)
    assert alloc_constrained == {"firm_1": 30.0, "firm_2": 20.0}
    assert sum(alloc_constrained.values()) == 50.0

    # Priority rationing: firm_2 has priority 10 vs firm_1 priority 5
    priorities = {"firm_1": 5.0, "firm_2": 10.0}
    alloc_priority = priority_rationing(demands, priorities, total_capacity=50.0)
    # firm_2 gets all 40.0 requested, remaining 10.0 goes to firm_1
    assert alloc_priority == {"firm_2": 40.0, "firm_1": 10.0}


def test_linear_programming_and_matching():
    # Min -2x - 3y subject to x + y <= 10, bounds [0, inf]
    # In min form: c = [-2, -3], A_ub = [[1, 1]], b_ub = [10]
    res = solve_linear_program(c=[-2.0, -3.0], a_ub=[[1.0, 1.0]], b_ub=[10.0], bounds=[(0.0, None), (0.0, None)])
    assert res.success
    assert pytest.approx(res.fun, 1e-5) == -30.0

    # Bipartite matching: 2 workers, 2 tasks
    costs = [[4.0, 1.0], [1.0, 3.0]]
    matching = optimal_bipartite_matching(costs)
    assert matching == ((0, 1), (1, 0))


def test_population_segmentation_choice_and_conservation():
    seg1 = ConstituentSegment(
        id="wealthy", population=100.0, base_utilities={"brand_a": 5.0, "brand_b": 4.0}, price_sensitivity=0.5
    )
    seg2 = ConstituentSegment(
        id="budget", population=200.0, base_utilities={"brand_a": 2.0, "brand_b": 3.0}, price_sensitivity=2.0
    )
    system = PopulationSystem(segments=(seg1, seg2))
    assert system.total_population == 300.0

    prices = {"brand_a": 2.0, "brand_b": 2.0}
    demand = system.aggregate_demand(prices)

    # Demands + outside option exactly conserve total population
    total_allocated = sum(demand.values())
    assert pytest.approx(total_allocated, 1e-5) == 300.0
    assert demand["brand_a"] > 0
    assert demand["brand_b"] > 0


def test_economic_metrics():
    # Gini: equality -> 0.0
    assert gini_coefficient([10.0, 10.0, 10.0]) == 0.0
    # Gini: one has everything -> approaches 1.0
    assert gini_coefficient([0.0, 0.0, 100.0]) == pytest.approx(2 / 3, 1e-5)

    # HHI: 2 firms with equal share 0.5 each -> 50^2 + 50^2 = 5000
    assert herfindahl_index({"A": 0.5, "B": 0.5}) == 5000.0

    # Social welfare & regret
    assert social_welfare({"A": 100.0, "B": 150.0}) == 250.0
    assert unilateral_regret(actual_payoff=50.0, counterfactual_best_payoff=80.0) == 30.0
    assert unilateral_regret(actual_payoff=90.0, counterfactual_best_payoff=80.0) == 0.0

    # Efficiency
    assert economic_efficiency(actual_surplus=80.0, theoretical_max_surplus=100.0) == 0.8
