import { expect, test, type Page } from "@playwright/test";
import type { components } from "../../packages/contracts/api";
import { prepared, mesh, solve } from "./support/runs";
type Geometry = components["schemas"]["GeometryRevision"];
type View = components["schemas"]["ResultView"];

async function results(page: Page, id: string): Promise<View> {
  await expect(page.locator(`[data-job-id="${id}"]`)).toHaveAttribute(
    "data-job-status",
    "succeeded",
  );
  await page
    .getByRole("combobox", { name: "Completed solve", exact: true })
    .selectOption(id);
  const response = page.waitForResponse((r) =>
    r.url().endsWith(`/runs/${id}/results`),
  );
  await page
    .getByRole("button", { name: "View selected results", exact: true })
    .click();
  const received = await response;
  expect(received.status()).toBe(200);
  await expect(
    page.getByLabel("Calculated result viewport", { exact: true }),
  ).toHaveAttribute("data-result-job", id);
  return received.json();
}

async function component(
  page: Page,
  face: string,
  name: string,
  axis: string,
  value: string,
) {
  await page
    .getByRole("button", { name: "Clear selection", exact: true })
    .click();
  await page.locator(`[data-face-id="${face}"]`).click();
  await page
    .getByRole("combobox", { name: "Face assignment", exact: true })
    .selectOption("displacement");
  await page.getByLabel("Assignment name", { exact: true }).fill(name);
  await page
    .getByRole("combobox", { name: "Prescribed global component", exact: true })
    .selectOption(axis);
  await page
    .getByLabel("Prescribed displacement (mm)", { exact: true })
    .fill(value);
  await page
    .getByRole("button", { name: "Save face assignment", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: `Remove ${name}`, exact: true }),
  ).toBeVisible();
}

test("real body gravity and prescribed component persist across units with frozen equilibrium", async ({
  page,
}, testInfo) => {
  test.setTimeout(45_000);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const { projectId, analysisId } = await prepared(
    page,
    "Gravity and prescribed displacement",
  );
  const geometry: Geometry = (
    await (
      await page.request.get(`/api/v1/projects/${projectId}/geometry`)
    ).json()
  ).items[0];
  await page
    .getByRole("button", { name: "Remove Axial pressure", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Remove Axial pressure", exact: true }),
  ).toHaveCount(0);
  await page
    .getByRole("combobox", { name: "Face assignment", exact: true })
    .selectOption("gravity");
  await page.getByLabel("Assignment name", { exact: true }).fill("Body weight");
  await page.getByLabel("Gravity body 1", { exact: true }).check();
  await page.getByLabel("Acceleration X (mm/s²)", { exact: true }).fill("0");
  await page.getByLabel("Acceleration Y (mm/s²)", { exact: true }).fill("0");
  await page
    .getByLabel("Acceleration Z (mm/s²)", { exact: true })
    .fill("-9806.65");
  await page
    .getByRole("button", { name: "Save body gravity", exact: true })
    .click();
  await expect(page.getByLabel("Deck blockers", { exact: true })).toContainText(
    "weight is unavailable",
  );
  await expect(
    page.getByRole("button", { name: "Generate checked deck", exact: true }),
  ).toBeDisabled();
  await page.getByRole("spinbutton", { name: /Density/ }).fill("7.85e-9");
  await page
    .getByLabel("I confirm the properties, condition and assumptions", {
      exact: true,
    })
    .check();
  await page
    .getByRole("button", { name: "Apply material", exact: true })
    .click();
  await expect(
    page.getByLabel("Deck blockers", { exact: true }),
  ).not.toContainText("density");
  const right = geometry.faces.find(
    (f) => (f.signature.center_m as number[])[0] === 1,
  )!;
  await component(page, right.id, "End motion", "x", "0.001");
  const frozenSetup = (
    await (
      await page.request.get(`/api/v1/analyses/${analysisId}/loads`)
    ).json()
  ).setup;
  expect(
    frozenSetup.assignments.find((a: { kind: string }) => a.kind === "gravity")
      .acceleration_m_s2,
  ).toEqual([0, 0, -9.80665]);
  expect(
    frozenSetup.assignments.find(
      (a: { kind: string }) => a.kind === "displacement",
    ).displacement_m,
  ).toBe(1e-6);
  await expect(
    page.getByLabel("Geometry viewport", { exact: true }),
  ).toHaveAttribute("data-load-markers", "3");
  await page
    .getByRole("button", { name: "Clear selection", exact: true })
    .click();
  await page.getByRole("button", { name: "Fit", exact: true }).click();
  const glyphImage = await page
    .getByLabel("Geometry viewport", { exact: true })
    .screenshot({ path: testInfo.outputPath("gravity-component-glyphs.png") });
  const brownPixels = await page.evaluate(async (encoded) => {
    const image = new Image();
    image.src = `data:image/png;base64,${encoded}`;
    await image.decode();
    const canvas = document.createElement("canvas");
    canvas.width = image.width;
    canvas.height = image.height;
    const context = canvas.getContext("2d")!;
    context.drawImage(image, 0, 0);
    const pixels = context.getImageData(0, 0, image.width, image.height).data;
    let count = 0;
    for (let i = 0; i < pixels.length; i += 4) {
      if (
        pixels[i] > 120 &&
        pixels[i] < 210 &&
        pixels[i + 1] > 45 &&
        pixels[i + 1] < 130 &&
        pixels[i + 2] < 40
      )
        count++;
    }
    return count;
  }, glyphImage.toString("base64"));
  expect(brownPixels).toBeGreaterThan(10);
  await mesh(page);
  const run = await solve(page);
  const view = await results(page, run.id);
  expect(view.data.equilibrium.passed).toBe(true);
  expect(view.data.reaction_force_n[2]).toBeCloseTo(76982.2025, 2);
  expect(view.data.equilibrium.prescribed_actuator_reference_n).toBeGreaterThan(
    0,
  );
  await expect(
    page.getByLabel("External equilibrium", { exact: true }),
  ).toContainText("Passed");
  await page
    .getByLabel("External equilibrium", { exact: true })
    .screenshot({ path: testInfo.outputPath("equilibrium-table.png") });
  await page
    .getByRole("combobox", { name: "Display units", exact: true })
    .selectOption("inch-lbf-psi");
  await expect(
    page.getByLabel("External equilibrium", { exact: true }),
  ).toContainText("lbf");
  expect(
    (
      await (
        await page.request.get(`/api/v1/analyses/${analysisId}/loads`)
      ).json()
    ).setup,
  ).toEqual(frozenSetup);
  expect(
    await (await page.request.get(`/api/v1/runs/${run.id}/results`)).json(),
  ).toEqual(view);
  await page.reload();
  await page.getByLabel("Open project").selectOption(projectId);
  await page.getByLabel("Open analysis").selectOption(analysisId);
  await expect(
    page.getByRole("button", { name: "Remove Body weight", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Remove End motion", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("combobox", { name: "Display units", exact: true }),
  ).toHaveValue("inch-lbf-psi");
  expect(errors).toEqual([]);
});

test("real coordinate component supports self-equilibrated pressure and near-zero absolute balance", async ({
  page,
}, testInfo) => {
  test.setTimeout(45_000);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const { projectId } = await prepared(
    page,
    "Component supports and absolute balance",
  );
  const geometry: Geometry = (
    await (
      await page.request.get(`/api/v1/projects/${projectId}/geometry`)
    ).json()
  ).items[0];
  await page
    .getByRole("button", { name: "Remove Axial pressure", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Remove Axial pressure", exact: true }),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: "Remove Fixed root", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Remove Fixed root", exact: true }),
  ).toHaveCount(0);
  for (let axis = 0; axis < 3; axis++) {
    const ref = geometry.faces.find(
      (f) => (f.signature.center_m as number[])[axis] === 0,
    )!;
    await component(page, ref.id, `Zero ${"xyz"[axis]}`, "xyz"[axis], "0");
  }
  await page
    .getByRole("button", { name: "Clear selection", exact: true })
    .click();
  for (const face of geometry.faces)
    await page.locator(`[data-face-id="${face.id}"]`).click();
  await page
    .getByRole("combobox", { name: "Face assignment", exact: true })
    .selectOption("pressure");
  await page
    .getByLabel("Assignment name", { exact: true })
    .fill("All-face compression");
  await page.getByLabel("Pressure (MPa)", { exact: true }).fill("0.001");
  await page
    .getByRole("button", { name: "Save face assignment", exact: true })
    .click();
  await expect(
    page.getByRole("button", {
      name: "Remove All-face compression",
      exact: true,
    }),
  ).toBeVisible();
  await mesh(page);
  const first = await solve(page);
  const closed = await results(page, first.id);
  expect(
    closed.data.equilibrium.applied_force_n.every((v) => Math.abs(v) < 1e-8),
  ).toBe(true);
  expect(closed.data.equilibrium.force.reference).toBeCloseTo(6000, 5);
  expect(closed.data.equilibrium.force.criterion).toBe("relative");
  await page
    .getByRole("button", { name: "Remove All-face compression", exact: true })
    .click();
  await expect(
    page.getByRole("button", {
      name: "Remove All-face compression",
      exact: true,
    }),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: "Clear selection", exact: true })
    .click();
  const loaded = geometry.faces.find(
    (f) => (f.signature.center_m as number[])[0] === 1,
  )!;
  await page.locator(`[data-face-id="${loaded.id}"]`).click();
  await page
    .getByRole("combobox", { name: "Face assignment", exact: true })
    .selectOption("force");
  await page
    .getByLabel("Assignment name", { exact: true })
    .fill("Near-zero force");
  await page
    .getByLabel("Total force X (N)", { exact: true })
    .fill("0.00000005");
  await page.getByLabel("Total force Y (N)", { exact: true }).fill("0");
  await page.getByLabel("Total force Z (N)", { exact: true }).fill("0");
  await page
    .getByRole("button", { name: "Save face assignment", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Remove Near-zero force", exact: true }),
  ).toBeVisible();
  const second = await solve(page);
  const small = await results(page, second.id);
  expect(small.data.equilibrium.force.criterion).toBe("absolute");
  expect(small.data.equilibrium.force.relative_residual).toBeNull();
  await expect(
    page.getByLabel("External equilibrium", { exact: true }),
  ).toContainText("normalized residual unavailable");
  await page
    .getByLabel("External equilibrium", { exact: true })
    .screenshot({ path: testInfo.outputPath("absolute-equilibrium.png") });
  expect(errors).toEqual([]);
});
