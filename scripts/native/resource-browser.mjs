// Repeatable display diagnostic. Use --headed on the target laptop for GPU evidence.
/* global document, Event, requestAnimationFrame */
import process from "node:process";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import assert from "node:assert/strict";
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { chromium } from "@playwright/test";

const input = resolve(process.argv[2]);
const headed = process.argv.includes("--headed");
const browser = await chromium.launch({
  headless: !headed,
  args: headed ? [] : ["--enable-unsafe-swiftshader"],
});
try {
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", (error) => errors.push(String(error)));
  await page.goto(pathToFileURL(resolve(input, "display.html")).href);
  await page.waitForFunction(() => globalThis.openfeaResource !== undefined);
  const payload = JSON.parse(
    readFileSync(resolve(input, "display.json"), "utf8"),
  );
  const before = await page.locator("canvas").screenshot();
  const stats = await page.evaluate(async () => {
    const angle = document.getElementById("angle");
    const frameIntervals = [];
    let previous = performance.now();
    for (let i = 0; i < 60; i++) {
      angle.value = String(i / 10);
      angle.dispatchEvent(new Event("input"));
      await new Promise(requestAnimationFrame);
      const now = performance.now();
      frameIntervals.push(now - previous);
      previous = now;
    }
    globalThis.openfeaResource.animation_intervals_ms = frameIntervals;
    return globalThis.openfeaResource;
  });
  assert.equal(stats.mesh_sha256, payload.mesh_sha256);
  assert.equal(stats.dat_sha256, payload.dat_sha256);
  assert.equal(stats.surface_triangles, payload.surface_triangles);
  assert.equal(stats.volume_elements, payload.volume_elements);
  assert.equal(stats.frame_ms.length, 61);
  assert(stats.buffer_bytes > 0);
  const rotated = await page.locator("canvas").screenshot();
  assert(!before.equals(rotated), "Rotation must change rendered pixels");
  await page.getByLabel("Displayed field").selectOption("4");
  const stress = await page.evaluate(() => globalThis.openfeaResource);
  const nativeValues = payload.vertices.filter((_, index) => index % 5 === 4);
  assert.deepEqual(
    stress.range,
    nativeValues.reduce(
      ([lo, hi], value) => [Math.min(lo, value), Math.max(hi, value)],
      [Infinity, -Infinity],
    ),
  );
  assert.equal(stress.field, "raw element IP1 xx");
  const changed = await page.locator("canvas").screenshot();
  assert(
    !rotated.equals(changed),
    "Field selection must change rendered pixels",
  );
  assert.deepEqual(errors, []);
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Performance.enable");
  const performance = await cdp.send("Performance.getMetrics");
  const sorted = [...stress.frame_ms].sort((a, b) => a - b);
  const result = {
    ...stress,
    code_commit: execFileSync("git", ["rev-parse", "HEAD"], {
      encoding: "utf8",
    }).trim(),
    viewer_source_sha256: createHash("sha256")
      .update(readFileSync("services/worker/worker/resource_viewer.py"))
      .digest("hex"),
    browser: browser.version(),
    mode: headed
      ? "headed target-machine test"
      : "headless software GPU permitted",
    software_renderer: /swiftshader|llvmpipe|software/i.test(stress.renderer),
    status:
      "DISPLAY DIAGNOSTIC PASS; integrated-GPU/laptop acceptance requires target-machine review",
    frame_median_ms: sorted[Math.floor(sorted.length / 2)],
    frame_p95_ms: sorted[Math.floor(sorted.length * 0.95)],
    js_heap_used_bytes: performance.metrics.find(
      (m) => m.name === "JSHeapUsedSize",
    )?.value,
    html_bytes: readFileSync(resolve(input, "display.html")).length,
    errors,
  };
  writeFileSync(
    resolve(input, "browser.json"),
    JSON.stringify(result, null, 2) + "\n",
  );
  await page.screenshot({
    path: resolve(input, "browser.png"),
    fullPage: true,
  });
  process.stdout.write(JSON.stringify(result, null, 2) + "\n");
} finally {
  await browser.close();
}
