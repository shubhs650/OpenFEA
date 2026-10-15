"""In-memory unsigned copies keep refusal tests independent of real owner records."""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from worker.runtime import ROOT


@contextmanager
def unsigned_manifest(monkeypatch: pytest.MonkeyPatch, case: str) -> Iterator[None]:
    name = "B07-mortar" if case == "B07" else case
    target = ROOT / f"tests/benchmarks/{name}.json"
    read_text, read_bytes = Path.read_text, Path.read_bytes

    def unsigned(raw: str) -> str:
        manifest = json.loads(raw)
        manifest["reviewer_signoff"] = "PENDING synthetic refusal test only"
        return json.dumps(manifest, allow_nan=False)

    def text(path: Path, *args: Any, **kwargs: Any) -> str:
        raw = read_text(path, *args, **kwargs)
        return unsigned(raw) if path == target else raw

    def data(path: Path) -> bytes:
        raw = read_bytes(path)
        return unsigned(raw.decode()).encode() if path == target else raw

    with monkeypatch.context() as patch:
        patch.setattr(Path, "read_text", text)
        patch.setattr(Path, "read_bytes", data)
        yield
