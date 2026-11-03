"""Muse Code headless authoring in one isolated session per experiment.

The CLI owns its model/tool loop. The existing controller still freezes plans,
seals versions, and submits code to the separate offline validation worker.
"""

import fcntl
import hashlib
import json
import os
import subprocess
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal
from uuid import UUID, uuid4

from pydantic import SecretStr

from simulation_core.model_gateway import GatewayError, ModelGateway, ModelRequest, ModelResponse

from .docker_worker import DockerWorker
from .process import bounded_command
from .progress import AuthoringProgress

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
        resume: bool = False,
    ) -> None:
        self.project = project.resolve()
        self.audit = audit
        self._api_key = api_key
        self.worker = DockerWorker(self.project, sandbox=sandbox)
        self.seconds = seconds
        self.prepared: dict[str, str] | None = None
        self.execution_capabilities: dict[str, object] = {}
        self.session_id = str(uuid4())
        self.identity: dict[str, str] | None = None
        self.turn = 0
        self.running = False
        self.closed = False
        self.resources_created = False
        self._lock = threading.Lock()
        session = self.audit / "session.json"
        if session.exists():
            if not resume or (self.audit / "session-closed.json").exists():
                raise ValueError("Use a fresh experiment or explicitly resume its active session")
            state = json.loads(session.read_text())
            self.session_id = str(UUID(state["session_id"]))
            self.identity = state["identity"]
            self.prepared = state["image"]
            self.turn = 1  # continuation; exact completed turns are retained in per-stage audits
            self.resources_created = True
        elif resume:
            raise ValueError(
                "No persistent Muse session exists for this audit; legacy trials cannot regain lost context"
            )

    @property
    def container_name(self) -> str:
        return "hypothesis-author-" + UUID(self.session_id).hex

    def volume(self, role: str) -> str:
        return self.container_name + "-" + role

    def _check_identity(self, request: ModelRequest) -> None:
        task = json.loads(request.input_json)
        identity = {
            "experiment_id": task.get("experiment_id")
            or task.get("frozen_plan", {}).get("bundle", {}).get("experiment_id")
            or self.audit.resolve().as_posix(),
            "model": request.model,
            "instructions": hashlib.sha256(request.instructions.encode()).hexdigest(),
            "request": hashlib.sha256(
                json.dumps(task.get("request", {}), sort_keys=True).encode()
            ).hexdigest(),
            "toolkit": hashlib.sha256(
                json.dumps(task.get("toolkit", {}), sort_keys=True).encode()
            ).hexdigest(),
        }
        if self.identity is not None and self.identity != identity:
            raise ValueError(
                "Cannot share an authoring session across experiments or changed trusted context"
            )
        self.identity = identity

    def _command(self, *args: str, seconds: int = 30) -> str:
        result = bounded_command(self.worker._docker(*args), seconds=seconds, max_bytes=100_000)
        if result.code:
            raise RuntimeError("Authoring session lifecycle failed: " + result.stderr[-2000:])
        return result.stdout.strip()

    def _update(self, mount: str) -> None:
        assert self.prepared is not None
        self._command(
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--user",
            "0:0",
            "--cap-drop",
            "ALL",
            "--cap-add",
            "SETUID",
            "--cap-add",
            "SETGID",
            "--security-opt",
            "no-new-privileges:true",
            "--memory",
            "256m",
            "--pids-limit",
            "32",
            "--mount",
            f"type=bind,src={mount},dst=/source,readonly",
            "--mount",
            f"type=volume,src={self.volume('inputs')},dst=/inputs",
            "--mount",
            f"type=volume,src={self.volume('workspace')},dst=/workspace",
            "--mount",
            f"type=volume,src={self.volume('home')},dst=/session-home",
            "--entrypoint",
            "python",
            self.prepared["image_id"],
            "-m",
            "extension_worker.muse",
            "update-session",
        )

    def _start(self, request: ModelRequest) -> None:
        assert self.prepared is not None
        if (self.audit / "session.json").exists():
            probe = bounded_command(
                self.worker._docker(
                    "inspect",
                    "--format",
                    '{{.State.Running}} {{index .Config.Labels "hypothesis.session"}}',
                    self.container_name,
                ),
                seconds=15,
                max_bytes=4096,
            )
            if probe.code == 0 and probe.stdout.strip() == "true " + self.session_id:
                self.running = True
                return
            if probe.code == 0 and probe.stdout.strip() == "false " + self.session_id:
                self._command("start", self.container_name)
                self.running = True
                return
            raise RuntimeError(
                "Persistent session container is unavailable; refusing a silent context reset"
            )
        for role in ("inputs", "workspace", "home"):
            self._command(
                "volume",
                "create",
                "--label",
                "hypothesis.session=" + self.session_id,
                self.volume(role),
            )
            self.resources_created = True
        # Input volume initialization happens before starting the author process.

    def close(self) -> None:
        """Destroy only this experiment's resources. Versioned bundles/audits remain."""
        with self._exclusive():
            self._close()

    def _close(self) -> None:
        from .authoring import private_json

        if self.closed or (self.audit / "session-closed.json").exists():
            self.closed = True
            return
        if not self.resources_created:
            self.closed = True
            return
        errors = []
        for args in [
            ("rm", "--force", self.container_name),
            *(("volume", "rm", self.volume(role)) for role in ("inputs", "workspace", "home")),
        ]:
            result = bounded_command(self.worker._docker(*args), seconds=30, max_bytes=4096)
            if result.code and "No such" not in result.stderr:
                errors.append(result.stderr[-1000:])
        if errors:
            raise RuntimeError("Could not close authoring resources: " + "; ".join(errors))
        self.running = False
        self.closed = True
        private_json(self.audit / "session-closed.json", {"session_id": self.session_id})

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
    def stage(
        request: ModelRequest,
        root: Path,
        *,
        execution_capabilities: dict[str, object] | None = None,
    ) -> None:
        """Stage only this request and inventory; sources are read on demand in the image."""
        root.chmod(0o755)
        task = json.loads(request.input_json)
        if request.actor_id != "coding_agent" or task.get("stage") not in {
            "plan_and_tests",
            "implementation",
            "repair_implementation",
            "review_notebook",
        }:
            raise ValueError("Muse authoring gateway accepts coding stages only")
        if execution_capabilities:
            task["execution_capabilities"] = {
                **execution_capabilities,
                **task.get("execution_capabilities", {}),
            }
        sources = task.get("toolkit", {}).get("sources", [])
        if "toolkit" in task:
            task["toolkit"] = {
                **task["toolkit"],
                "sources": [source["path"] for source in sources],
                "source_root": "/opt/toolkit",
            }
        inputs = root / "inputs"
        inputs.mkdir(mode=0o755)
        from .guide import write_starter

        route = task.get("request", {}).get("execution_kind", "agent_simulation")
        write_starter(inputs / "starter", kind="tool" if route == "tool" else "agent_simulation")
        task["authoring_guide"] = "/inputs/starter/INTERFACES.md"
        task["starter_directory"] = "/inputs/starter"
        if "toolkit" in task:
            task["toolkit"].pop("interface_guide", None)
        (root / "workspace").mkdir(mode=0o777)
        (root / "workspace").chmod(0o777)
        from .authoring import safe_source_path

        frozen = task.get("frozen_plan", {}).get("tests", [])
        for file in frozen:
            if not safe_source_path(file["path"], tests=True):
                raise ValueError("Invalid frozen test path")
            path = inputs / "frozen_tests" / file["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(file["content"])
        if frozen:
            task["frozen_tests_directory"] = "/inputs/frozen_tests/tests"
        for file in task.get("previous_implementation", {}).get("files", []):
            if not safe_source_path(file["path"], tests=False):
                raise ValueError("Invalid current-trial source path")
            path = root / "workspace" / file["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(file["content"])
        for path in (root / "workspace").rglob("*"):
            path.chmod(0o777 if path.is_dir() else 0o666)
        # Files copied into a VM must be readable by its unprivileged container UID.
        for path in inputs.rglob("*"):
            path.chmod(0o755 if path.is_dir() else 0o644)
        for name, content in {
            "task.json": json.dumps(task),
            "response-schema.json": json.dumps(request.response_schema),
            "AGENTS.md": request.instructions,
        }.items():
            (inputs / name).write_text(content)
            (inputs / name).chmod(0o644)

    def arguments(self, name: str, mount: str, image: str, request: ModelRequest) -> list[str]:
        """Start one experiment-owned container; subsequent stages use docker exec."""
        return self.worker._docker(
            "run",
            "--detach",
            "--init",
            "--name",
            name,
            "--label",
            "hypothesis.session=" + self.session_id,
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
            "--env",
            "HOME=/session-home",
            "--env",
            "XDG_CONFIG_HOME=/session-home/.config",
            "--env",
            "XDG_CACHE_HOME=/session-home/.cache",
            "--mount",
            f"type=volume,src={self.volume('inputs')},dst=/inputs,readonly",
            "--mount",
            f"type=volume,src={self.volume('workspace')},dst=/workspace",
            "--mount",
            f"type=volume,src={self.volume('home')},dst=/session-home",
            "--entrypoint",
            "sleep",
            image,
            "infinity",
        )

    def exec_arguments(self, request: ModelRequest) -> list[str]:
        return self.worker._docker(
            "exec",
            "--interactive",
            "--user",
            "10001:10001",
            self.container_name,
            "python",
            "-m",
            "extension_worker.muse",
            request.model,
            request.reasoning_effort or "max",
            self.session_id,
        )

    def _snapshot(self, mount: str, audit: Path) -> None:
        from .authoring import private_json

        assert self.prepared is not None
        result = bounded_command(
            self.worker._docker(
                "run",
                "--rm",
                "--network",
                "none",
                "--read-only",
                "--user",
                "10001:10001",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges:true",
                "--memory",
                "512m",
                "--pids-limit",
                "32",
                "--cpus",
                "1",
                "--mount",
                f"type=volume,src={self.volume('workspace')},dst=/workspace,readonly",
                "--entrypoint",
                "python",
                self.prepared["image_id"],
                "-m",
                "extension_worker.muse",
                "snapshot",
            ),
            seconds=30,
            max_bytes=8_000_000,
        )
        if result.code:
            raise RuntimeError("Partial snapshot collection failed")
        if self._api_key.get_secret_value() in result.stdout:
            raise RuntimeError("Credential detected in partial workspace; export refused")
        private_json(
            audit / "partial_workspace.json",
            {
                "status": "unapproved",
                "files": json.loads(result.stdout),
                "note": "Data only; incomplete or unvalidated source, never a completed result",
            },
        )

    @contextmanager
    def _exclusive(self) -> Iterator[None]:
        if not self._lock.acquire(blocking=False):
            raise RuntimeError("An authoring stage is already running in this session")
        descriptor = None
        try:
            self.audit.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(
                self.audit / "session.lock", os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW, 0o600
            )
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError(
                    "An authoring stage is already running in this experiment"
                ) from exc
            yield
        finally:
            if descriptor is not None:
                os.close(descriptor)
            self._lock.release()

    def complete(self, request: ModelRequest) -> ModelResponse:
        with self._exclusive():
            if self.closed or (self.audit / "session-closed.json").exists():
                raise RuntimeError("Authoring session is closed; start a new experiment")
            self._check_identity(request)
            return self._complete(request)

    def _complete(self, request: ModelRequest) -> ModelResponse:
        from .authoring import private_json

        if self.prepared is None:
            print("Preparing Muse Code authoring container", flush=True)
            self.prepare()
        assert self.prepared is not None
        call_id = uuid4().hex
        audit = self.audit / call_id
        stage = str(json.loads(request.input_json).get("stage", "authoring"))
        private_json(
            audit / "container.json",
            {
                **self.prepared,
                "model": request.model,
                "reasoning_effort": request.reasoning_effort,
                "transport": "muse exec --session-id; one experiment-local home/workspace; no turn cap",
                "session_id": self.session_id,
                "continuation": self.turn > 0,
                "credentials": "API key delivered once through stdin; no credential mount",
                "cli_prompt_sha256": hashlib.sha256(request.instructions.encode()).hexdigest(),
            },
        )
        progress = AuthoringProgress(
            audit / "progress.jsonl", stage, emit=lambda message: print(message, flush=True)
        )
        returned: list[str] = []
        authenticated = False
        event_count = 0
        descriptor = os.open(
            audit / "native-events.jsonl", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
        )
        raw = os.fdopen(descriptor, "w")

        def exchange(line: str) -> str | None:
            nonlocal authenticated, event_count
            if line == AUTH_FRAME:
                if authenticated:
                    raise GatewayError("duplicate_muse_auth_request")
                authenticated = True
                return json.dumps({"api_key": self._api_key.get_secret_value()})
            line = line.replace(self._api_key.get_secret_value(), "[REDACTED]")
            if line.startswith(RESULT_FRAME):
                returned.append(line[len(RESULT_FRAME) :])
                return None
            raw.write(line + "\n")
            raw.flush()
            event_count += 1
            try:
                event = json.loads(line)
                if isinstance(event, dict):
                    progress.consume(event)
            except ValueError:
                pass
            return None

        remote = "/tmp/hypothesis-muse-run-" + call_id
        name = self.container_name
        completed = False
        with TemporaryDirectory(prefix="hypothesis-muse-run-") as temporary:
            root = Path(temporary)
            mount = str(root)
            try:
                self.stage(request, root, execution_capabilities=self.execution_capabilities)
                task_path = root / "inputs/task.json"
                task = json.loads(task_path.read_text())
                task["authoring_session"] = {"id": self.session_id, "continuation": self.turn > 0}
                task_path.write_text(json.dumps(task))
                self._start(request)
                if self.worker.sandbox:
                    self.worker._copy_to_sandbox(root, remote)
                    mount = remote
                self._update(mount)
                if not self.running:
                    self._command(
                        *self.arguments(name, mount, self.prepared["image_id"], request)[
                            len(self.worker._docker()) :
                        ]
                    )
                    self.running = True
                    private_json(
                        self.audit / "session.json",
                        {
                            "session_id": self.session_id,
                            "identity": self.identity,
                            "image": self.prepared,
                        },
                    )
                self.turn += 1
                result = bounded_command(
                    self.exec_arguments(request),
                    seconds=self.seconds,
                    max_bytes=16_000_000,
                    exchange=exchange,
                    on_tick=progress.tick,
                )
                private_json(
                    audit / "events.json",
                    {
                        "events_path": "native-events.jsonl",
                        "stderr": result.stderr.replace(
                            self._api_key.get_secret_value(), "[REDACTED]"
                        ),
                        "exit_code": result.code,
                        "events": event_count,
                    },
                )
                if result.code or len(returned) != 1:
                    raise GatewayError("muse_cli_failed_or_missing_response")
                response = ModelResponse.model_validate_json(returned[0])
                if response.model != request.model:
                    raise GatewayError("muse_model_mismatch")
                usage = progress.usage()
                private_json(
                    audit / "usage.json",
                    {
                        **usage,
                        "available": bool(progress.runs),
                        "scope": "Native CLI totals; failed-call token usage may be incomplete",
                    },
                )
                progress.record("stage_completed", "Authoring response received", **usage)
                completed = True
                return response.model_copy(
                    update={
                        "input_tokens": usage["input_tokens"],
                        "output_tokens": usage["output_tokens"],
                    }
                )
            except BaseException as exc:
                private_json(
                    audit / "failure.json",
                    {
                        "category": str(exc)
                        if isinstance(exc, GatewayError)
                        else type(exc).__name__,
                        "elapsed_seconds": round(time.monotonic() - progress.started, 1),
                        "usage": progress.usage(),
                    },
                )
                progress.record(
                    "stage_failed", "Authoring failed; preserving partial files and native events"
                )
                raise
            finally:
                raw.close()
                # Keep successful stages alive; a failed exec may leave child tools running.
                # Stop the process tree before offline salvage, retaining only this trial's volumes.
                if not completed and self.resources_created:
                    subprocess.run(
                        self.worker._docker("stop", "--time", "1", name),
                        capture_output=True,
                        timeout=20,
                        check=False,
                    )
                    self.running = False
                if not completed and self.resources_created:
                    try:
                        self._snapshot(mount, audit)
                    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
                        private_json(
                            audit / "snapshot_failure.json", {"category": type(exc).__name__}
                        )
                self._remove_remote(remote)
