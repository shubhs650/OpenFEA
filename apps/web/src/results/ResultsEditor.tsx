import { useEffect, useRef, useState } from "react";
import {
  api,
  type LocalJob,
  type ResultView,
  type UnitPreset,
} from "../geometry/api";
import {
  fieldRange,
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
        scale: value,
        preset,
        range: custom ?? fieldRange(view, field),
      });
  }, [view, field, scale, preset, custom, showResult]);
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
      }
    } catch (e) {
      if (sequence === request.current) setError((e as Error).message);
    } finally {
      if (sequence === request.current) setLoading(false);
    }
  }
  const stress = preset.stress,
    length = preset.length,
    force = preset.force;
  function format(value: number, factor = 1) {
    return (value / factor).toPrecision(6);
  }
  function location(sample: ResultView["data"]["displacement"]["maximum"]) {
    return `${sample.location === "node" ? `Node ${sample.node_id}` : `Element ${sample.element_id}, IP ${sample.integration_point_id}`} at [${sample.position_m.map((v) => format(v, length.to_si)).join(", ")}] ${length.label}`;
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
              <option value="displacement">Displacement magnitude</option>
              <option value="von_mises">Von Mises stress</option>
            </select>
          </label>
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
            Contour minimum (
            {field === "displacement" ? length.label : stress.label})
            <input
              type="number"
              value={low}
              onChange={(e) => setLow(e.target.value)}
            />
          </label>
          <label>
            Contour maximum (
            {field === "displacement" ? length.label : stress.label})
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
                factor = field === "displacement" ? length.to_si : stress.to_si;
              if (
                !low.trim() ||
                !high.trim() ||
                !Number.isFinite(a * factor) ||
                !Number.isFinite(b * factor) ||
                a < 0 ||
                b <= a
              )
                setError(
                  "Enter finite nonnegative contour limits with maximum greater than minimum.",
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
          <h3>Fixed-support reactions</h3>
          <table aria-label="Support reactions">
            <thead>
              <tr>
                <th>Body</th>
                <th>Unique fixed nodes</th>
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
                  <td>{r.node_count}</td>
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
          <p>
            {view.data.reaction_method}. Full force/moment equilibrium
            validation is not available in this view.
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
