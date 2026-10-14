import { expect, test } from "@playwright/test";
import { resolve } from "node:path";
import { prepared, mesh } from "./support/runs";
import type { components } from "../../packages/contracts/api";
type Geometry = components["schemas"]["GeometryRevision"];
async function completedMesh(page: import("@playwright/test").Page) {
  const job = await mesh(page);
  return (await (
    await page.request.get(`/api/v1/jobs/${job.id}`)
  ).json()) as components["schemas"]["LocalJob"];
}

test("real mesh sizes, quality overlay, unit persistence and explicit coarsening", async ({
  page,
}, testInfo) => {
  test.setTimeout(45_000);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const { projectId, analysisId } = await prepared(
    page,
    "Mesh controls reference",
  );
  await expect(
    page.getByRole("button", { name: "Generate local mesh", exact: true }),
  ).toBeEnabled();
  const original = await completedMesh(page);
  await page
    .getByRole("button", { name: "Clear selection", exact: true })
    .click();
  const geometry: Geometry = (
    await (
      await page.request.get(`/api/v1/projects/${projectId}/geometry`)
    ).json()
  ).items[0];
  await page.locator(`[data-face-id="${geometry.faces[0].id}"]`).click();
  await page.getByLabel("Global mesh size (mm)", { exact: true }).fill("500");
  await page.getByLabel("Local mesh size (mm)", { exact: true }).fill("250");
  await page
    .getByRole("button", { name: "Add local mesh size", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Generate local mesh", exact: true }),
  ).toBeDisabled();
  await page
    .getByLabel(
      "I allow two additional disclosed meshing attempts with unchanged sizing",
    )
    .check();
  await page
    .getByRole("button", { name: "Preview mesh estimate", exact: true })
    .click();
  await expect(
    page.getByText("Estimate only. Saved mesh controls are unchanged.", {
      exact: true,
    }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Save mesh controls", exact: true })
    .click();
  await expect(
    page.getByText(
      "Mesh controls saved in a new analysis revision. Old jobs retain their sizes.",
      { exact: true },
    ),
  ).toBeVisible();
  const refined = await completedMesh(page);
  expect(Number(refined.summary.elements)).toBeGreaterThan(
    Number(original.summary.elements),
  );
  await page
    .getByRole("button", { name: "Preview selected mesh", exact: true })
    .click();
  await page
    .getByLabel(
      "Mesh quality overlay (all cell wireframes; face picking disabled)",
    )
    .check();
  await expect(page.getByText(/certified Jacobian lower bound/)).toBeVisible();
  const pixels = await page
    .getByLabel("Geometry viewport")
    .screenshot({ path: testInfo.outputPath("mesh-quality.png") });
  expect(pixels.length).toBeGreaterThan(5_000);
  await page
    .getByRole("combobox", { name: "Display units", exact: true })
    .selectOption("m-N-Pa");
  await expect(
    page.getByLabel("Global mesh size (m)", { exact: true }),
  ).toHaveValue("0.5");
  await page.getByRole("button", { name: /Remove local mesh control/ }).click();
  await page.getByLabel("Global mesh size (m)", { exact: true }).fill("0.01");
  await page
    .getByRole("button", { name: "Preview mesh estimate", exact: true })
    .click();
  await expect(page.getByText(/Proposed coarser global size:/)).toBeVisible();
  await page
    .getByRole("button", { name: "Save mesh controls", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Generate local mesh", exact: true }),
  ).toBeDisabled();
  const stored = await (
    await page.request.get(`/api/v1/analyses/${analysisId}/mesh-controls`)
  ).json();
  expect(stored.setup.global_size_m).toBe(0.01);
  await page
    .getByRole("button", {
      name: "Use coarsening proposal in draft (clear local sizes, curvature off)",
      exact: true,
    })
    .click();
  expect(
    (
      await (
        await page.request.get(`/api/v1/analyses/${analysisId}/mesh-controls`)
      ).json()
    ).setup.global_size_m,
  ).toBe(0.01);
  await page
    .getByRole("button", { name: "Save mesh controls", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Generate local mesh", exact: true }),
  ).toBeEnabled();
  await page.reload();
  await page.getByLabel("Open project").selectOption(projectId);
  await page.getByLabel("Open analysis").selectOption(analysisId);
  await expect(
    page.getByRole("button", { name: "Generate local mesh", exact: true }),
  ).toBeEnabled();
  expect(errors).toEqual([]);
});

async function imported(
  page: import("@playwright/test").Page,
  fixture: string,
  name: string,
) {
  await page.goto("/");
  await page.getByLabel("New project name").fill(name);
  await page
    .getByRole("button", { name: "Create project", exact: true })
    .click();
  await page
    .getByLabel("STEP file")
    .setInputFiles(resolve(`tests/fixtures/geometry/${fixture}`));
  await page
    .getByRole("button", { name: "Upload and inspect", exact: true })
    .click();
  await page.getByLabel("I confirm the dimensions and body count").check();
  await page
    .getByRole("button", { name: "Accept geometry", exact: true })
    .click();
  await expect(
    page.getByText("Geometry accepted and saved.", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("New analysis name").fill(name);
  await page
    .getByRole("button", {
      name: "Create analysis for this geometry",
      exact: true,
    })
    .click();
  await expect(
    page.getByLabel("Global mesh size (mm)", { exact: true }),
  ).toBeVisible();
}

test("actual curved quadratic mesh preview before loads and bounded failed-quality recovery", async ({
  page,
}, testInfo) => {
  test.setTimeout(45_000);
  await imported(page, "cylinder-m.step", "Curved mesh inspection");
  const curved = await completedMesh(page);
  expect((curved.summary.quality as { all_affine: boolean }).all_affine).toBe(
    false,
  );
  await page
    .getByRole("button", { name: "Preview selected mesh", exact: true })
    .click();
  await page
    .getByLabel(
      "Mesh quality overlay (all cell wireframes; face picking disabled)",
    )
    .check();
  await page
    .getByLabel(
      "I reviewed the selected mesh and current small-deformation linear elastic inputs",
    )
    .check();
  await expect(
    page.getByRole("button", { name: "Solve selected mesh", exact: true }),
  ).toBeDisabled();
  await page.screenshot({
    path: testInfo.outputPath("curved-mesh.png"),
    fullPage: true,
  });
  await imported(page, "sliver-m.step", "Recovery exhaustion");
  await page
    .getByLabel(
      "I allow two additional disclosed meshing attempts with unchanged sizing",
    )
    .check();
  await page
    .getByRole("button", { name: "Save mesh controls", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Generate local mesh", exact: true }),
  ).toBeEnabled();
  const response = page.waitForResponse(
    (r) => r.url().endsWith("/mesh-jobs") && r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Generate local mesh", exact: true })
    .click();
  const job = await (await response).json();
  await expect(page.locator(`[data-job-id="${job.id}"]`)).toHaveAttribute(
    "data-job-status",
    "failed",
  );
  await expect(
    page.getByLabel("Mesh recovery attempts").getByRole("listitem"),
  ).toHaveCount(3);
  await page
    .getByRole("button", {
      name: `Inspect failed mesh quality ${job.id.slice(0, 8)}`,
      exact: true,
    })
    .click();
  await expect(page.getByText(/FAILED — solve blocked/)).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Solve selected mesh", exact: true }),
  ).toBeDisabled();
  await page.screenshot({
    path: testInfo.outputPath("failed-quality.png"),
    fullPage: true,
  });
});

test("mesh recovery permission waits for the real saved settings before editing", async ({
  page,
}) => {
  let release = () => {};
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/v1/analyses/*/mesh-controls", async (route) => {
    if (route.request().method() === "GET") await gate;
    await route.continue();
  });
  try {
    await imported(page, "cube-m.step", "Mesh settings readiness");
    const permission = page.getByLabel(
      "I allow two additional disclosed meshing attempts with unchanged sizing",
    );
    const save = page.getByRole("button", {
      name: "Save mesh controls",
      exact: true,
    });
    await expect(permission).toBeDisabled();
    await expect(save).toBeDisabled();
    await expect(
      page.getByLabel("Global mesh size (mm)", { exact: true }),
    ).toBeDisabled();
    release();
    await expect(permission).toBeEnabled();
    await permission.check();
    const saved = page.waitForResponse(
      (response) =>
        response.url().endsWith("/mesh-controls") &&
        response.request().method() === "PUT",
    );
    await save.click();
    const response = await saved;
    expect(response.status()).toBe(200);
    expect((await response.json()).setup.recovery_enabled).toBe(true);
    await expect(permission).toBeEnabled();
    await expect(permission).toBeChecked();
    const project = await page.getByLabel("Open project").inputValue();
    const analysis = await page.getByLabel("Open analysis").inputValue();
    await page.reload();
    await page.getByLabel("Open project").selectOption(project);
    await page.getByLabel("Open analysis").selectOption(analysis);
    await expect(permission).toBeEnabled();
    await expect(permission).toBeChecked();
  } finally {
    release();
  }
});
