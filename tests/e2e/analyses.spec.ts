import { expect, test, type Page } from "@playwright/test";
import { prepared, mesh, solve } from "./support/runs";

async function copy(page: Page, name: string) {
  const summary = page.getByText("Duplicate saved setup", { exact: true });
  if ((await summary.locator("..").getAttribute("open")) === null)
    await summary.click();
  await page.getByLabel("New duplicate analysis name").fill(name);
  const response = page.waitForResponse(
    (r) => r.url().endsWith("/duplicates") && r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Duplicate analysis setup", exact: true })
    .click();
  const received = await response;
  expect(received.status()).toBe(201);
  const result = await received.json();
  await expect(page.getByLabel("Open analysis")).toHaveValue(result.id);
  await expect(page.getByLabel("Save state", { exact: true })).toContainText(
    "Saved",
  );
  return result.id as string;
}
async function completed(page: Page, run: { id: string }) {
  await expect(page.locator(`[data-job-id="${run.id}"]`)).toHaveAttribute(
    "data-job-status",
    "succeeded",
  );
}

test("independent duplicated setup reuses verified mesh, solves and preserves original run history", async ({
  page,
}, info) => {
  test.setTimeout(60_000);
  const { projectId, analysisId } = await prepared(page, "T018 original");
  const originalMesh = await mesh(page);
  const originalRun = await solve(page);
  await completed(page, originalRun);
  const rawPath = `/api/v1/jobs/${originalRun.id}/artifacts/results.json`;
  const oldRaw = await (await page.request.get(rawPath)).text();
  const variant = await copy(page, "T018 half-displacement variant");
  await expect(page.getByLabel("Checked mesh")).toHaveValue(originalMesh.id);
  await expect(page.getByLabel("Local job history")).not.toContainText(
    "succeeded",
  );
  await page.getByLabel(/Young's modulus E/).fill("136600");
  await page
    .getByLabel("I confirm the properties, condition and assumptions")
    .check();
  await page
    .getByRole("button", { name: "Apply material", exact: true })
    .click();
  await expect(page.getByLabel("Save state", { exact: true })).toHaveText(
    "Saved · revision 2",
  );
  await expect(page.getByLabel("Checked mesh")).toHaveValue(originalMesh.id);
  await page
    .getByRole("button", { name: "Preview selected mesh", exact: true })
    .click();
  await expect(
    page.locator(`[data-mesh-job="${originalMesh.id}"]`),
  ).toBeVisible();
  const variantRun = await solve(page);
  await completed(page, variantRun);
  await page
    .getByRole("button", { name: "View selected results", exact: true })
    .click();
  await expect(page.getByLabel("Calculated result viewport")).toBeVisible();
  const view = await (
    await page.request.get(`/api/v1/runs/${variantRun.id}/results`)
  ).json();
  expect(view.analysis_id).toBe(variant);
  expect(
    Math.abs(view.data.displacement.maximum.value - 1000 / 136.6e9),
  ).toBeLessThanOrEqual(1e-13);
  expect(await (await page.request.get(rawPath)).text()).toBe(oldRaw);
  await page
    .getByLabel("Calculated result viewport")
    .screenshot({ path: info.outputPath("independent-variant.png") });
  await page
    .getByRole("region", { name: "Workspace edit state" })
    .screenshot({ path: info.outputPath("variant-setup.png") });
  await page.getByLabel(/Global mesh size/).fill("300");
  await page
    .getByRole("button", { name: "Save mesh controls", exact: true })
    .click();
  await expect(page.getByLabel("Checked mesh").locator("option")).toHaveCount(
    1,
  );
  await expect(
    page.getByRole("button", { name: "Solve selected mesh", exact: true }),
  ).toBeDisabled();
  await page.getByLabel("Open analysis").selectOption(analysisId);
  await expect(page.getByLabel(/Young's modulus E/)).toHaveValue("68300");
  await expect(page.getByLabel("Completed solve")).toHaveValue(originalRun.id);
  await page
    .getByRole("button", { name: "View selected results", exact: true })
    .click();
  await expect(page.getByLabel("Calculated result viewport")).toBeVisible();
  await page.reload();
  await page.getByLabel("Open project").selectOption(projectId);
  await page.getByLabel("Open analysis").selectOption(variant);
  await expect(page.getByLabel(/Global mesh size/)).toHaveValue("300");
  expect(await (await page.request.get(rawPath)).text()).toBe(oldRaw);
});

test("two real browser tabs keep analyses independent and refuse stale duplication", async ({
  page,
  context,
}) => {
  test.setTimeout(45_000);
  const { projectId, analysisId } = await prepared(
    page,
    "T018 concurrent tabs",
  );
  const other = await context.newPage();
  await other.goto("/");
  await other.getByLabel("Open project").selectOption(projectId);
  await other.getByLabel("Open analysis").selectOption(analysisId);
  await expect(other.getByLabel("Save state", { exact: true })).toHaveText(
    "Saved · revision 4",
  );
  await other
    .getByLabel("Analysis name (autosaves)")
    .fill("Other tab updated original");
  await expect(other.getByLabel("Save state", { exact: true })).toHaveText(
    "Saved · revision 5",
  );
  await page.getByText("Duplicate saved setup", { exact: true }).click();
  await page.getByLabel("New duplicate analysis name").fill("Stale attempt");
  const refused = page.waitForResponse((r) => r.url().endsWith("/duplicates"));
  await page
    .getByRole("button", { name: "Duplicate analysis setup", exact: true })
    .click();
  expect((await refused).status()).toBe(409);
  await expect(page.getByLabel("Save state", { exact: true })).toContainText(
    "Conflict",
  );
  await page
    .getByRole("button", { name: "Reload saved workspace (discard drafts)" })
    .click();
  await expect(page.getByLabel("Analysis name (autosaves)")).toHaveValue(
    "Other tab updated original",
  );
  const variant = await copy(page, "Independent tab variant");
  await other
    .getByRole("button", { name: "Refresh analyses (keep selected setup)" })
    .click();
  await expect(
    other.getByLabel("Open analysis").locator(`option[value="${variant}"]`),
  ).toHaveCount(1);
  await expect(other.getByLabel("Open analysis")).toHaveValue(analysisId);
  await page
    .getByLabel("Analysis name (autosaves)")
    .fill("Variant changed alone");
  await expect(page.getByLabel("Save state", { exact: true })).toHaveText(
    "Saved · revision 2",
  );
  await expect(other.getByLabel("Analysis name (autosaves)")).toHaveValue(
    "Other tab updated original",
  );
  await other.close();
});
