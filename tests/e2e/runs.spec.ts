import { expect, test, type Page } from "@playwright/test";
import { resolve, join } from "node:path";
import { spawn } from "node:child_process";
import { readFile } from "node:fs/promises";
import type { components } from "../../packages/contracts/api";

type Geometry = components["schemas"]["GeometryRevision"];
type Job = components["schemas"]["LocalJob"];

async function prepared(page: Page, name: string) {
  await page.goto("/");
  await page.getByLabel("New project name").fill(name);
  await page
    .getByRole("button", { name: "Create project", exact: true })
    .click();
  await expect(page.getByLabel("Open project")).not.toHaveValue("");
  const projectId = await page.getByLabel("Open project").inputValue();
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
    .fill("Synthetic axial reference");
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
      "Isotropic analytical reference, E=68.3 GPa, nu=0. No certified allowable.",
    );
  await page
    .getByLabel("Source reference 1", { exact: true })
    .fill("Independent synthetic axial fixture");
  await page
    .getByRole("spinbutton", { name: /Young's modulus E/ })
    .fill("68300");
  await page.getByRole("spinbutton", { name: /Poisson ratio/ }).fill("0");
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
  const fixed = geometry.faces.find(
    (f) => (f.signature.center_m as number[])[0] === 0,
  )!;
  const loaded = geometry.faces.find(
    (f) => (f.signature.center_m as number[])[0] === 1,
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
    .selectOption("pressure");
  await page.getByLabel("Assignment name").fill("Axial pressure");
  await page.getByLabel("Pressure (MPa)", { exact: true }).fill("0.001");
  await page
    .getByRole("button", { name: "Save face assignment", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Remove Axial pressure", exact: true }),
  ).toBeVisible();
  return { projectId, analysisId };
}

async function mesh(page: Page): Promise<Job> {
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

async function solve(page: Page): Promise<Job> {
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

test("real asynchronous mesh preview, solve validation, downloads and retained history", async ({
  page,
}, testInfo) => {
  test.setTimeout(45_000);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const ids = await prepared(page, "Local axial run");
  const generated = await mesh(page);
  await page
    .getByRole("button", { name: "Preview selected mesh", exact: true })
    .click();
  await expect(page.locator(`[data-mesh-job="${generated.id}"]`)).toContainText(
    "100 C3D10 elements",
  );
  await expect(
    page.getByRole("button", { name: "Solve selected mesh", exact: true }),
  ).toBeDisabled();
  const run = await solve(page);
  const row = page.locator(`[data-job-id="${run.id}"]`);
  await expect(row).toHaveAttribute("data-job-status", "succeeded");
  await expect(row).toContainText(
    "Native solve completed and raw outputs validated",
  );
  const result = await (
    await page.request.get(`/api/v1/jobs/${run.id}/artifacts/results.json`)
  ).json();
  expect(result.input_sha256).toBe(run.input_sha256);
  expect(result.stress_location).toBe("integration_point");
  expect(result.integration_points).toHaveLength(400);
  const raw = await (
    await page.request.get(`/api/v1/jobs/${generated.id}/artifacts/mesh.json`)
  ).json();
  for (const [node, value] of Object.entries(
    result.dat.displacements_m as Record<string, number[]>,
  )) {
    expect(
      Math.abs(value[0] + (1000 / 68.3e9) * raw.nodes[node][0]),
    ).toBeLessThanOrEqual(1e-13);
  }
  const downloaded = page.waitForEvent("download");
  await row
    .getByRole("link", { name: "Download analysis.inp", exact: true })
    .click();
  const file = await downloaded;
  expect(file.suggestedFilename()).toBe("analysis.inp");
  expect(await readFile((await file.path())!, "utf8")).toContain("S,COORD");
  await page.screenshot({
    path: testInfo.outputPath("local-run.png"),
    fullPage: true,
  });
  await page.reload();
  await page.getByLabel("Open project").selectOption(ids.projectId);
  await page.getByLabel("Open analysis").selectOption(ids.analysisId);
  await expect(page.locator(`[data-job-id="${run.id}"]`)).toHaveAttribute(
    "data-job-status",
    "succeeded",
  );
  expect(errors).toEqual([]);
});

test("closing the browser preserves a queued solve; cancelling another queued job is durable", async ({
  page,
  context,
}, testInfo) => {
  test.setTimeout(45_000);
  const ids = await prepared(page, "Browser-independent job");
  await mesh(page);
  // Hold the actual server's native execution lease. This queues a real solve;
  // no HTTP response, mesh, solver output or job status is mocked.
  const locker = spawn(resolve(".venv/bin/python"), [
    "-c",
    `import fcntl,sys
with open(sys.argv[1],'a+b') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    print('LOCKED',flush=True)
    sys.stdin.buffer.read(1)
`,
    join(String(testInfo.config.metadata.localDataRoot), "native-import.lock"),
  ]);
  try {
    await new Promise<void>((resolve, reject) => {
      locker.stdout.once("data", () => resolve());
      locker.once("error", reject);
    });
    const run = await solve(page);
    expect(run.status).toBe("queued");
    await page.close();
    const reopened = await context.newPage();
    await reopened.goto("/");
    await reopened.getByLabel("Open project").selectOption(ids.projectId);
    await reopened.getByLabel("Open analysis").selectOption(ids.analysisId);
    await expect(reopened.locator(`[data-job-id="${run.id}"]`)).toHaveAttribute(
      "data-job-status",
      "queued",
    );
    await reopened.getByLabel("Display units").selectOption("m-N-Pa");
    await expect(
      reopened.getByText("Display units saved. Physical values unchanged.", {
        exact: true,
      }),
    ).toBeVisible();
    const queuedResponse = reopened.waitForResponse(
      (r) => r.url().endsWith("/mesh-jobs") && r.request().method() === "POST",
    );
    await reopened
      .getByRole("button", { name: "Generate local mesh", exact: true })
      .click();
    const queued: Job = await (await queuedResponse).json();
    const queuedRow = reopened.locator(`[data-job-id="${queued.id}"]`);
    await queuedRow.getByRole("button", { name: /Cancel mesh job/ }).click();
    await expect(queuedRow).toHaveAttribute("data-job-status", "cancelled");
    locker.stdin.write("\n");
    await expect(reopened.locator(`[data-job-id="${run.id}"]`)).toHaveAttribute(
      "data-job-status",
      "succeeded",
    );
    const frozen = await (
      await reopened.request.get(
        `/api/v1/jobs/${run.id}/artifacts/snapshot.json`,
      )
    ).json();
    expect(frozen.snapshot.analysis.revision).toBe(4);
    expect(frozen.snapshot.materials.display_units).toBe("mm-N-MPa");
    expect(
      (
        await (
          await reopened.request.get(`/api/v1/analyses/${ids.analysisId}`)
        ).json()
      ).revision,
    ).toBe(5);
    await reopened.close();
  } finally {
    locker.stdin.end();
    locker.kill();
  }
});
