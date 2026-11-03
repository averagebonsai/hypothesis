"""Observation privacy: decentralized information boundaries."""

from experiment_extension.mechanism import SupplyChainMechanism
from helpers import mechanism_and_state as _base_setup

from simulation_core.observation import observe, permissions_for
from simulation_core.types import Action, Observation, SimulationConfig, WorldState

ORDER = {"order_a": 80, "order_b": 80, "priority_a": 0, "priority_b": 0}


def mechanism_and_state() -> tuple[SupplyChainMechanism, SimulationConfig, WorldState]:
    """Local setup: helper fixture plus draft-config validation through a fresh mechanism."""
    mechanism, config, state = _base_setup()
    assert SupplyChainMechanism().validate_config(config.world) is None
    return mechanism, config, state


SUPPLY = {"produce": 80, "fulfill": 80, "ship_request": 80, "priority": 0}
ALLOCATE = {"allocate_a": 80, "allocate_b": 80}
PRODUCE = {"produce": 80}


def _observations_at(state: WorldState) -> dict[str, Observation]:
    mechanism, config, _ = mechanism_and_state()
    assert isinstance(mechanism, SupplyChainMechanism)
    actors = {actor.id: actor for actor in config.world.actors}
    return {
        actor_id: observe(actor, state, permissions_for(config, actor_id, state.phase))
        for actor_id, actor in actors.items()
    }


def _after_order() -> WorldState:
    mechanism, config, state = mechanism_and_state()
    transition = mechanism.transition(
        config.world,
        state,
        (Action(actor_id="manufacturer", kind="order", payload=dict(ORDER)),),
    )
    return WorldState(
        tick=1,
        phase="d1_supply",
        public=transition.public,
        private=dict(transition.private_updates),
    )


def test_suppliers_cannot_see_each_other() -> None:
    views = _observations_at(_after_order())
    assert set(views["supplier_a"].visible) == {
        "day",
        "capacity",
        "disrupted",
        "order_a",
        "commit_a",
        "offer_a",
        "allocation_a",
    }
    assert set(views["supplier_b"].visible) == {
        "day",
        "capacity",
        "disrupted",
        "order_b",
        "commit_b",
        "offer_b",
        "allocation_b",
    }
    assert views["supplier_a"].visible["order_a"] == 80
    assert "order_b" not in views["supplier_a"].visible
    assert "order_a" not in views["supplier_b"].visible
    assert views["supplier_a"].private.facts["inventory"] == 200
    assert views["supplier_a"].private.facts["backlog"] == 80
    assert set(views["supplier_a"].private.facts) == {
        "component",
        "inventory",
        "capacity",
        "unit_cost",
        "backlog",
        "produced_today",
        "cumulative_produced",
        "cumulative_dispatched",
        "cumulative_revenue",
        "cumulative_cost",
        "history",
    }


def test_manufacturer_and_logistics_views() -> None:
    _, _, state = mechanism_and_state()
    views = _observations_at(state)
    assert set(views["manufacturer"].visible) == {
        "day",
        "capacity",
        "disrupted",
        "arrivals",
        "in_transit",
        "order_a",
        "order_b",
        "commit_a",
        "commit_b",
    }
    assert "allocation_a" not in views["manufacturer"].visible
    assert "offer_a" not in views["manufacturer"].visible
    assert set(views["logistics"].visible) == {
        "day",
        "capacity",
        "disrupted",
        "offer_a",
        "offer_b",
        "allocation_a",
        "allocation_b",
        "priority_mfg_a",
        "priority_mfg_b",
        "priority_sa",
        "priority_sb",
    }
    assert "order_a" not in views["logistics"].visible
    assert "in_transit" not in views["logistics"].visible
    assert views["manufacturer"].private.facts["demand"] == 80
    assert "demand" not in views["logistics"].private.facts


def test_simultaneous_supply_boundary() -> None:
    supply = _after_order()
    before = _observations_at(supply)["supplier_a"]
    # Choosing B's action must not change A's committed precommit observation.
    peer = Action(actor_id="supplier_b", kind="supply", payload=dict(SUPPLY))
    assert peer.payload["produce"] == 80
    after = _observations_at(supply)["supplier_a"]
    assert before == after


def test_required_fields_available_every_phase() -> None:
    from components.protocols.sequential import SequentialProtocol

    mechanism, config, state = mechanism_and_state()
    actors = {actor.id: actor for actor in config.world.actors}
    protocol = SequentialProtocol(dict(config.protocol_parameters))
    batches = {
        "order": (Action(actor_id="manufacturer", kind="order", payload=dict(ORDER)),),
        "supply": (
            Action(actor_id="supplier_a", kind="supply", payload=dict(SUPPLY)),
            Action(actor_id="supplier_b", kind="supply", payload=dict(SUPPLY)),
        ),
        "ship": (Action(actor_id="logistics", kind="allocate", payload=dict(ALLOCATE)),),
        "settle": (Action(actor_id="manufacturer", kind="produce", payload=dict(PRODUCE)),),
    }
    seen = set()
    for _ in range(8):
        seen.add(state.phase)
        for actor_id, actor in actors.items():
            permissions = permissions_for(config, actor_id, state.phase)
            required = set(actor.policy_parameters.get("required_fields", []))
            assert required
            assert required <= set(permissions.public_fields)
            view = observe(actor, state, permissions)
            assert required <= set(view.visible)
        batch = batches[state.phase.rsplit("_", 1)[-1]]
        result = mechanism.transition(config.world, state, batch)
        state = WorldState(
            tick=state.tick + 1,
            phase=protocol.next_phase(config.world, state),
            public=result.public,
            private=dict(result.private_updates),
        )
    assert seen == {
        "d1_order",
        "d1_supply",
        "d1_ship",
        "d1_settle",
        "d2_order",
        "d2_supply",
        "d2_ship",
        "d2_settle",
    }


def test_policies_cannot_write_private_state() -> None:
    _, config, _ = mechanism_and_state()
    assert set(config.permissions) == {"manufacturer", "supplier_a", "supplier_b", "logistics"}
    for permissions in config.permissions.values():
        assert permissions.writable_private_fields == ()
        assert permissions.writable_memory is False
