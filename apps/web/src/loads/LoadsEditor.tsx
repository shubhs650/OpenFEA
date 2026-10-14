import { useEffect, useState } from "react";
import {
  DirectionEditor,
  type DirectionSelection,
  type DirectionSnapshot,
  type DirectionSource,
  type DraftDirection,
} from "./DirectionEditor";
import { MeshEditor } from "../mesh/MeshEditor";
import { RunsEditor } from "../runs/RunsEditor";
import type { ResultPresentation } from "../results/presentation";
import {
  api,
  mutate,
  RequestError,
  type DeckExport,
  type LoadState,
  type UnitPreset,
  type MeshPreview,
  type Geometry,
} from "../geometry/api";

type Props = {
  analysisId: string;
  revision: number;
  geometryId: string;
  selected: Set<string>;
  preset: UnitPreset;
  busy: boolean;
  setBusy: (value: boolean) => void;
  saved: (revision: number) => void;
  preview: (state: LoadState | null) => void;
  directionPreview: (values: DraftDirection[]) => void;
  showMesh: (mesh: MeshPreview | null) => void;
  showResult: (value: ResultPresentation | null) => void;
};

export function LoadsEditor({
  analysisId,
  revision,
  geometryId,
  selected,
  preset,
  busy,
  setBusy,
  saved,
  preview,
  directionPreview,
  showMesh,
  showResult,
}: Props) {
  const [meshReady, setMeshReady] = useState(false);
  const [state, setState] = useState<LoadState | null>(null);
  const [exports, setExports] = useState<DeckExport[]>([]);
  const [kind, setKind] = useState("fixed");
  const [name, setName] = useState("");
  const [pressure, setPressure] = useState("");
  const [force, setForce] = useState(["", "", ""]);
  const [displacement, setDisplacement] = useState("");
  const [axis, setAxis] = useState("x");
  const [geometry, setGeometry] = useState<Geometry | null>(null);
  const [directionSource, setDirectionSource] =
    useState<DirectionSource>("global");
  const [directionChoice, setDirectionChoice] =
    useState<DirectionSelection | null>(null);
  const [directionValues, setDirectionValues] = useState<DirectionSnapshot[]>(
    [],
  );
  const [magnitude, setMagnitude] = useState("");
  const [acceleration, setAcceleration] = useState(["", "", ""]);
  const [bodies, setBodies] = useState<string[]>([]);
  const [gravityBodies, setGravityBodies] = useState<string[]>([]);
  const [combine, setCombine] = useState(false);
  const [error, setError] = useState("");
  const [conflict, setConflict] = useState(false);
  const [status, setStatus] = useState("");
  // A unit change must not reinterpret an unsaved numeric draft.
  useEffect(() => {
    setPressure("");
    setForce(["", "", ""]);
    setDisplacement("");
    setMagnitude("");
    setAcceleration(["", "", ""]);
  }, [preset.id]);
  useEffect(() => {
    let current = true;
    setState(null);
    preview(null);
    void Promise.all([
      api<LoadState>(`/analyses/${analysisId}/loads`),
      api<DeckExport[]>(`/analyses/${analysisId}/deck-exports`),
      api<Geometry>(`/geometry/${geometryId}`),
    ])
      .then(([data, outputs, geometry]) => {
        if (current) {
          setState(data);
          setGeometry(geometry);
          setExports(outputs);
          const ids = geometry.bodies.map((b) => b.id);
          setBodies(ids);
          setGravityBodies((old) => old.filter((id) => ids.includes(id)));
          preview(data);
          const stale = data.analysis_revision !== revision;
          setConflict(stale);
          setError(
            stale
              ? "This analysis changed. Reload the saved analysis before applying again."
              : "",
          );
        }
      })
      .catch((e: Error) => {
        if (current) setError(e.message);
      });
    return () => {
      current = false;
    };
  }, [analysisId, revision, geometryId]);

  const aligned =
    state?.analysis_revision === revision &&
    state.geometry_revision_id === geometryId;
  const overlap = !!state?.setup.assignments?.some((a) =>
    kind === "gravity"
      ? a.kind === "gravity" &&
        !a.review_bodies?.length &&
        a.body_ids?.some((id) => gravityBodies.includes(id))
      : ["pressure", "force", "directional_force"].includes(kind) &&
        ["pressure", "force", "directional_force"].includes(a.kind) &&
        !a.review_faces?.length &&
        a.face_ids?.some((f) => selected.has(f)),
  );
  const hasDirectionReview = !!state?.setup.assignments?.some(
    (a) => a.review_direction && a.direction,
  );
  useEffect(() => {
    setDirectionSource(
      kind === "directional_force" || hasDirectionReview
        ? "plane_normal"
        : "global",
    );
    setDirectionChoice(null);
    setDirectionValues([]);
  }, [kind, geometryId, hasDirectionReview]);
  const directionReady =
    directionValues.length === (kind === "symmetry" ? selected.size : 1) &&
    directionValues.length > 0 &&
    directionValues.every((v) => v.geometry_revision_id === geometryId) &&
    (kind === "symmetry" || !!directionChoice);
  const valid =
    kind === "fixed" ||
    (kind === "symmetry"
      ? directionReady
      : kind === "directional_force"
        ? magnitude.trim() !== "" &&
          Number.isFinite(Number(magnitude)) &&
          Number(magnitude) !== 0 &&
          directionReady
        : kind === "displacement"
          ? displacement.trim() !== "" &&
            Number.isFinite(Number(displacement)) &&
            (directionSource === "global" || directionReady)
          : kind === "gravity"
            ? acceleration.every(
                (v) => v.trim() !== "" && Number.isFinite(Number(v)),
              ) && acceleration.some((v) => Number(v) !== 0)
            : kind === "pressure"
              ? pressure.trim() !== "" &&
                Number.isFinite(Number(pressure)) &&
                Number(pressure) !== 0
              : force.every(
                  (v) => v.trim() !== "" && Number.isFinite(Number(v)),
                ) && force.some((v) => Number(v) !== 0));
  async function change(path: string, payload?: unknown, method = "POST") {
    if (!aligned) return;
    setBusy(true);
    setError("");
    setStatus("Saving face assignment…");
    try {
      const next = await mutate<LoadState>(
        `/analyses/${analysisId}${path}`,
        revision,
        payload,
        method,
      );
      setState(next);
      preview(next);
      saved(next.analysis_revision);
      setStatus("Assignments saved in a new analysis revision.");
      setCombine(false);
    } catch (e) {
      setStatus("Assignment was not saved.");
      setConflict(e instanceof RequestError && e.code === "stale_revision");
      setError(
        (e as Error).message +
          (e instanceof RequestError && e.code === "stale_revision"
            ? " Reload the saved analysis before applying again."
            : ""),
      );
    } finally {
      setBusy(false);
    }
  }
  async function generate() {
    if (!aligned) return;
    setBusy(true);
    setError("");
    setStatus("Generating a bounded coarse mesh and checking loads…");
    try {
      const result = await mutate<DeckExport>(
        `/analyses/${analysisId}/deck-exports`,
        revision,
      );
      setExports((old) => [result, ...old.filter((e) => e.id !== result.id)]);
      setStatus("Checked deck saved. Download the immutable input below.");
    } catch (e) {
      setStatus("No deck was published.");
      setError((e as Error).message);
      setConflict(e instanceof RequestError && e.code === "stale_revision");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section aria-label="Face loads" className="loads-panel">
      <h2>Supports, face loads and body gravity</h2>
      <p>
        Global components or native geometry directions. Positive pressure acts
        inward; negative pressure acts outward. Total force is spread over the
        entire selected area once.
      </p>
      <p>
        {selected.size} selected faces · pinned geometry{" "}
        <code>{geometryId}</code>
      </p>
      <label>
        Assignment name
        <input
          value={name}
          maxLength={200}
          disabled={busy}
          onChange={(e) => setName(e.target.value)}
        />
      </label>
      <label>
        Face assignment
        <select
          value={kind}
          disabled={busy}
          onChange={(e) => {
            setKind(e.target.value);
            setCombine(false);
          }}
        >
          <option value="fixed">Fixed (all translations)</option>
          <option value="pressure">Uniform pressure</option>
          <option value="force">Total distributed force</option>
          <option value="directional_force">
            Total force along geometry direction
          </option>
          <option value="symmetry">
            Planar symmetry (normal displacement zero)
          </option>
          <option value="displacement">
            Prescribed displacement component
          </option>
          <option value="gravity">Gravity (body acceleration)</option>
        </select>
      </label>
      {(kind === "displacement" ||
        kind === "directional_force" ||
        kind === "symmetry" ||
        hasDirectionReview) && (
        <DirectionEditor
          key={`${analysisId}:${geometryId}:${kind}`}
          analysisId={analysisId}
          revision={revision}
          geometry={geometry}
          selected={selected}
          source={directionSource}
          setSource={setDirectionSource}
          globalAllowed={kind === "displacement"}
          symmetry={kind === "symmetry"}
          disabled={busy || conflict || !aligned}
          resolved={(choice, values) => {
            setDirectionChoice(choice);
            setDirectionValues(values);
          }}
          preview={directionPreview}
        />
      )}
      {kind === "directional_force" && (
        <label>
          Directed total force ({preset.force.label})
          <input
            type="number"
            step="any"
            disabled={busy}
            value={magnitude}
            onChange={(e) => setMagnitude(e.target.value)}
          />
        </label>
      )}
      {kind === "displacement" && (
        <>
          {directionSource === "global" && (
            <label>
              Prescribed global component
              <select
                value={axis}
                disabled={busy}
                onChange={(e) => setAxis(e.target.value)}
              >
                {["x", "y", "z"].map((a) => (
                  <option key={a} value={a}>
                    {a.toUpperCase()}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label>
            Prescribed displacement ({preset.length.label})
            <input
              type="number"
              step="any"
              disabled={busy}
              value={displacement}
              onChange={(e) => setDisplacement(e.target.value)}
            />
          </label>
          <p>
            Zero is allowed. Only this selected component is constrained; other
            translations remain free. Shared edges/vertices inherit face
            constraints. Conflicting values are refused.
          </p>
        </>
      )}
      {(kind === "gravity" ||
        state?.setup.assignments?.some((a) => a.review_bodies?.length)) && (
        <fieldset>
          <legend>Gravity bodies</legend>
          {bodies.map((id, i) => (
            <label key={id} className="check">
              <input
                type="checkbox"
                disabled={busy}
                checked={gravityBodies.includes(id)}
                onChange={(e) =>
                  setGravityBodies((old) =>
                    e.target.checked
                      ? [...old, id]
                      : old.filter((x) => x !== id),
                  )
                }
              />
              Gravity body {i + 1}
            </label>
          ))}
          <p>
            Apply acceleration to complete selected bodies. Positive density is
            required for weight and solve; missing density leaves weight
            unavailable.
          </p>
        </fieldset>
      )}
      {kind === "gravity" && (
        <div className="force-inputs">
          {["X", "Y", "Z"].map((a, i) => (
            <label key={a}>
              Acceleration {a} ({preset.acceleration.label})
              <input
                type="number"
                step="any"
                disabled={busy}
                value={acceleration[i]}
                onChange={(e) =>
                  setAcceleration((old) =>
                    old.map((v, k) => (k === i ? e.target.value : v)),
                  )
                }
              />
            </label>
          ))}
        </div>
      )}
      {kind === "pressure" && (
        <label>
          Pressure ({preset.stress.label})
          <input
            type="number"
            step="any"
            value={pressure}
            disabled={busy}
            onChange={(e) => setPressure(e.target.value)}
          />
        </label>
      )}
      {kind === "force" && (
        <div className="force-inputs">
          {["X", "Y", "Z"].map((axis, index) => (
            <label key={axis}>
              Total force {axis} ({preset.force.label})
              <input
                type="number"
                step="any"
                value={force[index]}
                disabled={busy}
                onChange={(e) =>
                  setForce((old) =>
                    old.map((v, i) => (i === index ? e.target.value : v)),
                  )
                }
              />
            </label>
          ))}
        </div>
      )}
      {overlap && (
        <label className="check">
          <input
            type="checkbox"
            checked={combine}
            disabled={busy}
            onChange={(e) => setCombine(e.target.checked)}
          />
          I confirm these overlapping loads combine with the saved loads
        </label>
      )}
      <button
        disabled={
          busy ||
          conflict ||
          !aligned ||
          !name.trim() ||
          (kind === "gravity" ? !gravityBodies.length : !selected.size) ||
          !valid ||
          (overlap && !combine)
        }
        onClick={() =>
          void change("/loads", {
            assignment: {
              kind,
              name,
              geometry_revision_id: geometryId,
              ...(kind === "gravity"
                ? { body_ids: gravityBodies }
                : { face_ids: [...selected] }),
              ...(kind === "displacement"
                ? {
                    units: preset.id,
                    ...(directionSource === "global"
                      ? { axis }
                      : { direction: directionChoice }),
                    displacement: Number(displacement),
                  }
                : kind === "gravity"
                  ? {
                      units: preset.id,
                      acceleration: acceleration.map(Number),
                      combine_confirmed: combine,
                    }
                  : kind === "pressure"
                    ? {
                        units: preset.id,
                        pressure: Number(pressure),
                        combine_confirmed: combine,
                      }
                    : kind === "directional_force"
                      ? {
                          units: preset.id,
                          magnitude: Number(magnitude),
                          direction: directionChoice,
                          combine_confirmed: combine,
                        }
                      : kind === "force"
                        ? {
                            units: preset.id,
                            force: force.map(Number),
                            combine_confirmed: combine,
                          }
                        : {}),
            },
          })
        }
      >
        {kind === "gravity" ? "Save body gravity" : "Save face assignment"}
      </button>
      {state && (
        <>
          <p>
            {state.resultant_complete
              ? "Saved resultant"
              : "Known resultant (incomplete — unresolved contributions withheld)"}{" "}
            (N): {state.total_force_n.map((v) => v.toPrecision(6)).join(", ")} ·
            Moment about global origin (N·m):{" "}
            {state.total_moment_nm.map((v) => v.toPrecision(6)).join(", ")}
          </p>
          <p>
            Arrow lengths are illustrative. Arrows show applied load directions;
            fixed glyphs constrain all translations. Blue component arrows show
            prescribed/support directions, not forces; gravity arrows start at
            native body centres of mass.
          </p>
          <ul>
            {state.setup.assignments?.map((a) => (
              <li key={a.id} data-assignment-id={a.id}>
                {a.direction && (
                  <div aria-label={`Saved direction ${a.name}`}>
                    <p>
                      {a.direction.kind} ·{" "}
                      {a.direction.reverse ? "reversed" : "native positive"} ·
                      X′ ={" "}
                      {a.direction.vector
                        .map((v) => v.toPrecision(7))
                        .join(", ")}
                    </p>
                    {a.source_magnitude !== null &&
                      a.source_magnitude !== undefined && (
                        <p>
                          Source directed force: {a.source_magnitude}{" "}
                          {a.source_units}
                        </p>
                      )}
                    {a.review_direction && (
                      <>
                        <p>
                          Geometry direction needs review. Reselect target faces
                          first, then choose its current direction reference.
                        </p>
                        <button
                          disabled={
                            busy ||
                            conflict ||
                            !aligned ||
                            !!a.review_faces?.length ||
                            !directionChoice ||
                            !directionValues.length
                          }
                          onClick={() =>
                            void change(
                              `/loads/${a.id}/direction`,
                              {
                                geometry_revision_id: geometryId,
                                direction: directionChoice,
                                reviewed: true,
                              },
                              "PUT",
                            )
                          }
                        >
                          Reselect direction for {a.name}
                        </button>
                      </>
                    )}
                  </div>
                )}
                {a.kind === "symmetry" && (
                  <p>
                    Planar symmetry:{" "}
                    {Object.values(a.symmetry_directions ?? {})
                      .map((value) =>
                        value.vector.map((v) => v.toPrecision(5)).join(", "),
                      )
                      .join("; ")}
                  </p>
                )}
                <strong>{a.name}</strong> · {a.kind} ·{" "}
                {a.kind === "gravity"
                  ? `${a.body_ids?.length ?? 0} bodies`
                  : `${a.face_ids?.length ?? 0} faces`}
                {a.displacement_m != null &&
                  ` · u${a.direction ? "X′" : a.axis?.toUpperCase()} = ${(a.displacement_m / preset.length.to_si).toPrecision(6)} ${preset.length.label}; other components free`}
                {a.acceleration_m_s2 &&
                  ` · [${a.acceleration_m_s2.map((v) => (v / preset.acceleration.to_si).toPrecision(6)).join(", ")}] ${preset.acceleration.label}`}
                {a.pressure_pa !== null &&
                  a.pressure_pa !== undefined &&
                  ` · ${(a.pressure_pa / preset.stress.to_si).toPrecision(6)} ${preset.stress.label} (${a.pressure_pa > 0 ? "inward" : "outward"})`}
                {a.force_n &&
                  ` · [${a.force_n.map((v) => (v / preset.force.to_si).toPrecision(6)).join(", ")}] ${preset.force.label}`}
                {!!a.review_faces?.length && (
                  <>
                    <p>
                      Needs geometry review: {a.review_faces.join(", ")}. Select
                      all intended replacement faces; the saved SI load remains
                      unchanged.
                    </p>
                    <button
                      disabled={busy || conflict || !aligned || !selected.size}
                      onClick={() =>
                        void change(
                          `/loads/${a.id}/faces`,
                          {
                            geometry_revision_id: geometryId,
                            face_ids: [...selected],
                            reviewed: true,
                            combine_confirmed: combine,
                          },
                          "PUT",
                        )
                      }
                    >
                      Reselect faces for {a.name}
                    </button>
                  </>
                )}
                {!!a.review_bodies?.length && (
                  <>
                    <p>
                      Needs body/weight review: {a.review_bodies.join(", ")}.
                      Geometry changed mass/centroid. Saved acceleration and
                      source values remain unchanged.
                    </p>
                    <button
                      disabled={
                        busy || conflict || !aligned || !gravityBodies.length
                      }
                      onClick={() =>
                        void change(
                          `/loads/${a.id}/bodies`,
                          {
                            geometry_revision_id: geometryId,
                            body_ids: gravityBodies,
                            reviewed: true,
                            combine_confirmed: combine,
                          },
                          "PUT",
                        )
                      }
                    >
                      Reselect bodies for {a.name}
                    </button>
                  </>
                )}
                <button
                  disabled={busy || conflict || !aligned}
                  onClick={() =>
                    void change(`/loads/${a.id}`, undefined, "DELETE")
                  }
                >
                  Remove {a.name}
                </button>
              </li>
            ))}
          </ul>
          {state.warnings.map((w) => (
            <p key={w}>{w}</p>
          ))}
          <ul aria-label="Deck blockers">
            {state.blockers.map((b) => (
              <li key={b}>{b}</li>
            ))}
          </ul>
        </>
      )}
      <button
        disabled={busy || conflict || !aligned || !!state?.blockers.length}
        onClick={() => void generate()}
      >
        Generate checked deck
      </button>
      <p>
        Coarse planar C3D10 preview: at most 3,000 elements and 60 seconds.
        Bodies remain independent and need sufficient global component supports.
        Export can reject an ambiguous mapping, unsuitable mesh or force on
        fixed degrees of freedom. Local solve jobs and calculated result views
        are available below.
      </p>
      <ul aria-label="Saved deck exports">
        {exports.map((e) => (
          <li key={e.id}>
            Revision {e.analysis_revision} · {String(e.summary.elements)} C3D10
            elements ·{" "}
            <a href={`/api/v1/deck-exports/${e.id}/input`}>
              Download analysis.inp
            </a>{" "}
            ·{" "}
            <a href={`/api/v1/deck-exports/${e.id}/snapshot`}>
              Download frozen snapshot
            </a>
            <p>
              Deck SHA-256: <code>{e.deck_sha256}</code>
            </p>
          </li>
        ))}
      </ul>
      <MeshEditor
        analysisId={analysisId}
        revision={revision}
        geometryId={geometryId}
        selected={selected}
        preset={preset}
        busy={busy}
        setBusy={setBusy}
        saved={saved}
        ready={setMeshReady}
      />
      <RunsEditor
        analysisId={analysisId}
        revision={revision}
        geometryId={geometryId}
        ready={aligned && !conflict && !!state && !state.blockers.length}
        meshReady={
          meshReady &&
          aligned &&
          !conflict &&
          !state?.setup.assignments?.some(
            (a) =>
              a.review_faces?.length ||
              a.review_bodies?.length ||
              a.review_direction,
          )
        }
        busy={busy}
        setBusy={setBusy}
        showMesh={showMesh}
        preset={preset}
        showResult={showResult}
      />
      {error && <p role="alert">{error}</p>}
      <p aria-live="polite">{status}</p>
    </section>
  );
}
