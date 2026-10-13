import { expect, test } from "@playwright/test";
import { resolve } from "node:path";
import { readFile } from "node:fs/promises";
import type { components } from "../../packages/contracts/api";

type Geometry = components["schemas"]["GeometryRevision"];
type Loads = components["schemas"]["LoadState"];

test("saved face loads, pressure arrows, immutable real deck downloads and conflicts", async ({
  page,
}, testInfo) => {
  test.setTimeout(45_000);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await page.getByLabel("New project name").fill("Face loads reference");
  await page
    .getByRole("button", { name: "Create project", exact: true })
    .click();
  await page
    .getByLabel("STEP file")
    .setInputFiles(resolve("tests/fixtures/geometry/cube-m.step"));
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
  const projectId = await page.getByLabel("Open project").inputValue();
  const geometry: Geometry = (
    await (
      await page.request.get(`/api/v1/projects/${projectId}/geometry`)
    ).json()
  ).items[0];
  const faces = geometry.faces.filter(
    (f) => f.body_id === geometry.bodies[0].id,
  );
  const fixed = faces.find((f) => (f.signature.center_m as number[])[0] === 0)!;
  const loaded = faces.find(
    (f) => (f.signature.center_m as number[])[0] === 1,
  )!;
  await page.getByLabel("New analysis name").fill("Face load setup");
  await page
    .getByRole("button", {
      name: "Create analysis for this geometry",
      exact: true,
    })
    .click();
  await expect(page.getByLabel("Material body")).toBeVisible();
  const analysisId = await page.getByLabel("Open analysis").inputValue();
  await page.getByLabel("Material example").selectOption("al-6061-t6-rod");
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
    .selectOption("force");
  await page.getByLabel("Assignment name").fill("End force");
  await page.getByLabel("Total force X (N)", { exact: true }).fill("1000");
  await page.getByLabel("Total force Y (N)", { exact: true }).fill("0");
  await page.getByLabel("Total force Z (N)", { exact: true }).fill("0");
  await page
    .getByRole("button", { name: "Save face assignment", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Remove End force", exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel("Geometry viewport")).toHaveAttribute(
    "data-load-markers",
    "2",
  );
  await page
    .getByRole("combobox", { name: "Face assignment", exact: true })
    .selectOption("pressure");
  await page.getByLabel("Assignment name").fill("Inward pressure");
  await page.getByLabel("Pressure (MPa)", { exact: true }).fill("0.001");
  await expect(
    page.getByRole("button", { name: "Save face assignment", exact: true }),
  ).toBeDisabled();
  await page
    .getByLabel(
      "I confirm these overlapping loads combine with the saved loads",
    )
    .check();
  await page
    .getByRole("button", { name: "Save face assignment", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Remove Inward pressure", exact: true }),
  ).toBeVisible();
  const state: Loads = await (
    await page.request.get(`/api/v1/analyses/${analysisId}/loads`)
  ).json();
  const pressureMarker = state.markers.find((m) => m.kind === "pressure")!;
  expect(pressureMarker.direction).toEqual([-1, 0, 0]);
  expect(pressureMarker.tip_on_face).toBe(true);
  expect(state.total_force_n).toEqual([0, 0, 0]);
  await page.getByLabel("Display detail").selectOption("fine");
  await expect(page.getByLabel("Geometry viewport")).toHaveAttribute(
    "data-load-markers",
    "3",
  );
  await page
    .getByRole("button", { name: "Isolate body 1", exact: true })
    .click();
  await page.getByRole("button", { name: "Isometric", exact: true }).click();
  await page
    .getByRole("button", { name: "Generate checked deck", exact: true })
    .click();
  const exports = page.getByLabel("Saved deck exports");
  await expect(
    exports.getByRole("link", { name: "Download analysis.inp", exact: true }),
  ).toBeVisible();
  const href = await exports
    .getByRole("link", { name: "Download analysis.inp", exact: true })
    .getAttribute("href");
  const downloadEvent = page.waitForEvent("download");
  await exports
    .getByRole("link", { name: "Download analysis.inp", exact: true })
    .click();
  const download = await downloadEvent;
  const deck = await readFile((await download.path())!, "utf8");
  expect(download.suggestedFilename()).toBe("analysis.inp");
  expect(deck).toContain("*ELEMENT,TYPE=C3D10");
  expect(deck).toContain("*CLOAD\n");
  expect(deck).toContain("*DLOAD\n");
  await page.screenshot({
    path: testInfo.outputPath("face-loads.png"),
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Remove Inward pressure", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Remove Inward pressure", exact: true }),
  ).not.toBeVisible();
  expect(await (await page.request.get(href!)).text()).toBe(deck);
  // A separate HTTP session edit makes the visible browser revision stale.
  const session = await (await page.request.get("/api/v1/session")).json();
  const saved: Loads = await (
    await page.request.get(`/api/v1/analyses/${analysisId}/loads`)
  ).json();
  const changed = await page.request.patch(
    `/api/v1/analyses/${analysisId}/display-units`,
    {
      headers: {
        "X-CSRF-Token": session.csrf_token,
        "If-Match": `"${saved.analysis_revision}"`,
      },
      data: { preset: "m-N-Pa" },
    },
  );
  expect(changed.status()).toBe(200);
  await page
    .getByRole("combobox", { name: "Face assignment", exact: true })
    .selectOption("fixed");
  await page.getByLabel("Assignment name").fill("Stale edit");
  await page
    .getByRole("button", { name: "Save face assignment", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "Reload the saved analysis",
  );
  await expect(
    page.getByRole("button", { name: "Save face assignment", exact: true }),
  ).toBeDisabled();
  await page
    .getByRole("button", {
      name: "Reload saved analysis (discard edits)",
      exact: true,
    })
    .click();
  await expect(page.getByLabel("Display units")).toHaveValue("m-N-Pa");
  await expect(
    exports.getByRole("link", { name: "Download analysis.inp", exact: true }),
  ).toBeVisible();
  await page.reload();
  await page.getByLabel("Open project").selectOption(projectId);
  await page.getByLabel("Open analysis").selectOption(analysisId);
  await expect(
    page.getByRole("button", { name: "Remove End force", exact: true }),
  ).toBeVisible();
  await expect(
    page
      .getByLabel("Saved deck exports")
      .getByRole("link", { name: "Download analysis.inp", exact: true }),
  ).toBeVisible();
  await page.getByLabel("Open analysis").selectOption("");
  await expect(page.getByLabel("Geometry viewport")).toHaveAttribute(
    "data-load-markers",
    "0",
  );
  await page.getByLabel("Open analysis").selectOption(analysisId);
  await expect(page.getByLabel("Geometry viewport")).toHaveAttribute(
    "data-load-markers",
    "2",
  );
  expect(errors).toEqual([]);
});
