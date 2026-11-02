"""Muse Code headless authoring in a fresh Docker container per stage.

The CLI owns its model/tool loop. The existing controller still freezes plans,
seals versions, and submits code to the separate offline validation worker.
"""

import hashlib
import json
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal
from uuid import uuid4

from pydantic import SecretStr

from simulation_core.model_gateway import GatewayError, ModelGateway, ModelRequest, ModelResponse

from .docker_worker import DockerWorker
from .process import bounded_command

AUTH_FRAME = "HYPOTHESIS_MUSE_AUTH"
RESULT_FRAME = "HYPOTHESIS_MUSE_RESULT:"


class MuseCodeGateway(ModelGateway):
    def __init__(
        self,
        project: Path,
        audit: Path,
        api_key: SecretStr,
        *,
        sandbox: str | None = None,
        seconds: int = 3600,
    ) -> None:
        self.project = project.resolve()
        self.audit = audit
        self._api_key = api_key
        self.worker = DockerWorker(self.project, sandbox=sandbox)
        self.seconds = seconds
        self.prepared: dict[str, str] | None = None

    @property
    def mode(self) -> Literal["live"]:
        return "live"

    def prepare(self) -> dict[str, str]:
        base = self.worker.prepare()
        tag = "hypothesis-muse:" + base["framework_digest"][:20]
        remote = "/tmp/hypothesis-muse-build-" + uuid4().hex
        with TemporaryDirectory(prefix="hypothesis-muse-build-") as temporary:
            context = Path(temporary)
            context.chmod(0o755)
            # The base already contains the pinned installer and release lock.
            (context / "Dockerfile").write_bytes(
                (self.project / "docker/muse.Dockerfile").read_bytes()
            )
            build_path = str(context)
            try:
                if self.worker.sandbox:
                    self.worker._copy_to_sandbox(context, remote)
                    build_path = remote
                # BuildKit's FROM expects a local image reference, not a bare sha256 ID.
                base_tag = "hypothesis-worker:" + base["framework_digest"][:20]
                if self.worker.image_id(base_tag) != base["image_id"]:
                    raise RuntimeError("Trusted base image changed before Muse build")
                result = bounded_command(
                    self.worker._docker(
                        "build",
                        "--file",
                        build_path + "/Dockerfile",
                        "--build-arg",
                        "TOOLKIT_IMAGE=" + base_tag,
                        "--tag",
                        tag,
                        build_path,
                    ),
                    seconds=900,
                    max_bytes=2_000_000,
                )
                if result.code:
                    raise RuntimeError("Muse image build failed: " + result.stderr[-6000:])
                release = json.loads((self.project / "docker/muse-release.json").read_text())
                self.prepared = {
                    **base,
                    "toolkit_image_id": base["image_id"],
                    "image_id": self.worker.image_id(tag),
                    "muse_version": release["version"],
                }
                return dict(self.prepared)
            finally:
                self._remove_remote(remote)

    def _remove_remote(self, path: str) -> None:
        if self.worker.sandbox:
            subprocess.run(
                [self.worker.sbx, "exec", self.worker.sandbox, "rm", "-rf", path],
                capture_output=True,
                timeout=20,
                check=False,
            )

    @staticmethod
    def stage(request: ModelRequest, root: Path) -> None:
        """Stage only this request and inventory; sources are read on demand in the image."""
        root.chmod(0o755)
        task = json.loads(request.input_json)
        if request.actor_id != "coding_agent" or task.get("stage") not in {
            "plan_and_tests",
            "implementation",
            "repair_implementation",
        }:
            raise ValueError("Muse authoring gateway accepts coding stages only")
        sources = task.get("toolkit", {}).get("sources", [])
        if "toolkit" in task:
            task["toolkit"] = {
                **task["toolkit"],
                "sources": [source["path"] for source in sources],
                "source_root": "/opt/toolkit",
            }
        inputs = root / "inputs"
        inputs.mkdir(mode=0o755)
        (root / "workspace").mkdir(mode=0o777)
        (root / "workspace").chmod(0o777)
        for name, content in {
            "task.json": json.dumps(task),
            "response-schema.json": json.dumps(request.response_schema),
            "AGENTS.md": request.instructions,
        }.items():
            (inputs / name).write_text(content)
            (inputs / name).chmod(0o644)

    def arguments(self, name: str, mount: str, image: str, request: ModelRequest) -> list[str]:
        return self.worker._docker(
            "run",
            "--rm",
            "--interactive",
            "--name",
            name,
            "--pull",
            "never",
            "--user",
            "10001:10001",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "--pids-limit",
            "256",
            "--cpus",
            "2",
            "--memory",
            "4g",
            "--memory-swap",
            "4g",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,size=536870912,mode=1777",
            "--mount",
            f"type=bind,src={mount}/inputs,dst=/inputs,readonly",
            "--mount",
            f"type=bind,src={mount}/workspace,dst=/workspace",
            "--mount",
            f"type=bind,src={mount}/inputs/AGENTS.md,dst=/workspace/AGENTS.md,readonly",
            "--entrypoint",
            "python",
            image,
            "-m",
            "extension_worker.muse",
            request.model,
            request.reasoning_effort or "max",
        )

    def complete(self, request: ModelRequest) -> ModelResponse:
        from .authoring import private_json

        if self.prepared is None:
            print("Preparing Muse Code authoring container", flush=True)
            self.prepare()
        assert self.prepared is not None
        call_id = uuid4().hex
        audit = self.audit / call_id
        private_json(
            audit / "container.json",
            {
                **self.prepared,
                "model": request.model,
                "reasoning_effort": request.reasoning_effort,
                "transport": "muse exec; CLI owns model/tool loop; no max-model-steps flag",
                "credentials": "API key delivered once over stdin, never in arguments or mounts",
                "cli_prompt_sha256": hashlib.sha256(request.instructions.encode()).hexdigest(),
            },
        )
        returned: list[str] = []
        authenticated = False
        event_count = 0

        def exchange(line: str) -> str | None:
            nonlocal authenticated, event_count
            if line == AUTH_FRAME:
                if authenticated:
                    raise GatewayError("duplicate_muse_auth_request")
                authenticated = True
                return json.dumps({"api_key": self._api_key.get_secret_value()})
            if line.startswith(RESULT_FRAME):
                returned.append(line[len(RESULT_FRAME) :])
                return None
            event_count += 1
            # Show event types without dumping source files, provider content, or secrets.
            try:
                event = json.loads(line)
                kind = (
                    event.get("payload_type", event.get("type", "event"))
                    if isinstance(event, dict)
                    else "event"
                )
                if kind != "event":
                    print(f"Muse Code: {kind}", flush=True)
            except ValueError:
                pass
            return None

        remote = "/tmp/hypothesis-muse-run-" + call_id
        name = "hypothesis-muse-" + call_id
        with TemporaryDirectory(prefix="hypothesis-muse-run-") as temporary:
            root = Path(temporary)
            self.stage(request, root)
            mount = str(root)
            try:
                if self.worker.sandbox:
                    self.worker._copy_to_sandbox(root, remote)
                    mount = remote
                result = bounded_command(
                    self.arguments(name, mount, self.prepared["image_id"], request),
                    seconds=self.seconds,
                    max_bytes=16_000_000,
                    exchange=exchange,
                )
                # Only redacted CLI events and sanitized diagnostics reach these files.
                private_json(
                    audit / "events.json",
                    {
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                        "exit_code": result.code,
                        "events": event_count,
                    },
                )
                if result.code or len(returned) != 1:
                    raise GatewayError("muse_cli_failed_or_missing_response")
                response = ModelResponse.model_validate_json(returned[0])
                if response.model != request.model:
                    raise GatewayError("muse_model_mismatch")
                return response
            finally:
                subprocess.run(
                    self.worker._docker("rm", "--force", name),
                    capture_output=True,
                    timeout=20,
                    check=False,
                )
                self._remove_remote(remote)
