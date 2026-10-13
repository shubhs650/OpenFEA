"""Fixed server-owned paths, immutable bytes and verified authorized artifact reads."""

import hashlib
import os
import re
import stat
import tempfile
from pathlib import Path
from uuid import UUID

from app.domain.errors import DomainError


class GeometryStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def directory(self, kind: str, identifier: UUID) -> Path:
        if kind not in ("uploads", "imports", "artifacts", "exports", "jobs", "edits"):
            raise ValueError("Unknown storage namespace")
        path = self.root / kind / str(identifier)
        if not path.resolve().is_relative_to(self.root):
            raise DomainError(503, "artifact_unavailable", "Geometry storage is unavailable")
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        return path

    @staticmethod
    def read_fixed(path: Path, expected: str | None = None, limit: int = 32 * 1024**2) -> bytes:
        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(descriptor, "rb") as source:
                if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                    raise OSError("Artifact must be a regular file")
                data = source.read(limit + 1)
        except OSError:
            raise DomainError(
                503, "artifact_unavailable", "Geometry artifact is unavailable"
            ) from None
        if len(data) > limit or (expected and hashlib.sha256(data).hexdigest() != expected):
            raise DomainError(
                503, "artifact_integrity", "Geometry artifact failed its integrity check"
            )
        return data

    def save(self, project: UUID, path: Path, expected: str) -> None:
        data = self.read_fixed(path, expected)
        destination = self.blob_path(project, expected)
        if destination.exists():
            self.read_fixed(destination, expected)
            return
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as temporary:
            temporary.write(data)
            temporary.flush()
            os.fsync(temporary.fileno())
            name = Path(temporary.name)
        try:
            name.chmod(0o400)
            try:
                os.link(name, destination)
            except FileExistsError:
                self.read_fixed(destination, expected)
        finally:
            name.unlink(missing_ok=True)

    def blob_path(self, project: UUID, digest: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise DomainError(503, "artifact_integrity", "Geometry artifact identity is invalid")
        return self.directory("artifacts", project) / digest

    def read(self, project: UUID, digest: str) -> bytes:
        return self.read_fixed(self.blob_path(project, digest), digest)
