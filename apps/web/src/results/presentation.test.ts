import { describe, expect, it } from "vitest";
import { color, constantRange, deformed } from "./presentation";

describe("result presentation", () => {
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
