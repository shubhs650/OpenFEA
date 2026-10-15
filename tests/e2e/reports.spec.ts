import { expect, test } from "@playwright/test";
import { prepared, mesh, solve } from "./support/runs";

test("dark workspace exports matching PDF and editable Word from a frozen historical model", async ({
  page,
}, info) => {
  test.setTimeout(45_000);
  const failures: string[] = [];
  page.on("pageerror", (e) => failures.push(e.message));
  const { projectId, analysisId } = await prepared(
    page,
    "T025 historical report",
    false,
    0.000001,
  );
  await mesh(page);
  const run = await solve(page);
  await expect(page.locator(`[data-job-id="${run.id}"]`)).toHaveAttribute(
    "data-job-status",
    "succeeded",
  );
  await page
    .getByRole("combobox", { name: "Completed solve", exact: true })
    .selectOption(run.id);
  await page
    .getByRole("button", { name: "View selected results", exact: true })
    .click();
  const viewport = page.getByLabel("Calculated result viewport", {
    exact: true,
  });
  await expect(viewport).toHaveAttribute("data-result-job", run.id);
  await page
    .getByRole("combobox", { name: "Theme", exact: true })
    .selectOption("dark");
  await page
    .getByRole("combobox", { name: "Result field", exact: true })
    .selectOption("sxx");
  await expect(viewport).toHaveAttribute("data-result-field", "sxx");
  await page
    .getByLabel("Smooth stress within each body and material", { exact: true })
    .check();
  await expect(viewport).toHaveAttribute("data-stress-smoothing", "smoothed");
  await page
    .getByRole("button", { name: "Add current view to report", exact: true })
    .click();
  await page
    .getByLabel("Report title", { exact: true })
    .fill("Frozen historical stress report");
  await page
    .getByLabel("User-written conclusion", { exact: true })
    .fill("Reviewer: refine the mesh before assessing a design.");
  const generated = page.waitForResponse(
    (r) =>
      r.url().endsWith(`/runs/${run.id}/reports`) &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Generate A4 PDF", exact: true })
    .click();
  const response = await generated;
  expect(response.status(), await response.text()).toBe(201);
  const record = await response.json();
  const modelResponse = await page.request.get(
    `/api/v1/reports/${record.id}/model`,
  );
  expect(modelResponse.status(), await modelResponse.text()).toBe(200);
  const model = await modelResponse.json();
  expect(model.source.job_id).toBe(run.id);
  expect(model.source.analysis_revision).toBe(run.analysis_revision);
  expect(model.request.views[0].field).toBe("sxx");
  expect(model.request.views[0].smoothed).toBe(true);
  expect(
    model.warnings.some((w: string) => w.includes("does not model plastic")),
  ).toBe(true);
  const pdf = await page.request.get(`/api/v1/reports/${record.id}/pdf`);
  expect(pdf.headers()["content-type"]).toContain("application/pdf");
  expect((await pdf.body()).subarray(0, 5).toString()).toBe("%PDF-");
  const wordReady = page.waitForResponse(
    (r) =>
      r.url().endsWith(`/reports/${record.id}/exports/word`) &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Generate editable Word", exact: true })
    .click();
  const wordResponse = await wordReady;
  expect(wordResponse.status(), await wordResponse.text()).toBe(201);
  const word = await wordResponse.json();
  expect(word.model_sha256).toBe(record.model_sha256);
  expect(word.pdf_sha256).toBe(record.pdf_sha256);
  const downloadedWord = await page.request.get(
    `/api/v1/word-exports/${word.id}/docx`,
  );
  expect(downloadedWord.status()).toBe(200);
  expect(downloadedWord.headers()["content-type"]).toContain(
    "wordprocessingml",
  );
  expect((await downloadedWord.body()).subarray(0, 2).toString()).toBe("PK");
  expect(
    await (await page.request.get(`/api/v1/reports/${record.id}/pdf`)).body(),
  ).toEqual(await pdf.body());
  const preview = await page.context().newPage();
  await preview.goto(`/api/v1/reports/${record.id}/html`);
  await expect(
    preview.getByRole("heading", {
      name: "Frozen historical stress report",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    preview.getByText("Reviewer: refine the mesh before assessing a design.", {
      exact: true,
    }),
  ).toBeVisible();
  expect(
    await preview
      .locator("html")
      .evaluate((node) => getComputedStyle(node).backgroundColor),
  ).toBe("rgb(255, 255, 255)");
  expect(await preview.locator("svg").count()).toBe(3);
  await preview.screenshot({
    path: info.outputPath("light-report-preview.png"),
    fullPage: true,
  });
  await preview.close();
  await page
    .getByLabel("Report export", { exact: true })
    .screenshot({ path: info.outputPath("dark-workspace-report.png") });
  await page.reload();
  await page.getByLabel("Open project").selectOption(projectId);
  await page.getByLabel("Open analysis").selectOption(analysisId);
  await page
    .getByRole("combobox", { name: "Completed solve", exact: true })
    .selectOption(run.id);
  await page
    .getByRole("button", { name: "View selected results", exact: true })
    .click();
  await expect(
    page.getByRole("link", { name: "Download A4 PDF", exact: true }),
  ).toBeVisible();
  expect(
    await (await page.request.get(`/api/v1/reports/${record.id}/model`)).json(),
  ).toEqual(model);
  await expect(
    page.getByRole("link", { name: "Download editable Word", exact: true }),
  ).toBeVisible();
  expect(
    await (
      await page.request.get(`/api/v1/word-exports/${word.id}/docx`)
    ).body(),
  ).toEqual(await downloadedWord.body());
  expect(failures).toEqual([]);
});
