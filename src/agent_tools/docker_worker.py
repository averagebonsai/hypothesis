"""Docker transport with an optional sbx outer VM; experimental code is data here."""

import json
import os
import re
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal
from uuid import uuid4

from simulation_core.execution import JobManifest

from .bundles import copy_trusted_context, snapshot_bundle, verify_bundle
from .jobs import ToolJobManifest
from .notebooks import export_diagnostic, export_notebook, validate_notebook_json
from .process import bounded_command
from .specs import RunReceipt, WorkerLimits, WorkerResponse


class DockerWorker:
    def __init__(
        self,
        project: Path,
        *,
        sandbox: str | None = None,
        docker: str = "docker",
        sbx: str = "sbx",
        limits: WorkerLimits | None = None,
    ) -> None:
        self.project = project.resolve()
        self.sandbox = sandbox
        self.docker = docker
        self.sbx = sbx
        self.limits = limits or WorkerLimits()
        if sandbox and not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9.-]+", sandbox):
            raise ValueError("Invalid sandbox name")

    def _docker(self, *args: str) -> list[str]:
        prefix = [self.sbx, "exec", self.sandbox, self.docker] if self.sandbox else [self.docker]
        return [*prefix, *args]

    def create_sandbox(self) -> None:
        if not self.sandbox:
            raise ValueError("Choose a sandbox name")
        # No workspace, shared skills, credentials, or host Docker socket.
        result = bounded_command(
            [
                self.sbx,
                "create",
                "--name",
                self.sandbox,
                "--cpus",
                str(self.limits.cpus),
                "--memory",
                f"{self.limits.memory_mb}m",
                "--skills",
                "off",
                "shell",
            ],
            seconds=300,
            max_bytes=100_000,
        )
        if result.code:
            raise RuntimeError(f"Sandbox creation failed: {result.stderr[-4000:]}")

    def _copy_to_sandbox(self, source: Path, destination: str) -> None:
        result = bounded_command(
            [self.sbx, "cp", str(source), f"{self.sandbox}:{destination}"],
            seconds=60,
            max_bytes=100_000,
        )
        if result.code:
            raise RuntimeError(f"Sandbox copy failed: {result.stderr[-2000:]}")

    def prepare(self) -> dict[str, str]:
        """Build only trusted framework/locked dependencies, without extension files."""
        with TemporaryDirectory(prefix="hypothesis-build-") as temporary:
            context = Path(temporary) / "context"
            digest = copy_trusted_context(self.project, context)
            tag = f"hypothesis-worker:{digest[:20]}"
            build_path = str(context)
            remote = f"/tmp/hypothesis-build-{uuid4().hex}"
            try:
                if self.sandbox:
                    self._copy_to_sandbox(context, remote)
                    build_path = remote
                result = bounded_command(
                    self._docker(
                        "build",
                        "--file",
                        f"{build_path}/docker/worker.Dockerfile",
                        "--tag",
                        tag,
                        build_path,
                    ),
                    seconds=900,
                    max_bytes=2_000_000,
                )
                if result.code:
                    raise RuntimeError(
                        f"Trusted worker image build failed: {result.stderr[-8000:]} {result.stdout[-2000:]}"
                    )
                return {"image_id": self.image_id(tag), "framework_digest": digest}
            finally:
                if self.sandbox:
                    # Only our uniquely named temporary directory in the outer VM.
                    subprocess.run(
                        [self.sbx, "exec", self.sandbox, "rm", "-rf", remote],
                        capture_output=True,
                        timeout=20,
                        check=False,
                    )

    def image_id(self, reference: str) -> str:
        result = bounded_command(
            self._docker("image", "inspect", "--format", "{{.Id}}", reference),
            seconds=30,
            max_bytes=4096,
        )
        value = result.stdout.strip()
        if result.code or not re.fullmatch(r"sha256:[a-f0-9]{64}", value):
            raise RuntimeError(
                "Worker image missing or invalid; prepare the trusted worker image first"
            )
        return value

    def run_arguments(
        self,
        name: str,
        bundle_path: str,
        job_path: str,
        image: str,
        operation: str,
        bundle_digest: str,
    ) -> list[str]:
        for path in (bundle_path, job_path):
            if any(char in path for char in (",", "\n", "\r")):
                raise ValueError("Mount path contains unsupported delimiter")
        return self._docker(
            "run",
            "--rm",
            "--name",
            name,
            "--pull",
            "never",
            "--init",
            "--user",
            "10001:10001",
            "--read-only",
            "--network",
            "none",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "--pids-limit",
            str(self.limits.pids),
            "--cpus",
            str(self.limits.cpus),
            "--memory",
            f"{self.limits.memory_mb}m",
            "--memory-swap",
            f"{self.limits.memory_mb}m",
            "--ulimit",
            "nofile=128:128",
            "--ipc",
            "private",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,size=268435456,mode=1777",
            "--mount",
            f"type=bind,src={bundle_path},dst=/bundle,readonly",
            "--mount",
            f"type=bind,src={job_path},dst=/job,readonly",
            image,
            operation,
            bundle_digest,
        )

    def execute(
        self,
        bundle: Path,
        job: JobManifest | ToolJobManifest,
        *,
        operation: Literal["validate", "run"] = "run",
        probes: tuple[JobManifest, ...] = (),
    ) -> RunReceipt:
        manifest, original_seal, _ = verify_bundle(bundle)
        if isinstance(job, ToolJobManifest) and probes:
            raise ValueError("Simulation probes do not apply to direct tools")
        # An image tag is derived from current trusted inputs and resolved to an immutable image ID.
        with TemporaryDirectory(prefix="hypothesis-run-") as temporary:
            root = Path(temporary)
            context = root / "context"
            framework_digest = copy_trusted_context(self.project, context)
            image = self.image_id(f"hypothesis-worker:{framework_digest[:20]}")
            stage = root / "stage"
            stage.mkdir(mode=0o755)
            seal = snapshot_bundle(bundle, stage / "bundle")
            if seal != original_seal:
                raise ValueError("Bundle changed before staging")
            job_dir = stage / "job"
            job_dir.mkdir(mode=0o755)
            manifest_path = job_dir / "manifest.json"
            manifest_path.write_text(job.model_dump_json())
            manifest_path.chmod(0o644)
            if probes:
                (job_dir / "probes.json").write_text(
                    json.dumps([probe.model_dump(mode="json") for probe in probes])
                )
                (job_dir / "probes.json").chmod(0o644)
            remote = f"/tmp/hypothesis-run-{uuid4().hex}"
            name = f"hypothesis-worker-{uuid4().hex}"
            try:
                mount = str(stage)
                if self.sandbox:
                    self._copy_to_sandbox(stage, remote)
                    mount = remote
                result = bounded_command(
                    self.run_arguments(
                        name, f"{mount}/bundle", f"{mount}/job", image, operation, seal.digest
                    ),
                    seconds=self.limits.wall_seconds,
                    max_bytes=self.limits.output_bytes,
                )
                if result.code:
                    raise RuntimeError(
                        f"Isolated worker failed ({result.code}): {result.stderr[-4000:]}"
                    )
                response = WorkerResponse.model_validate_json(result.stdout)
                if response.bundle_digest != seal.digest:
                    raise ValueError("Worker response refers to a different bundle")
                if response.result is not None and response.result.manifest != job:
                    raise ValueError("Worker returned a different experiment manifest")
                if response.tool_result is not None and response.tool_result.manifest != job:
                    raise ValueError("Worker returned a different tool manifest")
                if response.diagnostic is not None and response.diagnostic.result.manifest != job:
                    raise ValueError("Worker diagnostic refers to a different manifest")
                if (
                    operation == "run"
                    and response.result is not None
                    and manifest.notebook is not None
                    and response.notebook_json is None
                ):
                    raise ValueError("Worker omitted the required results notebook")
                if response.notebook_json is not None:
                    validate_notebook_json(response.notebook_json)
                if len(response.probe_results) != (
                    len(probes) if operation == "run" and response.result is not None else 0
                ):
                    raise ValueError("Unexpected probe result count")
                if any(
                    result.manifest != probe
                    for result, probe in zip(response.probe_results, probes)
                ):
                    raise ValueError("Worker returned a different probe manifest")
                receipt = RunReceipt(
                    bundle_digest=seal.digest,
                    image_id=image,
                    framework_digest=framework_digest,
                    limits=self.limits,
                    operation=operation,
                    response=response,
                )
                reports = bundle.parent.parent / "_runs" / bundle.parent.name / bundle.name
                reports.mkdir(parents=True, exist_ok=True)
                run_id = uuid4().hex
                path = reports / f"{run_id}.json"
                descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, "w") as stream:
                    stream.write(receipt.model_dump_json(indent=2) + "\n")
                if response.notebook_json is not None:
                    export_notebook(response, reports / run_id)
                if response.diagnostic is not None:
                    export_diagnostic(response.diagnostic, reports / (run_id + "-unapproved"))
                return receipt
            finally:
                subprocess.run(
                    self._docker("rm", "--force", name),
                    capture_output=True,
                    timeout=20,
                    check=False,
                )
                if self.sandbox:
                    subprocess.run(
                        [self.sbx, "exec", self.sandbox, "rm", "-rf", remote],
                        capture_output=True,
                        timeout=20,
                        check=False,
                    )
