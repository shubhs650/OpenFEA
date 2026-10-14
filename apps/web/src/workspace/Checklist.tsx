import { useEffect, useState } from "react";
import type { components } from "../../../../packages/contracts/api";
import {
  api,
  type LoadState,
  type MaterialState,
  type LocalJob,
} from "../geometry/api";
import { useEdits } from "./edits";

type Data = {
  materials: MaterialState;
  loads: LoadState;
  mesh: components["schemas"]["MeshState"];
  jobs: LocalJob[];
};
export function Checklist({
  analysisId,
  geometryId,
}: {
  analysisId: string;
  geometryId?: string;
}) {
  const edits = useEdits();
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let current = true;
    setData(null);
    setError("");
    if (analysisId && edits.revision)
      void Promise.all([
        api<MaterialState>(`/analyses/${analysisId}/materials`),
        api<LoadState>(`/analyses/${analysisId}/loads`),
        api<components["schemas"]["MeshState"]>(
          `/analyses/${analysisId}/mesh-controls`,
        ),
      ])
        .then(([materials, loads, mesh]) => {
          if (current) setData({ materials, loads, mesh, jobs: [] });
        })
        .catch((e: Error) => {
          if (current) setError(e.message);
        });
    return () => {
      current = false;
    };
  }, [analysisId, edits.revision, geometryId]);
  useEffect(() => {
    let current = true;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const jobs = await api<LocalJob[]>(`/analyses/${analysisId}/jobs`);
        if (current) setData((old) => (old ? { ...old, jobs } : old));
      } catch (e) {
        if (current) setError((e as Error).message);
      } finally {
        if (current) timer = setTimeout(() => void poll(), 1500);
      }
    }
    if (analysisId) void poll();
    return () => {
      current = false;
      clearTimeout(timer);
    };
  }, [analysisId, edits.revision]);
  const aligned =
    data &&
    data.materials.analysis_revision === edits.revision &&
    data.loads.analysis_revision === edits.revision &&
    data.mesh.analysis_revision === edits.revision;
  const materialMissing = aligned
    ? data.materials.bodies.filter(
        (b) =>
          !data.materials.setup.assignments?.some(
            (a) => a.body_id === b.body_id,
          ),
      ).length
    : 0;
  const currentJobs = aligned
    ? data.jobs.filter(
        (j) =>
          j.analysis_revision === edits.revision &&
          j.geometry_revision_id === geometryId,
      )
    : [];
  const meshDone = currentJobs.some(
    (j) => j.kind === "mesh" && j.status === "succeeded",
  );
  const solveDone = currentJobs.some(
    (j) => j.kind === "solve" && j.status === "succeeded",
  );
  const activeJob = currentJobs.find((j) =>
    ["queued", "running", "cancelling"].includes(j.status),
  );
  const failed = currentJobs.find((j) =>
    ["failed", "interrupted", "cancelled"].includes(j.status),
  );
  const rows = [
    {
      label: "Geometry",
      target: "setup-geometry",
      state: geometryId ? "Complete" : "Not started",
      action: geometryId
        ? "Accepted immutable geometry. Revisit import or cleanup."
        : "Create/open a project, import STEP and confirm dimensions.",
    },
    {
      label: "Materials",
      target: "setup-materials",
      state: !analysisId
        ? "Not started"
        : !aligned
          ? "Needs attention"
          : materialMissing
            ? "Needs attention"
            : "Complete",
      action: !analysisId
        ? "Create an analysis for accepted geometry."
        : !aligned
          ? "Load or reload the saved analysis."
          : materialMissing
            ? `Assign and confirm material for ${materialMissing} bodies.`
            : "Confirmed materials saved. Review density/yield prerequisites in the editor.",
    },
    {
      label: "Supports and loads",
      target: "setup-loads",
      state:
        aligned && !data.loads.blockers.length ? "Ready" : "Needs attention",
      action: aligned
        ? data.loads.blockers.join(" ") ||
          "Saved setup passes preflight. Native mesh/solve checks still apply."
        : "Select an analysis to inspect engineering blockers.",
    },
    {
      label: "Mesh",
      target: "setup-mesh",
      state: meshDone
        ? "Complete"
        : aligned && !data.mesh.blockers.length
          ? "Ready"
          : "Needs attention",
      action: aligned
        ? data.mesh.blockers.join(" ") ||
          (meshDone
            ? "Checked mesh completed for this revision."
            : "Review sizes, save drafts and generate a checked mesh.")
        : "Select an analysis to configure sizing.",
    },
    {
      label: "Runs and results",
      target: "setup-runs",
      state: solveDone
        ? "Complete"
        : activeJob
          ? "Needs attention"
          : "Not started",
      action: solveDone
        ? "Open the completed frozen result in Engineering results."
        : activeJob
          ? `${activeJob.kind}: ${activeJob.status} · ${activeJob.stage}. Expand job history for details.`
          : failed
            ? `${failed.kind} ${failed.status}: ${failed.reason_message ?? "Inspect diagnostics and revise setup."}`
            : "Resolve setup blockers, review a checked mesh, then solve. Earlier runs retain their frozen revisions.",
    },
  ];
  return (
    <nav className="checklist" aria-label="Model checklist">
      <h2>Model checklist</h2>
      <p>Edit any valid step; statuses describe acknowledged setup.</p>
      {edits.dirty.length > 0 && (
        <p>Drafts are unsaved; checklist describes the saved revision.</p>
      )}
      <ol>
        {rows.map((row) => (
          <li key={row.label}>
            <button
              onClick={() => {
                const target = document.getElementById(row.target);
                target?.scrollIntoView({ behavior: "smooth", block: "start" });
                target?.focus({ preventScroll: true });
              }}
            >
              {row.label} — {row.state}
            </button>
            <small>{row.action}</small>
          </li>
        ))}
      </ol>
      {error && (
        <p role="alert">
          Checklist unavailable: {error} Reload the saved workspace.
        </p>
      )}
    </nav>
  );
}
