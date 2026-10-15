"""Untrusted ZIP metadata is bounded and validated without extracting files."""

import io
import stat
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest

from app.domain.archives import ArchiveManifest
from app.jobs.service import JobService
from app.storage.archives import descriptor, json_bytes, read_archive, strict_json, write_archive


def packed(
    entries: list[tuple[str | zipfile.ZipInfo, bytes]], compression: int = zipfile.ZIP_STORED
) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=compression) as archive:
        for name, raw in entries:
            archive.writestr(name, raw)
    return output.getvalue()


def manifest() -> ArchiveManifest:
    return ArchiveManifest(
        kind="project",
        created_at=datetime.now(UTC),
        files={"project.json": descriptor(b"{}")},
        tools={},
    )


@pytest.mark.parametrize(
    "path",
    ["../evil", "/evil", "C:/evil", "a/../b", "a\\b", "a//b", "./a", "a/", "a/./b", "a\x00b"],
)
def test_reject_unsafe_paths(path: str) -> None:
    with pytest.raises(ValueError):
        read_archive(
            packed(
                [("manifest.json", json_bytes(manifest().model_dump(mode="json"))), (path, b"{}")]
            )
        )


@pytest.mark.parametrize("mode", [stat.S_IFLNK, stat.S_IFIFO, stat.S_IFCHR, stat.S_IFDIR])
def test_reject_nonregular_entries(mode: int) -> None:
    info = zipfile.ZipInfo("project.json")
    info.external_attr = (mode | 0o777) << 16
    with pytest.raises(ValueError):
        read_archive(
            packed(
                [("manifest.json", json_bytes(manifest().model_dump(mode="json"))), (info, b"{}")]
            )
        )


@pytest.mark.parametrize(
    "case",
    [
        "hash",
        "size",
        "version",
        "undeclared",
        "missing",
        "duplicate",
        "migration",
        "nested",
        "bomb",
        "count",
    ],
)
def test_reject_bad_manifest_and_expansion(case: str) -> None:
    fields = manifest().model_dump(mode="json")
    items: list[tuple[str | zipfile.ZipInfo, bytes]] = [("project.json", b"{}")]
    compression = zipfile.ZIP_STORED
    if case == "hash":
        fields["files"]["project.json"]["sha256"] = "0" * 64
    if case == "size":
        fields["files"]["project.json"]["size_bytes"] = 100
    if case == "version":
        fields["schema_version"] = 2
    if case == "undeclared":
        items.append(("evil.py", b"print(1)"))
    if case == "missing":
        items = [("tools.json", b"{}")]
    if case == "duplicate":
        items.append(("project.json", b"{}"))
    if case == "migration":
        fields["required_migrations"] = ["run this"]
    if case == "nested":
        fields["files"] = {"nested.zip": descriptor(b"{}").model_dump()}
        items = [("nested.zip", b"{}")]
    if case == "bomb":
        items = [("project.json", b"0" * 1024**2)]
        compression = zipfile.ZIP_DEFLATED
    if case == "count":
        items = [(f"item{i}", b"") for i in range(513)]
    with pytest.raises(ValueError):
        read_archive(packed([("manifest.json", json_bytes(fields)), *items], compression))


@pytest.mark.parametrize("raw", [b'{"a":1,"a":2}', b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1e400}'])
def test_json_duplicate_or_nonfinite_refused(raw: bytes) -> None:
    with pytest.raises(ValueError):
        strict_json(raw)


def test_stored_archive_roundtrip() -> None:
    model = manifest()
    raw = write_archive(model, {"project.json": b"{}"})
    parsed, files = read_archive(raw)
    assert parsed == model and files == {"project.json": b"{}"}


@pytest.mark.parametrize("model_name", ["ArchiveOptions", "DiagnosticOptions"])
def test_privacy_choices_require_real_booleans(model_name: str) -> None:
    from app.domain import archives

    model = getattr(archives, model_name)
    key = "include_outputs" if model_name == "ArchiveOptions" else "include_geometry"
    for value in ("true", "false", 0, 1, None):
        with pytest.raises(ValueError):
            model.model_validate({key: value})


@pytest.mark.parametrize(
    "raw",
    [
        b"PK\x05\x06",
        b"Rar!",
        b"\x1f\x8b",
        b"7z\xbc\xaf",
        b"BZh",
        b"\xfd7zXZ",
        b"x" * 257 + b"ustar",
    ],
)
def test_recursive_archive_objects_are_recognized(raw: bytes) -> None:
    from app.storage.archives import nested_archive

    assert nested_archive(raw)


def test_oversized_project_refuses_before_serializing_revisions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace
    from uuid import uuid4

    from sqlalchemy import text

    from app.domain.archive_service import ArchiveService
    from app.domain.archives import ArchiveOptions
    from app.domain.errors import DomainError
    from app.domain.models import ProjectCreate
    from app.persistence.database import Database
    from app.persistence.repository import Repository

    database = Database(tmp_path / "metadata.sqlite3")
    database.migrate()
    repository = Repository(database)
    owner = repository.local_owner()
    project = repository.create_project(owner, ProjectCreate(name="Archive capacity guard"))
    with repository.write() as connection:
        for _ in range(257):
            identifier = str(uuid4())
            connection.execute(
                text("INSERT INTO analyses VALUES (:id,:project,1,'2026-10-15','2026-10-15')"),
                {"id": identifier, "project": str(project.id)},
            )
            connection.execute(
                text(
                    "INSERT INTO analysis_revisions VALUES "
                    "(:id,:project,1,'Empty',NULL,'2026-10-15')"
                ),
                {"id": identifier, "project": str(project.id)},
            )

    def unexpected(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Must refuse excess count before loading setup records")

    monkeypatch.setattr(repository, "_analysis", unexpected)
    jobs = SimpleNamespace(
        decks=SimpleNamespace(repository=repository), storage=SimpleNamespace(root=tmp_path)
    )
    service = ArchiveService(cast(JobService, jobs))
    with pytest.raises(DomainError) as refused:
        service.export(owner, project.id, ArchiveOptions())
    assert refused.value.status == 422
    database.close()
