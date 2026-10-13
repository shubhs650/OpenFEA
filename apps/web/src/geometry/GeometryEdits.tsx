import { useEffect, useState } from "react";
import {
  api,
  mutate,
  type Analysis,
  type Display,
  type Geometry,
  type Project,
} from "./api";
import type { components } from "../../../../packages/contracts/api";
type Edit = components["schemas"]["GeometryEdit"];
type EditResult = components["schemas"]["EditResult"];
type Props = {
  project: Project;
  geometry: Geometry;
  analysisId: string;
  selected: Set<string>;
  busy: boolean;
  setBusy: (busy: boolean) => void;
  showPreview: (display: Display | null, highlights?: Set<string>) => void;
  applied: (result: EditResult) => void;
};

export function GeometryEdits({
  project,
  geometry,
  analysisId,
  selected,
  busy,
  setBusy,
  showPreview,
  applied,
}: Props) {
  const [edit, setEdit] = useState<Edit | null>(null);
  const [previewDisplay, setPreviewDisplay] = useState<Display | null>(null);
  const [command, setCommand] = useState<Edit | null>(null);
  const [reviewed, setReviewed] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [showingAfter, setShowingAfter] = useState(false);
  useEffect(() => {
    setEdit(null);
    setPreviewDisplay(null);
    setReviewed(false);
    setShowingAfter(false);
    showPreview(null);
  }, [geometry.id, analysisId]);

  function after(data: Display, current: Edit) {
    const unchanged = new Set(
      current.preview?.mappings
        .filter((m) => m.status === "unchanged")
        .map((m) => m.target_face_id),
    );
    showPreview(
      data,
      new Set(data.faces.filter((f) => !unchanged.has(f.id)).map((f) => f.id)),
    );
    setShowingAfter(true);
  }
  async function preview() {
    setBusy(true);
    setError("");
    setStatus("Creating cleanup preview…");
    showPreview(null);
    setEdit(null);
    setReviewed(false);
    setPreviewDisplay(null);
    try {
      const analysis = analysisId
        ? await api<Analysis>(`/analyses/${analysisId}`)
        : null;
      const current = await mutate<Edit>(
        `/geometry/${geometry.id}/edits`,
        project.revision,
        {
          operation: "remove_feature",
          face_id: [...selected][0],
          ...(analysis
            ? { analysis_id: analysis.id, analysis_revision: analysis.revision }
            : {}),
        },
      );
      setEdit(current);
      if (current.status !== "ready") {
        setError(current.error ?? "Cleanup failed. Original retained.");
        setStatus("Original geometry retained.");
      } else {
        const data = await api<Display>(
          `/geometry-edits/${current.id}/display`,
        );
        setPreviewDisplay(data);
        after(data, current);
        setStatus("Preview only. Original geometry and setup are still saved.");
      }
    } catch (e) {
      setError((e as Error).message);
      setStatus(
        "Preview was not saved. Reload the project or analysis after a revision conflict.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function apply() {
    if (!edit || !reviewed) return;
    setBusy(true);
    setError("");
    try {
      const result = await mutate<EditResult>(
        `/geometry/${edit.source_geometry_id}/edit-commits`,
        edit.project_revision,
        { preview_id: edit.id, reviewed: true },
      );
      setCommand(edit);
      showPreview(null);
      applied(result);
      setStatus(
        "Cleanup applied. Mesh must be regenerated; changed face assignments need review.",
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function undo() {
    if (!command) return;
    setBusy(true);
    setError("");
    try {
      const result = await mutate<EditResult>(
        `/geometry-edits/${command.id}/undo`,
        project.revision,
      );
      showPreview(null);
      applied(result);
      setCommand(null);
      setStatus(
        "Cleanup undone in a new saved revision. Original geometry and setup restored.",
      );
    } catch (e) {
      setError(
        (e as Error).message +
          " Undo requires the unchanged applied geometry and analysis; later edits must not be overwritten.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel geometry-edits" aria-label="Geometry cleanup">
      <h2>Geometry cleanup</h2>
      <p>
        Supported: the validated unit-solid through-hole and straight-edge
        fillet. Select one cylindrical feature face. Other features and
        automatic repair are unavailable; an unsupported edit retains the
        original.
      </p>
      <button
        disabled={busy || selected.size !== 1 || !!edit?.preview}
        onClick={() => void preview()}
      >
        Preview feature removal
      </button>
      {edit?.status === "ready" && edit.preview && previewDisplay && (
        <>
          <p>
            Before: {edit.preview.original_volume_m3.toPrecision(10)} m³ ·
            After: {edit.preview.preview_volume_m3.toPrecision(10)} m³ · Volume
            change: {edit.preview.volume_delta_m3.toPrecision(10)} m³
          </p>
          <p>
            {showingAfter
              ? "After preview: modified faces highlighted."
              : "Before: affected original faces highlighted."}{" "}
            Applying clears the mesh preview. Completed runs retain their frozen
            geometry and results.
          </p>
          <button
            disabled={busy}
            onClick={() => {
              showPreview(
                null,
                new Set(
                  edit
                    .preview!.mappings.filter((m) => m.status !== "unchanged")
                    .map((m) => m.source_face_id),
                ),
              );
              setShowingAfter(false);
            }}
          >
            Show before cleanup
          </button>
          <button disabled={busy} onClick={() => after(previewDisplay, edit)}>
            Show cleanup preview
          </button>
          <ul aria-label="Face mapping review">
            {edit.preview.mappings.map((m) => (
              <li key={m.source_face_id}>
                <code>{m.source_face_id.split(":").slice(-2).join(" ")}</code>:{" "}
                {m.status === "unchanged"
                  ? "unchanged — verified mapping"
                  : "needs review — " + m.status}
              </li>
            ))}
          </ul>
          <label className="check">
            <input
              type="checkbox"
              checked={reviewed}
              disabled={busy}
              onChange={(e) => setReviewed(e.target.checked)}
            />
            I reviewed the geometry difference and face assignment invalidation
          </label>
          <button disabled={busy || !reviewed} onClick={() => void apply()}>
            Apply cleanup
          </button>
        </>
      )}
      {edit && (
        <button
          disabled={busy}
          onClick={() => {
            setEdit(null);
            setPreviewDisplay(null);
            setReviewed(false);
            showPreview(null);
            setStatus("Preview cancelled. Original geometry retained.");
          }}
        >
          Cancel cleanup preview
        </button>
      )}
      {command && (
        <button
          disabled={
            busy ||
            !!edit?.preview ||
            (command.request.analysis_id ?? "") !== analysisId
          }
          onClick={() => void undo()}
        >
          Undo applied cleanup
        </button>
      )}
      {error && <p role="alert">{error}</p>}
      <p aria-live="polite">{status}</p>
    </section>
  );
}
