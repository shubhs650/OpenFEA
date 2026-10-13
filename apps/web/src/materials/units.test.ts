import { describe, expect, it } from "vitest";
import { displayQuantity, editQuantity, redisplay } from "./units";

describe("unit display preserves canonical physics", () => {
  it.each([
    [210e9, 1e6, 6894.757293168361],
    [7850, 1e12, 4.4482216152605 / 0.0254 ** 4],
    [-9.80665, 1e-3, 0.0254],
  ])(
    "keeps SI exactly through 100 display cycles (%s)",
    (si, metric, imperial) => {
      let field = displayQuantity(si, { label: "SI", to_si: 1 });
      for (let i = 0; i < 100; i++) {
        for (const factor of [metric, imperial, 1]) {
          field = redisplay(field, { label: "fixture", to_si: factor });
          expect(field.si).toBe(si);
          expect(Number(field.text) * factor).toBeCloseTo(si, 4);
        }
      }
    },
  );
  it("converts actual input once and preserves blank/invalid input", () => {
    const unit = { label: "MPa", to_si: 1e6 };
    expect(editQuantity("210000", unit).si).toBe(210e9);
    for (const text of ["", "NaN", "Infinity", "1e309"]) {
      const field = editQuantity(text, unit);
      expect(field.si).toBeNull();
      expect(redisplay(field, { label: "Pa", to_si: 1 }).text).toBe(text);
    }
    expect(editQuantity("1e308", unit).si).toBeNull();
  });
});
