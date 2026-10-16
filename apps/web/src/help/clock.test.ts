import { describe, expect, it } from "vitest";
import { TutorialClock } from "./clock";

describe("tutorial time excludes compute and breaks", () => {
  it("charges each interval once across repeated native waits and manual pauses", () => {
    const clock = new TutorialClock(100);
    clock.change("compute", 1100);
    clock.change("compute", 2100);
    clock.change("setup", 6100);
    clock.change("paused", 8100);
    clock.change("compute", 18100);
    clock.change("setup", 21100);
    expect(clock.snapshot(22100)).toEqual({
      setup: 4000,
      compute: 8000,
      paused: 10000,
    });
    expect(clock.snapshot(23100).setup).toBe(5000);
  });
  it("excludes a native job already active at the start", () => {
    const clock = new TutorialClock(0, "compute");
    clock.change("setup", 5000);
    expect(clock.snapshot(6000)).toEqual({
      setup: 1000,
      compute: 5000,
      paused: 0,
    });
  });
});
