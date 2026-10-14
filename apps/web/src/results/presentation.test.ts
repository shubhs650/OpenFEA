import { describe, expect, it } from "vitest";
import {
  color,
  constantRange,
  deformed,
  scalar,
  fieldRange,
  isDisplacement,
} from "./presentation";
import type { ResultView } from "../geometry/api";

const vertex: ResultView["data"]["vertices"][number] = {
  node_id: 1,
  element_id: 1,
  body_id: "body",
  material_id: "material",
  face_id: "face",
  position_m: [0, 0, 0],
  displacement_m: [-3, 4, 0],
  von_mises_pa: 9,
  stress: {
    tensor_pa: [-6, 2, 3, 4, 5, 7],
    principal_pa: [12, 2, -15],
    von_mises_pa: 9,
  },
  smoothed_stress: {
    tensor_pa: [2, 0, 0, 0, 0, 0],
    principal_pa: [2, 0, 0],
    von_mises_pa: 2,
  },
  smoothed_contributions: 2,
};

describe("result presentation", () => {
  it("maps all signed displacement/tensor/principal fields in canonical order", () => {
    expect(
      [
        "displacement",
        "ux",
        "uy",
        "uz",
        "von_mises",
        "sxx",
        "syy",
        "szz",
        "sxy",
        "syz",
        "szx",
        "s1",
        "s2",
        "s3",
      ].map((f) => scalar(vertex, f as Parameters<typeof scalar>[1])),
    ).toEqual([5, -3, 4, 0, 9, -6, 2, 3, 4, 5, 7, 12, 2, -15]);
  });
  it("selects smoothed tensor-derived fields without modifying frozen values", () => {
    const before = JSON.stringify(vertex);
    expect(scalar(vertex, "sxx", true)).toBe(2);
    expect(scalar(vertex, "s1", true)).toBe(2);
    expect(scalar(vertex, "s3", true)).toBe(0);
    expect(scalar(vertex, "von_mises", true)).toBe(2);
    expect(scalar(vertex, "ux", true)).toBe(-3);
    expect(JSON.stringify(vertex)).toBe(before);
  });
  it("uses signed ranges and the selected averaging mode", () => {
    const view = {
      data: {
        vertices: [
          vertex,
          {
            ...vertex,
            stress: { ...vertex.stress, tensor_pa: [6, 0, 0, 0, 0, 0] },
          },
        ],
      },
    } as ResultView;
    expect(fieldRange(view, "sxx")).toEqual([-6, 6]);
    expect(fieldRange(view, "sxx", true)).toEqual([2, 2]);
    expect(color(-6, [-6, 6])).toEqual([0, 0, 255]);
  });
  it("identifies length fields independently from stress and principal units", () => {
    for (const field of ["displacement", "ux", "uy", "uz"] as const)
      expect(isDisplacement(field)).toBe(true);
    for (const field of ["von_mises", "sxx", "sxy", "s1", "s3"] as const)
      expect(isDisplacement(field)).toBe(false);
  });
  it("maps constant and zero fields to a uniform finite color", () => {
    expect(color(0, [0, 0])).toEqual([128, 190, 128]);
    expect(color(1000, [1000, 1000])).toEqual(color(0, [0, 0]));
    expect(constantRange([1000, 1000 + 1e-10])).toBe(true);
  });
  it("clamps custom contours while preserving a monotone range", () => {
    expect(color(-1, [0, 10])).toEqual([0, 0, 255]);
    expect(color(20, [0, 10])).toEqual([255, 0, 0]);
    expect(color(5, [0, 10])).toEqual([128, 190, 128]);
  });
  it("deformation changes only displayed coordinates with an explicit scale", () => {
    const p = [1, 2, 3],
      u = [0.01, 0, -0.02];
    expect(deformed(p, u, 0)).toEqual(p);
    expect(deformed(p, u, 1)).toEqual([1.01, 2, 2.98]);
    expect(deformed(p, u, 10)).toEqual([1.1, 2, 2.8]);
    expect(u).toEqual([0.01, 0, -0.02]);
    for (const value of [NaN, Infinity, -1, 1e6 + 1])
      expect(() => deformed(p, u, value)).toThrow();
  });
});
