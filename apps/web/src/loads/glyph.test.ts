import { describe, expect, it } from "vitest";
import { glyph, type Point } from "./glyph";

describe("load glyph directions", () => {
  for (const axis of [0, 1, 2])
    for (const sign of [-1, 1]) {
      it(`shows global axis ${axis}, sign ${sign}`, () => {
        const direction: Point = [0, 0, 0];
        direction[axis] = sign;
        const lines = glyph([1, 2, 3], direction, 2, false);
        const expected: Point = [1, 2, 3];
        expected[axis] += sign * 2;
        expect(lines[0]).toEqual([[1, 2, 3], expected]);
        expect(lines[1][1]).toEqual(expected);
        expect(lines.flat(2).every(Number.isFinite)).toBe(true);
      });
    }
  it("marks all three fixed translations", () => {
    expect(glyph([0, 0, 0], [0, 0, 0], 2, true)).toEqual([
      [
        [-0.5, 0, 0],
        [0.5, 0, 0],
      ],
      [
        [0, -0.5, 0],
        [0, 0.5, 0],
      ],
      [
        [0, 0, -0.5],
        [0, 0, 0.5],
      ],
    ]);
  });
});
