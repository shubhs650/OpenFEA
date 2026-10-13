"""Immutable, synthetic-only OCCT cleanup diagnostic; product editing is T013."""

import json
from pathlib import Path
from typing import Any, Literal

from worker.runtime import NATIVE, ROOT, execute, sha256


def cleanup_fixture(directory: Path, kind: Literal["hole", "fillet"]) -> dict[str, Any]:
    if kind not in ("hole", "fillet") or directory.exists():
        raise ValueError("Fresh directory and allowlisted cleanup fixture required")
    directory.mkdir(parents=True)
    execute(
        [
            str(NATIVE / "venvs/cad/bin/python"),
            "-I",
            str(ROOT / "services/worker/worker/geometry_native/cleanup.py"),
            "create",
            kind,
        ],
        directory,
    )
    return json.loads((directory / "catalog.json").read_text())  # type: ignore[no-any-return]


def cleanup_preview(source: Path, destination: Path, face_ref: str) -> dict[str, Any]:
    if destination.exists():
        raise ValueError("Preview requires a fresh destination")
    files = {p.name: sha256(p) for p in source.iterdir() if p.is_file()}
    destination.mkdir(parents=True)
    try:
        execute(
            [
                str(NATIVE / "venvs/cad/bin/python"),
                "-I",
                str(ROOT / "services/worker/worker/geometry_native/cleanup.py"),
                "preview",
                str(source.resolve()),
                face_ref,
            ],
            destination,
        )
    finally:
        after = {p.name: sha256(p) for p in source.iterdir() if p.is_file()}
        if files != after:
            raise RuntimeError("Cleanup mutated the original revision")
    return json.loads((destination / "edit.json").read_text())  # type: ignore[no-any-return]
