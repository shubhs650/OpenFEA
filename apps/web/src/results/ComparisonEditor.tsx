import { useEffect, useRef, useState } from "react";
import {
  api,
  RequestError,
  type Analysis,
  type LocalJob,
  type ResultView,
  type UnitPreset,
} from "../geometry/api";
import type { components } from "../../../../packages/contracts/api";
import { isDisplacement, type ResultField } from "./presentation";
type Comparison = components["schemas"]["ResultComparison"];
type Point = components["schemas"]["ComparisonPoint"];
type Props = {
  view: ResultView;
  projectId: string;
  field: ResultField;
  smoothed: boolean;
  preset: UnitPreset;
  onUnavailable: (message: string) => void;
};
export function ComparisonEditor({
  view,
  projectId,
  field,
  smoothed,
  preset,
  onUnavailable,
}: Props) {
  const [analyses, setAnalyses] = useState<Analysis[]>([]);
  const [analysis, setAnalysis] = useState(view.analysis_id);
  const [refresh, setRefresh] = useState(0);
  const [runs, setRuns] = useState<LocalJob[]>([]);
  const [other, setOther] = useState("");
  const [point, setPoint] = useState(["0", "0", "0"]);
  const [body, setBody] = useState(view.data.yield_factors[0]?.body_id ?? "");
  const [first, setFirst] = useState("");
  const [second, setSecond] = useState("");
  const [label, setLabel] = useState("Sample 1");
  const [points, setPoints] = useState<Point[]>([]);
  const [result, setResult] = useState<Comparison | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const sequence = useRef(0);
  useEffect(() => {
    let active = true;
    api<{ items: Analysis[] }>(`/projects/${projectId}/analyses?limit=100`)
      .then((p) => {
        if (active) setAnalyses(p.items);
      })
      .catch((e) => {
        if (active) setError((e as Error).message);
      });
    return () => {
      active = false;
    };
  }, [projectId]);
  useEffect(() => {
    let active = true;
    setRuns([]);
    setOther("");
    api<LocalJob[]>(`/analyses/${analysis}/jobs`)
      .then((jobs) => {
        if (active)
          setRuns(
            jobs.filter(
              (j) =>
                j.kind === "solve" &&
                j.status === "succeeded" &&
                j.id !== view.job_id,
            ),
          );
      })
      .catch((e) => {
        if (active) setError((e as Error).message);
      });
    return () => {
      active = false;
    };
  }, [analysis, view.job_id, refresh]);
  useEffect(() => {
    setPoints([]);
  }, [other]);
  useEffect(() => {
    sequence.current++;
    setResult(null);
    setBusy(false);
    return () => {
      sequence.current++;
    };
  }, [other, field, smoothed, points]);
  useEffect(() => {
    setPoint(["0", "0", "0"]);
  }, [preset.id]);
  function add() {
    setError("");
    if (
      !label.trim() ||
      label.trim().length > 100 ||
      point.some((v) => !v.trim() || !Number.isFinite(Number(v))) ||
      ![first, second].every(
        (v) => Number.isSafeInteger(Number(v)) && Number(v) > 0,
      )
    ) {
      setError(
        "Enter a sample label, finite coordinates and both positive element IDs.",
      );
      return;
    }
    setPoints((p) => [
      ...p,
      {
        label: label.trim(),
        body_id: body,
        point_m: point.map((v) => Number(v) * preset.length.to_si) as [
          number,
          number,
          number,
        ],
        reference_element_id: Number(first),
        compared_element_id: Number(second),
      },
    ]);
    setLabel(`Sample ${points.length + 2}`);
  }
  async function compare() {
    const current = ++sequence.current;
    setError("");
    setBusy(true);
    setResult(null);
    try {
      const response = await api<Comparison>(
        `/runs/${view.job_id}/comparisons`,
        "POST",
        { compared_run_id: other, field, smoothed, points },
      );
      if (current !== sequence.current) return;
      if (
        response.reference.source.job_id !== view.job_id ||
        response.compared.source.job_id !== other ||
        response.reference.source.results_sha256 !== view.results_sha256
      )
        throw new Error(
          "Comparison belongs to a different frozen run. Reopen results.",
        );
      setResult(response);
    } catch (e) {
      if (current === sequence.current) {
        setError((e as Error).message);
        if (
          e instanceof RequestError &&
          [401, 404, 410, 503].includes(e.status)
        )
          onUnavailable((e as Error).message);
      }
    } finally {
      if (current === sequence.current) setBusy(false);
    }
  }
  function download() {
    if (!result) return;
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(result, null, 2) + "\n"], {
        type: "application/json",
      }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = `comparison-${view.job_id}-${other}.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }
  const unit = isDisplacement(field) ? preset.length : preset.stress;
  const fmt = (v: number) => (v / unit.to_si).toPrecision(6);
  return (
    <section aria-label="Mesh refinement comparison">
      <h3>Compare mesh refinements</h3>
      <p>
        Duplicate saved analysis settings and explicitly change mesh sizing
        before solving. Select the same physical body side and coordinates in
        both meshes. Geometry, material, loading, supports, bonds and solver
        contracts must match. One comparison cannot establish convergence.
      </p>
      <label>
        Compared analysis
        <select value={analysis} onChange={(e) => setAnalysis(e.target.value)}>
          {analyses.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </select>
      </label>
      <button onClick={() => setRefresh((v) => v + 1)}>
        Refresh compared runs
      </button>
      <label>
        Compared completed run
        <select value={other} onChange={(e) => setOther(e.target.value)}>
          <option value="">Choose a different completed run</option>
          {runs.map((j) => (
            <option key={j.id} value={j.id}>
              Revision {j.analysis_revision} · {j.id.slice(0, 8)}
            </option>
          ))}
        </select>
      </label>
      <p>
        Current field: {view.data.fields.find((f) => f.key === field)?.label};{" "}
        {smoothed && !isDisplacement(field)
          ? "partitioned-smoothed tensors"
          : "unaveraged"}
        . Samples below retain SI coordinates through display-unit changes.
      </p>
      <a href={`/api/v1/jobs/${view.job_id}/artifacts/mesh.json`}>
        Reference mesh element IDs
      </a>
      {" · "}
      {other && (
        <a href={`/api/v1/jobs/${other}/artifacts/mesh.json`}>
          Compared mesh element IDs
        </a>
      )}
      <label>
        Comparison sample label
        <input
          value={label}
          maxLength={100}
          onChange={(e) => setLabel(e.target.value)}
        />
      </label>
      <label>
        Comparison body side
        <select value={body} onChange={(e) => setBody(e.target.value)}>
          {view.data.yield_factors.map((f) => (
            <option key={f.body_id} value={f.body_id}>
              {f.body_id}
            </option>
          ))}
        </select>
      </label>
      {point.map((v, k) => (
        <label key={k}>
          Comparison {"xyz"[k]} ({preset.length.label})
          <input
            type="number"
            value={v}
            onChange={(e) =>
              setPoint((p) =>
                p.map((old, j) => (k === j ? e.target.value : old)),
              )
            }
          />
        </label>
      ))}
      <label>
        Reference element side
        <input
          type="number"
          min="1"
          step="1"
          value={first}
          onChange={(e) => setFirst(e.target.value)}
        />
      </label>
      <label>
        Compared element side
        <input
          type="number"
          min="1"
          step="1"
          value={second}
          onChange={(e) => setSecond(e.target.value)}
        />
      </label>
      <button disabled={points.length >= 8} onClick={add}>
        Add physical sample
      </button>
      <ul aria-label="Saved comparison locations">
        {points.map((p, k) => (
          <li key={k}>
            {p.label}: [
            {p.point_m
              .map((v) => (v / preset.length.to_si).toPrecision(6))
              .join(", ")}
            ] {preset.length.label}; element sides {p.reference_element_id} /{" "}
            {p.compared_element_id}
            <button
              onClick={() => setPoints((p) => p.filter((_, j) => j !== k))}
            >
              Remove sample {k + 1}
            </button>
          </li>
        ))}
      </ul>
      <button
        disabled={!other || !points.length || busy}
        onClick={() => void compare()}
      >
        Compare physical samples
      </button>
      {error && <p role="alert">{error}</p>}
      {result &&
        result.field === field &&
        result.compared.source.job_id === other && (
          <div aria-label="Refinement comparison result">
            <p>
              Reference: {result.reference.elements} elements /{" "}
              {result.reference.nodes} nodes. Compared:{" "}
              {result.compared.elements} elements / {result.compared.nodes}{" "}
              nodes. Frozen physics SHA-256:{" "}
              <code>{result.physics_sha256}</code>.
            </p>
            <table aria-label="Common physical sample changes">
              <thead>
                <tr>
                  <th>Location</th>
                  <th>Reference [{unit.label}]</th>
                  <th>Compared [{unit.label}]</th>
                  <th>Signed / absolute change [{unit.label}]</th>
                  <th>Relative change</th>
                </tr>
              </thead>
              <tbody>
                {result.rows.map((r, k) => (
                  <tr key={k}>
                    <th>{r.sample.label}</th>
                    <td>{fmt(r.change.reference)}</td>
                    <td>{fmt(r.change.compared)}</td>
                    <td>
                      {fmt(r.change.signed_change)} /{" "}
                      {fmt(r.change.absolute_change)}
                    </td>
                    <td>
                      {r.change.relative_change == null
                        ? "Unavailable — near-zero reference; use absolute change"
                        : `${(100 * r.change.relative_change).toPrecision(6)}%`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p>
              Relative reference floor: {fmt(result.reference_floor)}{" "}
              {unit.label}; display convention, not an accuracy tolerance.
            </p>
            <p>
              Raw native peak by absolute magnitude (moving mesh locations,
              independently unsmoothed): {fmt(result.reference.raw_peak.value)}{" "}
              → {fmt(result.compared.raw_peak.value)} {unit.label}; reference{" "}
              {result.reference.raw_peak.location} at [
              {result.reference.raw_peak.position_m
                .map((v) => (v / preset.length.to_si).toPrecision(6))
                .join(", ")}
              ], compared at [
              {result.compared.raw_peak.position_m
                .map((v) => (v / preset.length.to_si).toPrecision(6))
                .join(", ")}
              ] {preset.length.label}.
            </p>
            {result.warnings.map((w) => (
              <p role="note" key={w}>
                {w}
              </p>
            ))}
            {(["reference", "compared"] as const).map((side) => (
              <div key={side}>
                <h4>
                  {side === "reference" ? "Reference" : "Compared"} run
                  assumptions and frozen warnings
                </h4>
                {result[side].warnings.map((w) => (
                  <p role="note" key={w}>
                    {w}
                  </p>
                ))}
                {result[side].assumptions.map((n, k) => (
                  <p key={k}>
                    {n.code} ·{" "}
                    {n.triggered === true
                      ? "Screen exceeded"
                      : n.triggered === false
                        ? "No exceedance in this screen"
                        : "Not assessed"}
                    : {n.message}
                  </p>
                ))}
              </div>
            ))}
            <button onClick={download}>
              Download comparison JSON with warnings
            </button>
          </div>
        )}
    </section>
  );
}
