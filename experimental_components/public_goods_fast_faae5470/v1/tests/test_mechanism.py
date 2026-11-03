"""Mechanism acceptance: budget legality, payoffs, withdrawal boundary, identities.

All expectations are hand-derived from the request rules:
  available_i = saved_balance_i + endowment_this_round
  payoff_i = endowment_this_round - contribution_i + multiplier * sum(contributions) / N
  closing_i = opening_i + payoff_i
Round number is tick + 1; rounds 1-3 are endowed, rounds 4-6 pay zero.
"""

import copy

import pytest
from experiment_extension.mechanism import (
    ContributionPayload,
    PublicGoodsWithdrawalMechanism,
)

from simulation_core.types import Action, WorldConfig, WorldState

PARAMS = {
    "participant_count": 3,
    "rounds": 6,
    "endowed_rounds": 3,
    "endowment": 20.0,
    "multiplier": 2.0,
}


def make_config(params=None, actors=("p1", "p2", "p3")):
    params = PARAMS if params is None else params
    return WorldConfig.from_json_values(
        {
            "actors": [
                {
                    "id": aid,
                    "kind": "participant",
                    "action_space": {
                        "schemas": {
                            "contribute": "experimental.public_goods_fast_faae5470.contribution"
                        }
                    },
                    "policy_id": "llm.v1",
                    "policy_parameters": {},
                }
                for aid in actors
            ],
            "parameters": params,
            "initial_public_state": {},
            "initial_private_state": {},
        }
    )


def make_state(config, tick, balances, history=()):
    return WorldState.from_json_values(
        {
            "tick": tick,
            "phase": "act",
            "public": {
                "rounds": config.parameters["rounds"],
                "endowed_rounds": config.parameters["endowed_rounds"],
                "endowment": config.parameters["endowment"],
                "multiplier": config.parameters["multiplier"],
                "participant_count": config.parameters["participant_count"],
                "saved_balances": dict(balances),
                "history": list(history),
            },
            "private": {actor.id: {"facts": {}, "memory": {}} for actor in config.actors},
        }
    )


def actions_for(contributions):
    return [
        Action(
            actor_id=aid,
            kind="contribute",
            payload={"contribution": value},
        )
        for aid, value in contributions.items()
    ]


def test_contribution_payload_contract():
    config = make_config()
    required = PublicGoodsWithdrawalMechanism().required_action_schemas(config)
    assert set(required) == {"p1", "p2", "p3"}
    for schemas in required.values():
        assert set(schemas) == {"contribute"}
        assert schemas["contribute"] is ContributionPayload
    assert set(ContributionPayload.model_json_schema()["required"]) == {"contribution"}


def test_mechanism_requires_joint_actions():
    assert PublicGoodsWithdrawalMechanism.requires_joint_actions is True
    assert PublicGoodsWithdrawalMechanism().validate_config(make_config()) is None


def test_validate_config_accepts_request_values():
    config = make_config()
    assert PublicGoodsWithdrawalMechanism().validate_config(config) is None


@pytest.mark.parametrize(
    "override",
    [
        {"endowed_rounds": 7},
        {"multiplier": 0.0},
        {"multiplier": -1.0},
        {"endowment": -0.5},
        {"rounds": 0},
        {"participant_count": 2},
    ],
)
def test_validate_config_rejects_bad_parameters(override):
    params = {**PARAMS, **override}
    with pytest.raises((ValueError, TypeError)):
        PublicGoodsWithdrawalMechanism().validate_config(make_config(params))


def test_validate_state_rejects_missing_balances():
    config = make_config()
    state = make_state(config, 0, {"p1": 0.0, "p2": 0.0, "p3": 0.0})
    broken = state.model_copy(deep=True)
    public = dict(broken.public)
    del public["saved_balances"]
    broken = WorldState(
        tick=broken.tick,
        phase=broken.phase,
        public=public,
        private=broken.private,
    )
    with pytest.raises((ValueError, TypeError)):
        PublicGoodsWithdrawalMechanism().validate_state(config, broken)


def test_mechanism_withdrawal_boundary():
    # Zero contributions isolate the endowment: round 3 (tick 2) pays 20, round 4 pays 0.
    config = make_config()
    zero = {"p1": 0.0, "p2": 0.0, "p3": 0.0}
    state3 = make_state(config, 2, zero)
    out3 = PublicGoodsWithdrawalMechanism().evaluate(config, state3, actions_for(zero))
    assert out3.payoffs == {"p1": 20.0, "p2": 20.0, "p3": 20.0}
    state4 = make_state(config, 3, zero)
    out4 = PublicGoodsWithdrawalMechanism().evaluate(config, state4, actions_for(zero))
    assert out4.payoffs == {"p1": 0.0, "p2": 0.0, "p3": 0.0}


def test_payoff_hand_derived_mixed_contributions():
    # Contributions (10, 20, 0): pool = 2*30/3 = 20 each.
    # p1: 20-10+20=30; p2: 20-20+20=20; p3: 20-0+20=40.
    config = make_config()
    state = make_state(config, 0, {"p1": 0.0, "p2": 0.0, "p3": 0.0})
    contribs = {"p1": 10.0, "p2": 20.0, "p3": 0.0}
    outcome = PublicGoodsWithdrawalMechanism().evaluate(config, state, actions_for(contribs))
    assert outcome.payoffs == {"p1": 30.0, "p2": 20.0, "p3": 40.0}
    result = PublicGoodsWithdrawalMechanism().transition(config, state, actions_for(contribs))
    assert result.public["saved_balances"] == {"p1": 30.0, "p2": 20.0, "p3": 40.0}
    assert result.outcome.payoffs == {"p1": 30.0, "p2": 20.0, "p3": 40.0}


def test_over_20_contribution_legal_with_savings():
    # Balance 50 + endowment 20 allows 35; pool = 2*35/3 per head.
    config = make_config()
    state = make_state(config, 0, {"p1": 50.0, "p2": 0.0, "p3": 0.0})
    contribs = {"p1": 35.0, "p2": 0.0, "p3": 0.0}
    PublicGoodsWithdrawalMechanism().validate_actions(config, state, actions_for(contribs))
    outcome = PublicGoodsWithdrawalMechanism().evaluate(config, state, actions_for(contribs))
    assert outcome.payoffs["p1"] == pytest.approx(20.0 - 35.0 + 70.0 / 3.0)
    result = PublicGoodsWithdrawalMechanism().transition(config, state, actions_for(contribs))
    assert result.public["saved_balances"]["p1"] == pytest.approx(50.0 + outcome.payoffs["p1"])


def test_all_in_legal_after_withdrawal():
    # Tick 4 (round 5): no endowment, full 60 savings may be contributed.
    config = make_config()
    state = make_state(config, 4, {"p1": 60.0, "p2": 60.0, "p3": 60.0})
    contribs = {"p1": 60.0, "p2": 0.0, "p3": 0.0}
    PublicGoodsWithdrawalMechanism().validate_actions(config, state, actions_for(contribs))
    outcome = PublicGoodsWithdrawalMechanism().evaluate(config, state, actions_for(contribs))
    # Pool = 2*60/3 = 40: p1 gets 0-60+40 = -20, others get 40.
    assert outcome.payoffs == {"p1": -20.0, "p2": 40.0, "p3": 40.0}
    result = PublicGoodsWithdrawalMechanism().transition(config, state, actions_for(contribs))
    assert result.public["saved_balances"] == {"p1": 40.0, "p2": 100.0, "p3": 100.0}


def test_zero_contribution_always_legal():
    config = make_config()
    state = make_state(config, 5, {"p1": 0.0, "p2": 3.0, "p3": 100.0})
    batch = actions_for({"p1": 0.0, "p2": 0.0, "p3": 0.0})
    assert PublicGoodsWithdrawalMechanism().validate_actions(config, state, batch) is None


def test_mechanism_budget_legality():
    # Zero balances plus the 20 endowment: 0 and the full 20 are legal, 20.01 is not.
    config = make_config()
    state = make_state(config, 0, {"p1": 0.0, "p2": 0.0, "p3": 0.0})
    assert (
        PublicGoodsWithdrawalMechanism().validate_actions(
            config, state, actions_for({"p1": 0.0, "p2": 20.0, "p3": 0.0})
        )
        is None
    )
    with pytest.raises((ValueError, TypeError)):
        PublicGoodsWithdrawalMechanism().validate_actions(
            config, state, actions_for({"p1": 20.01, "p2": 0.0, "p3": 0.0})
        )


def test_rejects_negative_contribution():
    config = make_config()
    state = make_state(config, 0, {"p1": 0.0, "p2": 0.0, "p3": 0.0})
    with pytest.raises((ValueError, TypeError)):
        PublicGoodsWithdrawalMechanism().validate_actions(
            config, state, actions_for({"p1": -1.0, "p2": 0.0, "p3": 0.0})
        )


def test_rejects_nonfinite_payload_at_boundary():
    # Frozen core models forbid nonfinite transport values before evaluation.
    with pytest.raises((ValueError, TypeError)):
        Action(actor_id="p1", kind="contribute", payload={"contribution": float("inf")})
    with pytest.raises((ValueError, TypeError)):
        ContributionPayload.model_validate({"contribution": float("nan")})


def test_rejects_bad_batches():
    config = make_config()
    state = make_state(config, 0, {"p1": 0.0, "p2": 0.0, "p3": 0.0})
    good = actions_for({"p1": 1.0, "p2": 1.0, "p3": 1.0})
    with pytest.raises((ValueError, TypeError)):
        PublicGoodsWithdrawalMechanism().validate_actions(config, state, good[:2])
    with pytest.raises((ValueError, TypeError)):
        PublicGoodsWithdrawalMechanism().validate_actions(
            config,
            state,
            [*good, Action(actor_id="p1", kind="contribute", payload={"contribution": 1.0})],
        )
    with pytest.raises((ValueError, TypeError)):
        PublicGoodsWithdrawalMechanism().validate_actions(
            config,
            state,
            [
                Action(actor_id="p1", kind="other", payload={"contribution": 1.0}),
                *good[1:],
            ],
        )
    with pytest.raises((ValueError, TypeError)):
        PublicGoodsWithdrawalMechanism().validate_actions(
            config,
            state,
            [
                Action(actor_id="pX", kind="contribute", payload={"contribution": 1.0}),
                *good[1:],
            ],
        )


def test_mechanism_payoff_identity():
    # Round 2 (tick 1), pool = 2*39.5/3 per head.
    # p1: 20-12.5+79/3; p2: 20-7+79/3; p3: 20-20+79/3.
    config = make_config()
    opening = {"p1": 12.5, "p2": 7.0, "p3": 0.0}
    state = make_state(config, 1, opening)
    contribs = {"p1": 12.5, "p2": 7.0, "p3": 20.0}
    outcome = PublicGoodsWithdrawalMechanism().evaluate(config, state, actions_for(contribs))
    assert outcome.payoffs["p1"] == pytest.approx(7.5 + 79.0 / 3.0)
    assert outcome.payoffs["p2"] == pytest.approx(13.0 + 79.0 / 3.0)
    assert outcome.payoffs["p3"] == pytest.approx(79.0 / 3.0)
    result = PublicGoodsWithdrawalMechanism().transition(config, state, actions_for(contribs))
    for aid, opening_balance in opening.items():
        assert result.public["saved_balances"][aid] == pytest.approx(
            opening_balance + outcome.payoffs[aid]
        )
    total = sum(result.public["saved_balances"].values())
    assert total == pytest.approx(19.5 + 3 * 20.0 + (2.0 - 1.0) * 39.5)


def test_wealth_identity_request_values():
    # sum(closing) = sum(opening) + N*e + (m-1)*sum(c)
    # = 19.5 + 60 + 39.5 = 119.0 for the case below.
    config = make_config()
    opening = {"p1": 12.5, "p2": 7.0, "p3": 0.0}
    state = make_state(config, 1, opening)
    contribs = {"p1": 12.5, "p2": 7.0, "p3": 20.0}
    result = PublicGoodsWithdrawalMechanism().transition(config, state, actions_for(contribs))
    total = sum(result.public["saved_balances"].values())
    assert total == pytest.approx(19.5 + 3 * 20.0 + (2.0 - 1.0) * 39.5)


def test_wealth_identity_varied_parameters():
    # N=2, m=1.5, e=10, tick 0, zero balances, contributions (4, 6):
    # pool each = 1.5*10/2 = 7.5; p1: 10-4+7.5=13.5; p2: 10-6+7.5=11.5.
    params = {
        "participant_count": 2,
        "rounds": 4,
        "endowed_rounds": 1,
        "endowment": 10.0,
        "multiplier": 1.5,
    }
    config = make_config(params, actors=("p1", "p2"))
    PublicGoodsWithdrawalMechanism().validate_config(config)
    state = make_state(config, 0, {"p1": 0.0, "p2": 0.0})
    contribs = {"p1": 4.0, "p2": 6.0}
    outcome = PublicGoodsWithdrawalMechanism().evaluate(config, state, actions_for(contribs))
    assert outcome.payoffs == {"p1": 13.5, "p2": 11.5}
    result = PublicGoodsWithdrawalMechanism().transition(config, state, actions_for(contribs))
    total = sum(result.public["saved_balances"].values())
    assert total == pytest.approx(0.0 + 2 * 10.0 + 0.5 * 10.0)


def test_varied_horizon_withdrawal_first_round_unendowed():
    # endowed_rounds=1, rounds=2: tick 1 already pays zero endowment.
    params = {
        "participant_count": 2,
        "rounds": 2,
        "endowed_rounds": 1,
        "endowment": 10.0,
        "multiplier": 1.5,
    }
    config = make_config(params, actors=("p1", "p2"))
    state = make_state(config, 1, {"p1": 13.5, "p2": 11.5})
    outcome = PublicGoodsWithdrawalMechanism().evaluate(
        config, state, actions_for({"p1": 0.0, "p2": 0.0})
    )
    assert outcome.payoffs == {"p1": 0.0, "p2": 0.0}


def test_history_appends_one_record_per_round():
    config = make_config()
    state = make_state(config, 0, {"p1": 0.0, "p2": 0.0, "p3": 0.0})
    contribs = {"p1": 10.0, "p2": 20.0, "p3": 0.0}
    result = PublicGoodsWithdrawalMechanism().transition(config, state, actions_for(contribs))
    assert len(result.public["history"]) == 1
    record = result.public["history"][0]
    assert record["round"] == 1
    assert record["contributions"] == contribs
    assert record["payoffs"] == {"p1": 30.0, "p2": 20.0, "p3": 40.0}
    assert record["balances"] == {"p1": 30.0, "p2": 20.0, "p3": 40.0}
    assert record["endowment"] == 20.0


def test_evaluate_does_not_mutate_inputs():
    config = make_config()
    state = make_state(config, 0, {"p1": 5.0, "p2": 5.0, "p3": 5.0})
    batch = actions_for({"p1": 5.0, "p2": 5.0, "p3": 5.0})
    before_config = copy.deepcopy(config.model_dump())
    before_state = copy.deepcopy(state.model_dump())
    PublicGoodsWithdrawalMechanism().evaluate(config, state, batch)
    assert config.model_dump() == before_config
    assert state.model_dump() == before_state


def test_transition_leaves_private_state_to_policies():
    # No mechanism private updates, so policies may still write their own memory.
    config = make_config()
    state = make_state(config, 0, {"p1": 0.0, "p2": 0.0, "p3": 0.0})
    result = PublicGoodsWithdrawalMechanism().transition(
        config, state, actions_for({"p1": 1.0, "p2": 1.0, "p3": 1.0})
    )
    assert dict(result.private_updates) == {}
