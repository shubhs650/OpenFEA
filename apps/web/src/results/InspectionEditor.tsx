import { useEffect, useRef, useState } from "react";
import {
  api,
  RequestError,
  type ResultInspection,
  type ResultView,
  type UnitPreset,
} from "../geometry/api";
import { isDisplacement, scalar, type ResultField } from "./presentation";

type Props = {
  view: ResultView;
  field: ResultField;
  smoothed: boolean;
  preset: UnitPreset;
  onSection: (value: ResultInspection | null) => void;
  onUnavailable: (message: string) => void;
};
export function InspectionEditor({
  view,
  field,
  smoothed,
  preset,
  onSection,
  onUnavailable,
}: Props) {
  const [element, setElement] = useState("");
  const [point, setPoint] = useState(["0", "0", "0"]);
  const [normal, setNormal] = useState(["1", "0", "0"]);
  const [probe, setProbe] = useState<ResultInspection | null>(null);
  const [section, setSection] = useState<ResultInspection | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const sequence = useRef(0);
  useEffect(
    () => () => {
      sequence.current++;
    },
    [],
  );
  // Do not reinterpret pending coordinates after a unit change.
  useEffect(() => {
    sequence.current++;
    setPoint(["0", "0", "0"]);
    setBusy(false);
  }, [preset.id]);
  async function inspect(kind: "probes" | "sections") {
    const current = ++sequence.current;
    setError("");
    setBusy(true);
    if (kind === "probes") setProbe(null);
    else {
      setSection(null);
      onSection(null);
    }
    try {
      if (
        point.some((v) => !v.trim() || !Number.isFinite(Number(v))) ||
        normal.some((v) => !v.trim() || !Number.isFinite(Number(v)))
      )
        throw new Error(
          "Enter finite physical coordinates and a finite section normal.",
        );
      if (
        kind === "probes" &&
        (!Number.isSafeInteger(Number(element)) || Number(element) <= 0)
      )
        throw new Error("Select a positive element ID for the physical probe.");
      const result = await api<ResultInspection>(
        `/runs/${view.job_id}/${kind}`,
        "POST",
        {
          point_m: point.map((v) => Number(v) * preset.length.to_si),
          ...(kind === "probes"
            ? { element_id: Number(element) }
            : { normal: normal.map(Number) }),
        },
      );
      if (current !== sequence.current) return;
      if (
        result.job_id !== view.job_id ||
        result.mesh_sha256 !== view.mesh_sha256 ||
        result.results_sha256 !== view.results_sha256
      )
        throw new Error(
          "Inspection belongs to different frozen result data. Reopen the run.",
        );
      if (kind === "probes") setProbe(result);
      else {
        setSection(result);
        onSection(result);
      }
    } catch (e) {
      if (current !== sequence.current) return;
      setError((e as Error).message);
      if (e instanceof RequestError && [401, 404, 410, 503].includes(e.status))
        onUnavailable((e as Error).message);
    } finally {
      if (current === sequence.current) setBusy(false);
    }
  }
  const unit = isDisplacement(field) ? preset.length : preset.stress;
  const value = probe?.vertices[0];
  return (
    <section aria-label="Volume inspection">
      <h3>Physical probes and volume sections</h3>
      <p>
        Reference coordinates before deformation. Choose an explicit element
        side at boundaries; adjacent sides are never averaged together. Camera
        and field settings remain in place when inspecting a section.
      </p>
      <a href={`/api/v1/jobs/${view.job_id}/artifacts/mesh.json`}>
        Download retained volume mesh and element IDs
      </a>
      <label>
        Probe element ID
        <input
          type="number"
          min="1"
          step="1"
          value={element}
          onChange={(e) => setElement(e.target.value)}
        />
      </label>
      {point.map((v, k) => (
        <label key={k}>
          Inspection {"xyz"[k]} ({preset.length.label})
          <input
            type="number"
            value={v}
            onChange={(e) =>
              setPoint((p) =>
                p.map((old, j) => (j === k ? e.target.value : old)),
              )
            }
          />
        </label>
      ))}
      <button disabled={busy} onClick={() => void inspect("probes")}>
        Probe physical point
      </button>
      {normal.map((v, k) => (
        <label key={k}>
          Section normal {"xyz"[k]}
          <input
            type="number"
            value={v}
            onChange={(e) =>
              setNormal((p) =>
                p.map((old, j) => (j === k ? e.target.value : old)),
              )
            }
          />
        </label>
      ))}
      <button disabled={busy} onClick={() => void inspect("sections")}>
        Generate volume section
      </button>
      <button
        onClick={() => {
          sequence.current++;
          setBusy(false);
          setSection(null);
          onSection(null);
        }}
      >
        Show exterior surface
      </button>
      {error && <p role="alert">{error}</p>}
      {value && (
        <div aria-label="Physical probe result">
          <p>
            Element {value.element_id} · body {value.body_id} · material{" "}
            {value.material_id} · element_interpolated · global Cartesian.
          </p>
          <p>
            Reference position [
            {value.position_m
              .map((v) => (v / preset.length.to_si).toPrecision(6))
              .join(", ")}
            ] {preset.length.label}; barycentric [
            {value.barycentric.map((v) => v.toPrecision(6)).join(", ")}].
          </p>
          <p>
            Selected field:{" "}
            {(scalar(value, field, smoothed) / unit.to_si).toPrecision(6)}{" "}
            {unit.label} ·{" "}
            {smoothed && !isDisplacement(field) ? "smoothed" : "unaveraged"}.
          </p>
        </div>
      )}
      {section && (
        <p aria-label="Volume section status">
          {section.triangles.length
            ? `${section.triangles.length} display triangles from retained volume elements.`
            : "No volume area intersects this plane."}{" "}
          Plane reference [
          {section.point_m
            .map((v) => (v / preset.length.to_si).toPrecision(6))
            .join(", ")}
          ] {preset.length.label}; unit normal [
          {section.normal?.map((v) => v.toPrecision(6)).join(", ")}].
        </p>
      )}
      {(probe || section) && (
        <p aria-label="Inspection interpolation method">
          {(probe ?? section)?.method}
        </p>
      )}
    </section>
  );
}
