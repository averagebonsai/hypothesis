"""Replay-based privacy verification uses trusted toy fixtures, no model API."""

import json

from agent_tools.checks import verify_llm_observations
from examples.llm_payoff_matrix import fake_response, run_llm_job
from simulation_core.execution import JobResult
from simulation_core.model_gateway import FakeGateway


def test_precommit_verifier_handles_multiple_rounds_and_memory():
    artifact = run_llm_job(gateway=FakeGateway(fake_response), rounds=2)
    assert verify_llm_observations(artifact).status == "verified"


def test_identity_substitution_and_extra_observation_fields_rejected():
    artifact = run_llm_job(gateway=FakeGateway(fake_response), rounds=1)
    for identity in (True, False):
        data = artifact.model_dump(mode="json")
        for call in [
            data["result"]["model_calls"][0],
            data["result"]["events"][1]["model_calls"][0],
        ]:
            packet = json.loads(call["request"]["input_json"])
            if identity:
                packet["observation"]["actor_id"] = "B"
            else:
                packet["observation"]["private"]["memory"]["unauthorized"] = "foreign data"
            call["request"]["input_json"] = json.dumps(packet)
        finding = verify_llm_observations(JobResult.model_validate_json(json.dumps(data)))
        assert finding.status == "failed" and finding.required
