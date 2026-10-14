import type { components } from "../../../../packages/contracts/api";
import { useEffect, useRef, useState } from "react";
import { ResultsEditor } from "../results/ResultsEditor";
import type { ResultPresentation } from "../results/presentation";
import {
  api,
  RequestError,
  submitJob,
  type LocalJob,
  type MeshPreview,
  type UnitPreset,
} from "../geometry/api";

type Props = {
  analysisId: string;
  revision: number;
  geometryId: string;
  ready: boolean;
  meshReady: boolean;
  busy: boolean;
  setBusy: (value: boolean) => void;
  showMesh: (value: MeshPreview | null) => void;
  preset: UnitPreset;
  showResult: (value: ResultPresentation | null) => void;
};
const terminal = new Set(["succeeded", "failed", "cancelled", "interrupted"]);

export function RunsEditor({
  analysisId,
  revision,
  geometryId,
  ready,
  meshReady,
  busy,
  setBusy,
  showMesh,
  preset,
  showResult,
}: Props) {
  const [candidates, setCandidates] = useState<
    components["schemas"]["MeshCandidates"] | null
  >(null);
  const [refreshMeshes, setRefreshMeshes] = useState(0);
  const [candidateError, setCandidateError] = useState("");
  const [jobs, setJobs] = useState<LocalJob[]>([]);
  const [meshId, setMeshId] = useState("");
  const [reviewed, setReviewed] = useState(false);
  const [error, setError] = useState("");
  const [conflict, setConflict] = useState(false);
  const [status, setStatus] = useState("");
  const [worker, setWorker] = useState("");
  const [cancelling, setCancelling] = useState("");
  const [clock, setClock] = useState(Date.now());
  const requestKey = useRef<{ intent: string; key: string } | null>(null);

  useEffect(() => {
    setReviewed(false);
    setConflict(false);
    setError("");
    requestKey.current = null;
  }, [revision]);
  useEffect(() => {
    let current = true;
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const [data, control] = await Promise.all([
          api<LocalJob[]>(`/analyses/${analysisId}/jobs`),
          api<{ state: string }>("/local-worker"),
        ]);
        if (current) {
          setJobs(data);
          setWorker(control.state);
          setClock(Date.now());
        }
      } catch (e) {
        if (current) setError((e as Error).message);
      } finally {
        if (current) timer = setTimeout(() => void refresh(), 1000);
      }
    }
    void refresh();
    return () => {
      current = false;
      clearTimeout(timer);
    };
  }, [analysisId, geometryId]);

  const completedMeshes = jobs
    .filter((j) => j.kind === "mesh" && j.status === "succeeded")
    .map((j) => j.id)
    .join(",");
  useEffect(() => {
    let current = true;
    setCandidates(null);
    setCandidateError("");
    setReviewed(false);
    void api<components["schemas"]["MeshCandidates"]>(
      `/analyses/${analysisId}/compatible-meshes`,
    )
      .then((data) => {
        if (!current) return;
        if (
          data.analysis_id !== analysisId ||
          data.analysis_revision !== revision
        ) {
          setCandidateError("Mesh choices changed. Reload the saved analysis.");
          return;
        }
        setCandidates(data);
        setMeshId((old) =>
          data.items.some((item) => item.job.id === old)
            ? old
            : (data.items[0]?.job.id ?? ""),
        );
      })
      .catch((e: Error) => {
        if (current) setCandidateError(e.message);
      });
    return () => {
      current = false;
    };
  }, [analysisId, revision, geometryId, completedMeshes, refreshMeshes]);
  const meshes =
    candidates?.analysis_id === analysisId &&
    candidates.analysis_revision === revision
      ? candidates.items
      : [];
  const choice = meshes.find((item) => item.job.id === meshId);
  const selected = choice?.job;
  async function submit(solve: boolean) {
    const intent = `${revision}:${solve ? meshId : "mesh"}`;
    if (!requestKey.current || requestKey.current.intent !== intent)
      requestKey.current = { intent, key: crypto.randomUUID() };
    setBusy(true);
    setError("");
    setStatus("Submitting frozen inputs…");
    try {
      const result = await submitJob(
        `/analyses/${analysisId}/${solve ? "runs" : "mesh-jobs"}`,
        revision,
        requestKey.current.key,
        solve ? { mesh_job_id: meshId } : {},
      );
      setJobs((old) => [result, ...old.filter((j) => j.id !== result.id)]);
      setStatus(
        `${solve ? "Solve" : "Mesh"} job queued. Closing the browser keeps it active.`,
      );
      requestKey.current = null;
      setReviewed(false);
    } catch (e) {
      setConflict(e instanceof RequestError && e.code === "stale_revision");
      setError(
        (e as Error).message +
          (e instanceof RequestError && e.code === "stale_revision"
            ? " Reload the saved analysis before submitting again."
            : ""),
      );
      setStatus(
        "The request was not acknowledged. Retrying unchanged inputs uses the same request key.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function cancel(id: string) {
    setCancelling(id);
    setError("");
    try {
      const changed = await api<LocalJob>(`/jobs/${id}/cancel`, "POST", {});
      setJobs((old) => old.map((j) => (j.id === id ? changed : j)));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setCancelling("");
    }
  }
  async function preview(id = meshId) {
    try {
      showMesh(await api<MeshPreview>(`/jobs/${id}/mesh-display`));
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <section
      id="setup-runs"
      tabIndex={-1}
      className="runs-panel"
      aria-label="Local mesh and solve"
    >
      <h2>Local mesh and solve</h2>
      <p>
        One engineering job runs at a time. Inputs are frozen when submitted;
        you can keep editing. Browser closure does not cancel jobs.
      </p>
      <p>
        Quadratic C3D10 · saved global/body/face sizes and curvature · at most
        3,000 elements. Full-domain Jacobian and shape quality must pass.
        Approved recovery is at most three attempts; solving remains
        affine/planar.
      </p>
      {worker !== "ready" && worker && (
        <p aria-live="polite">
          {worker === "blocked"
            ? "Local worker stopped after a control error; restart the API and inspect local diagnostics."
            : "The local worker is waiting for the current operation to finish."}
        </p>
      )}
      <button
        disabled={busy || conflict || !meshReady || worker === "blocked"}
        onClick={() => void submit(false)}
      >
        Generate local mesh
      </button>
      <label>
        Checked mesh
        <select
          value={meshId}
          disabled={busy}
          onChange={(e) => {
            setMeshId(e.target.value);
            setReviewed(false);
            showMesh(null);
          }}
        >
          <option value="">Choose a completed mesh</option>
          {meshes.map(({ job: j, source_analysis_name }) => (
            <option key={j.id} value={j.id}>
              {source_analysis_name} · Revision {j.analysis_revision} ·{" "}
              {String(j.summary.elements)} C3D10 elements · {j.id.slice(0, 8)}
            </option>
          ))}
        </select>
      </label>
      <button
        disabled={busy}
        onClick={() => setRefreshMeshes((old) => old + 1)}
      >
        Refresh compatible meshes
      </button>
      <p>
        Only checked meshes in this project with the exact geometry, physical
        sizing and tool contract are offered. A draft or incompatible saved size
        requires a new mesh.
      </p>
      {choice && (
        <p>
          Mesh source analysis <code>{choice.job.analysis_id}</code> · revision{" "}
          {choice.job.analysis_revision}. Compatibility SHA-256{" "}
          <code>{choice.compatibility_sha256}</code> · Mesh SHA-256{" "}
          <code>{choice.mesh_sha256}</code>.
        </p>
      )}
      {candidateError && (
        <p className="material-notice" aria-live="polite">
          Compatible meshes unavailable: {candidateError}
        </p>
      )}
      <button disabled={!selected} onClick={() => void preview()}>
        Preview selected mesh
      </button>
      <button onClick={() => showMesh(null)}>Show CAD geometry</button>
      <p>
        Solve analysis revision {revision} using the selected immutable mesh.
        Material/load edits use this connectivity with a new frozen deck;
        geometry/tool changes require a new mesh.
      </p>
      <label className="check">
        <input
          type="checkbox"
          checked={reviewed}
          disabled={!selected || busy}
          onChange={(e) => setReviewed(e.target.checked)}
        />
        I reviewed the selected mesh and current small-deformation linear
        elastic inputs
      </label>
      <button
        disabled={
          busy ||
          conflict ||
          !ready ||
          !meshReady ||
          !selected ||
          !reviewed ||
          worker === "blocked"
        }
        onClick={() => void submit(true)}
      >
        Solve selected mesh
      </button>
      {error && <p role="alert">{error}</p>}
      <p aria-live="polite">{status}</p>
      <details open>
        <summary>Job history and diagnostics</summary>
        <ul aria-label="Local job history">
          {jobs.map((j) => (
            <li key={j.id} data-job-id={j.id} data-job-status={j.status}>
              <strong>
                {j.kind === "mesh" ? "Mesh" : "Solve"} · {j.status}
              </strong>{" "}
              · {j.stage} · Analysis revision {j.analysis_revision}
              <p>
                Geometry <code>{j.geometry_revision_id}</code> · Input SHA-256{" "}
                <code>{j.input_sha256}</code>
              </p>
              {!terminal.has(j.status) && (
                <>
                  <p>
                    Elapsed{" "}
                    {Math.max(
                      0,
                      Math.floor(
                        (clock - Date.parse(j.started_at ?? j.queued_at)) /
                          1000,
                      ),
                    )}{" "}
                    s
                    {j.heartbeat_at
                      ? ` · Last heartbeat ${new Date(j.heartbeat_at).toLocaleTimeString()}`
                      : " · Waiting in the durable queue"}
                  </p>
                  <button
                    disabled={cancelling === j.id || j.status === "cancelling"}
                    onClick={() => void cancel(j.id)}
                  >
                    Cancel {j.kind} job {j.id.slice(0, 8)}
                  </button>
                  {j.status === "cancelling" && (
                    <p>
                      Cancellation requested. Waiting for confirmed process
                      termination.
                    </p>
                  )}
                </>
              )}
              {j.summary.mesh_attempt != null && (
                <p>
                  Mesh attempt {String(j.summary.mesh_attempt)} of{" "}
                  {String(j.summary.max_mesh_attempts)} ·{" "}
                  {String(j.summary.mesh_profile)}
                </p>
              )}
              {Array.isArray(j.summary.mesh_attempts) && (
                <ul aria-label="Mesh recovery attempts">
                  {j.summary.mesh_attempts.map((attempt, i) =>
                    typeof attempt === "object" &&
                    attempt !== null &&
                    !Array.isArray(attempt) ? (
                      <li key={i}>
                        Attempt {String(attempt.number)}:{" "}
                        {String(attempt.profile)} — {String(attempt.status)};
                        sizing unchanged
                      </li>
                    ) : null,
                  )}
                </ul>
              )}
              {j.kind === "mesh" &&
                j.status === "failed" &&
                j.artifacts["mesh.json"] && (
                  <button onClick={() => void preview(j.id)}>
                    Inspect failed mesh quality {j.id.slice(0, 8)}
                  </button>
                )}
              {j.reason_message && (
                <p>
                  {j.reason_message} ({j.reason_code})
                </p>
              )}
              {Array.isArray(j.summary.warnings) &&
                j.summary.warnings.map((w) =>
                  typeof w === "string" ? <p key={w}>{w}</p> : null,
                )}
              {j.status === "succeeded" && (
                <p>
                  {j.kind === "mesh"
                    ? "Checked C3D10 mesh completed."
                    : "Native solve completed and raw outputs validated. Open the completed solve in Engineering results."}
                </p>
              )}
              <a href={`/api/v1/jobs/${j.id}/artifacts/snapshot.json`}>
                Download job snapshot
              </a>
              {Object.keys(j.artifacts)
                .filter((name) => name !== "snapshot.json")
                .map((name) => (
                  <span key={name}>
                    {" "}
                    ·{" "}
                    <a href={`/api/v1/jobs/${j.id}/artifacts/${name}`}>
                      Download {name}
                    </a>
                  </span>
                ))}
              {j.status !== "succeeded" && terminal.has(j.status) && (
                <p>
                  Retained raw files are diagnostics; no validated result is
                  available.
                </p>
              )}
            </li>
          ))}
        </ul>
      </details>
      <ResultsEditor
        jobs={jobs}
        analysisId={analysisId}
        revision={revision}
        preset={preset}
        showResult={showResult}
      />
    </section>
  );
}
