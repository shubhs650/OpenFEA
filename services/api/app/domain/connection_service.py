"""Owned read-only native connection measurements, repeated before saving approval."""

import fcntl
import hashlib
import json
import shutil
from uuid import UUID, uuid4

from app.domain.connections import (
    BondAssignment,
    BondCandidates,
    BondReport,
    BondRequest,
    BondState,
    validate_pair,
)
from app.domain.errors import DomainError, stale_revision
from app.domain.import_service import ImportService
from app.persistence.repository import Repository
from worker.step_import import ImportSandboxError, inspect_step


class ConnectionService:
    def __init__(self, repository: Repository, imports: ImportService):
        self.repository, self.imports = repository, imports

    def candidates(self, owner: UUID, analysis: UUID, expected: int) -> BondCandidates:
        current = self.repository.get_analysis(owner, analysis)
        if current.revision != expected:
            raise stale_revision()
        if current.geometry_revision_id is None:
            raise DomainError(422, "geometry_required", "Accept geometry first")
        geometry = self.repository.get_geometry(owner, current.geometry_revision_id)
        storage = self.imports.storage
        if len(geometry.faces) > 100:
            raise DomainError(
                422, "bond_review_limit", "Connection review supports at most 100 faces"
            )
        with (storage.root / "native-import.lock").open("a+b") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise DomainError(
                    429, "geometry_busy", "Another native geometry/mesh operation is processing"
                ) from None
            self.imports.verify_artifacts(geometry.project_id, geometry.model_dump(mode="json"))
            directory = storage.directory("bond-reviews", uuid4())
            try:
                metadata = directory / "source.json"
                metadata.write_text(geometry.model_dump_json())
                metadata.chmod(0o400)
                result = inspect_step(
                    storage.blob_path(geometry.project_id, geometry.brep_sha256),
                    directory / "output",
                    bond_review=metadata,
                )
                if result.get("status") != "bond_review":
                    raise DomainError(
                        422,
                        "bond_review_failed",
                        result.get("error_message", "Native review failed"),
                    )
                report = BondReport.model_validate(result["report"])
            except ImportSandboxError:
                raise DomainError(
                    503,
                    "native_unavailable",
                    "Isolated CAD review is unavailable or exceeded its resource budget",
                ) from None
            finally:
                shutil.rmtree(directory)
            self.imports.verify_artifacts(geometry.project_id, geometry.model_dump(mode="json"))
        if self.repository.get_analysis(owner, analysis).revision != expected:
            raise stale_revision()
        raw = json.dumps(
            {"geometry_id": str(geometry.id), "report": report.model_dump(mode="json")},
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
        return BondCandidates(
            analysis_id=analysis,
            analysis_revision=expected,
            geometry_revision_id=geometry.id,
            report_sha256=hashlib.sha256(raw).hexdigest(),
            report=report,
        )

    def approve(
        self, owner: UUID, analysis: UUID, expected: int, payload: BondRequest
    ) -> BondState:
        report = self.candidates(owner, analysis, expected)
        if payload.geometry_revision_id != report.geometry_revision_id:
            raise DomainError(422, "stale_bond", "Choose faces from the pinned geometry")
        pair = next(
            (
                p
                for p in report.report.pairs
                if {p.master_face_id, p.slave_face_id}
                == {payload.master_face_id, payload.slave_face_id}
            ),
            None,
        )
        if pair is None:
            raise DomainError(
                422,
                "unsupported_bond",
                "Pair has no verified opposing planar projected overlap "
                "within the review search bound",
            )
        if report.report.overlaps:
            raise DomainError(
                422, "body_overlap", "Body volume overlap blocks all connection approval"
            )
        if pair.master_face_id != payload.master_face_id:
            pair = pair.model_copy(
                update={
                    "master_face_id": pair.slave_face_id,
                    "slave_face_id": pair.master_face_id,
                    "master_coverage": pair.slave_coverage,
                    "slave_coverage": pair.master_coverage,
                    "master_normal": pair.slave_normal,
                    "slave_normal": pair.master_normal,
                    "master_center_m": pair.slave_center_m,
                    "slave_center_m": pair.master_center_m,
                }
            )
        validate_pair(payload, pair)
        item = BondAssignment(
            **payload.model_dump(),
            id=uuid4(),
            pair=pair,
            review_report=report.report,
            review_sha256=report.report_sha256,
        )
        return self.repository.edit_bonds(owner, analysis, expected, item)
