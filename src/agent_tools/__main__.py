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
    commands.add_parser("guide")
    starter = commands.add_parser(
        "starter", help="Write domain-neutral templates without running them"
    )
    starter.add_argument("directory", type=Path)
    starter.add_argument("--kind", choices=("agent_simulation", "tool"), default="agent_simulation")
    for name in ("preview", "report"):
        render = commands.add_parser(name, help="Render offline without any actor/model calls")
        render.add_argument("bundle", type=Path)
        render.add_argument("--job" if name == "preview" else "--result", type=Path, required=True)
        render.add_argument("--output", type=Path, required=True)
    author = commands.add_parser(
        "author", help="Create and validate a fresh experiment with Muse Code"
    )
    author.add_argument("--request", type=Path, required=True)
    author.add_argument("--experiment-id", required=True)
    author.add_argument("--backend", choices=("muse", "api"), default="muse")
    author.add_argument("--actor-settings", type=Path)
    author.add_argument("--actor-output-tokens", type=int, default=None)
    author.add_argument("--actor-call-budget", type=int, default=48)
    for command in ("seal", "inspect", "validate", "run"):
        subparser = commands.add_parser(command)
        subparser.add_argument("bundle", type=Path)
        if command in {"validate", "run"}:
            subparser.add_argument("--job", type=Path, required=True)
        if command == "run":
            subparser.add_argument("--live-actors", action="store_true")
            subparser.add_argument("--actor-settings", type=Path)
            subparser.add_argument("--checkpoint-dir", type=Path)
            subparser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    worker = DockerWorker(args.project, sandbox=args.sandbox)
    if args.command == "guide":
        from .guide import interface_guide

        print(interface_guide())
    elif args.command == "starter":
        from .guide import write_starter

        write_starter(args.directory, kind=args.kind)
    elif args.command in {"preview", "report"}:
        from simulation_core.execution import JobResult

        document = (
            JobManifest.model_validate_json(args.job.read_text())
            if args.command == "preview"
            else JobResult.model_validate_json(args.result.read_text())
        )
        worker.prepare()
        report_receipt = worker.render(args.bundle, document, args.output)
        print(report_receipt.model_dump_json(indent=2))
        if not report_receipt.response.passed:
            raise SystemExit(1)
    elif args.command == "author":
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
        from .execution_settings import ActorExecutionSettings

        actor_settings = (
            ActorExecutionSettings.model_validate_json(args.actor_settings.read_text())
            if args.actor_settings
            else None
        )
        agent = CodingAgent.from_environment(
            args.project,
            audit,
            backend=args.backend,
            sandbox=args.sandbox,
            actor_max_output_tokens=args.actor_output_tokens,
            actor_max_total_calls=args.actor_call_budget,
            actor_settings=actor_settings,
        )
        assert agent.execution_settings is not None
        model, gateway = configured_gateway(
            timeout=agent.execution_settings.provider_timeout_seconds,
            stream=agent.execution_settings.stream,
        )
        worker = DockerWorker(
            args.project,
            sandbox=args.sandbox,
            actor_gateway=gateway,
            actor_model=model,
            actor_settings=agent.execution_settings,
            limits=WorkerLimits(wall_seconds=900, pids=256),
        )
        worker.prepare()
        try:
            outcome = run_authoring(agent, request, args.experiment_id, destination, worker)
        finally:
            agent.close()
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
        options = {}
        if args.command == "run":
            if args.resume and args.checkpoint_dir is None:
                parser.error("--resume requires an explicit --checkpoint-dir")
            options = {"checkpoint_dir": args.checkpoint_dir, "resume": args.resume}
            if args.live_actors:
                from components.gateways.live import configured_gateway
                from components.gateways.settings import LiveModelSettings

                from .execution_settings import ActorExecutionSettings
                from .specs import WorkerLimits

                settings = (
                    ActorExecutionSettings.model_validate_json(args.actor_settings.read_text())
                    if args.actor_settings
                    else ActorExecutionSettings(model=LiveModelSettings.load().model)
                )
                if settings.model != LiveModelSettings.load().model:
                    parser.error("Actor settings must use MODEL")
                model, gateway = configured_gateway(
                    timeout=settings.provider_timeout_seconds, stream=settings.stream
                )
                worker = DockerWorker(
                    args.project,
                    sandbox=args.sandbox,
                    actor_gateway=gateway,
                    actor_model=model,
                    actor_settings=settings,
                    limits=WorkerLimits(wall_seconds=900, pids=256),
                )
        receipt = worker.execute(args.bundle, job, operation=args.command, **options)
        print(receipt.model_dump_json(indent=2))
        if not receipt.response.passed or (
            args.command == "run"
            and receipt.response.result is None
            and receipt.response.tool_result is None
        ):
            raise SystemExit(1)


if __name__ == "__main__":
    main()
