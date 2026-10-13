"""One-at-a-time embedded local worker; durable queue independent of browsers."""

import fcntl
import hashlib
import json
import logging
import threading
import time
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from app.domain.deck_service import canonical, deck_for
from app.domain.errors import DomainError
from app.domain.jobs import Artifact, JobInput, LocalJob, Status
from app.domain.loads import load_state
from app.jobs.service import JobService
from worker.local_process import NativeControl, NativeStop, fence
from worker.local_solve import solve_snapshot, validate_outputs
from worker.step_import import ImportSandboxError


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
            artifacts, _ = self.capture(UUID(row["project_id"]), paths)
            self.repository.finish(
                UUID(row["id"]),
                UUID(row["attempt_token"]),
                "interrupted",
                "worker_interrupted",
                "Execution was interrupted; it was not automatically retried",
                {"warning": "Interrupted partial files are diagnostics; no validated result"},
                artifacts,
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
        directory = self.storage.directory("jobs", job.id)
        started, last_pulse = time.monotonic(), 0.0

        def cancel() -> bool:
            nonlocal last_pulse
            if time.monotonic() - started > 180:
                raise NativeStop("job_wall_limit")
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
        )
        status: Status = "failed"
        reason, message = None, None
        summary: dict[str, Any] = {}
        paths: dict[str, Path] = {"snapshot.json": directory / "snapshot.json"}
        try:
            stored = self.storage.read(job.project_id, job.input_sha256)
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
                preview = load_state(
                    snapshot.analysis,
                    snapshot.geometry,
                    snapshot.materials,
                    snapshot.loads,
                    inputs.display,
                )
                deck, summary = deck_for(snapshot, mesh, preview, stress_coordinates=True)
                (directory / "analysis.inp").write_text(deck)
                paths["analysis.inp"] = directory / "analysis.inp"
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
                execution = solve_snapshot(
                    directory / "analysis.inp", directory / "output", control
                )
                if execution["returncode"] != 0:
                    raise ImportSandboxError("Native solver exited with an error")
                self.repository.pulse(job.id, token, stage="validating")
                for name in ("solver.log", "analysis.dat", "analysis.frd"):
                    self.storage.read_fixed(paths[name])
                materials = {body.id: f"M{i}" for i, body in enumerate(snapshot.geometry.bodies, 1)}
                result, summary = validate_outputs(
                    directory / "output",
                    json.loads(raw_mesh),
                    materials,
                    execution,
                    job.input_sha256,
                    inputs.deck_sha256,
                    inputs.mesh.sha256,
                )
                summary["warnings"] = list(dict.fromkeys([*inputs.warnings, *summary["warnings"]]))
                result["warnings"] = summary["warnings"]
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
                if self.stop.is_set()
                else "cancelled"
                if error.reason == "cancelled"
                else "failed"
            )
            reason = "worker_shutdown" if self.stop.is_set() else error.reason
            message = "Native execution stopped; no validated result was published"
        except DomainError as error:
            reason, message = error.code, error.message
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
        except (OSError, RuntimeError):
            reason, message = "worker_failed", "Local execution or artifact storage failed"
        if status != "succeeded":
            paths.pop("results.json", None)
        # Keep bounded raw failure/cancellation transcripts, never credit them as results.
        if job.kind == "mesh":
            paths.update(
                {
                    "mesh.log": directory / "output/native.log",
                    "resources.json": directory / "output/resources.json",
                }
            )
        artifacts, integrity = self.capture(job.project_id, paths, required=status == "succeeded")
        if not integrity:
            status, reason, message = (
                "failed",
                "artifact_integrity",
                "Job outputs could not be retained and verified",
            )
            artifacts.pop("results.json", None)
        summary["wall_seconds"] = time.monotonic() - started
        self.repository.finish(job.id, token, status, reason, message, summary, artifacts)

    def capture(
        self, project: UUID, paths: dict[str, Path], *, required: bool = False
    ) -> tuple[dict[str, Artifact], bool]:
        artifacts: dict[str, Artifact] = {}
        integrity = True
        for name, path in paths.items():
            if not path.exists():
                if required:
                    integrity = False
                continue
            try:
                raw = self.storage.read_fixed(path)
                digest = hashlib.sha256(raw).hexdigest()
                self.storage.save(project, path, digest)
                artifacts[name] = Artifact(
                    sha256=digest,
                    size_bytes=len(raw),
                    media_type="application/json" if name.endswith(".json") else "text/plain",
                )
            except (DomainError, OSError):
                integrity = False
        return artifacts, integrity
