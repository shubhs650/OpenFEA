export type Mode = "setup" | "compute" | "paused";

// Monotonic event boundaries avoid charging compute to a polling interval.
export class TutorialClock {
  private last: number;
  private totals = { setup: 0, compute: 0, paused: 0 };
  constructor(
    now: number,
    private mode: Mode = "setup",
  ) {
    this.last = now;
  }
  snapshot(now: number) {
    return {
      ...this.totals,
      [this.mode]: this.totals[this.mode] + Math.max(0, now - this.last),
    };
  }
  change(mode: Mode, now: number) {
    this.totals = this.snapshot(now);
    this.last = now;
    this.mode = mode;
  }
}
