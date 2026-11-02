"""Read, hash, and snapshot bundles as data. No experimental imports or eval."""

import hashlib
import json
import os
import shutil
import stat
from pathlib import Path

from .inventory import compatibility_findings
from .specs import BundleManifest, BundleSeal

MAX_FILES = 200
MAX_BYTES = 4_000_000


def _allowed(path: str) -> bool:
    parts = Path(path).parts
    if path in {"bundle.json", "job.example.json", "README.md"}:
        return True
    return (
        len(parts) > 1
        and parts[0] in {"experiment_extension", "tests"}
        and not any(part.startswith(".") or part == "__pycache__" for part in parts)
        and path.endswith(".py")
    )


def _read_file(name: str, directory_fd: int) -> bytes:
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > MAX_BYTES:
            raise ValueError("Bundle files must be regular, unlinked, and within size limits")
        data = stream.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError("Bundle file exceeds size limit")
        return data


def bundle_files(root: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    total = 0
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for directory, subdirs, names, directory_fd in os.fwalk(
            ".", dir_fd=descriptor, follow_symlinks=False
        ):
            for name in subdirs:
                if stat.S_ISLNK(os.stat(name, dir_fd=directory_fd, follow_symlinks=False).st_mode):
                    raise ValueError("Bundle directories cannot be symbolic links")
            for name in names:
                relative = (Path(directory) / name).as_posix()
                if relative == "bundle.lock.json":
                    _read_file(name, directory_fd)
                    continue
                if not _allowed(relative):
                    raise ValueError(f"Unexpected bundle file: {relative}")
                if len(files) >= MAX_FILES:
                    raise ValueError("Bundle exceeds file count limit")
                data = _read_file(name, directory_fd)
                total += len(data)
                if total > MAX_BYTES:
                    raise ValueError("Bundle exceeds total size limit")
                files[relative] = data
    finally:
        os.close(descriptor)
    if "bundle.json" not in files or "experiment_extension/__init__.py" not in files:
        raise ValueError("Bundle needs bundle.json and experiment_extension/__init__.py")
    if not any(path.startswith("tests/test_") for path in files):
        raise ValueError("Bundle needs acceptance tests")
    return files


def _read_seal(root: Path) -> BundleSeal:
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        return BundleSeal.model_validate_json(_read_file("bundle.lock.json", descriptor))
    finally:
        os.close(descriptor)


def content_seal(files: dict[str, bytes]) -> BundleSeal:
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}
    digest = hashlib.sha256(
        json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return BundleSeal(files=hashes, digest=digest)


def inspect_bundle(
    root: Path, *, check_location: bool = True
) -> tuple[BundleManifest, dict[str, bytes]]:
    files = bundle_files(root)
    manifest = BundleManifest.model_validate_json(files["bundle.json"])
    if check_location and (
        root.name != manifest.version or root.parent.name != manifest.experiment_id
    ):
        raise ValueError("Expected experimental_components/<experiment_id>/<version>")
    if compatibility_findings(manifest.gap_analysis):
        raise ValueError(
            "Known incompatible reuse: " + "; ".join(compatibility_findings(manifest.gap_analysis))
        )
    if not manifest.gap_analysis.ready:
        raise ValueError("Resolve critical unknowns and unsupported requirements before sealing")
    return manifest, files


def seal_bundle(root: Path) -> BundleSeal:
    _, files = inspect_bundle(root)
    seal = content_seal(files)
    path = root / "bundle.lock.json"
    if path.exists():
        existing = _read_seal(root)
        if existing != seal:
            raise ValueError("Sealed version changed; create a new version instead of resealing")
        return existing
    with path.open("x") as stream:
        stream.write(seal.model_dump_json(indent=2) + "\n")
    return seal


def verify_bundle(
    root: Path, *, check_location: bool = True
) -> tuple[BundleManifest, BundleSeal, dict[str, bytes]]:
    manifest, files = inspect_bundle(root, check_location=check_location)
    lock = root / "bundle.lock.json"
    if lock.is_symlink():
        raise ValueError("Bundle seal cannot be a symbolic link")
    seal = _read_seal(root)
    if seal != content_seal(files):
        raise ValueError("Bundle changed after sealing; validation is invalid")
    return manifest, seal, files


def snapshot_bundle(root: Path, destination: Path) -> BundleSeal:
    _, seal, files = verify_bundle(root)
    destination.mkdir(mode=0o755)
    for name, data in {
        **files,
        "bundle.lock.json": (seal.model_dump_json() + "\n").encode(),
    }.items():
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.parent.chmod(0o755)
        path.write_bytes(data)
        path.chmod(0o644)
    destination.chmod(0o755)
    return seal


def copy_trusted_context(project: Path, destination: Path) -> str:
    """Explicit allowlist: no .env, user settings, git data, or generated extensions."""
    trusted_paths = [
        project / name for name in ("pyproject.toml", "uv.lock", "src", "tests", "docker")
    ]
    safe_prompts = [
        project / "prompts" / name
        for name in (
            "blind_coding_agent.md",
            "muse_coding_agent.md",
        )
        if (project / "prompts" / name).exists()
    ]
    trusted_paths.extend(safe_prompts)
    if any(path.is_symlink() for root in trusted_paths for path in (root, *root.rglob("*"))):
        raise ValueError("Trusted build inputs cannot contain symbolic links")
    destination.mkdir()
    for name in ("pyproject.toml", "uv.lock"):
        shutil.copyfile(project / name, destination / name)
    for name in ("src", "tests", "docker"):
        shutil.copytree(
            project / name,
            destination / name,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".*"),
        )
    if safe_prompts:
        (destination / "prompts").mkdir()
        for prompt in safe_prompts:
            shutil.copyfile(prompt, destination / "prompts" / prompt.name)
    hashes = {
        path.relative_to(destination).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(destination.rglob("*"))
        if path.is_file()
    }
    return hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
