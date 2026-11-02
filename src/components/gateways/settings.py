"""Host-only credentials. Never include this object in simulation manifests."""

import os
from pathlib import Path
from typing import Literal

from dotenv import dotenv_values, find_dotenv
from pydantic import BaseModel, ConfigDict, Field, SecretStr


class LiveModelSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    api_key: SecretStr = Field(exclude=True)
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
        return cls(api_key=SecretStr(key), model=selected)
