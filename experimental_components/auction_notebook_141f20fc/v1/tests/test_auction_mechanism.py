"""Acceptance tests for the sealed-bid second-price mechanism and bid schema.

All expectations are hand-derived from the user's auction rules; the tests build
configurations through JSON-aware fixture boundaries and run the trusted runtime
with deterministic scripted policies (test-only stand-ins, never the primary
simulation's live LLM actors).
"""

import pytest
from experiment_extension.auction import SecondPriceAuctionMechanism
from experiment_extension.schemas import BidPayload

from agent_tools.fixtures import fixture_config, fixture_state
from components.library import standard_registry
from components.protocols.simultaneous import SimultaneousProtocol
from simulation_core.execution import JobRunner, LocalBackend
from simulation_core.observation import observe, permissions_for
from simulation_core.request import ExperimentRequest
from simulation_core.types import Action, WorldState

MECHANISM_ID = "experimental.auction_notebook_141f20fc.second_price"
BID_SCHEMA_ID = "experimental.auction_notebook_141f20fc.bid"
BIDDERS = ("bidder_a", "bidder_b", "bidder_c")


def config_json(bids, valuations):
    return {
        "world": {
            "actors": [
                {
                    "id": aid,
                    "kind": "bidder",
                    "action_space": {"schemas": {"submit_bid": BID_SCHEMA_ID}},
                    "policy_id": "scripted.v1",
                    "policy_parameters": {"kind": "submit_bid", "payload": {"bid": bids[aid]}},
                }
                for aid in BIDDERS
            ],
            "parameters": {
                "action_kind": "submit_bid",
                "bids_field": "bids",
                "outcome_field": "auction_outcome",
                "tie_break": "configuration_order",
            },
            "initial_public_state": {"rules": "Test auction rules."},
            "initial_private_state": {
                aid: {"facts": {"valuation": valuations[aid]}, "memory": {}} for aid in BIDDERS
            },
        },
        "mechanism_id": MECHANISM_ID,
        "protocol_id": "simultaneous.v1",
        "protocol_parameters": {"rounds": 1},
        "permissions": {
            aid: {
                "public_fields": ["rules"],
                "private_fields": ["valuation"],
                "readable_memory": True,
                "writable_private_fields": [],
                "writable_memory": True,
            }
            for aid in BIDDERS
        },
        "max_steps": 10,
    }


def auction_registry():
    registry = standard_registry()
    registry.mechanisms[MECHANISM_ID] = SecondPriceAuctionMechanism
    registry.action_schemas[BID_SCHEMA_ID] = BidPayload
    return registry


def world_and_state(bids, valuations):
    config = fixture_config(config_json(bids, valuations))
    protocol = SimultaneousProtocol({"rounds": 1})
    return config.world, fixture_state(config, protocol)


def bid_actions(bids):
    return [Action(actor_id=aid, kind="submit_bid", payload={"bid": bids[aid]}) for aid in BIDDERS]


def run_scripted_auction(bids, valuations):
    registry = auction_registry()
    config = fixture_config(config_json(bids, valuations))
    request = ExperimentRequest(hypothesis="Test auction run.", execution_kind="agent_simulation")
    return JobRunner(LocalBackend(registry)).run(request, config)


def test_mechanism_settles_second_price():
    mechanism = SecondPriceAuctionMechanism()
    bids = {"bidder_a": 80.0, "bidder_b": 70.0, "bidder_c": 40.0}
    valuations = {"bidder_a": 90.0, "bidder_b": 65.0, "bidder_c": 40.0}
    world, state = world_and_state(bids, valuations)
    mechanism.validate_config(world)
    mechanism.validate_state(world, state)
    actions = bid_actions(bids)
    mechanism.validate_actions(world, state, actions)
    outcome = mechanism.evaluate(world, state, actions)
    assert outcome.payoffs == {"bidder_a": 20.0, "bidder_b": 0.0, "bidder_c": 0.0}
    assert outcome.metrics["winner"] == "bidder_a"
    assert outcome.metrics["payment"] == 70.0
    assert outcome.metrics["bids"] == bids
    result = mechanism.transition(world, state, actions)
    assert result.outcome == outcome
    assert result.public["rules"] == "Test auction rules."
    assert result.public["bids"] == [bids]
    assert result.public["auction_outcome"] == [{"winner": "bidder_a", "payment": 70.0}]
    assert result.private_updates == {}


def test_mechanism_breaks_ties_by_configuration_order():
    mechanism = SecondPriceAuctionMechanism()
    valuations = {"bidder_a": 50.0, "bidder_b": 50.0, "bidder_c": 30.0}
    world, state = world_and_state(
        {"bidder_a": 50.0, "bidder_b": 50.0, "bidder_c": 30.0}, valuations
    )
    outcome = mechanism.evaluate(
        world, state, bid_actions({"bidder_a": 50.0, "bidder_b": 50.0, "bidder_c": 30.0})
    )
    assert outcome.metrics["winner"] == "bidder_a"
    assert outcome.metrics["payment"] == 50.0
    assert outcome.payoffs == {"bidder_a": 0.0, "bidder_b": 0.0, "bidder_c": 0.0}
    outcome = mechanism.evaluate(
        world, state, bid_actions({"bidder_a": 30.0, "bidder_b": 30.0, "bidder_c": 30.0})
    )
    assert outcome.metrics["winner"] == "bidder_a"
    assert outcome.metrics["payment"] == 30.0
    assert outcome.payoffs["bidder_a"] == 20.0


def test_mechanism_accepts_nontruthful_bids():
    mechanism = SecondPriceAuctionMechanism()
    valuations = {"bidder_a": 90.0, "bidder_b": 65.0, "bidder_c": 40.0}
    world, state = world_and_state(
        {"bidder_a": 60.0, "bidder_b": 100.0, "bidder_c": 90.0}, valuations
    )
    overbid = bid_actions({"bidder_a": 60.0, "bidder_b": 100.0, "bidder_c": 90.0})
    mechanism.validate_actions(world, state, overbid)
    outcome = mechanism.evaluate(world, state, overbid)
    assert outcome.metrics["winner"] == "bidder_b"
    assert outcome.metrics["payment"] == 90.0
    assert outcome.payoffs["bidder_b"] == -25.0
    underbid = bid_actions({"bidder_a": 10.0, "bidder_b": 20.0, "bidder_c": 30.0})
    mechanism.validate_actions(world, state, underbid)
    outcome = mechanism.evaluate(world, state, underbid)
    assert outcome.metrics["winner"] == "bidder_c"
    assert outcome.metrics["payment"] == 20.0
    assert outcome.payoffs["bidder_c"] == 20.0


def test_mechanism_rejects_illegal_bids():
    mechanism = SecondPriceAuctionMechanism()
    valuations = {"bidder_a": 90.0, "bidder_b": 65.0, "bidder_c": 40.0}
    world, state = world_and_state(
        {"bidder_a": 80.0, "bidder_b": 70.0, "bidder_c": 40.0}, valuations
    )
    good = bid_actions({"bidder_a": 80.0, "bidder_b": 70.0, "bidder_c": 40.0})
    bad_payloads = [
        {"bid": -5.0},
        {"bid": "70"},
        {},
        {"bid": None},
        {"bid": 70.0, "extra": 1.0},
    ]
    for payload in bad_payloads:
        actions = [good[0].model_copy(update={"payload": payload}), good[1], good[2]]
        with pytest.raises(ValueError):
            mechanism.validate_actions(world, state, actions)
    with pytest.raises(ValueError):
        mechanism.validate_actions(world, state, good[:2])
    with pytest.raises(ValueError):
        mechanism.validate_actions(
            world, state, [good[0].model_copy(update={"kind": "bid"}), good[1], good[2]]
        )
    with pytest.raises(ValueError):
        mechanism.validate_actions(
            world, state, [good[0].model_copy(update={"actor_id": "mallory"}), good[1], good[2]]
        )
    integer_bid = bid_actions({"bidder_a": 70, "bidder_b": 60, "bidder_c": 40})
    mechanism.validate_actions(world, state, integer_bid)
    zero_bid = bid_actions({"bidder_a": 0.0, "bidder_b": 0.0, "bidder_c": 0.0})
    mechanism.validate_actions(world, state, zero_bid)


def test_mechanism_rejects_bad_configurations():
    mechanism = SecondPriceAuctionMechanism()
    valuations = {"bidder_a": 90.0, "bidder_b": 65.0, "bidder_c": 40.0}
    bids = {"bidder_a": 80.0, "bidder_b": 70.0, "bidder_c": 40.0}
    data = config_json(bids, valuations)
    del data["world"]["initial_private_state"]["bidder_b"]["facts"]["valuation"]
    with pytest.raises(ValueError):
        mechanism.validate_config(fixture_config(data).world)
    data = config_json(bids, valuations)
    data["world"]["parameters"]["tie_break"] = "random"
    with pytest.raises(ValueError):
        mechanism.validate_config(fixture_config(data).world)
    data = config_json(bids, valuations)
    data["world"]["actors"] = data["world"]["actors"][:1]
    data["world"]["initial_private_state"] = {
        "bidder_a": {"facts": {"valuation": 90.0}, "memory": {}}
    }
    with pytest.raises(ValueError):
        mechanism.validate_config(fixture_config(data).world)


def test_mechanism_records_public_history():
    mechanism = SecondPriceAuctionMechanism()
    bids = {"bidder_a": 80.0, "bidder_b": 70.0, "bidder_c": 40.0}
    valuations = {"bidder_a": 90.0, "bidder_b": 65.0, "bidder_c": 40.0}
    world, state = world_and_state(bids, valuations)
    first = mechanism.transition(world, state, bid_actions(bids))
    assert len(first.public["bids"]) == 1
    assert len(first.public["auction_outcome"]) == 1
    private = {aid: {"facts": {"valuation": valuations[aid]}, "memory": {}} for aid in BIDDERS}
    tick_one = WorldState.from_json_values(
        {"tick": 1, "phase": "act", "public": first.public, "private": private}
    )
    mechanism.validate_state(world, tick_one)
    second = mechanism.transition(world, tick_one, bid_actions(bids))
    assert len(second.public["bids"]) == 2
    assert len(second.public["auction_outcome"]) == 2
    tampered = dict(first.public)
    tampered["bids"] = []
    bad = WorldState.from_json_values(
        {"tick": 1, "phase": "act", "public": tampered, "private": private}
    )
    with pytest.raises(ValueError):
        mechanism.validate_state(world, bad)


def test_sealed_bid_privacy_hides_others():
    valuations = {"bidder_a": 90.0, "bidder_b": 65.0, "bidder_c": 40.0}
    bids = {"bidder_a": 80.0, "bidder_b": 70.0, "bidder_c": 40.0}
    data = config_json(bids, valuations)
    for actor_json in data["world"]["actors"]:
        actor_json["policy_id"] = "llm.v1"
        actor_json["policy_parameters"] = {
            "model": "test-only",
            "instructions": "Submit one sealed bid.",
            "required_fields": ["rules"],
        }
    config = fixture_config(data)
    protocol = SimultaneousProtocol({"rounds": 1})
    state = fixture_state(config, protocol)
    assert protocol.active_actor_ids(config.world, state) == BIDDERS
    schemas = SecondPriceAuctionMechanism().required_action_schemas(config.world)
    for actor in config.world.actors:
        assert set(schemas[actor.id]) == {"submit_bid"}
        observation = observe(actor, state, permissions_for(config, actor.id, state.phase))
        assert observation.visible == {"rules": "Test auction rules."}
        expected = valuations[actor.id]
        assert observation.private.facts == {"valuation": expected}
        assert observation.private.memory == {}
        assert observation.allowed_action_kinds == ("submit_bid",)
        assert observation.writable_private_fields == ()
        blob = observation.model_dump_json()
        for other in BIDDERS:
            if other != actor.id:
                assert other not in blob
                assert str(float(valuations[other])) not in blob


def test_simulation_completes_single_simultaneous_round():
    bids = {"bidder_a": 80.0, "bidder_b": 70.0, "bidder_c": 40.0}
    valuations = {"bidder_a": 90.0, "bidder_b": 65.0, "bidder_c": 40.0}
    artifact = run_scripted_auction(bids, valuations)
    assert artifact.result.status == "completed"
    assert artifact.result.final_state.tick == 1
    assert artifact.result.final_state.phase == "finished"
    assert len(artifact.result.events) == 2
    committed = artifact.result.events[1]
    assert committed.kind == "committed"
    assert {action.actor_id for action in committed.actions} == set(BIDDERS)
    assert len(committed.decisions) == 3
    assert all(decision.rationale for decision in committed.decisions)
    assert committed.outcome is not None
    assert committed.outcome.payoffs == {"bidder_a": 20.0, "bidder_b": 0.0, "bidder_c": 0.0}
    assert committed.outcome.metrics["winner"] == "bidder_a"
    assert committed.outcome.metrics["payment"] == 70.0
    assert committed.state.public["bids"] == [bids]
    mechanism = SecondPriceAuctionMechanism()
    world, state = world_and_state(bids, valuations)
    direct = mechanism.evaluate(world, state, list(committed.actions))
    assert direct == committed.outcome


def test_bid_payload_accepts_finite_nonnegative():
    assert BidPayload.model_validate({"bid": 70}).bid == 70.0
    assert BidPayload.model_validate({"bid": 0}).bid == 0.0
    assert BidPayload.model_validate({"bid": 12.5}).bid == 12.5
    assert BidPayload.from_json_values({"bid": 3}).bid == 3.0
    assert BidPayload.model_validate_json('{"bid": 70}', strict=True).bid == 70.0


def test_bid_payload_rejects_invalid():
    with pytest.raises(ValueError):
        BidPayload.model_validate({"bid": -0.5})
    with pytest.raises(ValueError):
        BidPayload.model_validate({"bid": "70"}, strict=True)
    with pytest.raises(ValueError):
        BidPayload.model_validate({"bid": None})
    with pytest.raises(ValueError):
        BidPayload.model_validate({})
    with pytest.raises(ValueError):
        BidPayload.model_validate({"bid": 1.0, "extra": 0.0})
    with pytest.raises(ValueError):
        BidPayload(bid=float("nan"))
    with pytest.raises(ValueError):
        BidPayload(bid=float("inf"))
