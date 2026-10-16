import { expect, test } from "@playwright/test";
import { mesh, solve } from "./support/runs";
import { assembly, approve } from "./support/assembly";
import type { components } from "../../packages/contracts/api";

test("real reviewed connection passes necessary mesh checks and solves while detached setup stays blocked", async ({
  page,
}, info) => {
  test.setTimeout(60_000);
  const { analysisId, projectId } = await assembly(page);
  await expect(
    page.getByLabel("Assembly support preflight", { exact: true }),
  ).toContainText("support rank 0/6");
  await expect(
    page.getByRole("button", { name: "Solve selected mesh", exact: true }),
  ).toBeDisabled();
  await approve(page);
  await expect(
    page.getByLabel("Assembly support preflight", { exact: true }),
  ).toContainText("Component 1: 2 body/bodies; support rank 6/6");
  await expect(
    page.getByLabel("Assembly support preflight", { exact: true }),
  ).toContainText("not proof");
  await mesh(page);
  await page
    .getByRole("button", { name: "Check assembly constraints", exact: true })
    .click();
  await expect(
    page.getByLabel("Actual mesh assembly preflight", { exact: true }),
  ).toContainText("Necessary mesh checks passed");
  await page.screenshot({
    path: info.outputPath("assembly-preflight.png"),
    fullPage: true,
  });
  const run = await solve(page);
  await expect(page.locator(`[data-job-id="${run.id}"]`)).toHaveAttribute(
    "data-job-status",
    "succeeded",
  );
  const raw = await (
    await page.request.get(`/api/v1/jobs/${run.id}/artifacts/results.json`)
  ).json();
  expect(raw.equilibrium.passed).toBe(true);
  expect(raw.assembly.max_tie_residual_m).toBeLessThanOrEqual(2e-11);
  await page
    .getByRole("button", { name: "View selected results", exact: true })
    .click();
  await expect(page.getByLabel("Calculated result viewport")).toBeVisible();
  await page
    .getByRole("combobox", { name: "Result field", exact: true })
    .selectOption("sxx");
  await page
    .getByLabel("Smooth stress within each body and material", { exact: true })
    .check();
  await expect(page.getByLabel("Calculated result viewport")).toHaveAttribute(
    "data-stress-smoothing",
    "smoothed",
  );
  const wire = await (
    await page.request.get(`/api/v1/jobs/${run.id}/artifacts/mesh.json`)
  ).json();
  const [element, nodes] = Object.entries(wire.elements)[0] as [
    string,
    number[],
  ];
  await page.getByLabel("Probe element ID", { exact: true }).fill(element);
  for (let k = 0; k < 3; k++) {
    const center =
      nodes.slice(0, 4).reduce((sum, n) => sum + wire.nodes[n][k], 0) / 4;
    await page
      .getByLabel(`Inspection ${"xyz"[k]} (mm)`, { exact: true })
      .fill(String(center * 1000));
  }
  await page
    .getByRole("button", { name: "Probe physical point", exact: true })
    .click();
  await expect(page.getByLabel("Physical probe result")).toContainText(
    "-0.00100000 MPa",
  );
  for (let k = 0; k < 3; k++) {
    await page
      .getByLabel(`Inspection ${"xyz"[k]} (mm)`, { exact: true })
      .fill(k === 1 ? "500" : "0");
    await page
      .getByLabel(`Section normal ${"xyz"[k]}`, { exact: true })
      .fill(k === 1 ? "1" : "0");
  }
  const sectionResponse = page.waitForResponse((r) =>
    r.url().endsWith(`/runs/${run.id}/sections`),
  );
  await page
    .getByRole("button", { name: "Generate volume section", exact: true })
    .click();
  const received = await sectionResponse;
  expect(received.status()).toBe(200);
  const section: components["schemas"]["ResultInspection"] =
    await received.json();
  expect(new Set(section.vertices.map((v) => v.body_id)).size).toBe(2);
  expect(
    section.vertices.every((v) => Math.abs(v.position_m[1] - 0.5) < 1e-12),
  ).toBe(true);
  expect(
    section.vertices.every(
      (v) => Math.abs(v.stress.tensor_pa[0] + 1000) <= 0.01,
    ),
  ).toBe(true);
  await expect(page.getByLabel("Calculated result viewport")).toHaveAttribute(
    "data-result-section",
    "volume",
  );
  await page.screenshot({
    path: info.outputPath("assembly-volume-inspection.png"),
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  const original = await (
    await page.request.get(`/api/v1/jobs/${run.id}/artifacts/results.json`)
  ).text();
  await page.reload();
  await page.getByLabel("Open project").selectOption(projectId);
  await page.getByLabel("Open analysis").selectOption(analysisId);
  await expect(page.getByLabel("Saved bonds", { exact: true })).toContainText(
    "Reviewed zero gap",
  );
  expect(
    await (
      await page.request.get(`/api/v1/jobs/${run.id}/artifacts/results.json`)
    ).text(),
  ).toBe(original);
});
