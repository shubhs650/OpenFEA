import { useEffect, useRef, useState } from "react";
import {
  api,
  type LocalJob,
  type ResultView,
  type UnitPreset,
} from "../geometry/api";
import {
  fieldRange,
  isDisplacement,
  type ResultField,
  type ResultPresentation,
} from "./presentation";

type Props = {
  jobs: LocalJob[];
  analysisId: string;
  revision: number;
  preset: UnitPreset;
  showResult: (value: ResultPresentation | null) => void;
};
export function ResultsEditor({
  jobs,
  analysisId,
  revision,
  preset,
  showResult,
}: Props) {
  const [id, setId] = useState("");
  const [view, setView] = useState<ResultView | null>(null);
  const [field, setField] = useState<ResultField>("displacement");
  const [smoothed, setSmoothed] = useState(false);
  const [scale, setScale] = useState("0");
  const [custom, setCustom] = useState<[number, number] | null>(null);
  const [low, setLow] = useState("");
  const [high, setHigh] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const request = useRef(0);
  const runs = jobs.filter(
    (j) => j.kind === "solve" && j.status === "succeeded",
  );
  const selected = id || runs[0]?.id || "";
  useEffect(() => {
    setLow("");
    setHigh("");
  }, [preset.id]);
  useEffect(() => {
    request.current++;
    setView(null);
    setId("");
    showResult(null);
    return () => {
      request.current++;
      showResult(null);
    };
  }, [analysisId, showResult]);
  useEffect(() => {
    if (!view) return;
    const value = Number(scale);
    if (scale.trim() && Number.isFinite(value) && value >= 0 && value <= 1e6)
      showResult({
        view,
        field,
        smoothed,
        scale: value,
        preset,
        range: custom ?? fieldRange(view, field, smoothed),
      });
  }, [view, field, smoothed, scale, preset, custom, showResult]);
  async function open() {
    const sequence = ++request.current;
    setLoading(true);
    setError("");
    setView(null);
    showResult(null);
    try {
      const result = await api<ResultView>(`/runs/${selected}/results`);
      if (sequence === request.current && result.analysis_id === analysisId) {
        setView(result);
        setId(selected);
        setCustom(null);
        setScale("0");
        setSmoothed(false);
      }
    } catch (e) {
      if (sequence === request.current) setError((e as Error).message);
    } finally {
      if (sequence === request.current) setLoading(false);
    }
  }
  const selectedField = view?.data.fields.find((f) => f.key === field);
  const fieldUnit = isDisplacement(field) ? preset.length : preset.stress;
  const stress = preset.stress,
    length = preset.length,
    force = preset.force;
  function format(value: number, factor = 1) {
    return (value / factor).toPrecision(6);
  }
  function location(sample: ResultView["data"]["displacement"]["maximum"]) {
    return `${sample.location === "node" ? `Node ${sample.node_id}` : `Element ${sample.element_id}, IP ${sample.integration_point_id}`} ${sample.body_id ? `· Body ${sample.body_id} / material ${sample.material_id} ` : ""}at [${sample.position_m.map((v) => format(v, length.to_si)).join(", ")}] ${length.label}`;
  }
  return (
    <section className="results-panel" aria-label="Engineering results">
      <h2>Engineering results</h2>
      <label>
        Completed solve
        <select
          value={selected}
          onChange={(e) => {
            request.current++;
            setId(e.target.value);
            setView(null);
            showResult(null);
            setLoading(false);
          }}
        >
          <option value="">Choose a completed solve</option>
          {runs.map((j) => (
            <option key={j.id} value={j.id}>
              Revision {j.analysis_revision} · {j.id.slice(0, 8)}
            </option>
          ))}
        </select>
      </label>
      <button disabled={!selected || loading} onClick={() => void open()}>
        View selected results
      </button>
      <button
        onClick={() => {
          request.current++;
          setView(null);
          showResult(null);
          setLoading(false);
        }}
      >
        Close result view
      </button>
      {error && <p role="alert">{error}</p>}
      {view && (
        <>
          <p>
            Frozen run revision {view.analysis_revision} · Current analysis
            revision {revision}. Results use the run’s original mesh, materials
            and loads.
          </p>
          <p>
            Run <code>{view.job_id}</code> · Input SHA-256{" "}
            <code>{view.input_sha256}</code> · Raw result SHA-256{" "}
            <code>{view.results_sha256}</code>
          </p>
          <label>
            Result field
            <select
              value={field}
              onChange={(e) => {
                setField(e.target.value as ResultField);
                setCustom(null);
                setLow("");
                setHigh("");
              }}
            >
              {view.data.fields.map((f) => (
                <option key={f.key} value={f.key}>
                  {f.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            <input
              type="checkbox"
              checked={smoothed && !isDisplacement(field)}
              disabled={isDisplacement(field)}
              onChange={(e) => {
                setSmoothed(e.target.checked);
                setCustom(null);
                setLow("");
                setHigh("");
              }}
            />
            Smooth stress within each body and material
          </label>
          <p aria-label="Stress averaging method">
            {isDisplacement(field)
              ? "Native nodal displacement; stress smoothing does not alter this field."
              : smoothed
                ? view.data.smoothing_method
                : "Unaveraged element-node tensors from native DAT integration points; each element side is retained."}
          </p>
          <p>
            Global Cartesian frame; tensor order [
            {view.data.tensor_components.join(", ")}]. Principal order:{" "}
            {view.data.principal_order}. Tensile normal stresses are positive.
          </p>
          {selectedField && (
            <table aria-label="Selected field raw extrema">
              <thead>
                <tr>
                  <th>Field / raw location</th>
                  <th>Minimum</th>
                  <th>Minimum location</th>
                  <th>Maximum</th>
                  <th>Maximum location</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <th>
                    {selectedField.label} ({fieldUnit.label}) ·{" "}
                    {selectedField.raw_location}
                  </th>
                  <td data-testid="field-minimum">
                    {format(
                      selectedField.extrema.minimum.value,
                      fieldUnit.to_si,
                    )}
                  </td>
                  <td>{location(selectedField.extrema.minimum)}</td>
                  <td data-testid="field-maximum">
                    {format(
                      selectedField.extrema.maximum.value,
                      fieldUnit.to_si,
                    )}
                  </td>
                  <td>{location(selectedField.extrema.maximum)}</td>
                </tr>
              </tbody>
            </table>
          )}
          <label>
            Deformation scale
            <input
              type="number"
              min="0"
              max="1000000"
              value={scale}
              onChange={(e) => setScale(e.target.value)}
            />
          </label>
          {(!scale.trim() ||
            !Number.isFinite(Number(scale)) ||
            Number(scale) < 0 ||
            Number(scale) > 1e6) && (
            <p role="alert">
              Enter a deformation scale from 0 to 1,000,000. The last valid view
              is retained.
            </p>
          )}
          <p>
            0 shows undeformed geometry; 1 shows physical displacement. Larger
            values exaggerate the display.
          </p>
          <label>
            Contour minimum ({fieldUnit.label})
            <input
              type="number"
              value={low}
              onChange={(e) => setLow(e.target.value)}
            />
          </label>
          <label>
            Contour maximum ({fieldUnit.label})
            <input
              type="number"
              value={high}
              onChange={(e) => setHigh(e.target.value)}
            />
          </label>
          <button
            onClick={() => {
              const a = Number(low),
                b = Number(high),
                factor = fieldUnit.to_si;
              if (
                !low.trim() ||
                !high.trim() ||
                !Number.isFinite(a * factor) ||
                !Number.isFinite(b * factor) ||
                ((field === "displacement" || field === "von_mises") &&
                  a < 0) ||
                b <= a
              )
                setError(
                  "Enter finite contour limits with maximum greater than minimum; magnitudes must be nonnegative.",
                );
              else {
                setCustom([a * factor, b * factor]);
                setError("");
              }
            }}
          >
            Apply contour range
          </button>
          <button
            onClick={() => {
              setCustom(null);
              setLow("");
              setHigh("");
              setError("");
            }}
          >
            Reset contour range
          </button>
          <p>
            Contour limits clamp display colors only. Raw extrema and yield
            factors remain unchanged.
          </p>
          <table aria-label="Raw result extrema">
            <thead>
              <tr>
                <th>Quantity</th>
                <th>Minimum</th>
                <th>Maximum</th>
                <th>Maximum location</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <th>Displacement magnitude ({length.label})</th>
                <td>
                  {format(view.data.displacement.minimum.value, length.to_si)}
                </td>
                <td data-testid="displacement-maximum">
                  {format(view.data.displacement.maximum.value, length.to_si)}
                </td>
                <td>{location(view.data.displacement.maximum)}</td>
              </tr>
              <tr>
                <th>Von Mises at raw integration points ({stress.label})</th>
                <td>
                  {format(view.data.von_mises.minimum.value, stress.to_si)}
                </td>
                <td data-testid="stress-maximum">
                  {format(view.data.von_mises.maximum.value, stress.to_si)}
                </td>
                <td>{location(view.data.von_mises.maximum)}</td>
              </tr>
            </tbody>
          </table>
          <p>{view.data.extrema_method}</p>
          <h3>Yield factor — supplied yield / raw von Mises</h3>
          <p>
            Ductile yield assumption only. No fatigue, brittle failure,
            buckling, convergence or design approval is implied. Peaks near
            supports/reentrant corners may be singular and need refinement.
          </p>
          <table aria-label="Yield factors">
            <thead>
              <tr>
                <th>Body/material</th>
                <th>Frozen yield ({stress.label})</th>
                <th>Minimum factor</th>
                <th>Critical raw location</th>
              </tr>
            </thead>
            <tbody>
              {view.data.yield_factors.map((f) => (
                <tr key={f.body_id}>
                  <td>
                    {f.body_id} · {f.material_name}
                  </td>
                  <td>
                    {f.yield_strength_pa === null
                      ? "Unavailable"
                      : format(f.yield_strength_pa, stress.to_si)}
                  </td>
                  <td>
                    {f.state === "unavailable"
                      ? "Unavailable — missing yield"
                      : f.state === "unbounded"
                        ? `Unbounded/undefined — stress ≤ ${view.data.zero_stress_pa} Pa`
                        : format(f.minimum!)}
                  </td>
                  <td>{location(f.critical_sample)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <h3>External support and prescribed-displacement reactions</h3>
          <table aria-label="Support reactions">
            <thead>
              <tr>
                <th>Body</th>
                <th>Constrained nodes / DOFs</th>
                <th>Force [{force.label}]</th>
                <th>
                  Moment [{force.label}·{length.label}]
                </th>
              </tr>
            </thead>
            <tbody>
              {view.data.reactions.map((r) => (
                <tr key={r.body_id}>
                  <td>{r.body_id}</td>
                  <td>
                    {r.node_count} / {r.constrained_dof_count}
                  </td>
                  <td>
                    {r.force_n.map((v) => format(v, force.to_si)).join(", ")}
                  </td>
                  <td>
                    {r.moment_nm
                      .map((v) => format(v, force.to_si * length.to_si))
                      .join(", ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p>
            Total reaction force: [
            {view.data.reaction_force_n
              .map((v) => format(v, force.to_si))
              .join(", ")}
            ] {force.label}. Moment origin: global [0, 0, 0] {length.label}.
          </p>
          <p>{view.data.reaction_method}.</p>
          <h3>Force and moment equilibrium</h3>
          <p>
            Frozen external actions and reactions about global origin [0, 0, 0].
            Passing these limits does not establish mesh convergence or design
            safety.
          </p>
          <table aria-label="External equilibrium">
            <thead>
              <tr>
                <th>Balance</th>
                <th>Residual norm</th>
                <th>Reference magnitude</th>
                <th>Criterion / residual</th>
                <th>Allowed residual</th>
                <th>Outcome</th>
              </tr>
            </thead>
            <tbody>
              {(["force", "moment"] as const).map((kind) => {
                const check = view.data.equilibrium[kind];
                const factor =
                  force.to_si * (kind === "moment" ? length.to_si : 1);
                const label =
                  kind === "moment"
                    ? `${force.label}·${length.label}`
                    : force.label;
                return (
                  <tr key={kind}>
                    <th>{kind === "force" ? "Force" : "Moment"}</th>
                    <td>
                      {format(check.residual_norm, factor)} {label}
                    </td>
                    <td>
                      {format(check.reference, factor)} {label}
                    </td>
                    <td>
                      {check.relative_residual == null
                        ? "Absolute — near-zero reference; normalized residual unavailable"
                        : `${format(check.relative_residual * 100)}% (limit ${format(check.relative_tolerance * 100)}%)`}
                    </td>
                    <td>
                      {format(check.tolerance, factor)} {label}
                    </td>
                    <td>{check.passed ? "Passed" : "Failed"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p>
            Applied force: [
            {view.data.equilibrium.applied_force_n
              .map((v) => format(v, force.to_si))
              .join(", ")}
            ] {force.label}. Applied moment: [
            {view.data.equilibrium.applied_moment_nm
              .map((v) => format(v, force.to_si * length.to_si))
              .join(", ")}
            ] {force.label}·{length.label}.
          </p>
          <p>
            Residual force vector: [
            {view.data.equilibrium.force.residual
              .map((v) => format(v, force.to_si))
              .join(", ")}
            ] {force.label}. Residual moment vector: [
            {view.data.equilibrium.moment.residual
              .map((v) => format(v, force.to_si * length.to_si))
              .join(", ")}
            ] {force.label}·{length.label}.
          </p>
          <p>
            {view.data.equilibrium.method}. Actuator reference:{" "}
            {format(
              view.data.equilibrium.prescribed_actuator_reference_n,
              force.to_si,
            )}{" "}
            {force.label}; characteristic length:{" "}
            {format(
              view.data.equilibrium.characteristic_length_m,
              length.to_si,
            )}{" "}
            {length.label}.
          </p>
          <p>
            Warnings remain applicable when fields, units or contour limits
            change:
          </p>
          {view.data.warnings.map((w) => (
            <p role="note" key={w}>
              {w}
            </p>
          ))}
          <a href={`/api/v1/jobs/${view.job_id}/artifacts/results.json`}>
            Download raw parsed result
          </a>
          {" · "}
          <a href={`/api/v1/runs/${view.job_id}/results`}>
            Download current derived view JSON
          </a>
        </>
      )}
    </section>
  );
}
