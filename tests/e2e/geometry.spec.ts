import { expect, test } from "@playwright/test";
import type { components } from "../../packages/contracts/api";
import { resolve } from "node:path";

test("curved STEP picks survive actual triangle-count changes and replacement never mixes revisions", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("New project name").fill("Curved viewport fixture");
  await page
    .getByRole("button", { name: "Create project", exact: true })
    .click();
  for (const file of ["two-m.step", "cylinder-m.step"]) {
    await page
      .getByLabel("STEP file")
      .setInputFiles(resolve(`tests/fixtures/geometry/${file}`));
    await page
      .getByRole("button", { name: "Upload and inspect", exact: true })
      .click();
    await expect(
      page.getByLabel("I confirm the dimensions and body count"),
    ).toBeVisible();
    await page.getByLabel("I confirm the dimensions and body count").check();
    if (file === "cylinder-m.step") {
      // Hold the real response so the replacement guard is exercised before data arrives.
      await page.route("**/geometry/*/display?lod=coarse", async (route) => {
        const response = await route.fetch();
        await new Promise((resolve) => setTimeout(resolve, 300));
        await route.fulfill({ response });
      });
    }
    await page
      .getByRole("button", { name: "Accept geometry", exact: true })
      .click();
    if (file === "cylinder-m.step") {
      await expect(
        page.getByRole("heading", { name: "Loading geometry…", exact: true }),
      ).toBeVisible();
    }
    await expect(page.getByLabel("Geometry viewport")).toBeVisible();
  }
  await expect(page.locator(".viewport-caption")).toContainText(
    "1 bodies · 3 faces",
  );
  await page.unrouteAll({ behavior: "wait" });
  const revision = await page
    .getByLabel("Geometry viewport")
    .getAttribute("data-revision");
  const coarseCount = await page.locator(".viewport-caption").textContent();
  await page.getByRole("button", { name: "Front", exact: true }).click();
  const bounds = await page
    .getByLabel("Geometry viewport")
    .locator("canvas")
    .boundingBox();
  await page.mouse.click(
    bounds!.x + bounds!.width / 2,
    bounds!.y + bounds!.height / 2,
  );
  await expect(page.locator("[data-selected-face]")).toHaveCount(1);
  const selected = await page
    .locator("[data-selected-face]")
    .getAttribute("data-selected-face");
  const fine = page.waitForResponse(
    (r) =>
      r.url().includes(`/geometry/${revision}/display?lod=fine`) &&
      r.status() === 200,
  );
  await page.getByLabel("Display detail").selectOption("fine");
  await fine;
  await expect(page.locator(".viewport-caption")).not.toHaveText(coarseCount!);
  await expect(page.locator("[data-selected-face]")).toHaveAttribute(
    "data-selected-face",
    selected!,
  );
  const response = await page.request.get(`/api/v1/geometry/${revision}`);
  const geometry: components["schemas"]["GeometryRevision"] =
    await response.json();
  const face = geometry.faces.find((f) => f.id === selected);
  expect(face?.body_id).toBe(geometry.bodies[0].id);
  expect((face?.signature.center_m as number[])[2]).toBeCloseTo(1, 9);
});

test("real multibody STEP, vtk picking, camera and LOD preserve catalog references", async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await page.getByLabel("New project name").fill("Two-body viewport fixture");
  await page
    .getByRole("button", { name: "Create project", exact: true })
    .click();
  await page
    .getByLabel("STEP file")
    .setInputFiles(resolve("tests/fixtures/geometry/two-m.step"));
  await page
    .getByRole("button", { name: "Upload and inspect", exact: true })
    .click();
  await expect(page.getByText("2 solid bodies · 12 faces")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Accept geometry", exact: true }),
  ).toBeDisabled();
  await page.getByLabel("I confirm the dimensions and body count").check();
  await page
    .getByRole("button", { name: "Accept geometry", exact: true })
    .click();
  await expect(
    page.getByText("2 bodies · 12 faces · 24 display triangles"),
  ).toBeVisible();
  const viewport = page.getByLabel("Geometry viewport");
  const revision = await viewport.getAttribute("data-revision");
  const response = await page.request.get(`/api/v1/geometry/${revision}`);
  const geometry: components["schemas"]["GeometryRevision"] =
    await response.json();
  await page.getByRole("button", { name: "Front", exact: true }).click();
  const canvas = viewport.locator("canvas");
  const bounds = await canvas.boundingBox();
  expect(bounds).not.toBeNull();
  await page.mouse.click(
    bounds!.x + bounds!.width / 3,
    bounds!.y + bounds!.height / 2,
  );
  await expect(
    page.getByRole("heading", { name: "1 selected faces", exact: true }),
  ).toBeVisible();
  const selected = await page
    .locator("[data-selected-face]")
    .getAttribute("data-selected-face");
  const face = geometry.faces.find((f) => f.id === selected);
  expect(face?.body_id).toBe(geometry.bodies[0].id);
  expect((face?.signature.center_m as number[])[2]).toBeCloseTo(1, 9);
  const loaded = page.waitForResponse(
    (r) =>
      r.url().includes(`/geometry/${revision}/display?lod=fine`) &&
      r.status() === 200,
  );
  await page.getByLabel("Display detail").selectOption("fine");
  await loaded;
  await expect(page.locator("[data-selected-face]")).toHaveAttribute(
    "data-selected-face",
    selected!,
  );
  await page.getByRole("button", { name: "Isometric", exact: true }).click();
  await page.mouse.move(
    bounds!.x + bounds!.width / 2,
    bounds!.y + bounds!.height / 2,
  );
  await page.mouse.down();
  await page.mouse.move(
    bounds!.x + bounds!.width / 2 + 45,
    bounds!.y + bounds!.height / 2 + 20,
    { steps: 6 },
  );
  await page.mouse.up();
  await expect(page.locator("[data-selected-face]")).toHaveAttribute(
    "data-selected-face",
    selected!,
  );
  await page
    .getByRole("button", { name: "Isolate body 2", exact: true })
    .click();
  await expect(
    page.getByRole("checkbox", { name: "Body 1", exact: true }),
  ).not.toBeChecked();
  await page.getByRole("button", { name: "Front", exact: true }).click();
  await page.mouse.click(
    bounds!.x + bounds!.width / 2,
    bounds!.y + bounds!.height / 2,
  );
  await expect(
    page.getByRole("heading", { name: "2 selected faces", exact: true }),
  ).toBeVisible();
  const selectedIDs = await page
    .locator("[data-selected-face]")
    .evaluateAll((elements) =>
      elements.map((e) => e.getAttribute("data-selected-face")),
    );
  expect(
    selectedIDs.some((id) =>
      geometry.faces.some(
        (f) => f.id === id && f.body_id === geometry.bodies[1].id,
      ),
    ),
  ).toBe(true);
  await page.getByRole("checkbox", { name: "Body 2", exact: true }).uncheck();
  const coarse = page.waitForResponse(
    (r) =>
      r.url().includes(`/geometry/${revision}/display?lod=coarse`) &&
      r.status() === 200,
  );
  await page.getByLabel("Display detail").selectOption("coarse");
  await coarse;
  await expect(
    page.getByRole("checkbox", { name: "Body 1", exact: true }),
  ).not.toBeChecked();
  await expect(
    page.getByRole("checkbox", { name: "Body 2", exact: true }),
  ).not.toBeChecked();
  await page
    .getByRole("button", { name: "Show all bodies", exact: true })
    .click();
  await page.getByRole("button", { name: "Isometric", exact: true }).click();
  await page.screenshot({ path: testInfo.outputPath("geometry-viewport.png") });
  await page.reload();
  await page
    .getByLabel("Open project")
    .selectOption({ label: "Two-body viewport fixture" });
  await expect(page.getByLabel("Geometry viewport")).toHaveAttribute(
    "data-revision",
    revision!,
  );
  expect(errors).toEqual([]);
});

test("missing units need explicit choice and failed surface import retains accepted geometry", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("New project name").fill("Units viewport fixture");
  await page
    .getByRole("button", { name: "Create project", exact: true })
    .click();
  await page
    .getByLabel("STEP file")
    .setInputFiles(resolve("tests/fixtures/geometry/cube-missing.step"));
  await page
    .getByRole("button", { name: "Upload and inspect", exact: true })
    .click();
  await expect(page.getByLabel("Source length units")).toBeVisible();
  await expect(
    page.getByRole("button", {
      name: "Inspect with selected units",
      exact: true,
    }),
  ).toBeDisabled();
  await page.getByLabel("Source length units").selectOption("mm");
  await page
    .getByRole("button", { name: "Inspect with selected units", exact: true })
    .click();
  await expect(
    page.getByText("0.00100000 × 0.00100000 × 0.00100000"),
  ).toBeVisible();
  await page.getByLabel("I confirm the dimensions and body count").check();
  await page
    .getByRole("button", { name: "Accept geometry", exact: true })
    .click();
  await expect(
    page.getByText("1 bodies · 6 faces · 12 display triangles"),
  ).toBeVisible();
  const revision = await page
    .getByLabel("Geometry viewport")
    .getAttribute("data-revision");
  await page
    .getByLabel("STEP file")
    .setInputFiles(resolve("tests/fixtures/geometry/surface-m.step"));
  await page
    .getByRole("button", { name: "Upload and inspect", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "surface-only models are unsupported",
  );
  await expect(page.getByLabel("Geometry viewport")).toHaveAttribute(
    "data-revision",
    revision!,
  );
});
