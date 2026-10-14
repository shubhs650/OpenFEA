import { useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  mutate,
  session,
  upload,
  type Display,
  type Geometry,
  type Inspection,
  type Project,
  type Upload,
  type LoadState,
  type MeshPreview,
} from "./api";
import { GeometryEdits } from "./GeometryEdits";
import { Viewport } from "./Viewport";
import type { DraftDirection } from "../loads/DirectionEditor";
import { MaterialsEditor } from "../materials/MaterialsEditor";
import { ResultViewport } from "../results/ResultViewport";
import type { ResultPresentation } from "../results/presentation";

type Page<T> = { items: T[]; total: number };

export function Workspace() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [project, setProject] = useState<Project | null>(null);
  const [analysisId, setAnalysisId] = useState("");
  const [loadPreview, setLoadPreview] = useState<LoadState | null>(null);
  const [draftDirections, setDraftDirections] = useState<DraftDirection[]>([]);
  const [editDisplay, setEditDisplay] = useState<Display | null>(null);
  const [editHighlights, setEditHighlights] = useState<Set<string> | null>(
    null,
  );
  const [qualityOverlay, setQualityOverlay] = useState(false);
  const [editorEpoch, setEditorEpoch] = useState(0);
  const [editingPreview, setEditingPreview] = useState(false);
  const [meshPreview, setMeshPreview] = useState<MeshPreview | null>(null);
  const [resultPresentation, setResultPresentation] =
    useState<ResultPresentation | null>(null);
  const [name, setName] = useState("");
  const [geometry, setGeometry] = useState<Geometry | null>(null);
  const [latestGeometry, setLatestGeometry] = useState<Geometry | null>(null);
  const [display, setDisplay] = useState<Display | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [ticket, setTicket] = useState<Upload | null>(null);
  const [inspection, setInspection] = useState<Inspection | null>(null);
  const [unit, setUnit] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [lod, setLod] = useState<"coarse" | "fine">("coarse");
  const [selected, setSelected] = useState(new Set<string>());
  const [visible, setVisible] = useState(new Set<string>());
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState("");
  const [error, setError] = useState("");
  const displayedRevision = useRef<string | null>(null);

  useEffect(() => {
    let current = true;
    void session()
      .then(() => api<Page<Project>>("/projects"))
      .then((page) => {
        if (current) {
          setProjects(page.items);
          setReady(true);
        }
      })
      .catch((e: Error) => {
        if (current) setError(e.message);
      });
    return () => {
      current = false;
    };
  }, []);

  useEffect(() => {
    let current = true;
    setSelected(new Set());
    setEditDisplay(null);
    setEditHighlights(null);
    setEditingPreview(false);
    setAnalysisId("");
    setDraftDirections([]);
    displayedRevision.current = null;
    setGeometry(null);
    setLatestGeometry(null);
    setInspection(null);
    setTicket(null);
    setDisplay(null);
    if (project)
      void api<Page<Geometry>>(`/projects/${project.id}/geometry?limit=1`)
        .then(async (page) => {
          const last =
            page.total > 1
              ? await api<Page<Geometry>>(
                  `/projects/${project.id}/geometry?limit=1&offset=${page.total - 1}`,
                )
              : page;
          if (current) {
            setGeometry(last.items[0] ?? null);
            setLatestGeometry(last.items[0] ?? null);
          }
        })
        .catch((e: Error) => {
          if (current) setError(e.message);
        });
    return () => {
      current = false;
    };
  }, [project?.id]);

  useEffect(() => {
    let current = true;
    if (geometry)
      void api<Display>(`/geometry/${geometry.id}/display?lod=${lod}`)
        .then((data) => {
          if (current) {
            setDisplay(data);
            if (displayedRevision.current !== geometry.id) {
              setVisible(new Set(data.bodies.map((b) => b.id)));
              displayedRevision.current = geometry.id;
            }
          }
        })
        .catch((e: Error) => {
          if (current) setError(e.message);
        });
    return () => {
      current = false;
    };
  }, [geometry, lod]);

  function toggle(face: string) {
    if (editingPreview || busy) return;
    setSelected((previous) => {
      const next = new Set(previous);
      if (next.has(face)) next.delete(face);
      else next.add(face);
      return next;
    });
  }
  async function createProject() {
    if (!ready) return;
    setBusy(true);
    setError("");
    try {
      const created = await api<Project>("/projects", "POST", { name });
      setProjects((previous) => [...previous, created]);
      setProject(created);
      setName("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function inspect(selectedUnit?: string) {
    if (!project || !file) return;
    setBusy(true);
    setError("");
    setConfirmed(false);
    try {
      let source = ticket;
      if (!source) {
        setStage("Uploading STEP…");
        source = await upload(project, file, (percent) =>
          setStage(`Uploading STEP: ${percent}%`),
        );
        setTicket(source);
      }
      setStage("Inspecting solid geometry…");
      const result = await mutate<Inspection>(
        `/projects/${project.id}/geometry-imports`,
        project.revision,
        {
          upload_id: source.id,
          ...(selectedUnit ? { source_length_unit: selectedUnit } : {}),
        },
      );
      setInspection(result);
      setStage(
        result.status === "ready"
          ? "Review units, dimensions and body count."
          : result.status === "needs_units"
            ? "Choose the missing source length unit."
            : "Import failed. Existing geometry is unchanged.",
      );
      if (result.status === "failed")
        setError(result.error_message ?? "Geometry import failed.");
    } catch (e) {
      setError((e as Error).message);
      setStage("");
    } finally {
      setBusy(false);
    }
  }
  async function accept() {
    if (!inspection || !project || !confirmed) return;
    setBusy(true);
    setError("");
    try {
      const result = await mutate<Geometry>(
        `/geometry-imports/${inspection.id}/confirm`,
        project.revision,
        { dimensions_confirmed: true },
      );
      const updated = await api<Project>(`/projects/${project.id}`);
      setProject(updated);
      setProjects((all) => all.map((p) => (p.id === updated.id ? updated : p)));
      setSelected(new Set());
      setAnalysisId("");
      setVisible(new Set(result.bodies.map((b) => b.id)));
      setGeometry(result);
      setLatestGeometry(result);
      setInspection(null);
      setTicket(null);
      setFile(null);
      setStage("Geometry accepted and saved.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const details = inspection?.inspection;
  const shown =
    geometry?.project_id === project?.id &&
    display?.brep_sha256 === geometry?.brep_sha256
      ? display
      : null;
  const activeMesh =
    meshPreview?.analysis_id === analysisId &&
    meshPreview.geometry_revision_id === geometry?.id
      ? meshPreview
      : null;
  const activeResult =
    resultPresentation?.view.analysis_id === analysisId
      ? resultPresentation
      : null;
  const qualityColors = useMemo(() => {
    const colors: Record<string, [number, number, number]> = {};
    for (const face of activeMesh?.quality_display?.faces ?? []) {
      colors[face.id] = face.id.endsWith(":failed")
        ? [0.9, 0.12, 0.1]
        : face.id.endsWith(":warning")
          ? [0.95, 0.6, 0.1]
          : [0.2, 0.65, 0.4];
    }
    return colors;
  }, [activeMesh]);
  const previewVisible = useMemo(
    () =>
      editDisplay ? new Set(editDisplay.bodies.map((b) => b.id)) : visible,
    [editDisplay, visible],
  );
  const resultVisible = useMemo(
    () =>
      activeResult && activeResult.view.geometry_revision_id !== geometry?.id
        ? new Set(activeResult.view.data.vertices.map((v) => v.body_id))
        : visible,
    [activeResult, geometry?.id, visible],
  );
  return (
    <div className="workspace">
      <aside className="panel">
        <h2>Project</h2>
        <label>
          Open project
          <select
            disabled={!ready || busy}
            value={project?.id ?? ""}
            onChange={(e) => {
              setVisible(new Set());
              setProject(projects.find((p) => p.id === e.target.value) ?? null);
              setError("");
            }}
          >
            <option value="">Choose a project</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          New project name
          <input
            value={name}
            maxLength={200}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <button
          disabled={!ready || busy || !name.trim()}
          onClick={() => void createProject()}
        >
          Create project
        </button>
        {project && (
          <>
            <h2>Import geometry</h2>
            <label>
              STEP file
              <input
                type="file"
                accept=".step,.stp"
                disabled={busy}
                onChange={(e) => {
                  setFile(e.target.files?.[0] ?? null);
                  setTicket(null);
                  setInspection(null);
                  setUnit("");
                  setConfirmed(false);
                  setError("");
                }}
              />
            </label>
            <small>Solid STEP · 1–10 bodies · Up to 16 MiB</small>
            <button disabled={busy || !file} onClick={() => void inspect()}>
              Upload and inspect
            </button>
            {inspection?.status === "needs_units" && (
              <>
                <label>
                  Source length units
                  <select
                    value={unit}
                    onChange={(e) => setUnit(e.target.value)}
                  >
                    <option value="">Choose units</option>
                    <option value="mm">Millimetres (mm)</option>
                    <option value="m">Metres (m)</option>
                    <option value="inch">Inches (inch)</option>
                  </select>
                </label>
                <button
                  disabled={busy || !unit}
                  onClick={() => void inspect(unit)}
                >
                  Inspect with selected units
                </button>
              </>
            )}
            {inspection?.status === "ready" && details && (
              <div className="confirmation">
                <p>
                  Source units: <strong>{details.source_length_unit}</strong>
                </p>
                <p>
                  {details.body_count} solid bodies · {details.face_count} faces
                </p>
                {details.bounds_m && (
                  <p>
                    Size in metres:{" "}
                    <strong>
                      {[0, 1, 2]
                        .map((i) =>
                          (
                            details.bounds_m![i + 3] - details.bounds_m![i]
                          ).toPrecision(6),
                        )
                        .join(" × ")}
                    </strong>
                  </p>
                )}
                {(details.warnings ?? []).map((warning) => (
                  <p key={warning}>{warning}</p>
                ))}
                <label className="check">
                  <input
                    type="checkbox"
                    checked={confirmed}
                    onChange={(e) => setConfirmed(e.target.checked)}
                  />
                  I confirm the dimensions and body count
                </label>
                <button
                  disabled={busy || !confirmed}
                  onClick={() => void accept()}
                >
                  Accept geometry
                </button>
              </div>
            )}
          </>
        )}
        <p aria-live="polite">{stage}</p>
        {error && <p role="alert">{error}</p>}
        {shown && (
          <>
            <h2>Bodies and faces</h2>
            <button
              onClick={() => setVisible(new Set(shown.bodies.map((b) => b.id)))}
            >
              Show all bodies
            </button>
            {shown.bodies.map((body, index) => (
              <section className="body-tree" key={body.id}>
                <label className="check">
                  <input
                    type="checkbox"
                    checked={visible.has(body.id)}
                    onChange={(e) =>
                      setVisible((old) => {
                        const next = new Set(old);
                        if (e.target.checked) next.add(body.id);
                        else next.delete(body.id);
                        return next;
                      })
                    }
                  />
                  Body {index + 1}
                </label>
                <button onClick={() => setVisible(new Set([body.id]))}>
                  Isolate body {index + 1}
                </button>
                <details>
                  <summary>Faces</summary>
                  {shown.faces
                    .filter((f) => f.body_id === body.id)
                    .map((face, fi) => (
                      <button
                        key={face.id}
                        data-face-id={face.id}
                        aria-pressed={selected.has(face.id)}
                        onClick={() => toggle(face.id)}
                      >
                        Body {index + 1} face {fi + 1}
                      </button>
                    ))}
                </details>
              </section>
            ))}
          </>
        )}
      </aside>
      <div className="geometry-content">
        {activeResult && !editingPreview ? (
          <ResultViewport presentation={activeResult} visible={resultVisible} />
        ) : shown && geometry ? (
          <Viewport
            display={
              editDisplay ??
              (editingPreview
                ? shown
                : ((qualityOverlay
                    ? activeMesh?.quality_display
                    : activeMesh?.display) ?? shown))
            }
            revision={editDisplay?.brep_sha256 ?? geometry.id}
            selected={editHighlights ?? selected}
            visible={previewVisible}
            toggle={qualityOverlay && activeMesh ? () => {} : toggle}
            draftDirections={
              !editingPreview
                ? draftDirections.filter(
                    (d) =>
                      d.geometry_revision_id === geometry.id &&
                      d.analysis_id === analysisId,
                  )
                : []
            }
            faceColors={
              qualityOverlay && activeMesh ? qualityColors : undefined
            }
            wireframe={qualityOverlay && !!activeMesh}
            markers={
              !editingPreview &&
              loadPreview?.analysis_id === analysisId &&
              loadPreview.geometry_revision_id === geometry.id
                ? loadPreview.markers
                : []
            }
          />
        ) : (
          <div className="empty-viewport">
            <h2>
              {geometry && geometry.project_id === project?.id
                ? "Loading geometry…"
                : "Bring in your solid model"}
            </h2>
            <p>
              Create or open a project, then import a STEP file and confirm its
              size.
            </p>
          </div>
        )}
        {geometry && shown && (
          <section className="selection-panel">
            {activeMesh && !editingPreview && (
              <p data-mesh-job={activeMesh.job_id}>
                Generated mesh: {activeMesh.nodes} nodes · {activeMesh.elements}{" "}
                C3D10 elements. Boundary triangles show the actual quadratic
                mesh. Quality:{" "}
                {activeMesh.quality?.accepted
                  ? "passed"
                  : "FAILED — solve blocked"}
                . Minimum mean ratio{" "}
                {Number(activeMesh.quality?.minimum_mean_ratio).toPrecision(5)};
                certified Jacobian lower bound{" "}
                {Number(activeMesh.quality?.minimum_jacobian_m3).toPrecision(5)}{" "}
                m³.
              </p>
            )}
            {activeMesh && !editingPreview && (
              <label className="check">
                <input
                  type="checkbox"
                  checked={qualityOverlay}
                  onChange={(e) => setQualityOverlay(e.target.checked)}
                />
                Mesh quality overlay (all cell wireframes; face picking
                disabled)
              </label>
            )}
            {activeMesh && qualityOverlay && (
              <p>
                Green: accepted; orange: mean ratio below 0.2; red: failed.
                Quality uses the complete quadratic cell, not corner volume
                alone.
              </p>
            )}
            <label>
              Display detail
              <select
                value={lod}
                onChange={(e) => setLod(e.target.value as "coarse" | "fine")}
              >
                <option value="coarse">Coarse</option>
                <option value="fine">Fine</option>
              </select>
            </label>
            <h2>{selected.size} selected faces</h2>
            <button onClick={() => setSelected(new Set())}>
              Clear selection
            </button>
            <p>
              Geometry revision: <code>{geometry.id}</code>
            </p>
            <ul>
              {[...selected].map((face) => (
                <li key={face} data-selected-face={face}>
                  <button onClick={() => toggle(face)}>
                    Remove {face.split(":").slice(-2).join(" ")}
                  </button>
                  <code>{face}</code>
                </li>
              ))}
            </ul>
          </section>
        )}
        {project && geometry && (
          <GeometryEdits
            key={project.id}
            project={project}
            geometry={geometry}
            analysisId={analysisId}
            selected={selected}
            busy={busy}
            setBusy={setBusy}
            showPreview={(data, highlights) => {
              setEditDisplay(data);
              setEditHighlights(highlights ?? null);
              setEditingPreview(!!data || !!highlights);
            }}
            applied={(result) => {
              setProject(result.project);
              setProjects((all) =>
                all.map((p) =>
                  p.id === result.project.id ? result.project : p,
                ),
              );
              setGeometry(result.geometry);
              setLatestGeometry(result.geometry);
              setSelected(new Set());
              setMeshPreview(null);
              setResultPresentation(null);
              setLoadPreview(null);
              setEditorEpoch((old) => old + 1);
            }}
          />
        )}
        {project && (
          <MaterialsEditor
            key={`${project.id}:${editorEpoch}`}
            project={project}
            geometry={geometry}
            analysisId={analysisId}
            selectAnalysis={(id) => {
              setAnalysisId(id);
              if (!id) {
                setGeometry(latestGeometry);
                setSelected(new Set());
              }
            }}
            showGeometry={(pinned) => {
              setGeometry(pinned);
              setSelected(new Set());
            }}
            busy={busy || editingPreview}
            setBusy={setBusy}
            selected={selected}
            preview={setLoadPreview}
            directionPreview={setDraftDirections}
            showMesh={(mesh) => {
              setResultPresentation(null);
              setMeshPreview(mesh);
              setQualityOverlay(mesh?.quality?.accepted === false);
            }}
            showResult={setResultPresentation}
          />
        )}
      </div>
    </div>
  );
}
