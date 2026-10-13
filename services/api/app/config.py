"""Fail closed for modes outside the local-only bootstrap."""

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast


@dataclass(frozen=True)
class Settings:
    mode: Literal["local", "test"]
    bind_host: str
    data_root: Path

    @classmethod
    def from_environment(cls) -> "Settings":
        mode = os.environ.get("FEA_ENV", "local")
        if mode not in ("local", "test"):
            raise ValueError("Only local and test environments are supported; beta is disabled")
        if os.environ.get("FEA_AUTH_MODE", "local") != "local":
            raise ValueError("Only local authentication mode is supported")
        host = os.environ.get("FEA_BIND_HOST", "127.0.0.1")
        if host != "127.0.0.1":
            raise ValueError("Local mode requires FEA_BIND_HOST=127.0.0.1")
        data_root = Path(
            os.environ.get("FEA_DATA_ROOT", str(Path(tempfile.gettempdir()) / "openfea-data"))
        )
        repository = Path(__file__).resolve().parents[3]
        if not data_root.is_absolute() or data_root.resolve().is_relative_to(repository):
            raise ValueError("FEA_DATA_ROOT must be an absolute path outside the checkout")
        return cls(mode=cast(Literal["local", "test"], mode), bind_host=host, data_root=data_root)
