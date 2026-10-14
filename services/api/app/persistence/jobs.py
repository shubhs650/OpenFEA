"""Atomic FIFO admission/claim, attempt fencing and owner-scoped durable history."""

import json
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Connection, text

from app.domain.errors import DomainError, not_found, stale_revision
from app.domain.jobs import TERMINAL, Artifact, JobEvent, JobInput, LocalJob, Stage, Status
from app.persistence.repository import Repository, now


class JobRepository:
    def __init__(self, projects: Repository) -> None:
        self.projects = projects

    @staticmethod
    def event(connection: Connection, identifier: str) -> None:
        connection.execute(
            text("""INSERT INTO local_job_events
            SELECT id,(SELECT coalesce(max(sequence),0)+1 FROM local_job_events WHERE job_id=id),
            status,stage,:at,reason_code FROM local_jobs WHERE id=:id"""),
            {"id": identifier, "at": now()},
        )

    @staticmethod
    def row(connection: Connection, identifier: UUID) -> dict[str, Any]:
        row = (
            connection.execute(
                text("SELECT * FROM local_jobs WHERE id=:id"), {"id": str(identifier)}
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise not_found()
        return dict(row)

    def authorized(self, connection: Connection, owner: UUID, identifier: UUID) -> dict[str, Any]:
        row = self.row(connection, identifier)
        self.projects._project(connection, owner, UUID(row["project_id"]))
        return row

    def model(self, connection: Connection, row: dict[str, Any]) -> LocalJob:
        fields = {name: row[name] for name in LocalJob.model_fields if name in row}
        fields["summary"] = json.loads(row["summary_json"])
        fields["artifacts"] = json.loads(row["artifacts_json"])
        events = connection.execute(
            text(
                "SELECT sequence,status,stage,at,reason_code "
                "FROM local_job_events WHERE job_id=:id ORDER BY sequence"
            ),
            {"id": row["id"]},
        ).mappings()
        fields["events"] = [JobEvent.model_validate(dict(e)) for e in events]
        return LocalJob.model_validate(fields)

    def get(self, owner: UUID, identifier: UUID) -> LocalJob:
        with self.projects.database.engine.connect() as connection, connection.begin():
            return self.model(connection, self.authorized(connection, owner, identifier))

    def inputs(self, owner: UUID, identifier: UUID) -> JobInput:
        with self.projects.database.engine.connect() as connection:
            self.authorized(connection, owner, identifier)
            raw = connection.execute(
                text("SELECT input_json FROM local_job_inputs WHERE job_id=:id"),
                {"id": str(identifier)},
            ).scalar_one()
            return JobInput.model_validate_json(raw)

    def list_jobs(self, owner: UUID, analysis: UUID) -> list[LocalJob]:
        with self.projects.database.engine.connect() as connection, connection.begin():
            self.projects._analysis(connection, owner, analysis)
            rows = connection.execute(
                text(
                    "SELECT * FROM local_jobs WHERE analysis_id=:id "
                    "ORDER BY queued_at DESC,id DESC LIMIT 100"
                ),
                {"id": str(analysis)},
            ).mappings()
            return [self.model(connection, dict(row)) for row in rows]

    def project_meshes(self, owner: UUID, analysis: UUID) -> list[LocalJob]:
        with self.projects.database.engine.connect() as connection, connection.begin():
            current = self.projects._analysis(connection, owner, analysis)
            rows = connection.execute(
                text(
                    "SELECT * FROM local_jobs WHERE project_id=:project AND kind='mesh' "
                    "AND status='succeeded' ORDER BY queued_at DESC,id DESC LIMIT 100"
                ),
                {"project": str(current.project_id)},
            ).mappings()
            return [self.model(connection, dict(row)) for row in rows]

    def existing(self, owner: UUID, key: UUID, request_hash: str) -> LocalJob | None:
        with self.projects.database.engine.connect() as connection:
            row = (
                connection.execute(
                    text("SELECT * FROM local_jobs WHERE owner_id=:owner AND idempotency_key=:key"),
                    {"owner": str(owner), "key": str(key)},
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                return None
            self.projects._project(connection, owner, UUID(row["project_id"]))
            if row["request_sha256"] != request_hash:
                raise DomainError(
                    409,
                    "idempotency_conflict",
                    "This request key already belongs to different inputs",
                )
            return self.model(connection, dict(row))

    def enqueue(
        self,
        owner: UUID,
        key: UUID,
        request_hash: str,
        identifier: UUID,
        inputs: JobInput,
        input_hash: str,
    ) -> LocalJob:
        with self.projects.write() as connection:
            existing = (
                connection.execute(
                    text("SELECT * FROM local_jobs WHERE owner_id=:owner AND idempotency_key=:key"),
                    {"owner": str(owner), "key": str(key)},
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                self.authorized(connection, owner, UUID(existing["id"]))
                if existing["request_sha256"] != request_hash:
                    raise DomainError(
                        409, "idempotency_conflict", "This request key belongs to different inputs"
                    )
                return self.model(connection, dict(existing))
            analysis = inputs.snapshot.analysis
            current = self.projects._analysis(connection, owner, analysis.id)
            if current.revision != analysis.revision:
                raise stale_revision()
            count = connection.execute(
                text(
                    "SELECT count(*) FROM local_jobs "
                    "WHERE status IN ('queued','running','cancelling')"
                )
            ).scalar_one()
            if count >= 20:
                raise DomainError(
                    429, "queue_full", "The local queue already has 20 pending or active jobs"
                )
            connection.execute(
                text("""INSERT INTO local_jobs
                (id,analysis_id,project_id,analysis_revision,geometry_revision_id,kind,
                 mesh_job_id,owner_id,idempotency_key,request_sha256,input_sha256,status,stage,queued_at)
                VALUES (:id,:analysis,:project,:revision,:geometry,:kind,:mesh,:owner,:key,:request,
                        :hash,'queued','queued',:at)"""),
                {
                    "id": str(identifier),
                    "analysis": str(analysis.id),
                    "project": str(analysis.project_id),
                    "revision": analysis.revision,
                    "geometry": str(inputs.snapshot.geometry.id),
                    "kind": inputs.kind,
                    "mesh": str(inputs.mesh.job_id) if inputs.mesh else None,
                    "owner": str(owner),
                    "key": str(key),
                    "request": request_hash,
                    "hash": input_hash,
                    "at": now(),
                },
            )
            connection.execute(
                text("INSERT INTO local_job_inputs VALUES (:id,:json)"),
                {"id": str(identifier), "json": inputs.model_dump_json()},
            )
            self.event(connection, str(identifier))
            return self.model(connection, self.row(connection, identifier))

    def pending(self) -> bool:
        with self.projects.database.engine.connect() as connection:
            return bool(
                connection.execute(
                    text(
                        "SELECT EXISTS(SELECT 1 FROM local_jobs j "
                        "JOIN projects p ON p.id=j.project_id "
                        "WHERE j.status='queued' AND p.deleted_at IS NULL)"
                    )
                ).scalar_one()
            )

    def claim(self, worker: UUID) -> tuple[LocalJob, UUID, UUID] | None:
        with self.projects.write() as connection:
            if connection.execute(
                text("SELECT count(*) FROM local_jobs WHERE status IN ('running','cancelling')")
            ).scalar_one():
                return None
            row = (
                connection.execute(
                    text(
                        "SELECT j.* FROM local_jobs j JOIN projects p ON p.id=j.project_id "
                        "WHERE j.status='queued' AND p.deleted_at IS NULL ORDER BY "
                        "j.queued_at,j.id LIMIT 1"
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                return None
            token = uuid4()
            connection.execute(
                text(
                    "UPDATE local_jobs SET status='running',stage=:stage,"
                    "started_at=:at,heartbeat_at=:at,attempt_token=:token,w"
                    "orker_id=:worker WHERE id=:id"
                ),
                {
                    "id": row["id"],
                    "stage": "meshing" if row["kind"] == "mesh" else "solving",
                    "at": now(),
                    "token": str(token),
                    "worker": str(worker),
                },
            )
            self.event(connection, row["id"])
            return (
                self.model(connection, self.row(connection, UUID(row["id"]))),
                token,
                UUID(row["owner_id"]),
            )

    def cancel(self, owner: UUID, identifier: UUID) -> LocalJob:
        with self.projects.write() as connection:
            row = self.authorized(connection, owner, identifier)
            if row["status"] not in TERMINAL and not row["cancel_requested"]:
                queued = row["status"] == "queued"
                connection.execute(
                    text(
                        "UPDATE local_jobs SET cancel_requested=1,status=:status,"
                        "stage=:stage,finished_at=:finished WHERE id=:id"
                    ),
                    {
                        "id": str(identifier),
                        "status": "cancelled" if queued else "cancelling",
                        "stage": "finished" if queued else row["stage"],
                        "finished": now() if queued else None,
                    },
                )
                self.event(connection, str(identifier))
            return self.model(connection, self.row(connection, identifier))

    def control(self, identifier: UUID, token: UUID) -> bool:
        with self.projects.database.engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT j.status,j.attempt_token,j.cancel_requested,p.deleted_at, "
                        "j.owner_id,p.owner_id AS project_owner "
                        "FROM local_jobs j JOIN projects p ON p.id=j.project_id WHERE j.id=:id"
                    ),
                    {"id": str(identifier)},
                )
                .mappings()
                .one()
            )
            return (
                row["attempt_token"] != str(token)
                or row["status"] not in ("running", "cancelling")
                or bool(row["cancel_requested"])
                or row["deleted_at"] is not None
                or row["owner_id"] != row["project_owner"]
            )

    def pulse(
        self,
        identifier: UUID,
        token: UUID,
        *,
        stage: Stage | None = None,
        pid: int | None = None,
        process_start: str | None = None,
        progress: dict[str, Any] | None = None,
    ) -> None:
        with self.projects.write() as connection:
            row = self.row(connection, identifier)
            if row["attempt_token"] != str(token) or row["status"] not in ("running", "cancelling"):
                raise DomainError(409, "lease_lost", "The execution attempt is no longer current")
            connection.execute(
                text(
                    "UPDATE local_jobs SET heartbeat_at=:at,stage=:stage,"
                    "process_pid=coalesce(:pid,process_pid),p"
                    "rocess_start=coalesce(:start,process_start),summary_json=:summary WHERE id=:id"
                ),
                {
                    "id": str(identifier),
                    "at": now(),
                    "stage": stage or row["stage"],
                    "pid": pid,
                    "start": process_start,
                    "summary": json.dumps(
                        json.loads(row["summary_json"]) | (progress or {}), allow_nan=False
                    ),
                },
            )
            if stage and stage != row["stage"]:
                self.event(connection, str(identifier))

    def finish(
        self,
        identifier: UUID,
        token: UUID,
        status: Status,
        reason: str | None,
        message: str | None,
        summary: dict[str, Any],
        artifacts: dict[str, Artifact],
    ) -> None:
        with self.projects.write() as connection:
            row = self.row(connection, identifier)
            if row["attempt_token"] != str(token) or row["status"] not in ("running", "cancelling"):
                raise DomainError(409, "lease_lost", "A stale attempt cannot publish outputs")
            deleted = (
                connection.execute(
                    text("SELECT deleted_at,owner_id FROM projects WHERE id=:id"),
                    {"id": row["project_id"]},
                )
                .mappings()
                .one()
            )
            if (
                row["cancel_requested"]
                or deleted["deleted_at"] is not None
                or deleted["owner_id"] != row["owner_id"]
            ):
                status, reason, message = (
                    "cancelled",
                    "cancelled",
                    "Execution stopped; no validated result was published",
                )
                artifacts = {
                    name: item for name, item in artifacts.items() if name != "results.json"
                }
            if status not in TERMINAL:
                raise ValueError("Completion must be terminal")
            if status == "succeeded":
                required = {"snapshot.json", "mesh.json", "resources.json"}
                if row["kind"] == "solve":
                    required.update(
                        {
                            "analysis.inp",
                            "solver.log",
                            "analysis.dat",
                            "analysis.frd",
                            "results.json",
                        }
                    )
                else:
                    required.update({"mesh.log", "recovery.json"})
                if (
                    not required <= artifacts.keys()
                    or artifacts["snapshot.json"].sha256 != row["input_sha256"]
                ):
                    raise ValueError(
                        "Successful completion requires a complete frozen artifact manifest"
                    )
                if row["kind"] == "mesh" and summary.get("quality", {}).get("accepted") is not True:
                    raise ValueError("Successful mesh requires passing quadratic quality")
                if row["kind"] == "solve":
                    balance = summary.get("equilibrium", {})
                    if balance.get("passed") is not True or any(
                        balance.get(k, {}).get("passed") is not True for k in ("force", "moment")
                    ):
                        raise ValueError(
                            "Successful solve requires passing external "
                            "force and moment equilibrium"
                        )
            connection.execute(
                text(
                    "UPDATE local_jobs SET status=:status,stage='finished',finished_at=:at,"
                    "heartbeat_at=:at,reason_code=:reason,reason_message=:message,s"
                    "ummary_json=:summary,"
                    "artifacts_json=:artifacts,process_pid=NULL,process_start=NULL WHERE id=:id"
                ),
                {
                    "id": str(identifier),
                    "status": status,
                    "at": now(),
                    "reason": reason,
                    "message": message,
                    "summary": json.dumps(summary, allow_nan=False),
                    "artifacts": json.dumps(
                        {k: v.model_dump(mode="json") for k, v in artifacts.items()}
                    ),
                },
            )
            self.event(connection, str(identifier))

    def interrupted(self) -> list[dict[str, Any]]:
        with self.projects.database.engine.connect() as connection:
            return [
                dict(r)
                for r in connection.execute(
                    text("SELECT * FROM local_jobs WHERE status IN ('running','cancelling')")
                ).mappings()
            ]
