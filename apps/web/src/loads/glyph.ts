export type Point = [number, number, number];

/** Cosmetic world-space glyphs; physics stays in SI and independent of the camera. */
export function glyph(
  position: Point,
  direction: Point,
  length: number,
  fixed: boolean,
): Point[][] {
  const plus = (a: Point, b: Point, s: number): Point =>
    a.map((v, i) => v + b[i] * s) as Point;
  if (fixed)
    return (
      [
        [1, 0, 0],
        [0, 1, 0],
        [0, 0, 1],
      ] as Point[]
    ).map((axis) => [
      plus(position, axis, -length / 4),
      plus(position, axis, length / 4),
    ]);
  const end = plus(position, direction, length);
  const base = plus(position, direction, length * 0.72);
  const reference: Point = Math.abs(direction[2]) < 0.8 ? [0, 0, 1] : [0, 1, 0];
  const perpendicular: Point = [
    direction[1] * reference[2] - direction[2] * reference[1],
    direction[2] * reference[0] - direction[0] * reference[2],
    direction[0] * reference[1] - direction[1] * reference[0],
  ];
  const n = Math.hypot(...perpendicular);
  const side = perpendicular.map((v) => v / n) as Point;
  return [
    [position, end],
    [plus(base, side, length * 0.12), end, plus(base, side, -length * 0.12)],
  ];
}
