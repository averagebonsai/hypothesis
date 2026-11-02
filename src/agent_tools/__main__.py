"""CLI for external agents; no generation, scientific inference, or repair loop."""

import argparse
import json
from pathlib import Path

from simulation_core.execution import JobManifest

from .bundles import seal_bundle, verify_bundle
from .docker_worker import DockerWorker
from .inventory import inventory


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
    for command in ("seal", "inspect", "validate", "run"):
        subparser = commands.add_parser(command)
        subparser.add_argument("bundle", type=Path)
        if command in {"validate", "run"}:
            subparser.add_argument("--job", type=Path, required=True)
    args = parser.parse_args()
    worker = DockerWorker(args.project, sandbox=args.sandbox)
    if args.command == "inventory":
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
        job = JobManifest.model_validate_json(args.job.read_text())
        receipt = worker.execute(args.bundle, job, operation=args.command)
        print(receipt.model_dump_json(indent=2))
        if not receipt.response.passed or (
            args.command == "run" and receipt.response.result is None
        ):
            raise SystemExit(1)


if __name__ == "__main__":
    main()
