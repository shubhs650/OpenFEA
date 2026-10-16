"""One-at-a-time embedded local worker; durable queue independent of browsers."""

import errno
import fcntl
import hashlib
import json
import logging
import shutil
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from app.domain.deck_service import canonical, deck_for
from app.domain.errors import DomainError
from app.domain.jobs import Artifact, JobInput, LocalJob, Status
from app.domain.loads import load_state
from app.jobs.postprocess import ValidationFailure
from app.jobs.service import JobService
from app.jobs.stages import postprocess
from worker.deck_mesh import MeshFailure
from worker.limits import ARTIFACT_BYTES, DISK_RESERVE_BYTES, SCRATCH_BYTES
from worker.local_process import NativeControl, NativeStop, fence
from worker.local_solve import (
    SolverSingularity,
    check_numerical_log,
    solve_snapshot,
)
from worker.mesh_quality import mesh_quality
from worker.step_import import ImportSandboxError, scratch_usage


class LocalWorker:
    def __init__(self, service: JobService) -> None:
        self.service, self.repository, self.storage = service, service.repository, service.storage
        self.stop = threading.Event()
        self.identifier = uuid4()
        self.state = "starting"
        self.thread = threading.Thread(target=self.loop, name="local-fea-worker", daemon=True)

    def start(self) -> None:
        self.thread.start()

    def close(self) -> None:
        self.stop.set()
        self.thread.join(timeout=15)
        if self.thread.is_alive():
            raise RuntimeError("Local worker has not stopped; native lease must remain fenced")

    def recover(self) -> None:
        # Both OS locks are held here. Native children retain the execution flock
        # through Bubblewrap --sync-fd, and recorded process identity is fenced.
        for row in self.repository.interrupted():
            fence(row["process_pid"], row["process_start"])
            directory = self.storage.directory("jobs", UUID(row["id"]))
            attempt = directory / f"attempt-{row['attempt_number']}"
            if attempt.is_dir():
                directory = attempt
            paths = {
                "snapshot.json": directory / "snapshot.json",
                "analysis.inp": directory / "analysis.inp",
                "resources.json": directory / "output/resources.json",
            }
            if row["kind"] == "mesh":
                paths.update(
                    {
                        "mesh.log": directory / "output/native.log",
                        "mesh.json": directory / "output/mesh.json",
                    }
                )
            else:
                paths.update(
                    {
                        "mesh.json": directory / "mesh.json",
                        "solver.log": directory / "output/solver.log",
                        "analysis.dat": directory / "output/analysis.dat",
                        "analysis.frd": directory / "output/analysis.frd",
                    }
                )
            if row["kind"] == "mesh":
                paths["recovery.json"] = directory / "output/recovery.json"
                for number in range(1, 4):
                    paths[f"mesh-attempt-{number}.log"] = (
                        directory / f"output/attempt-{number}/native.log"
                    )
                    paths[f"mesh-attempt-{number}-resources.json"] = (
                        directory / f"output/attempt-{number}/resources.json"
                    )
            artifacts, _ = self.capture(UUID(row["project_id"]), paths, job_id=UUID(row["id"]))
            self.repository.finish(
                UUID(row["id"]),
                UUID(row["attempt_token"]),
                "interrupted",
                "worker_interrupted",
                "Execution was interrupted and fenced before recovery",
                {"warning": "Interrupted partial files are diagnostics; no validated result"},
                artifacts,
                retry=True,
            )

    def loop(self) -> None:
        recovered = False
        try:
            with (self.storage.root / "jobs-worker.lock").open("a+b") as worker_lock:
                while not self.stop.is_set():
                    try:
                        fcntl.flock(worker_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        self.state = "waiting_for_worker"
                        self.stop.wait(0.2)
                        continue
                    # An empty queue needs no native lease, including startup
                    # without interrupted attempts. Avoid racing synchronous CAD
                    # imports/deck exports merely to discover there is no work.
                    if not recovered and not self.repository.interrupted():
                        recovered = True
                    if not recovered:
                        # Holding the controller lock proves the former controller
                        # has gone. Fence its recorded process before waiting for
                        # the inherited native lock, including a stopped child.
                        for row in self.repository.interrupted():
                            fence(row["process_pid"], row["process_start"])
                    if recovered and not self.repository.pending():
                        self.state = "ready"
                        self.stop.wait(0.1)
                        continue
                    with (self.storage.root / "native-import.lock").open("a+b") as native_lock:
                        try:
                            fcntl.flock(native_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        except BlockingIOError:
                            self.state = "waiting_for_native"
                            self.stop.wait(0.2)
                            continue
                        if not recovered:
                            self.recover()
                            recovered = True
                        self.state = "ready"
                        claimed = self.repository.claim(self.identifier)
                        if claimed is not None:
                            job, token, owner = claimed
                            self.execute(job, token, owner, native_lock.fileno())
                    self.stop.wait(0.1)
        except Exception as failure:
            # Fail closed: expose no traceback/model content; do not clear a lease
            # or launch a second native process on an unknown control failure.
            self.state = "blocked"
            logging.getLogger("openfea.jobs").error(
                "local_worker_blocked: %s", type(failure).__name__
            )
        finally:
            if self.state != "blocked":
                self.state = "stopped"

    def execute(self, job: LocalJob, token: UUID, owner: UUID, lease_fd: int) -> None:
        root = self.storage.directory("jobs", job.id)
        directory = root / f"attempt-{len(job.attempts)}"
        started, last_pulse = time.monotonic(), 0.0
        remaining = (
            (job.deadline_at - datetime.now(UTC)).total_seconds() if job.deadline_at else 180
        )

        def cancel() -> bool:
            nonlocal last_pulse
            if time.monotonic() - started >= remaining or (
                job.deadline_at and datetime.now(UTC) >= job.deadline_at
            ):
                raise NativeStop("job_wall_limit")
            if scratch_usage(root) > SCRATCH_BYTES:
                raise NativeStop("resource_exceeded")
            if shutil.disk_usage(root).free < DISK_RESERVE_BYTES:
                raise NativeStop("disk_full")
            if self.stop.is_set() or self.repository.control(job.id, token):
                return True
            if time.monotonic() - last_pulse > 1:
                self.repository.pulse(job.id, token)
                last_pulse = time.monotonic()
            return False

        control = NativeControl(
            cancel,
            lambda pid, identity: self.repository.pulse(
                job.id, token, pid=pid, process_start=identity
            ),
            lease_fd,
            lambda number, profile, total: self.repository.pulse(
                job.id,
                token,
                progress={
                    "mesh_attempt": number,
                    "mesh_profile": profile,
                    "max_mesh_attempts": total,
                },
            ),
        )
        control.scratch_root = root
        previous_profile = job.summary.get("mesh_attempt", 1)
        control.mesh_profile_offset = (
            max(0, previous_profile - 1) if isinstance(previous_profile, int) else 0
        )
        status: Status = "failed"
        reason, message = None, None
        summary: dict[str, Any] = {}
        paths: dict[str, Path] = {"snapshot.json": directory / "snapshot.json"}
        try:
            directory.mkdir(mode=0o700)
            stored = self.storage.read(job.project_id, job.input_sha256)
            (directory / "snapshot.json").write_bytes(stored)
            inputs = JobInput.model_validate_json(stored)
            recorded = self.repository.inputs(owner, job.id)
            if (
                inputs != recorded
                or hashlib.sha256(canonical(inputs.model_dump(mode="json"))).hexdigest()
                != job.input_sha256
            ):
                raise ValueError("Frozen input identity differs")
            if inputs.policy != self.service.policy():
                raise DomainError(
                    409,
                    "tool_contract_changed",
                    "Native tool/source contract changed; submit a new job",
                )
            if cancel():
                raise NativeStop("cancelled")
            snapshot = inputs.snapshot
            if inputs.kind == "mesh":
                mesh = self.service.decks.mesh(snapshot, inputs.display, directory, control)
                paths.update(
                    {
                        "mesh.json": directory / "output/mesh.json",
                        "mesh.log": directory / "output/native.log",
                        "resources.json": directory / "output/resources.json",
                    }
                )
                self.repository.pulse(job.id, token, stage="validating")
                quality = mesh_quality(mesh)
                if not quality["accepted"]:
                    raise ValueError("Host quality verification refused the mesh")
                summary = {
                    "nodes": len(mesh["nodes"]),
                    "elements": len(mesh["elements"]),
                    "quality": {k: v for k, v in quality.items() if k != "cells"},
                }
                preview = load_state(
                    snapshot.analysis,
                    snapshot.geometry,
                    snapshot.materials,
                    snapshot.loads,
                    inputs.display,
                    snapshot.bonds,
                )
                if quality["all_affine"] and not preview.blockers:
                    try:
                        deck, detail = deck_for(snapshot, mesh, preview, stress_coordinates=True)
                        summary.update(detail)
                        (directory / "analysis.inp").write_text(deck)
                        paths["analysis.inp"] = directory / "analysis.inp"
                    except DomainError as error:
                        if not snapshot.bonds.assignments or error.code not in (
                            "assembly_preflight",
                            "dependent_dof_load",
                        ):
                            raise
                        summary["warnings"] = ["Mesh preview only: " + error.message]
                        summary["solve_blockers"] = [error.message]
                else:
                    summary["warnings"] = [
                        "Mesh preview only: complete setup and validated "
                        "affine/planar loads are required for solve."
                    ]
            else:
                assert inputs.mesh is not None and inputs.deck_sha256 is not None
                raw_mesh = self.storage.read(job.project_id, inputs.mesh.sha256)
                (directory / "mesh.json").write_bytes(raw_mesh)
                paths.update(
                    {
                        "mesh.json": directory / "mesh.json",
                        "analysis.inp": directory / "analysis.inp",
                        "solver.log": directory / "output/solver.log",
                        "analysis.dat": directory / "output/analysis.dat",
                        "analysis.frd": directory / "output/analysis.frd",
                        "resources.json": directory / "output/resources.json",
                    }
                )
                (directory / "analysis.inp").write_bytes(
                    self.storage.read(job.project_id, inputs.deck_sha256)
                )
                saved = self.repository.reusable(job.id, token)
                if saved is None:
                    execution = solve_snapshot(
                        directory / "analysis.inp", directory / "output", control
                    )
                else:
                    manifest, execution = saved
                    (directory / "output").mkdir(mode=0o700)
                    for name, artifact in manifest.items():
                        raw = self.storage.read(job.project_id, artifact.sha256)
                        if len(raw) != artifact.size_bytes:
                            raise DomainError(503, "artifact_integrity", "Stage checkpoint differs")
                        (directory / "output" / name).write_bytes(raw)
                    summary["reused_stage"] = "solving"
                check_numerical_log((directory / "output/solver.log").read_text(errors="replace"))
                if execution["returncode"] != 0:
                    raise ImportSandboxError("Native solver exited with an error")
                self.repository.pulse(job.id, token, stage="validating")
                for name in ("solver.log", "analysis.dat", "analysis.frd"):
                    self.storage.read_fixed(paths[name])
                if saved is None:
                    manifest, intact = self.capture(
                        job.project_id,
                        {
                            name: paths[name]
                            for name in (
                                "solver.log",
                                "analysis.dat",
                                "analysis.frd",
                                "resources.json",
                            )
                        },
                        required=True,
                        job_id=job.id,
                    )
                    if not intact:
                        raise DomainError(
                            503, "artifact_integrity", "Raw solver checkpoint is incomplete"
                        )
                    self.repository.checkpoint(job.id, token, manifest, execution)
                paths["validation-resources.json"] = directory / "validation/resources.json"
                result, parsed = postprocess(
                    directory, inputs, job.input_sha256, execution, control
                )
                summary.update(parsed)
                (directory / "assembly.json").write_bytes(canonical(result["assembly"]))
                paths["assembly.json"] = directory / "assembly.json"
                (directory / "results.json").write_bytes(canonical(result))
                paths["results.json"] = directory / "results.json"
            if cancel():
                raise NativeStop("cancelled")
            warnings = summary.get("warnings", [])
            if not isinstance(warnings, list):
                raise ValueError("Invalid warning manifest")
            summary["warnings"] = list(dict.fromkeys([*inputs.warnings, *warnings]))
            status = "succeeded"
        except NativeStop as error:
            status = (
                "interrupted"
                if self.stop.is_set() or error.reason == "parser_interrupted"
                else "cancelled"
                if error.reason == "cancelled"
                else "failed"
            )
            reason = "worker_shutdown" if self.stop.is_set() else error.reason
            message = "Native execution stopped; no validated result was published"
        except SolverSingularity as error:
            reason, message = "solver_singular", str(error)
        except ValidationFailure as error:
            reason, message, summary = error.code, error.message, summary | error.summary
        except DomainError as error:
            reason, message = error.code, error.message
            if error.code == "lease_lost":
                status = "interrupted"
        except MeshFailure as error:
            reason, message, summary = error.reason, str(error), error.summary
        except ImportSandboxError:
            reason, message = (
                "native_failed",
                "Isolated native execution failed; inspect the private diagnostic log",
            )
        except (ValueError, KeyError, TypeError, AssertionError):
            reason, message = (
                "invalid_output",
                "Native execution or outputs failed validation; no result was published",
            )
        except OSError as error:
            reason = "disk_full" if error.errno == errno.ENOSPC else "worker_failed"
            message = "Local execution or artifact storage failed"
        except RuntimeError:
            reason, message = "worker_failed", "Local execution or artifact storage failed"
        if status != "succeeded":
            paths.pop("results.json", None)
        # Keep bounded raw failure/cancellation transcripts, never credit them as results.
        if job.kind == "mesh":
            paths.update(
                {
                    "mesh.log": directory / "output/native.log",
                    "resources.json": directory / "output/resources.json",
                    "mesh.json": directory / "output/mesh.json",
                    "recovery.json": directory / "output/recovery.json",
                    **{
                        f"mesh-attempt-{n}.log": directory / f"output/mesh-attempt-{n}.log"
                        for n in range(1, 4)
                    },
                    **{
                        f"mesh-attempt-{n}-resources.json": directory
                        / f"output/mesh-attempt-{n}-resources.json"
                        for n in range(1, 4)
                    },
                }
            )
            report = directory / "output/recovery.json"
            if report.is_file() and not report.is_symlink():
                summary.update(json.loads(self.storage.read_fixed(report)))
        paths = {
            name: path
            for name, path in paths.items()
            if not name.startswith("mesh-attempt-") or path.exists()
        }
        artifacts, integrity = self.capture(
            job.project_id, paths, required=status == "succeeded", job_id=job.id
        )
        if not integrity and reason != "disk_full":
            status, reason, message = (
                "failed",
                "artifact_integrity",
                "Job outputs could not be retained and verified",
            )
            artifacts.pop("results.json", None)
        summary["attempt_wall_seconds"] = time.monotonic() - started
        summary["wall_seconds"] = (
            datetime.now(UTC) - (job.started_at or datetime.now(UTC))
        ).total_seconds()
        try:
            self.repository.finish(
                job.id,
                token,
                status,
                reason,
                message,
                summary,
                artifacts,
                retry=status == "interrupted",
            )
        except DomainError as error:
            if error.code != "lease_lost":
                raise
            # Native groups have already exited. If storage work outlasted the
            # heartbeat, record interruption rather than publishing stale success.
            # A genuinely superseded token is refused by this transaction too.
            artifacts.pop("results.json", None)
            self.repository.finish(
                job.id,
                token,
                "interrupted",
                "lease_lost",
                "Execution heartbeat expired before publication",
                summary,
                artifacts,
                retry=True,
            )

    def capture(
        self,
        project: UUID,
        paths: dict[str, Path],
        *,
        required: bool = False,
        job_id: UUID | None = None,
    ) -> tuple[dict[str, Artifact], bool]:
        artifacts: dict[str, Artifact] = {}
        integrity = True
        retained = self.repository.retained(job_id) if job_id else {}
        for name, path in paths.items():
            if not path.exists():
                if required:
                    integrity = False
                continue
            try:
                raw = self.storage.read_fixed(path)
                digest = hashlib.sha256(raw).hexdigest()
                if digest not in retained and sum(retained.values()) + len(raw) > ARTIFACT_BYTES:
                    integrity = False
                    continue
                self.storage.save(project, path, digest)
                retained[digest] = len(raw)
                artifacts[name] = Artifact(
                    sha256=digest,
                    size_bytes=len(raw),
                    media_type="application/json" if name.endswith(".json") else "text/plain",
                )
            except (DomainError, OSError):
                integrity = False
        return artifacts, integrity
