import { expect, test } from "@playwright/test";
import { prepared, mesh, solve } from "./support/runs";
import type { components } from "../../packages/contracts/api";
type Geometry = components["schemas"]["GeometryRevision"];

test("real hole preview apply undo retains setup and displays frozen old run", async ({
  page,
}, testInfo) => {
  test.setTimeout(45_000);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const { projectId, analysisId } = await prepared(
    page,
    "Cleanup frozen run",
    false,
    null,
    "hole-m.step",
  );
  const source: Geometry = (
    await (
      await page.request.get(`/api/v1/projects/${projectId}/geometry`)
    ).json()
  ).items[0];
  await page
    .getByRole("button", { name: "Clear selection", exact: true })
    .click();
  const feature = source.faces.find((f) =>
    String(f.signature.surface_type).endsWith("GeomAbs_Cylinder"),
  )!;
  await page.locator(`[data-face-id="${feature.id}"]`).click();
  await page
    .getByRole("button", { name: "Preview feature removal", exact: true })
    .click();
  await expect(page.getByLabel("Face mapping review")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Apply cleanup", exact: true }),
  ).toBeDisabled();
  await expect(page.getByLabel("Geometry viewport")).not.toHaveAttribute(
    "data-revision",
    source.id,
  );
  await page
    .getByRole("button", { name: "Show before cleanup", exact: true })
    .click();
  await expect(page.getByLabel("Geometry viewport")).toHaveAttribute(
    "data-revision",
    source.id,
  );
  await expect(
    page.getByRole("button", { name: "Generate local mesh", exact: true }),
  ).toBeDisabled();
  await page
    .getByRole("button", { name: "Show cleanup preview", exact: true })
    .click();
  await page
    .getByLabel(
      "I reviewed the geometry difference and face assignment invalidation",
    )
    .check();
  // A blank renderer compresses to under 5 KiB at this pinned viewport size.
  // Check the actual rendered canvas, alongside the retained visual evidence.
  const previewPixels = await page.getByLabel("Geometry viewport").screenshot({
    path: testInfo.outputPath("cleanup-viewport.png"),
  });
  expect(previewPixels.length).toBeGreaterThan(5_000);
  await page.screenshot({
    path: testInfo.outputPath("cleanup-preview.png"),
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Apply cleanup", exact: true })
    .click();
  await expect(
    page.getByText(
      "Cleanup applied. Mesh must be regenerated; changed face assignments need review.",
      { exact: true },
    ),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Undo applied cleanup", exact: true }),
  ).toBeEnabled();
  await expect(page.getByLabel("Geometry viewport")).not.toHaveAttribute(
    "data-revision",
    source.id,
  );
  await mesh(page);
  const run = await solve(page);
  await expect(page.locator(`[data-job-id="${run.id}"]`)).toHaveAttribute(
    "data-job-status",
    "succeeded",
  );
  const frozen = await (
    await page.request.get(`/api/v1/runs/${run.id}/results`)
  ).json();
  await page
    .getByRole("button", { name: "Undo applied cleanup", exact: true })
    .click();
  await expect(
    page.getByText(
      "Cleanup undone in a new saved revision. Original geometry and setup restored.",
      { exact: true },
    ),
  ).toBeVisible();
  await expect(page.locator(".viewport-caption")).toContainText("7 faces");
  expect(
    await (await page.request.get(`/api/v1/runs/${run.id}/results`)).json(),
  ).toEqual(frozen);
  await page
    .getByRole("button", { name: "View selected results", exact: true })
    .click();
  await expect(page.getByLabel("Calculated result viewport")).toBeVisible();
  expect(await page.getByLabel("Open analysis").inputValue()).toBe(analysisId);
  await expect(page.getByLabel("Calculated result viewport")).toHaveAttribute(
    "data-result-job",
    run.id,
  );
  await page.screenshot({
    path: testInfo.outputPath("old-run-after-undo.png"),
    fullPage: true,
  });
  expect(errors).toEqual([]);
});

test("changed face load requires explicit reselection and unsupported fillet keeps source", async ({
  page,
}) => {
  test.setTimeout(45_000);
  const { projectId, analysisId } = await prepared(
    page,
    "Changed face review",
    false,
    null,
    "fillet-m.step",
  );
  const source: Geometry = (
    await (
      await page.request.get(`/api/v1/projects/${projectId}/geometry`)
    ).json()
  ).items[0];
  await page
    .getByRole("button", { name: "Clear selection", exact: true })
    .click();
  // A planar selection is an unsupported fillet request; no geometry is published.
  await page
    .locator(
      `[data-face-id="${source.faces.find((f) => String(f.signature.surface_type).endsWith("GeomAbs_Plane"))!.id}"]`,
    )
    .click();
  await page
    .getByRole("button", { name: "Preview feature removal", exact: true })
    .click();
  await expect(
    page.getByText("Original geometry retained.", { exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel("Geometry viewport")).toHaveAttribute(
    "data-revision",
    source.id,
  );
  await page
    .getByRole("button", { name: "Cancel cleanup preview", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Clear selection", exact: true })
    .click();
  await page
    .locator(
      `[data-face-id="${source.faces.find((f) => String(f.signature.surface_type).endsWith("GeomAbs_Cylinder"))!.id}"]`,
    )
    .click();
  await page
    .getByRole("button", { name: "Preview feature removal", exact: true })
    .click();
  await page
    .getByLabel(
      "I reviewed the geometry difference and face assignment invalidation",
    )
    .check();
  await page
    .getByRole("button", { name: "Apply cleanup", exact: true })
    .click();
  await expect(
    page.getByText(
      "Cleanup applied. Mesh must be regenerated; changed face assignments need review.",
      { exact: true },
    ),
  ).toBeVisible();
  const state = await (
    await page.request.get(`/api/v1/analyses/${analysisId}/loads`)
  ).json();
  expect(
    state.setup.assignments.some(
      (a: { review_faces: string[] }) => a.review_faces.length,
    ),
  ).toBe(true);
  await expect(
    page.getByRole("button", { name: "Generate local mesh", exact: true }),
  ).toBeDisabled();
  const geometryId = state.geometry_revision_id;
  const newGeometry: Geometry = await (
    await page.request.get(`/api/v1/geometry/${geometryId}`)
  ).json();
  await page.locator(".body-tree summary").click();
  for (const assignment of state.setup.assignments.filter(
    (a: { review_faces: string[] }) => a.review_faces.length,
  )) {
    await page
      .getByRole("button", { name: "Clear selection", exact: true })
      .click();
    const oldFace = source.faces.find((f) => f.id === assignment.face_ids[0])!;
    const oldCenter = oldFace.signature.center_m as number[];
    const axis = oldCenter.findIndex((v) => v === 0 || v === 1);
    const replacement = newGeometry.faces.find(
      (f) => (f.signature.center_m as number[])[axis] === oldCenter[axis],
    )!;
    await page.locator(`[data-face-id="${replacement.id}"]`).click();
    await page
      .getByRole("button", {
        name: `Reselect faces for ${assignment.name}`,
        exact: true,
      })
      .click();
    await expect(
      page.getByRole("button", {
        name: `Reselect faces for ${assignment.name}`,
        exact: true,
      }),
    ).toHaveCount(0);
  }
  await expect(
    page.getByRole("button", { name: "Generate local mesh", exact: true }),
  ).toBeEnabled();
  await page.reload();
  await page.getByLabel("Open project").selectOption(projectId);
  await page.getByLabel("Open analysis").selectOption(analysisId);
  await expect(
    page.getByRole("button", { name: "Generate local mesh", exact: true }),
  ).toBeEnabled();
});
