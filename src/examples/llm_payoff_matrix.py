"""Generic LLMPolicy and a separate pure-Nash benchmark on the normal-form fixture."""

import json
from importlib.resources import files

from components.gateways.meta import MetaResponsesGateway
from components.gateways.openai import OpenAIResponsesGateway
from components.gateways.settings import LiveModelSettings
from components.library import standard_registry
from simulation_core.execution import JobResult, JobRunner, LocalBackend
from simulation_core.model_gateway import BoundedGateway, FakeGateway, ModelGateway, ModelRequest
from simulation_core.request import ExperimentRequest
from simulation_core.types import Assumption, BenchmarkSpec, SimulationConfig

from .payoff_matrix import build_experiment


def fake_response(request: ModelRequest) -> str:
    # Deliberately non-equilibrium test fixture. It is not evidence of LLM behavior.
    move = "cooperate" if request.actor_id == "A" else "defect"
    return json.dumps(
        {
            "action": {
                "actor_id": request.actor_id,
                "kind": "choose_move",
                "payload": {"move": move},
            },
            "memory_update": [{"key": "last_move", "value_json": json.dumps(move)}],
            "private_updates": [],
            "rationale": "Deterministic fake-gateway fixture.",
        }
    )


def build_llm_experiment(
    model: str, rounds: int = 1, max_profiles: int = 10000
) -> SimulationConfig:
    base, _ = build_experiment(rounds)
    actors = tuple(
        actor.model_copy(
            update={
                "policy_id": "llm.v1",
                "policy_parameters": {
                    "model": model,
                    "instructions": "Choose a legal move to maximize your own payoff. "
                    "The public game gives choices and payoff cells. Other actors choose simultaneously.",
                    "persona": f"You are player {actor.id}.",
                    "required_fields": ["game"],
                    "max_attempts": 2,
                    "max_calls": 4,
                    "max_output_tokens": 1000,
                    "reasoning_effort": "low" if model.startswith("muse-") else None,
                },
            }
        )
        for actor in base.world.actors
    )
    public = {
        **base.world.initial_public_state,
        "game": {
            "choices": base.world.parameters["choices"],
            "cells": base.world.parameters["cells"],
        },
    }
    permissions = {
        aid: permission.model_copy(update={"public_fields": ("history", "payoffs", "game")})
        for aid, permission in base.permissions.items()
    }
    assumptions = [
        item
        for item in base.assumptions
        if not item.path.startswith("/world/actors/") and not item.path.startswith("/permissions/")
    ]
    assumptions.extend(
        Assumption(
            path=f"/permissions/{aid}",
            value=permission.model_dump(mode="json"),
            source="default",
            rationale="Both players know the full payoff table and choices, "
            "observe committed past moves, and see only their own private state.",
        )
        for aid, permission in permissions.items()
    )
    assumptions.extend(
        Assumption(
            path=f"/world/actors/{i}/policy_parameters",
            value=actor.policy_parameters,
            source="default",
            rationale="Use the configured model and own-payoff objective with bounded calls; "
            "model/persona behavior is synthetic and uncalibrated.",
        )
        for i, actor in enumerate(actors)
    )
    benchmark = BenchmarkSpec(
        solver_id="pure_nash.v1",
        game_view_id="normal_form.v1",
        parameters={"max_profiles": max_profiles, "payoff_tolerance": 1e-9},
    )
    return SimulationConfig.model_validate(
        base.model_copy(
            update={
                "world": base.world.model_copy(
                    update={"actors": actors, "initial_public_state": public}
                ),
                "permissions": permissions,
                "assumptions": tuple(assumptions),
                "benchmark": benchmark,
            }
        ).model_dump()
    )


def run_llm_job(
    model: str = "fake-model",
    gateway: ModelGateway | None = None,
    rounds: int = 1,
    max_profiles: int = 10000,
) -> JobResult:
    transport = gateway if gateway is not None else FakeGateway(fake_response)
    bounded = BoundedGateway(transport, max_calls=8, max_output_tokens_per_call=1200)
    config = build_llm_experiment(model, rounds, max_profiles)
    fixture = ExperimentRequest.model_validate_json(
        files("examples").joinpath("configs/prisoners_dilemma_request.json").read_text()
    )
    request = fixture.model_copy(
        update={
            "hypothesis": "What moves do the configured LLM policies choose, and how do they deviate from pure Nash?"
        }
    )
    return JobRunner(LocalBackend(standard_registry(bounded))).run(request, config)


def run_live_job(model: str | None = None) -> JobResult:
    settings = LiveModelSettings.load(model)
    gateway_type = (
        MetaResponsesGateway if settings.model.startswith("muse-") else OpenAIResponsesGateway
    )
    gateway = gateway_type(settings.api_key.get_secret_value(), frozenset({settings.model}))
    return run_llm_job(settings.model, gateway)


if __name__ == "__main__":
    print(run_llm_job().model_dump_json(indent=2))
