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
