"""Shared auction fixtures mirroring the draft simulation configuration.

Builders return plain JSON dictionaries so tests can cross the strict
tuple-backed core-model boundary with ``fixture_config`` or ``from_json_values``.
Expected settlement values come from the small first-principles oracle
:func:`settle_expected`, and headline cases additionally assert hardcoded literals
grounded in the user's auction rules.
"""

import json

from simulation_core.types import Action

ACTORS = ("bidder_a", "bidder_b", "bidder_c")
VALUATIONS = {"bidder_a": 90.0, "bidder_b": 65.0, "bidder_c": 40.0}
MODEL = "muse-spark-1.3-contributor"
MECH_ID = "experimental.auction_muse_20261102.auction"
BID_ID = "experimental.auction_muse_20261102.auction.bid"

RULES = (
    "Sealed-bid second-price auction for one indivisible item. Each bidder submits "
    "exactly one sealed bid, a finite nonnegative number; bidding above or below your "
    "own valuation is allowed. The highest bid wins and pays the second-highest "
    "submitted bid. The winner earns its own valuation minus that payment; every other "
    "bidder pays nothing and earns zero. Tied highest bids are broken in bidder "
    "configuration order. There is no reserve price and no budget limit. You observe "
    "only these public rules and your own private valuation; you cannot see other "
    "bidders' valuations or bids before committing."
)

INSTRUCTIONS = (
    "Bid in a sealed-bid second-price auction for one indivisible item with no reserve "
    "and no budget limits. Your observation shows the public rules and your own private "
    "valuation. Submit exactly one bid as a finite nonnegative number; bids above or "
    "below your valuation are legal and will not be rejected. The highest bid wins and "
    "pays the second-highest submitted bid, the winner earns its valuation minus that "
    "payment, and every other bidder pays nothing and earns zero. Tied highest bids are "
    "broken in bidder configuration order. Choose the bid you prefer given your own "
    "valuation and the rules, and write a concise rationale citing your valuation. Do "
    "not claim knowledge of other bidders' simultaneous uncommitted choices."
)


def settle_expected(
    bids: dict[str, float], valuations: dict[str, float], order: list[str] | tuple[str, ...]
) -> tuple[str, float, dict[str, float]]:
    """First-principles second-price settlement oracle used by the tests."""
    order = list(order)
    winner = order[0]
    for actor_id in order[1:]:
        if bids[actor_id] > bids[winner]:
            winner = actor_id
    payment = max(bids[actor_id] for actor_id in order if actor_id != winner)
    payoffs = {
        actor_id: (valuations[actor_id] - payment if actor_id == winner else 0.0)
        for actor_id in order
    }
    return winner, payment, payoffs


def world_parameters(order: list[str] | tuple[str, ...] = ACTORS, **overrides) -> dict:
    params = {
        "action_kind": "bid",
        "valuation_fact": "valuation",
        "bids_field": "bids",
        "winner_field": "winner",
        "payment_field": "payment",
        "payoffs_field": "payoffs",
        "tie_break_order": list(order),
        "pricing": "second_price",
        "values_model": "independent_private_values",
        "utility_model": "risk_neutral_quasilinear",
        "item": "single_indivisible",
        "reserve": 0.0,
        "budgets": "none",
        "allow_above_valuation": True,
    }
    params.update(overrides)
    return params


def simulation_dict(
    actor_ids: list[str] | tuple[str, ...] = ACTORS,
    valuations: dict[str, float] | None = None,
    tie_break: list[str] | tuple[str, ...] | None = None,
    rounds: int = 1,
) -> dict:
    actor_ids = list(actor_ids)
    values = dict(VALUATIONS if valuations is None else valuations)
    order = list(tie_break) if tie_break is not None else list(actor_ids)
    return {
        "schema_version": "simulation.config.v1",
        "world": {
            "actors": [
                {
                    "id": actor_id,
                    "kind": "bidder",
                    "action_space": {"schemas": {"bid": BID_ID}},
                    "policy_id": "llm.v1",
                    "policy_parameters": {
                        "model": MODEL,
                        "instructions": INSTRUCTIONS,
                        "persona": f"You are {actor_id} and decide only your own sealed bid.",
                        "reasoning_effort": None,
                        "required_fields": ["rules"],
                        "max_attempts": 2,
                        "max_calls": 4,
                        "max_output_tokens": 2000,
                    },
                }
                for actor_id in actor_ids
            ],
            "parameters": world_parameters(order),
            "initial_public_state": {"rules": RULES, "bids": []},
            "initial_private_state": {
                actor_id: {"facts": {"valuation": values[actor_id]}, "memory": {}}
                for actor_id in actor_ids
            },
        },
        "mechanism_id": MECH_ID,
        "protocol_id": "simultaneous.v1",
        "protocol_parameters": {"rounds": rounds},
        "permissions": {
            actor_id: {
                "public_fields": ["rules"],
                "private_fields": ["valuation"],
                "readable_memory": True,
                "writable_private_fields": [],
                "writable_memory": True,
            }
            for actor_id in actor_ids
        },
        "benchmark": None,
        "max_steps": 5,
        "assumptions": [],
    }


def bid_actions(bids: dict[str, float], kind: str = "bid") -> list[Action]:
    return [
        Action(actor_id=actor_id, kind=kind, payload={"bid": bid}) for actor_id, bid in bids.items()
    ]


def observation_payload(actor_id: str, valuation: float, leak: dict | None = None) -> dict:
    observation = {
        "actor_id": actor_id,
        "phase": "act",
        "visible": {"rules": RULES},
        "private": {"facts": {"valuation": valuation}, "memory": {}},
        "allowed_action_kinds": ["bid"],
        "writable_private_fields": [],
        "writable_memory": True,
    }
    if leak:
        observation["visible"].update(leak)
    return observation


def model_call(actor_id: str, valuation: float, rationale: str, leak: dict | None = None) -> dict:
    return {
        "actor_id": actor_id,
        "attempt": 1,
        "mode": "fake",
        "model": MODEL,
        "request": {
            "actor_id": actor_id,
            "model": MODEL,
            "reasoning_effort": None,
            "instructions": INSTRUCTIONS,
            "input_json": json.dumps(
                {
                    "persona": f"You are {actor_id}.",
                    "observation": observation_payload(actor_id, valuation, leak),
                    "retry": False,
                }
            ),
            "response_schema": {},
            "response_strict": True,
            "max_output_tokens": 2000,
        },
        "rationale": rationale,
        "response_model": MODEL,
        "response_text": rationale,
        "request_id": f"fake-{actor_id}",
        "input_tokens": 10,
        "output_tokens": 5,
        "status": "accepted",
        "error_category": None,
    }


def job_result_dict(
    bids: dict[str, float],
    valuations: dict[str, float] | None = None,
    order: list[str] | tuple[str, ...] = ACTORS,
    tamper: str | None = None,
    leak_actor: str | None = None,
    committed: bool = True,
) -> dict:
    """Full JobResult JSON with settlement computed by the test oracle."""
    order = list(order)
    values = dict(VALUATIONS if valuations is None else valuations)
    winner, payment, payoffs = settle_expected(bids, values, order)
    public = {"rules": RULES, "bids": [dict(bids)]}
    metrics = {"winner": winner, "payment": payment, "bids": dict(bids)}
    if tamper == "payoffs":
        payoffs = dict(payoffs)
        payoffs[winner] = payoffs[winner] + 1.0
    elif tamper == "winner":
        public["winner"] = order[-1]
        metrics["winner"] = order[-1]
    elif tamper == "payment":
        public["payment"] = payment + 1.0
        metrics["payment"] = payment + 1.0
    if tamper != "winner":
        public["winner"] = winner
    public.setdefault("payment", payment)
    public["payoffs"] = dict(payoffs)
    outcome = {"payoffs": dict(payoffs), "metrics": metrics}
    if tamper == "history":
        public["bids"] = [{aid: 0.0 for aid in order}]

    initial_state = {
        "tick": 0,
        "phase": "act",
        "public": {"rules": RULES, "bids": []},
        "private": {aid: {"facts": {"valuation": values[aid]}, "memory": {}} for aid in order},
    }
    events = [
        {
            "schema_version": "simulation.event.v1",
            "sequence": 0,
            "kind": "initialized",
            "state": initial_state,
            "actions": [],
            "decisions": [],
            "outcome": None,
            "model_calls": [],
        }
    ]
    model_calls = []
    if committed:
        actions = [{"actor_id": aid, "kind": "bid", "payload": {"bid": bids[aid]}} for aid in order]
        decisions = [
            {
                "action": action,
                "rationale": f"Fixture rationale for {aid}.",
                "memory_update": None,
                "private_updates": {},
            }
            for aid, action in zip(order, actions)
        ]
        for aid, decision in zip(order, decisions):
            leak = None
            if leak_actor == aid:
                leak = {f"{other}_valuation": values[other] for other in order if other != aid}
            model_calls.append(model_call(aid, values[aid], decision["rationale"], leak))
        events.append(
            {
                "schema_version": "simulation.event.v1",
                "sequence": 1,
                "kind": "committed",
                "state": {
                    "tick": 1,
                    "phase": "finished",
                    "public": public,
                    "private": {
                        aid: {"facts": {"valuation": values[aid]}, "memory": {}} for aid in order
                    },
                },
                "actions": actions,
                "decisions": decisions,
                "outcome": outcome,
                "model_calls": model_calls,
            }
        )
        final_state = dict(events[-1]["state"])
        outcomes = [outcome]
    else:
        final_state = dict(initial_state)
        outcomes = []
    return {
        "schema_version": "simulation.job_result.v1",
        "manifest": {
            "schema_version": "simulation.job.v1",
            "request": {
                "schema_version": "experiment.request.v1",
                "hypothesis": "Fixture auction hypothesis.",
                "execution_kind": "agent_simulation",
                "problem": None,
                "supplied_inputs": [],
                "requirements": [],
            },
            "simulation": simulation_dict(order, values, order),
        },
        "result": {
            "status": "completed",
            "final_state": final_state,
            "outcomes": outcomes,
            "events": events,
            "assumptions": [],
            "component_ids": [MECH_ID, "simultaneous.v1", "llm.v1", "llm.v1", "llm.v1"],
            "model_calls": model_calls,
        },
        "benchmark": None,
    }
