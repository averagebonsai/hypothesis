"""Deterministic source normalization before freezing/sealing, never code execution."""

import hashlib
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from .contracts import SourceFile
from .process import bounded_command


def normalize_sources(
    project: Path, sources: tuple[SourceFile, ...]
) -> tuple[tuple[SourceFile, ...], list[dict[str, str]]]:
    from .authoring import safe_source_path

    result = []
    changes = []
    with TemporaryDirectory(prefix="authoring-format-") as temporary:
        root = Path(temporary)
        for source in sources:
            if not safe_source_path(source.path, tests=source.path.startswith("tests/")):
                raise ValueError("Unsafe source path during normalization")
            if not source.path.endswith(".py"):
                result.append(source)
                continue
            path = root / source.path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source.content)
            base = [sys.executable, "-m", "ruff"]
            ordered = bounded_command(
                base
                + [
                    "check",
                    "--select",
                    "I",
                    "--fix",
                    "--config",
                    str(project / "pyproject.toml"),
                    str(path),
                ],
                seconds=30,
                max_bytes=100000,
            )
            formatted = bounded_command(
                base + ["format", "--config", str(project / "pyproject.toml"), str(path)],
                seconds=30,
                max_bytes=100000,
            )
            content = (
                path.read_text() if ordered.code == 0 and formatted.code == 0 else source.content
            )
            result.append(source.model_copy(update={"content": content}))
            if content != source.content:
                changes.append(
                    {
                        "path": source.path,
                        "raw_sha256": hashlib.sha256(source.content.encode()).hexdigest(),
                        "normalized_sha256": hashlib.sha256(content.encode()).hexdigest(),
                    }
                )
    return tuple(result), changes
