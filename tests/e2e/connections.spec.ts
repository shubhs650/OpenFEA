import { expect, test, type Page } from "@playwright/test";
import { resolve } from "node:path";

async function prepared(page: Page, fixture = "bond-gap-m.step") {
  await page.goto("/");
  await page.getByLabel("New project name").fill("T019 connection review");
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
  await page.getByLabel("New analysis name").fill("Reviewed assembly");
  await page
    .getByRole("button", {
      name: "Create analysis for this geometry",
      exact: true,
    })
    .click();
  await expect(
    page.getByLabel("Bond connections", { exact: true }),
  ).toBeVisible();
  return {
    analysisId: await page.getByLabel("Open analysis").inputValue(),
    projectId: await page.getByLabel("Open project").inputValue(),
  };
}

async function inspect(page: Page) {
  const response = page.waitForResponse(
    (r) =>
      r.url().endsWith("/bond-candidates") && r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Inspect bond candidates", exact: true })
    .click();
  expect((await response).status()).toBe(200);
}

test("real gap suggestion needs explicit review, master/slave preview, tolerance approval and persists", async ({
  page,
}, info) => {
  test.setTimeout(60_000);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const { analysisId, projectId } = await prepared(page);
  await inspect(page);
  await expect(page.getByLabel("Saved bonds", { exact: true })).toBeEmpty();
  await expect(
    page.getByLabel("Bond suggestions", { exact: true }),
  ).toContainText("1.000000e-5");
  await page
    .getByRole("button", { name: "Review pair 1", exact: true })
    .click();
  await expect(page.getByLabel("Bond pair measurements")).toContainText(
    "100.000000% / 100.000000%",
  );
  const master = await page
    .getByLabel("Master face", { exact: true })
    .inputValue();
  await page
    .getByRole("button", { name: "Swap master/slave", exact: true })
    .click();
  await expect(page.getByLabel("Slave face", { exact: true })).toHaveValue(
    master,
  );
  await page
    .getByRole("button", { name: "Preview pair normals", exact: true })
    .click();
  await page
    .getByLabel("Connection name", { exact: true })
    .fill("Explicit 10 µm gap");
  await page.getByLabel(/I reviewed roles, coverage/).check();
  await expect(
    page.getByRole("button", { name: "Approve saved bond", exact: true }),
  ).toBeDisabled();
  await page
    .getByLabel("Approved gap tolerance (m)", { exact: true })
    .fill("0.00001");
  await expect(
    page.getByRole("button", { name: "Approve saved bond", exact: true }),
  ).toBeDisabled();
  await page.getByLabel(/I explicitly approve this physical gap/).check();
  await page.screenshot({
    path: info.outputPath("bond-gap-review.png"),
    fullPage: true,
  });
  const saved = page.waitForResponse(
    (r) => r.url().endsWith("/bonds") && r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Approve saved bond", exact: true })
    .click();
  expect((await saved).status()).toBe(200);
  await expect(page.getByLabel("Saved bonds", { exact: true })).toContainText(
    "Explicit 10 µm gap",
  );
  await expect(page.getByLabel("Save state", { exact: true })).toHaveText(
    "Saved · revision 2",
  );
  const original = await (
    await page.request.get(`/api/v1/analyses/${analysisId}/bonds`)
  ).json();
  expect(original.setup.assignments[0].gap_approved).toBe(true);
  expect(original.solve_blockers.join(" ")).toContain("cannot be ignored");
  await page.reload();
  await page.getByLabel("Open project").selectOption(projectId);
  await page.getByLabel("Open analysis").selectOption(analysisId);
  await expect(page.getByLabel("Saved bonds", { exact: true })).toContainText(
    "Explicit 10 µm gap",
  );
  expect(
    await (
      await page.request.get(`/api/v1/analyses/${analysisId}/bonds`)
    ).json(),
  ).toEqual(original);
  await page
    .getByRole("button", { name: "Remove Explicit 10 µm gap", exact: true })
    .click();
  await expect(page.getByLabel("Saved bonds", { exact: true })).toBeEmpty();
  const history = await (
    await page.request.get(`/api/v1/analyses/${analysisId}/revisions/2/bonds`)
  ).json();
  expect(history.setup).toEqual(original.setup);
  expect(errors).toEqual([]);
});

test("real partial coverage, excessive gap and body volume overlap never autoapprove", async ({
  page,
}) => {
  test.setTimeout(60_000);
  for (const [fixture, message] of [
    ["bond-partial-m.step", "Partial projected coverage"],
    ["bond-excess-m.step", "Gap exceeds"],
    ["bond-overlap-m.step", "Body volume overlap"],
  ]) {
    await prepared(page, fixture);
    await inspect(page);
    await expect(
      page.getByLabel("Bond connections", { exact: true }),
    ).toContainText(message);
    await expect(page.getByLabel("Saved bonds", { exact: true })).toBeEmpty();
    await expect(
      page.getByRole("button", { name: "Approve saved bond", exact: true }),
    ).toBeDisabled();
  }
});
