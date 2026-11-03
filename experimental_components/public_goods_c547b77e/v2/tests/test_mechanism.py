"""Acceptance tests for the saved-balance public-goods mechanism and payload."""

import math

import pytest
from experiment_extension.mechanism import PublicGoodsMechanism
from experiment_extension.schemas import ContributionPayload

from agent_tools.fixtures import fixture_config, fixture_state
from components.protocols.simultaneous import SimultaneousProtocol
from simulation_core.observation import observe, permissions_for
from simulation_core.protocol import DecisionPhase
from simulation_core.types import Action, WorldState
from simulation_core.validation import equivalent_payload_schema

MECHANISM_ID = "experimental.public_goods_c547b77e.public_goods.v1"
SCHEMA_ID = "experimental.public_goods_c547b77e.contribution.v1"
ACTION_KIND = "contribute"
PUBLIC_FIELDS = (
    "round",
    "rounds",
    "endowed_rounds",
    "endowment",
    "multiplier",
    "endowment_this_round",
    "balances",
    "history",
)


def actor_ids(n):
    return tuple(f"p{i + 1}" for i in range(n))


def config_dict(n=5, rounds=10, endowed_rounds=5, endowment=20.0, multiplier=2.0):
    ids = actor_ids(n)
    return {
        "world": {
            "actors": [
                {
                    "id": aid,
                    "kind": "participant",
                    "action_space": {"schemas": {ACTION_KIND: SCHEMA_ID}},
                    "policy_id": "scripted.v1",
                    "policy_parameters": {
                        "kind": ACTION_KIND,
                        "payload": {"contribution": 0.0},
                    },
                }
                for aid in ids
            ],
            "parameters": {
                "participant_count": n,
                "rounds": rounds,
                "endowed_rounds": endowed_rounds,
                "endowment": endowment,
                "multiplier": multiplier,
            },
            "initial_public_state": {
                "round": 1,
                "rounds": rounds,
                "endowed_rounds": endowed_rounds,
                "endowment": endowment,
                "multiplier": multiplier,
                "endowment_this_round": endowment if endowed_rounds >= 1 else 0.0,
                "balances": {aid: 0.0 for aid in ids},
                "history": [],
            },
        },
        "mechanism_id": MECHANISM_ID,
        "protocol_id": "simultaneous.v1",
        "protocol_parameters": {"rounds": rounds},
        "permissions": {
            aid: {
                "public_fields": list(PUBLIC_FIELDS),
                "private_fields": [],
                "readable_memory": True,
                "writable_private_fields": [],
                "writable_memory": True,
            }
            for aid in ids
        },
    }


def setup(n=5, **kwargs):
    raw = config_dict(n, **kwargs)
    config = fixture_config(raw)
    protocol = SimultaneousProtocol({"rounds": raw["world"]["parameters"]["rounds"]})
    mechanism = PublicGoodsMechanism()
    state = fixture_state(config, protocol)
    mechanism.validate_config(config.world)
    mechanism.validate_state(config.world, state)
    return mechanism, config, state


def contribute(aid, amount):
    return Action(actor_id=aid, kind=ACTION_KIND, payload={"contribution": float(amount)})


def full_batch(ids, amounts):
    if isinstance(amounts, dict):
        return tuple(contribute(aid, amounts[aid]) for aid in ids)
    return tuple(contribute(aid, amounts) for aid in ids)


def apply_transition(mechanism, config, state, actions):
    result = mechanism.transition(config.world, state, actions)
    private = {aid: item.model_copy(deep=True) for aid, item in state.private.items()}
    for aid, update in result.private_updates.items():
        private[aid] = update
    return WorldState(
        tick=state.tick + 1,
        phase=state.phase,
        public=result.public,
        private=private,
    )


def all_twenty_entry(round_no, ids):
    # Hand-derived: five contributions of 20 give total 100, payout 40, payoff 40.
    return {
        "round": round_no,
        "endowment": 20.0,
        "contributions": {aid: 20.0 for aid in ids},
        "total_contribution": 100.0,
        "per_capita_payout": 40.0,
        "payoffs": {aid: 40.0 for aid in ids},
    }


def hand_state(config, tick, balances, history):
    params = config.world.parameters
    round_no = tick + 1
    return WorldState(
        tick=tick,
        phase="act",
        public={
            "round": round_no,
            "rounds": params["rounds"],
            "endowed_rounds": params["endowed_rounds"],
            "endowment": params["endowment"],
            "multiplier": params["multiplier"],
            "endowment_this_round": params["endowment"]
            if round_no <= params["endowed_rounds"]
            else 0.0,
            "balances": dict(balances),
            "history": [dict(entry) for entry in history],
        },
        private={aid: {"facts": {}, "memory": {}} for aid in actor_ids(len(balances))},
    )


def test_mechanism_requires_joint_actions():
    assert PublicGoodsMechanism.requires_joint_actions is True
    mechanism, config, _ = setup()
    with pytest.raises(ValueError):
        mechanism.validate_schedule(config.world, (DecisionPhase(name="act", actor_ids=("p1",)),))


def test_mechanism_action_schema_contract():
    mechanism, config, _ = setup()
    contract = mechanism.required_action_schemas(config.world)
    assert set(contract) == set(actor_ids(5))
    for schemas in contract.values():
        assert set(schemas) == {ACTION_KIND}
        assert equivalent_payload_schema(schemas[ACTION_KIND], ContributionPayload)


def test_validate_config_accepts_experiment_parameters():
    _mechanism, config, state = setup()
    assert config.world.parameters["participant_count"] == 5
    assert state.public["balances"] == {aid: 0.0 for aid in actor_ids(5)}


def test_validate_config_rejects_shape_mismatch():
    mechanism = PublicGoodsMechanism()
    raw = config_dict()
    raw["world"]["parameters"]["participant_count"] = 4
    with pytest.raises(ValueError):
        mechanism.validate_config(fixture_config(raw).world)
    raw = config_dict(endowed_rounds=11)
    with pytest.raises(ValueError):
        mechanism.validate_config(fixture_config(raw).world)
    raw = config_dict(endowed_rounds=-1)
    with pytest.raises(ValueError):
        mechanism.validate_config(fixture_config(raw).world)
    raw = config_dict(rounds=0)
    with pytest.raises(ValueError):
        mechanism.validate_config(fixture_config(raw).world)
    raw = config_dict(n=1)
    with pytest.raises(ValueError):
        mechanism.validate_config(fixture_config(raw).world)
    raw = config_dict()
    raw["world"]["parameters"]["bonus"] = 1.0
    with pytest.raises(ValueError):
        mechanism.validate_config(fixture_config(raw).world)
    mechanism2, config, _ = setup()
    bad = hand_state(config, 0, {aid: 10.0 for aid in actor_ids(5)}, [])
    with pytest.raises(ValueError):
        mechanism2.validate_state(config.world, bad)


def test_validate_config_rejects_negative_values():
    mechanism = PublicGoodsMechanism()
    with pytest.raises(ValueError):
        mechanism.validate_config(fixture_config(config_dict(endowment=-5.0)).world)
    with pytest.raises(ValueError):
        mechanism.validate_config(fixture_config(config_dict(multiplier=-1.0)).world)
    with pytest.raises(ValueError):
        fixture_config(config_dict(endowment=float("inf")))
    with pytest.raises(ValueError):
        fixture_config(config_dict(multiplier=float("nan")))


def test_hand_derived_round_payoffs():
    mechanism, config, state = setup()
    ids = actor_ids(5)
    amounts = {"p1": 20.0, "p2": 10.0, "p3": 0.0, "p4": 5.0, "p5": 15.0}
    outcome = mechanism.evaluate(config.world, state, full_batch(ids, amounts))
    expected = {"p1": 20.0, "p2": 30.0, "p3": 40.0, "p4": 35.0, "p5": 25.0}
    assert set(outcome.payoffs) == set(ids)
    for aid, value in expected.items():
        assert math.isclose(outcome.payoffs[aid], value, rel_tol=1e-9)
    assert math.isclose(outcome.metrics["total_contribution"], 50.0, rel_tol=1e-9)
    assert math.isclose(outcome.metrics["per_capita_payout"], 20.0, rel_tol=1e-9)


def test_wealth_identity_hand_case():
    mechanism, config, state = setup()
    ids = actor_ids(5)
    amounts = {"p1": 20.0, "p2": 10.0, "p3": 0.0, "p4": 5.0, "p5": 15.0}
    result = mechanism.transition(config.world, state, full_batch(ids, amounts))
    closing = result.public["balances"]
    # sum(closing) = sum(opening) + N*endowment + (multiplier-1)*total = 0+100+50.
    assert math.isclose(sum(closing.values()), 150.0, rel_tol=1e-9)
    assert math.isclose(sum(result.outcome.payoffs.values()), 150.0, rel_tol=1e-9)


def test_validate_actions_rejects_over_budget():
    mechanism, config, state = setup()
    ids = actor_ids(5)
    with pytest.raises(ValueError):
        mechanism.validate_actions(
            config.world,
            state,
            full_batch(ids, {"p1": 20.01, "p2": 0.0, "p3": 0.0, "p4": 0.0, "p5": 0.0}),
        )
    with pytest.raises(ValueError):
        mechanism.validate_actions(config.world, state, full_batch(ids, 25.0))


def test_validate_actions_rejects_negative_and_nonfinite():
    mechanism, config, state = setup()
    ids = actor_ids(5)
    with pytest.raises(ValueError):
        mechanism.validate_actions(config.world, state, full_batch(ids, -1.0))
    bad_kind = full_batch(ids, 0.0)
    as_list = list(bad_kind)
    as_list[0] = Action(actor_id="p1", kind=ACTION_KIND, payload={"contribution": True})
    with pytest.raises(ValueError):
        mechanism.validate_actions(config.world, state, tuple(as_list))
    as_list[0] = Action(actor_id="p1", kind=ACTION_KIND, payload={"contribution": "10"})
    with pytest.raises(ValueError):
        mechanism.validate_actions(config.world, state, tuple(as_list))
    for bad in (float("inf"), float("nan")):
        actions = list(full_batch(ids, 0.0))
        actions[0] = Action.model_construct(
            actor_id="p1", kind=ACTION_KIND, payload={"contribution": bad}
        )
        with pytest.raises(ValueError):
            mechanism.validate_actions(config.world, state, tuple(actions))


def test_validate_actions_rejects_partial_batch():
    mechanism, config, state = setup()
    ids = actor_ids(5)
    with pytest.raises(ValueError):
        mechanism.validate_actions(config.world, state, full_batch(ids[:4], 5.0))
    duplicate = (
        contribute("p1", 5.0),
        contribute("p1", 5.0),
        contribute("p2", 5.0),
        contribute("p3", 5.0),
        contribute("p4", 5.0),
    )
    with pytest.raises(ValueError):
        mechanism.validate_actions(config.world, state, duplicate)
    wrong_kind = list(full_batch(ids, 5.0))
    wrong_kind[0] = Action(actor_id="p1", kind="donate", payload={"contribution": 5.0})
    with pytest.raises(ValueError):
        mechanism.validate_actions(config.world, state, tuple(wrong_kind))
    unknown = list(full_batch(ids[:4], 5.0)) + [contribute("pX", 5.0)]
    with pytest.raises(ValueError):
        mechanism.validate_actions(config.world, state, tuple(unknown))


def test_large_and_all_in_contributions_legal():
    mechanism, config, _ = setup()
    ids = actor_ids(5)
    base = hand_state(
        config, 2, {aid: 80.0 for aid in ids}, [all_twenty_entry(1, ids), all_twenty_entry(2, ids)]
    )
    mechanism.validate_state(config.world, base)
    # Available funds are 80 saved + 20 endowment, so 30 (above 20) is legal.
    over_twenty = mechanism.transition(config.world, base, full_batch(ids, 30.0))
    for aid in ids:
        assert math.isclose(over_twenty.public["balances"][aid], 130.0, rel_tol=1e-9)
    all_in = mechanism.transition(config.world, base, full_batch(ids, 100.0))
    for aid in ids:
        assert math.isclose(all_in.public["balances"][aid], 200.0, rel_tol=1e-9)


def test_post_withdrawal_saved_fund_contribution():
    mechanism, config, _ = setup()
    ids = actor_ids(5)
    history = [all_twenty_entry(i, ids) for i in range(1, 6)]
    base = hand_state(config, 5, {aid: 200.0 for aid in ids}, history)
    mechanism.validate_state(config.world, base)
    assert base.public["round"] == 6
    assert base.public["endowment_this_round"] == 0.0
    # Positive contributions from savings remain legal after withdrawal.
    result = mechanism.transition(config.world, base, full_batch(ids, 25.0))
    for aid in ids:
        assert math.isclose(result.public["balances"][aid], 225.0, rel_tol=1e-9)
    stayed_out = mechanism.transition(config.world, base, full_batch(ids, 0.0))
    for aid in ids:
        assert math.isclose(stayed_out.public["balances"][aid], 200.0, rel_tol=1e-9)
    with pytest.raises(ValueError):
        mechanism.validate_actions(config.world, base, full_batch(ids, 500.0))


def test_poor_strategy_remains_legal():
    mechanism, config, _ = setup()
    ids = actor_ids(5)
    base = hand_state(
        config, 2, {aid: 80.0 for aid in ids}, [all_twenty_entry(1, ids), all_twenty_entry(2, ids)]
    )
    amounts = {"p1": 100.0, "p2": 0.0, "p3": 0.0, "p4": 0.0, "p5": 0.0}
    result = mechanism.transition(config.world, base, full_batch(ids, amounts))
    # Unilateral all-in loses 40 this round but stays legal: no strategy policing.
    assert math.isclose(result.public["balances"]["p1"], 40.0, rel_tol=1e-9)
    for aid in ("p2", "p3", "p4", "p5"):
        assert math.isclose(result.public["balances"][aid], 140.0, rel_tol=1e-9)


def test_five_six_round_boundary():
    mechanism, config, state = setup()
    ids = actor_ids(5)
    for _ in range(4):
        state = apply_transition(mechanism, config, state, full_batch(ids, 10.0))
    assert state.tick == 4
    assert state.public["round"] == 5
    assert state.public["endowment_this_round"] == 20.0
    state = apply_transition(mechanism, config, state, full_batch(ids, 10.0))
    assert state.tick == 5
    assert state.public["round"] == 6
    assert state.public["endowment_this_round"] == 0.0
    for aid in ids:
        assert math.isclose(state.public["balances"][aid], 150.0, rel_tol=1e-9)
    assert state.public["history"][4]["round"] == 5
    assert state.public["history"][4]["endowment"] == 20.0
    state = apply_transition(mechanism, config, state, full_batch(ids, 10.0))
    assert state.public["history"][5]["round"] == 6
    assert state.public["history"][5]["endowment"] == 0.0
    for aid in ids:
        assert math.isclose(state.public["balances"][aid], 160.0, rel_tol=1e-9)


def test_no_double_counting_across_rounds():
    mechanism, config, state = setup()
    ids = actor_ids(5)
    first = {"p1": 20.0, "p2": 10.0, "p3": 0.0, "p4": 5.0, "p5": 15.0}
    state = apply_transition(mechanism, config, state, full_batch(ids, first))
    entry = state.public["history"][0]
    for aid in ids:
        assert math.isclose(state.public["balances"][aid], entry["payoffs"][aid], rel_tol=1e-9)
    opening = dict(state.public["balances"])
    state = apply_transition(mechanism, config, state, full_batch(ids, 10.0))
    expected = {"p1": 50.0, "p2": 60.0, "p3": 70.0, "p4": 65.0, "p5": 55.0}
    for aid in ids:
        # Closing is opening plus the round payoff, never the payoff alone.
        assert math.isclose(state.public["balances"][aid], expected[aid], rel_tol=1e-9)
        assert math.isclose(
            state.public["balances"][aid],
            opening[aid] + state.public["history"][1]["payoffs"][aid],
            rel_tol=1e-9,
        )
    assert math.isclose(sum(state.public["balances"].values()), 300.0, rel_tol=1e-9)


def test_observation_privacy_and_memory():
    _, config, state = setup()
    ids = actor_ids(5)
    private = {aid: {"facts": {}, "memory": {"note": f"{aid}-plan"}} for aid in ids}
    private["p2"]["memory"] = {"secret": "p2-only"}
    observed_state = WorldState(
        tick=state.tick,
        phase=state.phase,
        public=dict(state.public),
        private=private,
    )
    actor = next(item for item in config.world.actors if item.id == "p1")
    permissions = permissions_for(config, "p1", observed_state.phase)
    observation = observe(actor, observed_state, permissions)
    assert set(observation.visible) == set(PUBLIC_FIELDS)
    assert "actions" not in observation.visible
    assert observation.private.memory == {"note": "p1-plan"}
    assert "p2-only" not in observation.model_dump_json()
    assert observation.writable_private_fields == ()
    assert observation.writable_memory is True
    other = next(item for item in config.world.actors if item.id == "p2")
    other_observation = observe(
        other, observed_state, permissions_for(config, "p2", observed_state.phase)
    )
    assert "p1-plan" not in other_observation.model_dump_json()


def test_parameter_variations():
    cases = [
        {"n": 2, "rounds": 3, "endowed_rounds": 1, "endowment": 10.0, "multiplier": 1.5},
        {"n": 3, "rounds": 4, "endowed_rounds": 0, "endowment": 25.0, "multiplier": 3.0},
        {"n": 4, "rounds": 2, "endowed_rounds": 2, "endowment": 5.0, "multiplier": 0.5},
    ]
    for case in cases:
        mechanism, config, state = setup(**case)
        ids = actor_ids(case["n"])
        for _ in range(case["rounds"]):
            available = {
                aid: state.public["balances"][aid] + state.public["endowment_this_round"]
                for aid in ids
            }
            amounts = {aid: available[aid] / 2 for aid in ids}
            endowment = state.public["endowment_this_round"]
            opening = sum(state.public["balances"].values())
            total = sum(amounts[aid] for aid in ids)
            state = apply_transition(mechanism, config, state, full_batch(ids, amounts))
            expected = opening + case["n"] * endowment + (case["multiplier"] - 1.0) * total
            assert math.isclose(sum(state.public["balances"].values()), expected, rel_tol=1e-9)
        assert state.tick == case["rounds"]
        endowments = [entry["endowment"] for entry in state.public["history"]]
        if case["endowed_rounds"] == 0:
            assert endowments == [0.0] * case["rounds"]
        if case["endowed_rounds"] == case["rounds"]:
            assert endowments == [case["endowment"]] * case["rounds"]


def test_contribution_payload_accepts_valid():
    assert ContributionPayload(contribution=0.0).contribution == 0.0
    assert ContributionPayload(contribution=10).contribution == 10.0
    assert ContributionPayload(contribution=1000000000.0).contribution == 1000000000.0
    assert ContributionPayload.model_validate({"contribution": 2.5}).contribution == 2.5


def test_contribution_payload_rejects_negative():
    with pytest.raises(ValueError):
        ContributionPayload(contribution=-0.1)
    with pytest.raises(ValueError):
        ContributionPayload(contribution=-1000000000.0)
    with pytest.raises(ValueError):
        ContributionPayload.model_validate({"contribution": float("nan")})
