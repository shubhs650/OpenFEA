import { expect, type Page } from "@playwright/test";
import { prepared } from "./runs";
import type { components } from "../../../packages/contracts/api";
type Geometry = components["schemas"]["GeometryRevision"];

export async function assembly(page: Page, onOpen?: () => Promise<void>) {
  const ids = await prepared(
    page,
    "T020 reviewed assembly",
    false,
    null,
    "bond-zero-m.step",
    false,
    onOpen,
  );
  const geometry: Geometry = (
    await (
      await page.request.get(`/api/v1/projects/${ids.projectId}/geometry`)
    ).json()
  ).items[0];
  await page.getByLabel("Material body").selectOption(geometry.bodies[1].id);
  await page.getByLabel("Material example").selectOption("al-6061-t6-rod");
  await page
    .getByRole("button", { name: "Edit as custom", exact: true })
    .click();
  await page
    .getByRole("spinbutton", { name: /Young's modulus E/ })
    .fill("68300");
  await page.getByRole("spinbutton", { name: /Poisson ratio/ }).fill("0");
  await page.getByRole("spinbutton", { name: /Yield strength/ }).fill("");
  await page
    .getByRole("textbox", { name: "Material name", exact: true })
    .fill("Synthetic axial body two");
  await page
    .getByRole("textbox", { name: "Assumptions", exact: true })
    .fill(
      "Independent analytical isotropic fixture: E=68.3 GPa, nu=0; no certified allowable.",
    );
  await page
    .getByLabel("Source reference 1", { exact: true })
    .fill("Independent axial continuum reference");
  await page.getByLabel("Source URL 1 (optional)", { exact: true }).fill("");
  await page
    .getByLabel("I confirm the properties, condition and assumptions")
    .check();
  await page
    .getByRole("button", { name: "Apply material", exact: true })
    .click();
  await expect(page.getByLabel("Material body")).toBeEnabled();
  const fixed = geometry.faces.find(
    (f) => Math.abs((f.signature.center_m as number[])[0]) < 1e-12,
  )!;
  const end = geometry.faces.find(
    (f) => Math.abs((f.signature.center_m as number[])[0] - 2) < 1e-12,
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
  await page.locator(`[data-face-id="${end.id}"]`).click();
  await page
    .getByRole("combobox", { name: "Face assignment", exact: true })
    .selectOption("pressure");
  await page.getByLabel("Assignment name").fill("End pressure");
  await page.getByLabel("Pressure (MPa)", { exact: true }).fill("0.001");
  await page
    .getByRole("button", { name: "Save face assignment", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Remove End pressure", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Clear selection", exact: true })
    .click();
  return { ...ids, geometry };
}
export async function approve(page: Page) {
  await page
    .getByRole("button", { name: "Inspect bond candidates", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Review pair 1", exact: true })
    .click();
  await page
    .getByLabel("Connection name", { exact: true })
    .fill("Reviewed zero gap");
  await page.getByLabel(/I reviewed roles, coverage/).check();
  await page
    .getByRole("button", { name: "Approve saved bond", exact: true })
    .click();
  await expect(page.getByLabel("Saved bonds", { exact: true })).toContainText(
    "Reviewed zero gap",
  );
}
