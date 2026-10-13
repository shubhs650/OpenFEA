import type { ResultView, UnitPreset } from "../geometry/api";

export type ResultField = "displacement" | "von_mises";
export type ResultPresentation = {
  view: ResultView;
  field: ResultField;
  scale: number;
  preset: UnitPreset;
  range: [number, number];
};
export function scalar(
  vertex: ResultView["data"]["vertices"][number],
  field: ResultField,
) {
  return field === "displacement"
    ? Math.hypot(...vertex.displacement_m)
    : vertex.von_mises_pa;
}
export function fieldRange(
  view: ResultView,
  field: ResultField,
): [number, number] {
  let low = Infinity,
    high = -Infinity;
  for (const vertex of view.data.vertices) {
    const value = scalar(vertex, field);
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
