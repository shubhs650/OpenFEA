import { useEffect, useState } from "react";
import type { components } from "../../../../packages/contracts/api";
import { api, mutate, type UnitPreset } from "../geometry/api";
type State = components["schemas"]["MeshState"];
type Local = components["schemas"]["LocalSizeInput"];
type Props = {
  analysisId: string;
  revision: number;
  geometryId: string;
  selected: Set<string>;
  preset: UnitPreset;
  busy: boolean;
  setBusy: (busy: boolean) => void;
  saved: (revision: number) => void;
  ready: (ready: boolean) => void;
};
export function MeshEditor({
  analysisId,
  revision,
  geometryId,
  selected,
  preset,
  busy,
  setBusy,
  saved,
  ready,
}: Props) {
  const [state, setState] = useState<State | null>(null);
  const [global, setGlobal] = useState("");
  const [locals, setLocals] = useState<Local[]>([]);
  const [kind, setKind] = useState<"face" | "body">("face");
  const [local, setLocal] = useState("");
  const [body, setBody] = useState("");
  const [bodies, setBodies] = useState<string[]>([]);
  const [curvature, setCurvature] = useState("16");
  const [recovery, setRecovery] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [preview, setPreview] = useState<State | null>(null);
  useEffect(() => {
    let current = true;
    ready(false);
    setPreview(null);
    setError("");
    void Promise.all([
      api<State>(`/analyses/${analysisId}/mesh-controls`),
      api<{ bodies: { id: string }[] }>(`/geometry/${geometryId}`),
    ])
      .then(([data, geometry]) => {
        if (!current) return;
        setState(data);
        setGlobal(
          data.setup.global_size_m == null
            ? ""
            : String(data.setup.global_size_m / preset.length.to_si),
        );
        setLocals(
          (data.setup.local_sizes ?? []).map((s) => ({
            kind: s.kind,
            entity_id: s.entity_id,
            size: s.size_m / preset.length.to_si,
          })),
        );
        setCurvature(String(data.setup.curvature_elements));
        setRecovery(data.setup.recovery_enabled);
        setBodies(geometry.bodies.map((b) => b.id));
        setBody(geometry.bodies[0]?.id ?? "");
        setLocal("");
        ready(data.analysis_revision === revision && !data.blockers.length);
      })
      .catch((e: Error) => {
        if (current) setError(e.message);
      });
    return () => {
      current = false;
    };
  }, [analysisId, revision, geometryId, preset.id]);
  const changed =
    !!state &&
    (global !==
      (state.setup.global_size_m == null
        ? ""
        : String(state.setup.global_size_m / preset.length.to_si)) ||
      curvature !== String(state.setup.curvature_elements) ||
      recovery !== state.setup.recovery_enabled ||
      JSON.stringify(locals) !==
        JSON.stringify(
          (state.setup.local_sizes ?? []).map((s) => ({
            kind: s.kind,
            entity_id: s.entity_id,
            size: s.size_m / preset.length.to_si,
          })),
        ));
  useEffect(() => {
    ready(
      !!state &&
        state.analysis_revision === revision &&
        state.geometry_revision_id === geometryId &&
        !state.blockers.length &&
        !changed,
    );
  }, [state, changed, revision, geometryId]);
  const valid =
    (global === "" ||
      (Number.isFinite(Number(global)) && Number(global) > 0)) &&
    (Number(curvature) === 0 ||
      (Number.isInteger(Number(curvature)) &&
        Number(curvature) >= 8 &&
        Number(curvature) <= 64));
  async function request(save: boolean) {
    setBusy(true);
    setError("");
    try {
      const data = await mutate<State>(
        `/analyses/${analysisId}/mesh-controls${save ? "" : "/preview"}`,
        revision,
        {
          units: preset.id,
          global_size: global === "" ? null : Number(global),
          local_sizes: locals,
          curvature_elements: Number(curvature),
          recovery_enabled: recovery,
        },
        save ? "PUT" : "POST",
      );
      if (save) {
        setState(data);
        saved(data.analysis_revision);
        setPreview(null);
        setStatus(
          "Mesh controls saved in a new analysis revision. Old jobs retain their sizes.",
        );
      } else {
        setPreview(data);
        setStatus("Estimate only. Saved mesh controls are unchanged.");
      }
    } catch (e) {
      setError(
        (e as Error).message +
          " Reload the saved analysis after a revision conflict.",
      );
    } finally {
      setBusy(false);
    }
  }
  const planning = preview ?? state;
  return (
    <section className="mesh-controls" aria-label="Mesh sizing">
      <h2>Mesh sizing and recovery</h2>
      <label>
        Global mesh size ({preset.length.label})
        <input
          type="number"
          step="any"
          value={global}
          disabled={busy}
          onChange={(e) => {
            setGlobal(e.target.value);
            setPreview(null);
          }}
        />
      </label>
      <p>
        Empty global size uses half each body's largest extent. Local sizes
        refine; the smallest applicable size wins.
      </p>
      <label>
        Local mesh target
        <select
          value={kind}
          disabled={busy}
          onChange={(e) => setKind(e.target.value as "face" | "body")}
        >
          <option value="face">Selected CAD faces</option>
          <option value="body">Body</option>
        </select>
      </label>
      {kind === "body" && (
        <label>
          Mesh body
          <select value={body} onChange={(e) => setBody(e.target.value)}>
            {bodies.map((b, i) => (
              <option key={b} value={b}>
                Body {i + 1}
              </option>
            ))}
          </select>
        </label>
      )}
      <label>
        Local mesh size ({preset.length.label})
        <input
          type="number"
          step="any"
          value={local}
          disabled={busy}
          onChange={(e) => setLocal(e.target.value)}
        />
      </label>
      <button
        disabled={
          busy ||
          !local.trim() ||
          !Number.isFinite(Number(local)) ||
          Number(local) <= 0 ||
          (kind === "face" ? !selected.size : !body)
        }
        onClick={() => {
          const ids = kind === "face" ? [...selected] : [body];
          setLocals((old) =>
            [
              ...old.filter(
                (s) => s.kind !== kind || !ids.includes(s.entity_id),
              ),
              ...ids.map((entity_id) => ({
                kind,
                entity_id,
                size: Number(local),
              })),
            ].sort(
              (a, b) =>
                a.kind.localeCompare(b.kind) ||
                a.entity_id.localeCompare(b.entity_id),
            ),
          );
          setPreview(null);
        }}
      >
        Add local mesh size
      </button>
      <ul>
        {locals.map((s) => (
          <li key={`${s.kind}:${s.entity_id}`}>
            {s.kind} · <code>{s.entity_id}</code> · {s.size}{" "}
            {preset.length.label}
            <button
              disabled={busy}
              onClick={() => {
                setLocals((old) => old.filter((x) => x !== s));
                setPreview(null);
              }}
            >
              Remove local mesh control {s.entity_id.split(":").at(-1)}
            </button>
          </li>
        ))}
      </ul>
      <label>
        Curvature elements per full circle
        <input
          type="number"
          value={curvature}
          disabled={busy}
          onChange={(e) => {
            setCurvature(e.target.value);
            setPreview(null);
          }}
        />
      </label>
      <p>
        0 disables curvature refinement; otherwise 8–64. Curved quadratic mesh
        inspection is available for plane/cylinder bodies. Solving retains the
        validated affine/planar contract.
      </p>
      <label className="check">
        <input
          type="checkbox"
          checked={recovery}
          disabled={busy}
          onChange={(e) => {
            setRecovery(e.target.checked);
            setPreview(null);
          }}
        />
        I allow two additional disclosed meshing attempts with unchanged sizing
      </label>
      <p>
        Initial Delaunay; approved alternatives: Frontal, then Delaunay with
        Netgen optimization. No geometry deletion or automatic coarsening.
        Resource stops, mapping failures, cancellation and interruptions are not
        retried.
      </p>
      <button disabled={busy || !valid} onClick={() => void request(false)}>
        Preview mesh estimate
      </button>
      <button disabled={busy || !valid} onClick={() => void request(true)}>
        Save mesh controls
      </button>
      {changed && (
        <p>Unsaved mesh controls. Save or reload before submitting a mesh.</p>
      )}
      {planning && (
        <>
          <p>
            Planning estimate: {planning.estimated_elements_upper} elements · up
            to {planning.estimated_nodes_upper} nodes /{" "}
            {planning.estimated_dofs_upper} DOFs.
          </p>
          <p>{planning.estimate_basis}</p>
          <p>
            Native limit: 3,000 elements · 30,000 nodes · 60 seconds/stage · 180
            seconds/job · 1,536 MiB RSS · 192 MiB scratch.
          </p>
          {planning.warnings.map((w) => (
            <p key={w}>{w}</p>
          ))}
          <ul aria-label="Mesh blockers">
            {planning.blockers.map((b) => (
              <li key={b}>{b}</li>
            ))}
          </ul>
          {planning.coarsening_proposal_m != null && (
            <>
              <p>
                Proposed coarser global size:{" "}
                {(
                  planning.coarsening_proposal_m / preset.length.to_si
                ).toPrecision(6)}{" "}
                {preset.length.label}; remove finer overrides and disable/review
                curvature.
              </p>
              <button
                disabled={busy}
                onClick={() => {
                  setGlobal(
                    String(
                      planning.coarsening_proposal_m! / preset.length.to_si,
                    ),
                  );
                  setLocals([]);
                  setCurvature("0");
                  setPreview(null);
                  setStatus(
                    "Coarsening proposal copied to draft: local overrides removed, curvature off. Review and save explicitly.",
                  );
                }}
              >
                Use coarsening proposal in draft (clear local sizes, curvature
                off)
              </button>
            </>
          )}
        </>
      )}
      {error && <p role="alert">{error}</p>}
      <p aria-live="polite">{status}</p>
    </section>
  );
}
