"""Wrapper policy: canonical packets, contextual retry, exact fallback."""

import json

import pytest
from experiment_extension.mechanism import SupplyChainMechanism
from experiment_extension.policy import SupplyChainPolicy
from experiment_extension.schemas import (
    AllocateAction,
    OrderAction,
    ProduceAction,
    SupplyAction,
)
from helpers import draft_data, mechanism_and_state, step_day

from simulation_core.model_gateway import FakeGateway, GatewayError, ModelRequest
from simulation_core.observation import observe, permissions_for
from simulation_core.types import Observation, WorldState

ORDER = {"order_a": 80, "order_b": 80, "priority_a": 0, "priority_b": 0}
SUPPLY = {"produce": 80, "fulfill": 80, "ship_request": 80, "priority": 0}
ALLOCATE = {"allocate_a": 80, "allocate_b": 80}
PRODUCE = {"produce": 80}
SCHEMAS = {
    "order": OrderAction,
    "produce": ProduceAction,
    "supply": SupplyAction,
    "allocate": AllocateAction,
}


def _policy_for(actor_id: str, gateway: FakeGateway) -> SupplyChainPolicy:
    data = draft_data()["simulation"]
    assert isinstance(data, dict)
    world = data["world"]
    assert isinstance(world, dict)
    actors = world["actors"]
    assert isinstance(actors, list)
    for actor in actors:
        assert isinstance(actor, dict)
        if actor["id"] == actor_id:
            params = actor["policy_parameters"]
            assert isinstance(params, dict)
            policy = SupplyChainPolicy(dict(params), gateway)
            schemas = actor["action_space"]["schemas"]
            assert isinstance(schemas, dict)
            policy.configure_action_schemas({kind: SCHEMAS[kind] for kind in schemas})
            return policy
    raise AssertionError(f"Unknown actor {actor_id}")


def _observation_at(
    actor_id: str, phase: str, tick: int, public: dict, private: dict
) -> Observation:
    _, config, _ = mechanism_and_state()
    actor = next(actor for actor in config.world.actors if actor.id == actor_id)
    state = WorldState(tick=tick, phase=phase, public=dict(public), private=dict(private))
    return observe(actor, state, permissions_for(config, actor_id, phase))


def _settle_observation() -> Observation:
    _, _, state = mechanism_and_state()
    return _observation_at("manufacturer", "d1_settle", 3, dict(state.public), dict(state.private))


def _wire(actor_id: str, kind: str, payload: dict) -> str:
    return json.dumps(
        {
            "action": {"actor_id": actor_id, "kind": kind, "payload": payload},
            "memory_update": None,
            "private_updates": [],
            "rationale": "Test response with a lawful structured action.",
        }
    )


def test_accepted_decision_preserves_canonical_packet() -> None:
    observation = _settle_observation()
    gateway = FakeGateway(lambda request: _wire("manufacturer", "produce", {"produce": 50}))
    policy = _policy_for("manufacturer", gateway)
    decision = policy.choose_action(observation)
    assert decision.action.payload == {"produce": 50}
    assert decision.rationale
    assert decision.memory_update is None
    assert decision.private_updates == {}
    assert len(gateway.requests) == 1
    packet = json.loads(gateway.requests[0].input_json)
    assert Observation.from_json_values(packet["observation"]) == observation
    calls = policy.model_calls()
    assert len(calls) == 1
    assert calls[0].status == "accepted"
    assert calls[0].mode == "fake"


def test_infeasible_proposal_retries_then_falls_back() -> None:
    observation = _settle_observation()
    gateway = FakeGateway(lambda request: _wire("manufacturer", "produce", {"produce": 999}))
    policy = _policy_for("manufacturer", gateway)
    decision = policy.choose_action(observation)
    assert decision.action.kind == "produce"
    assert decision.action.payload == {"produce": 0}
    assert (decision.rationale or "").startswith("Safe fallback after 2 exhausted attempts")
    assert decision.memory_update is None
    assert decision.private_updates == {}
    assert len(gateway.requests) == 2
    assert policy.fallback_count == 1
    assert len(policy.infeasible_proposals) == 2
    assert all(call.status == "invalid_response" for call in policy.model_calls())
    # The fallback itself is legal for the mechanism at this state.
    mechanism, config, _ = mechanism_and_state()
    _, _, state = mechanism_and_state()
    mechanism.validate_actions(
        config.world,
        WorldState(
            tick=3, phase="d1_settle", public=dict(state.public), private=dict(state.private)
        ),
        (decision.action,),
    )
    assert isinstance(mechanism, SupplyChainMechanism)


def test_retry_then_accept() -> None:
    observation = _settle_observation()
    responses = [
        _wire("manufacturer", "produce", {"produce": 999}),
        _wire("manufacturer", "produce", {"produce": 10}),
    ]
    gateway = FakeGateway(lambda request: responses.pop(0))
    policy = _policy_for("manufacturer", gateway)
    decision = policy.choose_action(observation)
    assert decision.action.payload == {"produce": 10}
    assert policy.fallback_count == 0
    assert [call.status for call in policy.model_calls()] == ["invalid_response", "accepted"]


def test_gateway_error_falls_back() -> None:
    observation = _settle_observation()

    def fail(request: ModelRequest) -> str:
        raise GatewayError("boom")

    policy = _policy_for("manufacturer", FakeGateway(fail))
    decision = policy.choose_action(observation)
    assert decision.action.payload == {"produce": 0}
    assert (decision.rationale or "").startswith("Safe fallback after 2 exhausted attempts")
    assert policy.fallback_count == 1
    assert all(call.status == "gateway_error" for call in policy.model_calls())


def test_fallback_kind_follows_phase() -> None:
    _, _, state = mechanism_and_state()
    cases = [
        (
            "manufacturer",
            "d1_order",
            0,
            "order",
            {"order_a": 0, "order_b": 0, "priority_a": 0, "priority_b": 0},
        ),
        ("manufacturer", "d1_settle", 3, "produce", {"produce": 0}),
        (
            "supplier_a",
            "d1_supply",
            1,
            "supply",
            {"produce": 0, "fulfill": 0, "ship_request": 0, "priority": 0},
        ),
        ("logistics", "d1_ship", 2, "allocate", {"allocate_a": 0, "allocate_b": 0}),
    ]
    for actor_id, phase, tick, kind, payload in cases:
        observation = _observation_at(
            actor_id, phase, tick, dict(state.public), dict(state.private)
        )

        def fail(request: ModelRequest) -> str:
            raise GatewayError("boom")

        policy = _policy_for(actor_id, FakeGateway(fail))
        decision = policy.choose_action(observation)
        assert decision.action.kind == kind
        assert decision.action.payload == payload
        assert decision.memory_update is None
        assert decision.private_updates == {}


def test_fallback_matches_declared_attributes() -> None:
    data = draft_data()["simulation"]
    assert isinstance(data, dict)
    world = data["world"]
    assert isinstance(world, dict)
    actors = world["actors"]
    assert isinstance(actors, list)
    assert len(actors) == 4
    for actor in actors:
        assert isinstance(actor, dict)
        params = actor["policy_parameters"]
        attributes = actor["attributes"]
        assert isinstance(params, dict) and isinstance(attributes, dict)
        assert attributes["model_policy"] == "llm.v1"
        assert params["fallback"] == attributes["safe_fallback_actions"]
        fallback = params["fallback"]
        assert isinstance(fallback, dict)
        schemas = actor["action_space"]["schemas"]
        assert isinstance(schemas, dict)
        for kind, payload in fallback.items():
            assert kind in schemas
            SCHEMAS[kind].from_json_values(payload)
    by_actor = {actor["id"]: actor["policy_parameters"]["fallback"] for actor in actors}
    assert OrderAction.from_json_values(by_actor["manufacturer"]["order"]).order_a == 0
    assert ProduceAction.from_json_values(by_actor["manufacturer"]["produce"]).produce == 0
    assert SupplyAction.from_json_values(by_actor["supplier_a"]["supply"]).produce == 0
    assert SupplyAction.from_json_values(by_actor["supplier_b"]["supply"]).produce == 0
    assert AllocateAction.from_json_values(by_actor["logistics"]["allocate"]).allocate_a == 0


def test_contextual_bounds_mirror_mechanism() -> None:
    from simulation_core.types import Action as CoreAction

    mechanism, config, state = mechanism_and_state()
    world = config.world
    gateway = FakeGateway(lambda request: _wire("manufacturer", "produce", {"produce": 0}))
    policies = {
        actor_id: _policy_for(actor_id, gateway)
        for actor_id in ("manufacturer", "supplier_a", "supplier_b", "logistics")
    }
    actors = {actor.id: actor for actor in world.actors}

    def verdicts(
        actor_id: str,
        phase: str,
        tick: int,
        state: WorldState,
        kind: str,
        payloads: list[dict],
        *,
        require_both: bool = True,
    ) -> None:
        actor = actors[actor_id]
        candidate = WorldState(
            tick=tick, phase=phase, public=dict(state.public), private=dict(state.private)
        )
        observation = observe(actor, candidate, permissions_for(config, actor_id, phase))
        seen = set()
        for payload in payloads:
            action = CoreAction(actor_id=actor_id, kind=kind, payload=dict(payload))
            try:
                policies[actor_id].check_action(observation, action)
                policy_ok = True
            except ValueError:
                policy_ok = False
            if kind == "supply":
                peer_id = "supplier_b" if actor_id == "supplier_a" else "supplier_a"
                batch = (
                    action,
                    CoreAction(
                        actor_id=peer_id,
                        kind="supply",
                        payload={"produce": 0, "fulfill": 0, "ship_request": 0, "priority": 0},
                    ),
                )
            else:
                batch = (action,)
            try:
                mechanism.validate_actions(world, candidate, batch)
                mechanism_ok = True
            except ValueError:
                mechanism_ok = False
            assert policy_ok == mechanism_ok, (actor_id, kind, payload)
            seen.add(policy_ok)
        if require_both:
            assert seen == {True, False}, (actor_id, kind, "needs both outcomes")

    # Day-one states at every stage.
    settle = WorldState(
        tick=3, phase="d1_settle", public=dict(state.public), private=dict(state.private)
    )
    maker_facts = state.private["manufacturer"].facts
    limit = min(maker_facts["comp_a"], maker_facts["comp_b"], maker_facts["capacity"])
    assert isinstance(limit, int)
    verdicts(
        "manufacturer",
        "d1_settle",
        3,
        settle,
        "produce",
        [{"produce": max(limit - 1, 0)}, {"produce": limit}, {"produce": limit + 1}],
    )
    verdicts(
        "manufacturer",
        "d1_order",
        0,
        state,
        "order",
        [dict(ORDER), {"order_a": 0, "order_b": 0, "priority_a": 5, "priority_b": 0}],
        require_both=False,
    )
    supply_state = WorldState(
        tick=1, phase="d1_supply", public=dict(state.public), private=dict(state.private)
    )
    supplier_facts = state.private["supplier_a"].facts
    cap = supplier_facts["capacity"]
    backlog = supplier_facts["backlog"]
    inventory = supplier_facts["inventory"]
    assert isinstance(cap, int) and isinstance(backlog, int) and isinstance(inventory, int)
    verdicts(
        "supplier_a",
        "d1_supply",
        1,
        supply_state,
        "supply",
        [
            {"produce": 0, "fulfill": 0, "ship_request": 0, "priority": 0},
            {"produce": cap, "fulfill": backlog, "ship_request": inventory + cap, "priority": 0},
            {"produce": cap + 1, "fulfill": 0, "ship_request": 0, "priority": 0},
            {"produce": 0, "fulfill": backlog + 1, "ship_request": 0, "priority": 0},
            {"produce": 0, "fulfill": 0, "ship_request": inventory + 1, "priority": 0},
        ],
    )
    ship_state = WorldState(
        tick=2,
        phase="d1_ship",
        public={**state.public, "offer_a": 60, "offer_b": 50},
        private=dict(state.private),
    )
    verdicts(
        "logistics",
        "d1_ship",
        2,
        ship_state,
        "allocate",
        [
            {"allocate_a": 0, "allocate_b": 0},
            {"allocate_a": 60, "allocate_b": 50},
            {"allocate_a": 61, "allocate_b": 0},
            {"allocate_a": 0, "allocate_b": 51},
            {"allocate_a": 60, "allocate_b": 50},
        ],
    )
    # Flood-day state with tight capacity.
    flood = state
    for _ in range(3):
        capacity = flood.public["capacity"]
        assert isinstance(capacity, int)
        half = min(80, capacity // 2)
        flood = step_day(
            mechanism,
            config,
            flood,
            ORDER,
            SUPPLY,
            SUPPLY,
            {"allocate_a": half, "allocate_b": min(80, capacity - half)},
            PRODUCE,
        )
    assert flood.public["capacity"] == 80
    tight_ship = WorldState(
        tick=14,
        phase="d4_ship",
        public={**flood.public, "day": 4, "offer_a": 80, "offer_b": 80, "capacity": 80},
        private=dict(flood.private),
    )
    verdicts(
        "logistics",
        "d4_ship",
        14,
        tight_ship,
        "allocate",
        [
            {"allocate_a": 40, "allocate_b": 40},
            {"allocate_a": 80, "allocate_b": 80},
        ],
    )
    with pytest.raises(ValueError, match="Unknown action kind"):
        policies["manufacturer"].check_action(
            _settle_observation(),
            CoreAction(actor_id="manufacturer", kind="nap", payload={}),
        )
