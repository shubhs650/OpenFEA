import { expect, test, type Page } from "@playwright/test";
import type { components } from "../../packages/contracts/api";
import { prepared, mesh, solve } from "./support/runs";
type View = components["schemas"]["ResultView"];

async function openResults(page: Page, job: string): Promise<View> {
  await expect(page.locator(`[data-job-id="${job}"]`)).toHaveAttribute(
    "data-job-status",
    "succeeded",
  );
  await page
    .getByRole("combobox", { name: "Completed solve", exact: true })
    .selectOption(job);
  const response = page.waitForResponse((r) =>
    r.url().endsWith(`/runs/${job}/results`),
  );
  await page
    .getByRole("button", { name: "View selected results", exact: true })
    .click();
  const received = await response;
  expect(received.status()).toBe(200);
  await expect(
    page.getByLabel("Calculated result viewport", { exact: true }),
  ).toHaveAttribute("data-result-job", job);
  await expect(
    page.getByLabel("Result 3D canvas", { exact: true }).locator("canvas"),
  ).toBeVisible();
  return received.json();
}

test("full signed fields and partitioned smoothing preserve warnings, raw extrema and history", async ({
  page,
}, info) => {
  test.setTimeout(45_000);
  const failures: string[] = [];
  page.on("pageerror", (e) => failures.push(e.message));
  const { projectId, analysisId } = await prepared(
    page,
    "T021 signed field inspection",
    false,
    0.000001,
  );
  await mesh(page);
  const run = await solve(page);
  const result = await openResults(page, run.id);
  const rawPath = `/api/v1/jobs/${run.id}/artifacts/results.json`;
  const rawBefore = await (await page.request.get(rawPath)).text();
  const warning = page.getByRole("note").filter({
    hasText: "linear elasticity does not model plastic deformation",
  });
  await expect(warning).toBeVisible();
  for (const field of result.data.fields) {
    await page
      .getByRole("combobox", { name: "Result field", exact: true })
      .selectOption(field.key);
    await expect(page.getByLabel("Calculated result viewport")).toHaveAttribute(
      "data-result-field",
      field.key,
    );
    await expect(page.getByTestId("field-maximum")).toHaveText(
      (
        field.extrema.maximum.value / (field.unit === "m" ? 0.001 : 1e6)
      ).toPrecision(6),
    );
    await expect(warning).toBeVisible();
  }
  await page
    .getByRole("combobox", { name: "Result field", exact: true })
    .selectOption("sxx");
  const extrema = await page
    .getByLabel("Raw result extrema", { exact: true })
    .textContent();
  const factors = await page
    .getByLabel("Yield factors", { exact: true })
    .textContent();
  await page
    .getByLabel("Smooth stress within each body and material", { exact: true })
    .check();
  await expect(page.getByLabel("Calculated result viewport")).toHaveAttribute(
    "data-stress-smoothing",
    "smoothed",
  );
  await expect(page.getByLabel("Stress averaging method")).toContainText(
    "Invariants are calculated after tensor averaging",
  );
  await page
    .getByLabel("Contour minimum (MPa)", { exact: true })
    .fill("-0.002");
  await page
    .getByLabel("Contour maximum (MPa)", { exact: true })
    .fill("-0.0005");
  await page
    .getByRole("button", { name: "Apply contour range", exact: true })
    .click();
  await expect(page.getByLabel("Result legend")).toContainText(
    "-0.00200000 — -0.000500000 MPa",
  );
  await expect(
    page.getByLabel("Raw result extrema", { exact: true }),
  ).toHaveText(extrema!);
  await expect(page.getByLabel("Yield factors", { exact: true })).toHaveText(
    factors!,
  );
  await expect(warning).toBeVisible();
  await page
    .getByRole("combobox", { name: "Display units", exact: true })
    .selectOption("inch-lbf-psi");
  await expect(page.getByLabel("Result legend")).toContainText(
    "Stress σxx (psi)",
  );
  await page
    .getByRole("combobox", { name: "Display units", exact: true })
    .selectOption("m-N-Pa");
  await expect(page.getByTestId("field-maximum")).toHaveText(
    result.data.fields
      .find((f) => f.key === "sxx")!
      .extrema.maximum.value.toPrecision(6),
  );
  await page
    .getByLabel("Calculated result viewport")
    .screenshot({ path: info.outputPath("signed-smoothed-stress.png") });
  await page.screenshot({
    path: info.outputPath("result-inspection.png"),
    fullPage: true,
  });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(await page.evaluate(() => window.innerWidth));
  await page
    .getByLabel("Smooth stress within each body and material", { exact: true })
    .uncheck();
  await expect(page.getByLabel("Calculated result viewport")).toHaveAttribute(
    "data-stress-smoothing",
    "unaveraged",
  );
  expect(await (await page.request.get(rawPath)).text()).toBe(rawBefore);
  await page.reload();
  await page.getByLabel("Open project").selectOption(projectId);
  await page.getByLabel("Open analysis").selectOption(analysisId);
  expect(await openResults(page, run.id)).toEqual(result);
  await expect(warning).toBeVisible();
  expect(failures).toEqual([]);
});

test("synthetic bracket completes real import to contours, reactions and frozen result history", async ({
  page,
}) => {
  const failures: string[] = [];
  page.on("pageerror", (e) => failures.push(e.message));
  const { projectId, analysisId } = await prepared(
    page,
    "T012 real bracket",
    true,
  );
  await mesh(page);
  const run = await solve(page);
  const result = await openResults(page, run.id);
  expect(result.data.reaction_force_n[2]).toBeCloseTo(10, 3);
  expect(result.data.reaction_moment_nm[1]).toBeCloseTo(-0.8, 4);
  await expect(page.getByTestId("displacement-maximum")).toHaveText(
    (result.data.displacement.maximum.value / 0.001).toPrecision(6),
  );
  await expect(page.getByLabel("Raw result extrema")).toContainText(
    "raw integration points",
  );
  await expect(page.getByLabel("Yield factors")).toContainText("276");
  await page
    .getByRole("combobox", { name: "Result field", exact: true })
    .selectOption("von_mises");
  await expect(page.getByLabel("Result legend")).toContainText(
    "Von Mises stress (MPa)",
  );
  await expect(page.getByLabel("Result legend")).toContainText(
    "no stress averaging",
  );
  const peak = await page.getByTestId("stress-maximum").textContent();
  await page.getByLabel("Deformation scale", { exact: true }).fill("100");
  await expect(page.getByLabel("Calculated result viewport")).toHaveAttribute(
    "data-deformation-scale",
    "100",
  );
  await expect(page.getByTestId("stress-maximum")).toHaveText(peak!);
  await page.getByLabel("Contour minimum (MPa)", { exact: true }).fill("0");
  await page.getByLabel("Contour maximum (MPa)", { exact: true }).fill("1");
  await page
    .getByRole("button", { name: "Apply contour range", exact: true })
    .click();
  await expect(page.getByLabel("Result legend")).toContainText(
    "0.00000 — 1.00000 MPa",
  );
  await expect(page.getByTestId("stress-maximum")).toHaveText(peak!);
  await page
    .getByRole("button", { name: "Reset contour range", exact: true })
    .click();
  await expect(page.getByLabel("Result legend")).not.toContainText(
    "0.00000 — 1.00000 MPa",
  );
  await page
    .getByRole("combobox", { name: "Display units", exact: true })
    .selectOption("inch-lbf-psi");
  await expect(page.getByLabel("Result legend")).toContainText(
    "Von Mises stress (psi)",
  );
  await expect(page.getByTestId("stress-maximum")).toHaveText(
    (
      result.data.von_mises.maximum.value /
      (4.4482216152605 / 0.0254 ** 2)
    ).toPrecision(6),
  );
  await page
    .getByRole("combobox", { name: "Display units", exact: true })
    .selectOption("m-N-Pa");
  await expect(page.getByLabel("Result legend")).toContainText(
    "Von Mises stress (Pa)",
  );
  await expect(page.getByTestId("stress-maximum")).toHaveText(
    result.data.von_mises.maximum.value.toPrecision(6),
  );
  await page
    .getByRole("combobox", { name: "Display units", exact: true })
    .selectOption("mm-N-MPa");
  await expect(page.getByTestId("stress-maximum")).toHaveText(peak!);
  await expect(page.getByLabel("Engineering results")).toContainText(
    `Frozen run revision ${run.analysis_revision}`,
  );
  await page
    .getByLabel("Calculated result viewport")
    .screenshot({ path: test.info().outputPath("bracket-results.png") });
  await page.reload();
  await page
    .getByRole("combobox", { name: "Open project", exact: true })
    .selectOption(projectId);
  await page
    .getByRole("combobox", { name: "Open analysis", exact: true })
    .selectOption(analysisId);
  const retained = await openResults(page, run.id);
  expect(retained).toEqual(result);
  await expect(page.getByLabel("Engineering results")).toContainText(
    "Peaks near supports/reentrant corners may be singular",
  );
  await page
    .getByRole("button", { name: "Close result view", exact: true })
    .click();
  await expect(page.getByLabel("Calculated result viewport")).toHaveCount(0);
  await expect(
    page.getByLabel("Geometry viewport", { exact: true }),
  ).toBeVisible();
  expect(failures).toEqual([]);
});

test("actual zero-stress solve displays constant field and unbounded factor; missing yield stays unavailable", async ({
  page,
}) => {
  await prepared(page, "T012 zero stress", false, 276);
  // The same selected distal face has explicit equal/opposite saved pressures.
  await page
    .getByLabel("Assignment name", { exact: true })
    .fill("Deliberate reverse pressure");
  await page.getByLabel("Pressure (MPa)", { exact: true }).fill("-0.001");
  await page
    .getByLabel(
      "I confirm these overlapping loads combine with the saved loads",
    )
    .check();
  await page
    .getByRole("button", { name: "Save face assignment", exact: true })
    .click();
  await expect(
    page.getByRole("button", {
      name: "Remove Deliberate reverse pressure",
      exact: true,
    }),
  ).toBeVisible();
  await mesh(page);
  const run = await solve(page);
  const result = await openResults(page, run.id);
  expect(result.data.von_mises.maximum.value).toBe(0);
  await page
    .getByRole("combobox", { name: "Result field", exact: true })
    .selectOption("von_mises");
  await expect(page.getByLabel("Result legend")).toContainText(
    "Constant field",
  );
  await expect(page.getByLabel("Yield factors")).toContainText(
    "Unbounded/undefined",
  );
  await page.getByRole("spinbutton", { name: /Yield strength/ }).fill("");
  await page
    .getByLabel("I confirm the properties, condition and assumptions")
    .check();
  await page
    .getByRole("button", { name: "Apply material", exact: true })
    .click();
  await expect(page.getByLabel("Yield factors")).toContainText(
    "Unbounded/undefined",
  );
  const later = await solve(page);
  const missing = await openResults(page, later.id);
  expect(missing.data.yield_factors[0].state).toBe("unavailable");
  await expect(page.getByLabel("Yield factors")).toContainText(
    "Unavailable — missing yield",
  );
});

test("physical probes and volume sections preserve field and camera and reject unavailable data", async ({
  page,
}, info) => {
  test.setTimeout(45_000);
  const failures: string[] = [];
  page.on("pageerror", (e) => failures.push(e.message));
  const { projectId } = await prepared(page, "T022 volume inspection");
  await mesh(page);
  const run = await solve(page);
  const view = await openResults(page, run.id);
  const wire = await (
    await page.request.get(`/api/v1/jobs/${run.id}/artifacts/mesh.json`)
  ).json();
  const [element, nodes] = Object.entries(wire.elements)[0] as [
    string,
    number[],
  ];
  const center = [0, 1, 2].map(
    (k) => nodes.slice(0, 4).reduce((sum, n) => sum + wire.nodes[n][k], 0) / 4,
  );
  await page
    .getByRole("combobox", { name: "Result field", exact: true })
    .selectOption("sxx");
  await page.getByLabel("Probe element ID", { exact: true }).fill(element);
  for (let k = 0; k < 3; k++)
    await page
      .getByLabel(`Inspection ${"xyz"[k]} (mm)`, { exact: true })
      .fill(String(center[k] * 1000));
  await page.getByLabel("Section normal x", { exact: true }).fill("");
  await page
    .getByRole("button", { name: "Probe physical point", exact: true })
    .click();
  await expect(page.getByLabel("Physical probe result")).toContainText(
    `Element ${element}`,
  );
  await expect(page.getByLabel("Physical probe result")).toContainText(
    "-0.00100000 MPa",
  );
  await page.getByLabel("Section normal x", { exact: true }).fill("1");
  const canvas = page.getByLabel("Result 3D canvas", { exact: true });
  await canvas.scrollIntoViewIfNeeded();
  const initialCamera = await canvas.getAttribute("data-camera-state");
  const box = (await canvas.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(
    box.x + box.width / 2 + 50,
    box.y + box.height / 2 + 25,
    { steps: 8 },
  );
  await page.mouse.up();
  const camera = await canvas.getAttribute("data-camera-state");
  expect(camera).not.toBe(initialCamera);
  const rawExtrema = await page
    .getByLabel("Raw result extrema", { exact: true })
    .textContent();
  for (let k = 0; k < 3; k++)
    await page
      .getByLabel(`Inspection ${"xyz"[k]} (mm)`, { exact: true })
      .fill(k === 0 ? "500" : "0");
  const response = page.waitForResponse((r) =>
    r.url().endsWith(`/runs/${run.id}/sections`),
  );
  await page
    .getByRole("button", { name: "Generate volume section", exact: true })
    .click();
  const received = await response;
  expect(received.status()).toBe(200);
  const section: components["schemas"]["ResultInspection"] =
    await received.json();
  expect(section.vertices.length).toBeGreaterThan(0);
  expect(
    section.vertices.every((v) => Math.abs(v.position_m[0] - 0.5) < 1e-12),
  ).toBe(true);
  await expect(page.getByLabel("Calculated result viewport")).toHaveAttribute(
    "data-result-section",
    "volume",
  );
  await expect(canvas).toHaveAttribute("data-camera-state", camera!);
  await expect(
    page.getByLabel("Inspection interpolation method"),
  ).toContainText("interior centroid");
  await page
    .getByLabel("Smooth stress within each body and material", { exact: true })
    .check();
  await expect(canvas).toHaveAttribute("data-camera-state", camera!);
  await page
    .getByRole("combobox", { name: "Result field", exact: true })
    .selectOption("ux");
  await expect(page.getByLabel("Calculated result viewport")).toHaveAttribute(
    "data-result-field",
    "ux",
  );
  await expect(canvas).toHaveAttribute("data-camera-state", camera!);
  await expect(
    page.getByLabel("Raw result extrema", { exact: true }),
  ).toHaveText(rawExtrema!);
  await page.screenshot({
    path: info.outputPath("volume-section.png"),
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page
    .getByLabel("Volume inspection", { exact: true })
    .screenshot({ path: info.outputPath("inspection-controls.png") });
  await canvas.scrollIntoViewIfNeeded();
  await page.screenshot({ path: info.outputPath("volume-viewport.png") });
  await page
    .getByRole("button", { name: "Show exterior surface", exact: true })
    .click();
  await expect(page.getByLabel("Calculated result viewport")).toHaveAttribute(
    "data-result-section",
    "surface",
  );
  await expect(canvas).toHaveAttribute("data-camera-state", camera!);
  await page
    .getByRole("button", { name: "Reset result camera", exact: true })
    .click();
  await expect(canvas).not.toHaveAttribute("data-camera-state", camera!);
  await page.getByLabel("Inspection x (mm)", { exact: true }).fill("2000");
  await page
    .getByRole("button", { name: "Generate volume section", exact: true })
    .click();
  await expect(page.getByLabel("Volume section status")).toContainText(
    "No volume area intersects",
  );
  await expect(canvas).toHaveAttribute("data-camera-state", initialCamera!);
  await page.getByLabel("Inspection x (mm)", { exact: true }).fill("500");
  // An actual old section response cannot reopen a closed result view.
  let release!: () => void;
  let started!: () => void;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  const fetched = new Promise<void>((resolve) => {
    started = resolve;
  });
  const sectionPath = `**/api/v1/runs/${run.id}/sections`;
  await page.route(sectionPath, async (route) => {
    const response = await route.fetch();
    started();
    await held;
    await route.fulfill({ response });
  });
  await page
    .getByRole("button", { name: "Generate volume section", exact: true })
    .click();
  await fetched;
  await page
    .getByRole("button", { name: "Close result view", exact: true })
    .click();
  release();
  await page.unrouteAll({ behavior: "wait" });
  await expect(page.getByLabel("Calculated result viewport")).toHaveCount(0);
  await openResults(page, run.id);
  // Force actual retained-DAT unavailability; a prior successful section cannot be reused.
  const { readFile, unlink, writeFile } = await import("node:fs/promises");
  const { join } = await import("node:path");
  const dataRoot = info.config.metadata.localDataRoot as string;
  const datPath = join(dataRoot, "artifacts", projectId, view.dat_sha256);
  const dat = await readFile(datPath);
  await unlink(datPath);
  try {
    await page
      .getByRole("button", { name: "Generate volume section", exact: true })
      .click();
    await expect(page.getByRole("alert")).toContainText(
      "artifact is unavailable",
    );
    await expect(page.getByLabel("Calculated result viewport")).toHaveCount(0);
    await expect(page.getByLabel("Physical probe result")).toHaveCount(0);
  } finally {
    await writeFile(datPath, dat, { mode: 0o400 });
  }
  expect(failures).toEqual([]);
});

test("refinement compares real meshes at saved physical locations and exports all warnings", async ({
  page,
}, info) => {
  test.setTimeout(45_000);
  const { analysisId } = await prepared(
    page,
    "T023 physical refinement",
    false,
    0.000001,
  );
  const coarse = await mesh(page);
  const firstRun = await solve(page);
  await expect(page.locator(`[data-job-id="${firstRun.id}"]`)).toHaveAttribute(
    "data-job-status",
    "succeeded",
  );
  await page.getByText("Duplicate saved setup", { exact: true }).click();
  await page
    .getByLabel("New duplicate analysis name", { exact: true })
    .fill("T023 refined copy");
  const duplicated = page.waitForResponse(
    (r) => r.url().endsWith("/duplicates") && r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Duplicate analysis setup", exact: true })
    .click();
  const duplicateResponse = await duplicated;
  expect(duplicateResponse.status()).toBe(201);
  const refinedAnalysis = (await duplicateResponse.json()).id as string;
  await expect(
    page.getByRole("combobox", { name: "Open analysis", exact: true }),
  ).toHaveValue(refinedAnalysis);
  await expect(page.getByLabel("Save state", { exact: true })).toContainText(
    "Saved",
  );
  // The duplicated saved physics gets an explicit mesh change and actual solve.
  await page.getByRole("spinbutton", { name: /Global mesh size/ }).fill("300");
  await page
    .getByRole("button", { name: "Save mesh controls", exact: true })
    .click();
  const refined = await mesh(page);
  const secondRun = await solve(page);
  await expect(page.locator(`[data-job-id="${secondRun.id}"]`)).toHaveAttribute(
    "data-job-status",
    "succeeded",
  );
  await page
    .getByRole("combobox", { name: "Open analysis", exact: true })
    .selectOption(analysisId);
  await openResults(page, firstRun.id);
  await page
    .getByRole("combobox", { name: "Result field", exact: true })
    .selectOption("uz");
  await page.getByText("Mesh refinement comparison", { exact: true }).click();
  await page
    .getByRole("button", { name: "Refresh compared runs", exact: true })
    .click();
  await expect(
    page.getByRole("combobox", { name: "Compared analysis", exact: true }),
  ).toHaveValue(analysisId);
  await page
    .getByRole("combobox", { name: "Compared analysis", exact: true })
    .selectOption(refinedAnalysis);
  await page
    .getByRole("combobox", { name: "Compared completed run", exact: true })
    .selectOption(secondRun.id);
  const meshes = await Promise.all(
    [coarse, refined].map(async (job) =>
      (
        await page.request.get(`/api/v1/jobs/${job.id}/artifacts/mesh.json`)
      ).json(),
    ),
  );
  const ids = meshes.map(
    (wire) =>
      Object.entries(wire.elements).find(([, ns]) =>
        (ns as number[])
          .slice(0, 4)
          .some((n) => wire.nodes[n].every((v: number) => v === 0)),
      )![0],
  );
  await page
    .getByLabel("Comparison sample label", { exact: true })
    .fill("Fixed physical corner");
  await page.getByLabel("Reference element side", { exact: true }).fill(ids[0]);
  await page.getByLabel("Compared element side", { exact: true }).fill(ids[1]);
  await page
    .getByRole("button", { name: "Add physical sample", exact: true })
    .click();
  await expect(page.getByLabel("Saved comparison locations")).toContainText(
    "Fixed physical corner",
  );
  const response = page.waitForResponse((r) =>
    r.url().endsWith(`/runs/${firstRun.id}/comparisons`),
  );
  await page
    .getByRole("button", { name: "Compare physical samples", exact: true })
    .click();
  const received = await response;
  expect(received.status()).toBe(200);
  const data: components["schemas"]["ResultComparison"] = await received.json();
  expect(data.compared.elements).toBeGreaterThan(data.reference.elements);
  expect(data.rows[0].change.relative_change).toBeNull();
  expect(data.convergence_claim).toBe(false);
  await expect(page.getByLabel("Common physical sample changes")).toContainText(
    "Unavailable — near-zero reference",
  );
  await expect(page.getByLabel("Refinement comparison result")).toContainText(
    "No automatic singularity detection",
  );
  const download = page.waitForEvent("download");
  await page
    .getByRole("button", {
      name: "Download comparison JSON with warnings",
      exact: true,
    })
    .click();
  const file = await download;
  const path = await file.path();
  const { readFile } = await import("node:fs/promises");
  const exported = JSON.parse(
    await readFile(path!, "utf8"),
  ) as components["schemas"]["ResultComparison"];
  expect(exported).toEqual(data);
  expect(
    exported.reference.assumptions.some(
      (n) => n.code === "yielding" && n.triggered,
    ),
  ).toBe(true);
  expect(
    exported.reference.warnings.some((w) =>
      w.includes("does not model plastic"),
    ),
  ).toBe(true);
  await page
    .getByLabel("Mesh refinement comparison", { exact: true })
    .screenshot({ path: info.outputPath("refinement-comparison.png") });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  // Changing fields invalidates the prior derivative; the same stored SI point remains.
  await page
    .getByRole("combobox", { name: "Result field", exact: true })
    .selectOption("sxx");
  await expect(page.getByLabel("Refinement comparison result")).toHaveCount(0);
  await expect(page.getByLabel("Saved comparison locations")).toContainText(
    "Fixed physical corner",
  );
  await page
    .getByRole("button", { name: "Compare physical samples", exact: true })
    .click();
  await expect(page.getByLabel("Common physical sample changes")).toContainText(
    "-0.00100000",
  );
  let release!: () => void;
  let started!: () => void;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  const fetched = new Promise<void>((resolve) => {
    started = resolve;
  });
  await page.route(
    `**/api/v1/runs/${firstRun.id}/comparisons`,
    async (route) => {
      const response = await route.fetch();
      started();
      await held;
      await route.fulfill({ response });
    },
  );
  await page
    .getByRole("button", { name: "Compare physical samples", exact: true })
    .click();
  await fetched;
  await page
    .getByRole("combobox", { name: "Result field", exact: true })
    .selectOption("ux");
  release();
  await page.unrouteAll({ behavior: "wait" });
  await expect(page.getByLabel("Refinement comparison result")).toHaveCount(0);
});
