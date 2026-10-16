import { expect, test } from "@playwright/test";
import { readFile } from "node:fs/promises";
import { reference } from "./support/reference";
import { prepared, mesh, solve } from "./support/runs";

test("review diagnostic contents and round-trip an owned project archive", async ({
  page,
}, info) => {
  test.setTimeout(45_000);
  const failures: string[] = [];
  page.on("pageerror", (e) => failures.push(e.message));
  const { projectId } = await prepared(
    page,
    "T027 synthetic archive",
    false,
    0.000001,
  );
  await mesh(page);
  const run = await solve(page);
  await expect(page.locator(`[data-job-id="${run.id}"]`)).toHaveAttribute(
    "data-job-status",
    "succeeded",
  );
  const panel = page.getByRole("region", {
    name: "Portable archives and diagnostics",
  });
  await expect(
    panel.getByLabel("Include geometry (reveals coordinates)", { exact: true }),
  ).not.toBeChecked();
  await expect(
    panel.getByLabel("Include results (reveals coordinates)", { exact: true }),
  ).not.toBeChecked();
  const previewResponse = page.waitForResponse(
    (r) =>
      r.url().endsWith("/diagnostic-previews") &&
      r.request().method() === "POST",
  );
  await panel
    .getByRole("button", { name: "Preview diagnostic bundle", exact: true })
    .click();
  const preview = await (await previewResponse).json();
  expect(Object.keys(preview.manifest.files)).toEqual(["diagnostic.json"]);
  await expect(
    panel.getByText("Geometry excluded", { exact: true }),
  ).toBeVisible();
  await expect(
    panel.getByText("Results excluded", { exact: true }),
  ).toBeVisible();
  await panel
    .getByRole("button", { name: "Preview diagnostic bundle", exact: true })
    .scrollIntoViewIfNeeded();
  await page.screenshot({
    path: info.outputPath("diagnostic-preview.png"),
    fullPage: false,
  });
  await reference(
    page,
    info,
    "archive-01-diagnostics",
    "Diagnostic preview with geometry and results excluded",
    panel,
  );
  const diagnosticDownload = page.waitForEvent("download");
  await panel
    .getByRole("link", {
      name: "Download reviewed diagnostic bundle",
      exact: true,
    })
    .click();
  const diagnostic = await diagnosticDownload;
  const diagnosticBytes = await readFile((await diagnostic.path())!);
  expect(diagnosticBytes.includes(Buffer.from(projectId))).toBe(false);
  await panel
    .getByLabel("Include available meshes, results and reports", {
      exact: true,
    })
    .check();
  await panel
    .getByRole("button", { name: "Preview project archive", exact: true })
    .click();
  const link = panel.getByRole("link", {
    name: "Download reviewed project archive",
    exact: true,
  });
  await expect(link).toBeVisible();
  await reference(
    page,
    info,
    "archive-02-portable",
    "Portable project archive preview",
    panel,
  );
  const downloadPromise = page.waitForEvent("download");
  await link.click();
  const download = await downloadPromise;
  await panel
    .getByLabel("Project archive ZIP", { exact: true })
    .setInputFiles((await download.path())!);
  const importedResponse = page.waitForResponse(
    (r) =>
      r.url().endsWith("/archive-imports") && r.request().method() === "POST",
  );
  await panel
    .getByRole("button", { name: "Import project archive", exact: true })
    .click();
  expect((await importedResponse).status()).toBe(201);
  const chooser = page.getByRole("combobox", {
    name: "Open project",
    exact: true,
  });
  await expect(chooser).not.toHaveValue(projectId);
  await expect(chooser).not.toHaveValue("");
  const importedProject = await chooser.inputValue();
  // Verify the real imported record through its owned discovery endpoint and UI.
  const discovery = await page.request.get(
    `/api/v1/projects/${importedProject}/archive-imports`,
  );
  expect(discovery.status()).toBe(200);
  const [imported] = await discovery.json();
  expect(imported.project.id).toBe(importedProject);
  await expect(
    panel.getByLabel("Imported read-only history", { exact: true }),
  ).toBeVisible();
  await panel.locator("details").last().locator("summary").click();
  await expect(
    panel
      .getByRole("link", {
        name: "Download historical analysis.inp",
        exact: true,
      })
      .last(),
  ).toBeVisible();
  await page.reload();
  await page
    .getByRole("combobox", { name: "Open project", exact: true })
    .selectOption(imported.project.id);
  await expect(
    panel.getByLabel("Imported read-only history", { exact: true }),
  ).toBeVisible();
  await reference(
    page,
    info,
    "archive-03-restored",
    "Reimported project with inert historical downloads",
    panel,
  );
  expect(failures).toEqual([]);
  await panel
    .getByRole("heading", { name: "Portable archives", exact: true })
    .scrollIntoViewIfNeeded();
  await page.screenshot({
    path: info.outputPath("archive-roundtrip.png"),
    fullPage: false,
  });
});
