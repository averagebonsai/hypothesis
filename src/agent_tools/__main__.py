"""Component inspection, isolated validation, and opt-in Muse Code authoring."""

import argparse
import json
from pathlib import Path

from pydantic import TypeAdapter

from simulation_core.execution import JobManifest

from .bundles import seal_bundle, verify_bundle
from .docker_worker import DockerWorker
from .inventory import inventory
from .jobs import ToolJobManifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument(
        "--sandbox", help="Use the private Docker Engine in an existing sbx shell sandbox"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("inventory")
    commands.add_parser("create-sandbox")
    commands.add_parser("prepare")
    author = commands.add_parser(
        "author", help="Create and validate a fresh experiment with Muse Code"
    )
    author.add_argument("--request", type=Path, required=True)
    author.add_argument("--experiment-id", required=True)
    author.add_argument("--backend", choices=("muse", "api"), default="muse")
    for command in ("seal", "inspect", "validate", "run"):
        subparser = commands.add_parser(command)
        subparser.add_argument("bundle", type=Path)
        if command in {"validate", "run"}:
            subparser.add_argument("--job", type=Path, required=True)
    args = parser.parse_args()
    worker = DockerWorker(args.project, sandbox=args.sandbox)
    if args.command == "author":
        import re

        from components.gateways.live import configured_gateway
        from simulation_core.request import ExperimentRequest

        from .authoring import CodingAgent, private_json
        from .specs import WorkerLimits
        from .workflow import run_authoring

        if not re.fullmatch(r"[a-z][a-z0-9_]*", args.experiment_id):
            parser.error("experiment-id must be a simple lowercase namespace")
        request = ExperimentRequest.model_validate_json(args.request.read_text())
        root = args.project.resolve() / "experimental_components"
        audit = root / "_authoring" / args.experiment_id
        destination = root / args.experiment_id
        if audit.exists() or destination.exists():
            parser.error("Use a fresh experiment namespace")
        agent = CodingAgent.from_environment(
            args.project, audit, backend=args.backend, sandbox=args.sandbox
        )
        model, gateway = configured_gateway()
        worker = DockerWorker(
            args.project,
            sandbox=args.sandbox,
            actor_gateway=gateway,
            actor_model=model,
            limits=WorkerLimits(wall_seconds=900, pids=256),
        )
        worker.prepare()
        outcome = run_authoring(agent, request, args.experiment_id, destination, worker)
        private_json(audit / "outcome.json", outcome.model_dump(mode="json"))
        print(outcome.model_dump_json(indent=2))
        if outcome.status != "completed":
            raise SystemExit(1)
    elif args.command == "inventory":
        print(json.dumps(inventory(), indent=2))
    elif args.command == "create-sandbox":
        worker.create_sandbox()
    elif args.command == "prepare":
        print(json.dumps(worker.prepare(), indent=2))
    elif args.command == "seal":
        print(seal_bundle(args.bundle).model_dump_json(indent=2))
    elif args.command == "inspect":
        manifest, seal, _ = verify_bundle(args.bundle)
        print(
            json.dumps(
                {
                    "manifest": manifest.model_dump(mode="json"),
                    "seal": seal.model_dump(mode="json"),
                },
                indent=2,
            )
        )
    else:
        job = TypeAdapter(JobManifest | ToolJobManifest).validate_json(args.job.read_text())
        receipt = worker.execute(args.bundle, job, operation=args.command)
        print(receipt.model_dump_json(indent=2))
        if not receipt.response.passed or (
            args.command == "run"
            and receipt.response.result is None
            and receipt.response.tool_result is None
        ):
            raise SystemExit(1)


if __name__ == "__main__":
    main()
