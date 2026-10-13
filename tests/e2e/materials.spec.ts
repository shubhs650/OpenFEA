import { expect, test, type Page } from "@playwright/test";
import { resolve } from "node:path";
import type { components } from "../../packages/contracts/api";

type MaterialState = components["schemas"]["MaterialState"];
type ProjectPage = components["schemas"]["ProjectPage"];

async function importModel(page: Page, file: string) {
  await page
    .getByLabel("STEP file")
    .setInputFiles(resolve(`tests/fixtures/geometry/${file}`));
  await page
    .getByRole("button", { name: "Upload and inspect", exact: true })
    .click();
  await page.getByLabel("I confirm the dimensions and body count").check();
  await page
    .getByRole("button", { name: "Accept geometry", exact: true })
    .click();
  await expect(page.getByLabel("Geometry viewport")).toBeVisible();
  await expect(
    page.getByText("Geometry accepted and saved.", { exact: true }),
  ).toBeVisible();
}
async function createAnalysis(page: Page, name: string) {
  await page.getByLabel("New analysis name").fill(name);
  await page
    .getByRole("button", {
      name: "Create analysis for this geometry",
      exact: true,
    })
    .click();
  await expect(page.getByLabel("Material body")).toBeVisible();
  return page.getByLabel("Open analysis").inputValue();
}
async function savedState(page: Page, id: string): Promise<MaterialState> {
  const response = await page.request.get(`/api/v1/analyses/${id}/materials`);
  expect(response.status()).toBe(200);
  return response.json();
}

test("real per-body sample/custom materials, prerequisite blockers, unit cycles and reload", async ({
  page,
}, testInfo) => {
  test.setTimeout(30_000);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await page.getByLabel("New project name").fill("Material units fixture");
  await page
    .getByRole("button", { name: "Create project", exact: true })
    .click();
  await expect(page.getByLabel("Open project")).not.toHaveValue("");
  const projectId = await page.getByLabel("Open project").inputValue();
  await importModel(page, "two-m.step");
  const analysisId = await createAnalysis(page, "Independent body setup");
  await page.getByLabel("Material example").selectOption("al-6061-t6-rod");
  await expect(
    page.getByRole("textbox", { name: "Assumptions", exact: true }),
  ).toHaveValue(/Poisson ratio 0.33 is an explicit project assumption/);
  await expect(
    page.getByRole("link", { name: "Open source 1" }),
  ).toHaveAttribute("href", /kaiseraluminum/);
  await expect(
    page.getByRole("button", { name: "Apply material", exact: true }),
  ).toBeDisabled();
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
  const first = await savedState(page, analysisId);
  expect(first.setup.assignments![0].material.properties.young_modulus_pa).toBe(
    68.3e9,
  );
  await page.getByLabel("Material body").selectOption(first.bodies[1].body_id);
  await page
    .getByRole("textbox", { name: "Material name", exact: true })
    .fill("Custom body two");
  await page
    .getByRole("textbox", { name: "Grade", exact: true })
    .fill("Synthetic fixture");
  await page
    .getByRole("textbox", { name: "Condition", exact: true })
    .fill("Test only");
  await page
    .getByRole("textbox", { name: "Temperature applicability", exact: true })
    .fill("20 °C example");
  await page
    .getByRole("textbox", { name: "Assumptions", exact: true })
    .fill("Isotropic analytical example, not a certified allowable.");
  await page
    .getByLabel("Source reference 1", { exact: true })
    .fill("Synthetic test definition");
  await page
    .getByLabel("Source URL 1 (optional)")
    .fill("https://example.org/t009-fixture");
  await page.getByLabel(/Young's modulus E/).fill("190000");
  await page.getByLabel(/Poisson ratio/).fill("0.49");
  await expect(
    page.getByRole("button", { name: "Apply material", exact: true }),
  ).toBeDisabled();
  await expect(page.getByRole("alert")).toContainText("0 ≤ ν ≤ 0.45");
  await page.getByLabel(/Poisson ratio/).fill("0.3");
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
  await expect(
    page.getByText("Gravity: unavailable — density required", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText(
      "Yield factor of safety: unavailable — yield strength required",
      { exact: true },
    ),
  ).toBeVisible();
  const saved = await savedState(page, analysisId);
  const snapshots = saved.setup.assignments;
  expect(snapshots).toHaveLength(2);
  expect(
    snapshots!.find((a) => a.body_id === first.bodies[1].body_id)?.material
      .properties,
  ).toEqual({
    young_modulus_pa: 190e9,
    poisson_ratio: 0.3,
    density_kg_m3: null,
    yield_strength_pa: null,
  });
  await page.getByLabel("Display units").selectOption("m-N-Pa");
  await expect(
    page.getByText("Display units saved. Physical values unchanged.", {
      exact: true,
    }),
  ).toBeVisible();
  await page.getByLabel(/Young's modulus E/).fill("200000000000");
  for (const preset of ["inch-lbf-psi", "mm-N-MPa", "m-N-Pa"]) {
    const response = page.waitForResponse(
      (r) => r.url().endsWith("/display-units") && r.status() === 200,
    );
    await page.getByLabel("Display units").selectOption(preset);
    await response;
    expect((await savedState(page, analysisId)).setup.assignments).toEqual(
      snapshots,
    );
  }
  await expect(page.getByLabel(/Young's modulus E/)).toHaveValue(
    "200000000000",
  );
  await page
    .getByRole("button", { name: "Cancel material edits", exact: true })
    .click();
  await expect(page.getByLabel(/Young's modulus E/)).toHaveValue(
    "190000000000",
  );
  await page.reload();
  await page.getByLabel("Open project").selectOption(projectId);
  await page.getByLabel("Open analysis").selectOption(analysisId);
  await expect(page.getByLabel("Display units")).toHaveValue("m-N-Pa");
  await page.getByLabel("Material body").selectOption(first.bodies[1].body_id);
  await expect(page.getByLabel(/Young's modulus E/)).toHaveValue(
    "190000000000",
  );
  expect((await savedState(page, analysisId)).setup.assignments).toEqual(
    snapshots,
  );
  await page.screenshot({
    path: testInfo.outputPath("materials-editor.png"),
    fullPage: true,
  });
  expect(errors).toEqual([]);
});

test("conflicting material edits refuse and analysis geometry remains pinned after replacement", async ({
  page,
}) => {
  test.setTimeout(30_000);
  await page.goto("/");
  await page
    .getByLabel("New project name")
    .fill("Material pin and conflict fixture");
  await page
    .getByRole("button", { name: "Create project", exact: true })
    .click();
  await importModel(page, "two-m.step");
  const originalId = await createAnalysis(page, "Original geometry setup");
  await page.getByLabel("Material example").selectOption("stainless-304");
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
  const original = await savedState(page, originalId);
  const session = await (await page.request.get("/api/v1/session")).json();
  const changed = await page.request.patch(
    `/api/v1/analyses/${originalId}/display-units`,
    {
      headers: {
        "X-CSRF-Token": session.csrf_token,
        "If-Match": `"${original.analysis_revision}"`,
      },
      data: { preset: "m-N-Pa" },
    },
  );
  expect(changed.status()).toBe(200);
  await page.getByLabel(/Young's modulus E/).fill("100000");
  await page
    .getByLabel("I confirm the properties, condition and assumptions")
    .check();
  await page
    .getByRole("button", { name: "Apply material", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "changed in another session",
  );
  expect((await savedState(page, originalId)).setup.assignments).toEqual(
    original.setup.assignments,
  );
  await page
    .getByRole("button", {
      name: "Reload saved analysis (discard edits)",
      exact: true,
    })
    .click();
  await expect(page.getByLabel(/Young's modulus E/)).toHaveValue(
    "200000000000",
  );
  await importModel(page, "cylinder-m.step");
  const replacement = await page
    .getByLabel("Geometry viewport")
    .getAttribute("data-revision");
  expect(replacement).not.toBe(original.geometry_revision_id);
  const independent = await createAnalysis(
    page,
    "Replacement independent setup",
  );
  const empty = await savedState(page, independent);
  expect(empty.setup.assignments).toEqual([]);
  expect(empty.geometry_revision_id).toBe(replacement);
  await page.getByLabel("Open analysis").selectOption(originalId);
  await expect(page.getByLabel("Geometry viewport")).toHaveAttribute(
    "data-revision",
    original.geometry_revision_id!,
  );
  await expect(page.getByLabel("Material body").locator("option")).toHaveCount(
    2,
  );
  expect((await savedState(page, originalId)).setup.assignments).toEqual(
    original.setup.assignments,
  );
  await page.getByLabel("Open analysis").selectOption("");
  await expect(page.getByLabel("Geometry viewport")).toHaveAttribute(
    "data-revision",
    replacement!,
  );
  const projects = (await (
    await page.request.get("/api/v1/projects")
  ).json()) as ProjectPage;
  expect(
    projects.items.some((p) => p.name === "Material pin and conflict fixture"),
  ).toBe(true);
});
