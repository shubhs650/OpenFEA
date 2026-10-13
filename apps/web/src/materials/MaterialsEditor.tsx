import { useEffect, useState } from "react";
import {
  api,
  mutate,
  RequestError,
  type Analysis,
  type Geometry,
  type MaterialAssignment,
  type MaterialExample,
  type MaterialState,
  type Project,
  type UnitPreset,
} from "../geometry/api";
import { MaterialForm } from "./MaterialForm";

type Props = {
  project: Project;
  geometry: Geometry | null;
  analysisId: string;
  selectAnalysis: (id: string) => void;
  showGeometry: (geometry: Geometry | null) => void;
  busy: boolean;
  setBusy: (busy: boolean) => void;
};

export function MaterialsEditor({
  project,
  geometry,
  analysisId,
  selectAnalysis,
  showGeometry,
  busy,
  setBusy,
}: Props) {
  const [analyses, setAnalyses] = useState<Analysis[]>([]);
  const [name, setName] = useState("");
  const [state, setState] = useState<MaterialState | null>(null);
  const [presets, setPresets] = useState<UnitPreset[]>([]);
  const [library, setLibrary] = useState<MaterialExample[]>([]);
  const [body, setBody] = useState("");
  const [error, setError] = useState("");
  const [conflict, setConflict] = useState(false);
  const [status, setStatus] = useState("");
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let current = true;
    void Promise.all([
      api<{ items: Analysis[]; total: number }>(
        `/projects/${project.id}/analyses?limit=100`,
      ),
      api<UnitPreset[]>("/unit-presets"),
      api<MaterialExample[]>("/material-library"),
    ])
      .then(([page, units, samples]) => {
        if (current) {
          setAnalyses(page.items);
          setPresets(units);
          setLibrary(samples);
        }
      })
      .catch((e: Error) => {
        if (current) setError(e.message);
      });
    return () => {
      current = false;
    };
  }, [project.id, reload]);

  useEffect(() => {
    let current = true;
    setState(null);
    setBody("");
    setError("");
    setConflict(false);
    setStatus("");
    if (analysisId) {
      void api<MaterialState>(`/analyses/${analysisId}/materials`)
        .then(async (data) => {
          const pinned = data.geometry_revision_id
            ? await api<Geometry>(`/geometry/${data.geometry_revision_id}`)
            : null;
          if (current) {
            showGeometry(pinned);
            setState(data);
            setBody(data.bodies[0]?.body_id ?? "");
          }
        })
        .catch((e: Error) => {
          if (current) setError(e.message);
        });
    }
    return () => {
      current = false;
    };
  }, [analysisId, reload]);

  const active = state?.analysis_id === analysisId ? state : null;
  const aligned = !!active && active.geometry_revision_id === geometry?.id;
  const preset = presets.find(
    (item) => item.id === active?.setup.display_units,
  );
  const material = active?.setup.assignments?.find(
    (item) => item.body_id === body,
  )?.material;
  const readiness = active?.bodies.find((item) => item.body_id === body);

  async function createAnalysis() {
    if (!geometry || geometry.project_id !== project.id) return;
    setBusy(true);
    setError("");
    try {
      const created = await mutate<Analysis>(
        `/projects/${project.id}/analyses`,
        project.revision,
        { name, geometry_revision_id: geometry.id },
      );
      setAnalyses((old) => [...old, created]);
      selectAnalysis(created.id);
      setName("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function save(
    path: string,
    payload: unknown,
    method: string,
    message: string,
  ) {
    if (!active) return false;
    setBusy(true);
    setError("");
    setStatus("Saving…");
    try {
      const result = await mutate<MaterialState>(
        `/analyses/${active.analysis_id}${path}`,
        active.analysis_revision,
        payload,
        method,
      );
      setState(result);
      setStatus(message);
      return true;
    } catch (e) {
      setStatus("Changes were not saved.");
      setConflict(e instanceof RequestError && e.status === 409);
      setError(
        e instanceof RequestError && e.code === "material_library_changed"
          ? e.message +
              " Reload the saved analysis, then select the sample again."
          : e instanceof RequestError && e.status === 409
            ? "This analysis changed in another session. Reload the saved analysis before applying again. Your edits have not overwritten it."
            : (e as Error).message,
      );
    } finally {
      setBusy(false);
    }
    return false;
  }
  return (
    <section className="materials-panel panel" aria-label="Analysis materials">
      <h2>Analysis and materials</h2>
      <label>
        Open analysis
        <select
          value={analysisId}
          disabled={busy}
          onChange={(e) => selectAnalysis(e.target.value)}
        >
          <option value="">Geometry preview (no analysis)</option>
          {analyses.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        New analysis name
        <input
          value={name}
          maxLength={200}
          disabled={busy}
          onChange={(e) => setName(e.target.value)}
        />
      </label>
      <button
        disabled={
          busy ||
          !name.trim() ||
          !geometry ||
          geometry.project_id !== project.id
        }
        onClick={() => void createAnalysis()}
      >
        Create analysis for this geometry
      </button>
      {active && (
        <>
          <p>
            Analysis revision {active.analysis_revision} · Geometry revision{" "}
            <code>{active.geometry_revision_id ?? "not assigned"}</code>
          </p>
          <label>
            Display units
            <select
              value={active.setup.display_units}
              disabled={busy || conflict || !preset}
              onChange={(e) =>
                void save(
                  "/display-units",
                  { preset: e.target.value },
                  "PATCH",
                  "Display units saved. Physical values unchanged.",
                )
              }
            >
              {presets.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>
          {preset && (
            <p className="material-notice">
              Density: {preset.density.label} · Acceleration:{" "}
              {preset.acceleration.label}. These mass-density units are derived
              from force, length and seconds; pound-force is not pound-mass.
            </p>
          )}
          <ul className="body-material-summary">
            {active.bodies.map((b, index) => (
              <li key={b.body_id}>
                Body {index + 1}:{" "}
                {active.setup.assignments?.find((a) => a.body_id === b.body_id)
                  ?.material.provenance.name ?? "material missing"}
              </li>
            ))}
          </ul>
          {aligned && preset && (
            <>
              <label>
                Material body
                <select
                  value={body}
                  disabled={busy || conflict}
                  onChange={(e) => {
                    setBody(e.target.value);
                    setStatus("");
                  }}
                >
                  {active.bodies.map((b, index) => (
                    <option key={b.body_id} value={b.body_id}>
                      Body {index + 1}
                    </option>
                  ))}
                </select>
              </label>
              {readiness && (
                <div
                  className="material-readiness"
                  aria-label="Saved material prerequisites"
                >
                  <p>
                    Gravity:{" "}
                    {readiness.gravity_available
                      ? "density supplied"
                      : "unavailable — density required"}
                  </p>
                  <p>
                    Yield factor of safety:{" "}
                    {readiness.yield_factor_available
                      ? "yield supplied"
                      : "unavailable — yield strength required"}
                  </p>
                  {readiness.warnings.map((warning) => (
                    <p key={warning}>{warning}</p>
                  ))}
                </div>
              )}
              {body && (
                <MaterialForm
                  key={`${active.analysis_id}:${body}:${reload}`}
                  saved={material}
                  library={library}
                  preset={preset}
                  busy={busy || conflict}
                  apply={(assignment: MaterialAssignment) =>
                    save(
                      `/materials/${encodeURIComponent(body)}`,
                      assignment,
                      "PUT",
                      "Material saved in a new analysis revision.",
                    )
                  }
                  remove={() =>
                    void save(
                      `/materials/${encodeURIComponent(body)}`,
                      undefined,
                      "DELETE",
                      "Material removed in a new analysis revision.",
                    )
                  }
                />
              )}
            </>
          )}
          {!active.geometry_revision_id && (
            <p>
              Assign materials in a new analysis created for accepted geometry.
            </p>
          )}
        </>
      )}
      {analysisId && (
        <button disabled={busy} onClick={() => setReload((old) => old + 1)}>
          Reload saved analysis (discard edits)
        </button>
      )}
      {error && <p role="alert">{error}</p>}
      <p aria-live="polite">{status}</p>
      <p className="material-notice">
        Material prerequisites only. Load setup, meshing, solving and calculated
        results are not available yet.
      </p>
    </section>
  );
}
