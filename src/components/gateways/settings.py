"""Host-only credentials. Never include this object in simulation manifests."""

import os
import re
from pathlib import Path
from typing import Literal

from dotenv import dotenv_values, find_dotenv
from pydantic import BaseModel, ConfigDict, Field, SecretStr


class LiveModelSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    api_key: SecretStr = Field(exclude=True)
    actor_api_keys: tuple[SecretStr, ...] = Field(default=(), exclude=True, repr=False)
    model: str = Field(min_length=1)

    @classmethod
    def load(
        cls,
        model: str | None = None,
        env_file: Path | None = None,
        *,
        role: Literal["actor", "coding"] = "actor",
    ) -> "LiveModelSettings":
        # Explicit environment beats file values; both requested and standard names work.
        found = find_dotenv(usecwd=True) if env_file is None else ""
        path = env_file if env_file is not None else Path(found) if found else Path.cwd() / ".env"
        values = dotenv_values(path, interpolate=False) if path.is_file() else {}
        key = (
            os.environ.get("API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or values.get("API_KEY")
            or values.get("OPENAI_API_KEY")
        )
        selected = model or (
            os.environ.get("MODEL_CODING") or values.get("MODEL_CODING")
            if role == "coding"
            else os.environ.get("MODEL")
            or os.environ.get("OPENAI_MODEL")
            or values.get("MODEL")
            or values.get("OPENAI_MODEL")
        )
        if not key:
            raise ValueError("Set API_KEY in .env or the process environment")
        if not selected:
            variable = "MODEL_CODING" if role == "coding" else "MODEL"
            raise ValueError(f"Set {variable} in .env or pass an explicit model")
        if role == "coding" and selected != "muse-spark-1.3":
            raise ValueError(
                "MODEL_CODING must be muse-spark-1.3 for the requested max reasoning setup"
            )
        keys = [key]
        if role == "actor":
            names = sorted(
                {
                    name
                    for name in {*values, *os.environ}
                    if re.fullmatch(r"API_KEY_(?:[2-9]|[1-9][0-9]+)", name)
                },
                key=lambda name: int(name.rsplit("_", 1)[1]),
            )
            for name in names:
                extra = os.environ.get(name) or values.get(name)
                if extra and extra not in keys:
                    keys.append(extra)
        return cls(
            api_key=SecretStr(key),
            model=selected,
            actor_api_keys=tuple(SecretStr(value) for value in keys) if role == "actor" else (),
        )
