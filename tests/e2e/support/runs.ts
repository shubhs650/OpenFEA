import { expect, type Page } from "@playwright/test";
import { resolve } from "node:path";
import type { components } from "../../../packages/contracts/api";
type Geometry = components["schemas"]["GeometryRevision"];
type Job = components["schemas"]["LocalJob"];
export async function prepared(
  page: Page,
  name: string,
  bracket = false,
  yieldStrength: number | null = bracket ? 276 : null,
) {
  await page.goto("/");
  await page.getByLabel("New project name").fill(name);
  await page
    .getByRole("button", { name: "Create project", exact: true })
    .click();
  await expect(page.getByLabel("Open project")).not.toHaveValue("");
  const projectId = await page.getByLabel("Open project").inputValue();
  await page
    .getByLabel("STEP file")
    .setInputFiles(
      resolve(
        bracket
          ? "tests/fixtures/geometry/bracket-m.step"
          : "tests/fixtures/geometry/cube-m.step",
      ),
    );
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
  const geometry: Geometry = (
    await (
      await page.request.get(`/api/v1/projects/${projectId}/geometry`)
    ).json()
  ).items[0];
  await page.getByLabel("New analysis name").fill(name);
  await page
    .getByRole("button", {
      name: "Create analysis for this geometry",
      exact: true,
    })
    .click();
  await expect(page.getByLabel("Material body")).toBeVisible();
  const analysisId = await page.getByLabel("Open analysis").inputValue();
  await page
    .getByRole("textbox", { name: "Material name", exact: true })
    .fill(
      bracket ? "Synthetic bracket reference" : "Synthetic axial reference",
    );
  await page
    .getByRole("textbox", { name: "Grade", exact: true })
    .fill("Synthetic");
  await page
    .getByRole("textbox", { name: "Condition", exact: true })
    .fill("Test only");
  await page
    .getByRole("textbox", { name: "Temperature applicability", exact: true })
    .fill("20 C reference");
  await page
    .getByRole("textbox", { name: "Assumptions", exact: true })
    .fill(
      bracket
        ? "Synthetic planar bracket, E=210 GPa, nu=0.3. No certified allowable."
        : "Isotropic analytical reference, E=68.3 GPa, nu=0. No certified allowable.",
    );
  await page
    .getByLabel("Source reference 1", { exact: true })
    .fill("Independent synthetic axial fixture");
  await page
    .getByRole("spinbutton", { name: /Young's modulus E/ })
    .fill(bracket ? "210000" : "68300");
  await page
    .getByRole("spinbutton", { name: /Poisson ratio/ })
    .fill(bracket ? "0.3" : "0");
  if (yieldStrength !== null)
    await page
      .getByRole("spinbutton", { name: /Yield strength/ })
      .fill(String(yieldStrength));
  await page
    .getByLabel("I confirm the properties, condition and assumptions")
    .check();
  await page
    .getByRole("button", { name: "Apply material", exact: true })
    .click();
  await expect(
    page.getByText("Material saved in a new analysis revision.", {
      exact: true,
    }),
  ).toBeVisible();
  await page.locator(".body-tree summary").click();
  const fixed = geometry.faces.find((f) =>
    bracket
      ? Math.abs((f.signature.center_m as number[])[2] - 0.06) < 1e-10
      : (f.signature.center_m as number[])[0] === 0,
  )!;
  const loaded = geometry.faces.find((f) =>
    bracket
      ? Math.abs((f.signature.center_m as number[])[0] - 0.08) < 1e-10
      : (f.signature.center_m as number[])[0] === 1,
  )!;
  await page.locator(`[data-face-id="${fixed.id}"]`).click();
  await page.getByLabel("Assignment name").fill("Fixed root");
  await page
    .getByRole("button", { name: "Save face assignment", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Remove Fixed root", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Clear selection", exact: true })
    .click();
  await page.locator(`[data-face-id="${loaded.id}"]`).click();
  await page
    .getByRole("combobox", { name: "Face assignment", exact: true })
    .selectOption(bracket ? "force" : "pressure");
  await page.getByLabel("Assignment name").fill("Axial pressure");
  if (bracket) {
    await page.getByLabel("Total force X (N)", { exact: true }).fill("0");
    await page.getByLabel("Total force Y (N)", { exact: true }).fill("0");
    await page.getByLabel("Total force Z (N)", { exact: true }).fill("-10");
  } else {
    await page.getByLabel("Pressure (MPa)", { exact: true }).fill("0.001");
  }
  await page
    .getByRole("button", { name: "Save face assignment", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Remove Axial pressure", exact: true }),
  ).toBeVisible();
  return { projectId, analysisId };
}

export async function mesh(page: Page): Promise<Job> {
  const response = page.waitForResponse(
    (r) => r.url().endsWith("/mesh-jobs") && r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Generate local mesh", exact: true })
    .click();
  const received = await response;
  expect(received.status()).toBe(202);
  const job: Job = await received.json();
  await expect(page.locator(`[data-job-id="${job.id}"]`)).toHaveAttribute(
    "data-job-status",
    "succeeded",
  );
  await page
    .getByRole("combobox", { name: "Checked mesh", exact: true })
    .selectOption(job.id);
  return job;
}

export async function solve(page: Page): Promise<Job> {
  await page
    .getByLabel(
      "I reviewed the selected mesh and current small-deformation linear elastic inputs",
    )
    .check();
  const response = page.waitForResponse(
    (r) => r.url().endsWith("/runs") && r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Solve selected mesh", exact: true })
    .click();
  const received = await response;
  expect(received.status()).toBe(202);
  return received.json();
}
