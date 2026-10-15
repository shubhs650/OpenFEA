import type { ResultInspection, ResultView, UnitPreset } from "../geometry/api";

export type ResultField = ResultView["data"]["fields"][number]["key"];
export const isDisplacement = (field: ResultField) =>
  field === "displacement" || field.startsWith("u");
export type ResultPresentation = {
  view: ResultView;
  section?: ResultInspection | null;
  comparison?:
    | import("../../../../packages/contracts/api").components["schemas"]["ComparisonRequest"]
    | null;
  field: ResultField;
  smoothed: boolean;
  scale: number;
  preset: UnitPreset;
  range: [number, number];
};
export function scalar(
  vertex: Pick<
    ResultView["data"]["vertices"][number],
    "displacement_m" | "stress" | "smoothed_stress"
  >,
  field: ResultField,
  smoothed = false,
) {
  if (field === "displacement") return Math.hypot(...vertex.displacement_m);
  if (field === "ux" || field === "uy" || field === "uz")
    return vertex.displacement_m[["ux", "uy", "uz"].indexOf(field)];
  const stress = smoothed ? vertex.smoothed_stress : vertex.stress;
  if (field === "von_mises") return stress.von_mises_pa;
  if (field === "s1" || field === "s2" || field === "s3")
    return stress.principal_pa[["s1", "s2", "s3"].indexOf(field)];
  return stress.tensor_pa[
    ["sxx", "syy", "szz", "sxy", "syz", "szx"].indexOf(field)
  ];
}
export function fieldRange(
  view: ResultView,
  field: ResultField,
  smoothed = false,
  vertices: readonly Parameters<typeof scalar>[0][] = view.data.vertices,
): [number, number] {
  let low = Infinity,
    high = -Infinity;
  for (const vertex of vertices.length ? vertices : view.data.vertices) {
    const value = scalar(vertex, field, smoothed);
    low = Math.min(low, value);
    high = Math.max(high, value);
  }
  return [low, high];
}
export function constantRange([low, high]: [number, number]) {
  return (
    high - low <=
    Math.max(1e-14, Math.max(Math.abs(low), Math.abs(high)) * 1e-12)
  );
}
export function color(
  value: number,
  range: [number, number],
): [number, number, number] {
  const t = constantRange(range)
    ? 0.5
    : Math.min(1, Math.max(0, (value - range[0]) / (range[1] - range[0])));
  return [
    Math.round(255 * t),
    Math.round(190 * (1 - Math.abs(2 * t - 1))),
    Math.round(255 * (1 - t)),
  ];
}
export function deformed(
  position: number[],
  displacement: number[],
  scale: number,
) {
  if (!Number.isFinite(scale) || scale < 0 || scale > 1e6)
    throw new Error("Invalid deformation scale");
  return position.map((v, axis) => v + scale * displacement[axis]);
}
