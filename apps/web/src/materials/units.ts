import type { UnitPreset } from "../geometry/api";

export type Unit = UnitPreset["stress"];
export type QuantityField = { si: number | null; text: string };

export function displayQuantity(
  si: number | null | undefined,
  unit: Unit,
): QuantityField {
  return {
    si: si ?? null,
    text: si == null ? "" : (si / unit.to_si).toString(),
  };
}

export function editQuantity(text: string, unit: Unit): QuantityField {
  const parsed = text.trim() === "" ? NaN : Number(text);
  const si = parsed * unit.to_si;
  return {
    text,
    si: Number.isFinite(parsed) && Number.isFinite(si) ? si : null,
  };
}

// Never parse the formatted display back into canonical physics on a unit change.
export function redisplay(field: QuantityField, unit: Unit): QuantityField {
  return field.si === null ? field : displayQuantity(field.si, unit);
}
