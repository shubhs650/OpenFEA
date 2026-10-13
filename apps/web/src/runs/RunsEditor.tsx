import { useEffect, useRef, useState } from "react";
import {
  api,
  RequestError,
  submitJob,
  type LocalJob,
  type MeshPreview,
} from "../geometry/api";

type Props = {
  analysisId: string;
  revision: number;
  geometryId: string;
  ready: boolean;
  busy: boolean;
  setBusy: (value: boolean) => void;
  showMesh: (value: MeshPreview | null) => void;
};
const terminal = new Set(["succeeded", "failed", "cancelled", "interrupted"]);

export function RunsEditor({
  analysisId,
  revision,
  geometryId,
  ready,
  busy,
  setBusy,
  showMesh,
}: Props) {
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
          setMeshId((old) =>
            data.some((j) => j.id === old && j.kind === "mesh")
              ? old
              : (data.find(
                  (j) =>
                    j.kind === "mesh" &&
                    j.status === "succeeded" &&
                    j.geometry_revision_id === geometryId,
                )?.id ?? ""),
          );
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

  const meshes = jobs.filter(
    (j) =>
      j.kind === "mesh" &&
      j.status === "succeeded" &&
      j.geometry_revision_id === geometryId,
  );
  const selected = meshes.find((j) => j.id === meshId);
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
  async function preview() {
    try {
      showMesh(await api<MeshPreview>(`/jobs/${meshId}/mesh-display`));
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <section className="runs-panel" aria-label="Local mesh and solve">
      <h2>Local mesh and solve</h2>
      <p>
        One engineering job runs at a time. Inputs are frozen when submitted;
        you can keep editing. Browser closure does not cancel jobs.
      </p>
      <p>
        Coarse planar affine C3D10 only · largest body extent / 2 · at most
        3,000 elements · 60 seconds per native stage. Meshing recovery and local
        sizing follow later.
      </p>
      {worker !== "ready" && worker && (
        <p aria-live="polite">
          {worker === "blocked"
            ? "Local worker stopped after a control error; restart the API and inspect local diagnostics."
            : "The local worker is waiting for the current operation to finish."}
        </p>
      )}
      <button
        disabled={busy || conflict || !ready || worker === "blocked"}
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
          {meshes.map((j) => (
            <option key={j.id} value={j.id}>
              Revision {j.analysis_revision} · {String(j.summary.elements)}{" "}
              C3D10 elements · {j.id.slice(0, 8)}
            </option>
          ))}
        </select>
      </label>
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
                      (clock - Date.parse(j.started_at ?? j.queued_at)) / 1000,
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
            {j.reason_message && (
              <p>
                {j.reason_message} ({j.reason_code})
              </p>
            )}
            {j.status === "succeeded" && (
              <p>
                {j.kind === "mesh"
                  ? "Checked C3D10 mesh completed."
                  : "Native solve completed and raw outputs validated. Engineering result views follow later."}
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
    </section>
  );
}
