import { prepared, mesh, solve } from "./support/runs";
import { expect, test } from "@playwright/test";
import { join, resolve } from "node:path";
import { spawn } from "node:child_process";
import { readFile } from "node:fs/promises";
import type { components } from "../../packages/contracts/api";

type Job = components["schemas"]["LocalJob"];

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
