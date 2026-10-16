import { expect, test, type Page, type TestInfo } from "@playwright/test";
import { readFile, writeFile } from "node:fs/promises";
import { prepared, mesh, solve } from "./support/runs";
import { assembly, approve } from "./support/assembly";

type Wire = {
  nodes: Record<string, number[]>;
  elements: Record<string, number[]>;
};
function containing(wire: Wire, point: number[]) {
  const sub = (a: number[], b: number[]) => a.map((v, k) => v - b[k]);
  const cross = (a: number[], b: number[]) => [
    a[1] * b[2] - a[2] * b[1],
    a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0],
  ];
  const dot = (a: number[], b: number[]) =>
    a.reduce((s, v, k) => s + v * b[k], 0);
  return Object.entries(wire.elements).find(([, ns]) => {
    const origin = wire.nodes[ns[0]];
    const [a, b, c] = ns.slice(1, 4).map((n) => sub(wire.nodes[n], origin));
    const d = sub(point, origin),
      determinant = dot(a, cross(b, c));
    const bary = [
      dot(d, cross(b, c)) / determinant,
      dot(a, cross(d, c)) / determinant,
      dot(a, cross(b, d)) / determinant,
    ];
    return [...bary, 1 - bary.reduce((s, v) => s + v, 0)].every(
      (v) => v >= -1e-12 && v <= 1 + 1e-12,
    );
  })![0];
}

async function start(page: Page, info: TestInfo, bond: boolean) {
  await page.getByText("Guided tutorials", { exact: true }).click();
  await page
    .getByRole("combobox", { name: "Choose tutorial", exact: true })
    .selectOption(bond ? "bond" : "bracket");
  const pending = page.waitForEvent("download");
  await page
    .getByRole("link", { name: "Download tutorial STEP", exact: true })
    .click();
  const file = await pending;
  const path = info.outputPath(file.suggestedFilename());
  await file.saveAs(path);
  expect(await readFile(path)).toEqual(
    await readFile(
      `tests/fixtures/geometry/${bond ? "bond-zero-m.step" : "bracket-m.step"}`,
    ),
  );
  await page
    .getByRole("button", { name: "Start tutorial timer", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Finish learning log", exact: true }),
  ).toBeDisabled();
}

async function sizing(page: Page, size: number) {
  await page
    .getByRole("spinbutton", { name: /Global mesh size/ })
    .fill(String(size));
  await page
    .getByLabel("Curvature elements per full circle", { exact: true })
    .fill("0");
  await page
    .getByRole("button", { name: "Save mesh controls", exact: true })
    .click();
  await expect(page.getByLabel("Save state", { exact: true })).toContainText(
    "Saved",
  );
}

for (const bond of [false, true]) {
  test(`guided ${bond ? "bond" : "bracket"} performs real refinement/report with compute excluded`, async ({
    page,
  }, info) => {
    // Two native meshes/solves plus real PDF export, same 60s budget as assembly flow.
    test.setTimeout(60_000);
    const failures: string[] = [];
    page.on("pageerror", (error) => failures.push(error.message));
    const open = () => start(page, info, bond);
    if (bond) {
      await assembly(page, open);
      await approve(page);
    } else
      await prepared(
        page,
        "T028 bracket tutorial",
        true,
        null,
        "cube-m.step",
        true,
        open,
      );
    const timing = page.getByLabel("Tutorial timing", { exact: true });
    const runs: Awaited<ReturnType<typeof solve>>[] = [];
    const meshes: Wire[] = [];
    for (const size of bond ? [600, 400] : [8, 6]) {
      await sizing(page, size);
      // Hold a real response to observe the pending compute state reliably.
      let release!: () => void;
      let observed!: () => void;
      const gate = new Promise<void>((resolve) => {
        release = resolve;
      });
      const seen = new Promise<void>((resolve) => {
        observed = resolve;
      });
      await page.route("**/api/v1/analyses/*/mesh-jobs", async (route) => {
        const response = await route.fetch();
        observed();
        await gate;
        await route.fulfill({ response });
      });
      const pending = mesh(page);
      await seen;
      await expect(timing).toHaveAttribute("data-mode", "compute");
      release();
      const job = await pending;
      await page.unroute("**/api/v1/analyses/*/mesh-jobs");
      meshes.push(
        await (
          await page.request.get(`/api/v1/jobs/${job.id}/artifacts/mesh.json`)
        ).json(),
      );
      if (bond) {
        await page
          .getByRole("button", {
            name: "Check assembly constraints",
            exact: true,
          })
          .click();
        await expect(
          page.getByLabel("Actual mesh assembly preflight", { exact: true }),
        ).toContainText("Necessary mesh checks passed");
      }
      const run = await solve(page);
      await expect(page.locator(`[data-job-id="${run.id}"]`)).toHaveAttribute(
        "data-job-status",
        "succeeded",
      );
      runs.push(run);
    }
    await page
      .getByRole("combobox", { name: "Completed solve", exact: true })
      .selectOption(runs[0].id);
    await page
      .getByRole("button", { name: "View selected results", exact: true })
      .click();
    await page
      .getByRole("combobox", { name: "Result field", exact: true })
      .selectOption(bond ? "sxx" : "von_mises");
    await expect(page.getByLabel("Calculated result viewport")).toBeVisible();
    const point = bond ? [1.5, 0.5, 0.5] : [0.04, 0.01, 0.0075];
    await page
      .getByLabel("Probe element ID", { exact: true })
      .fill(containing(meshes[0], point));
    for (let k = 0; k < 3; k++)
      await page
        .getByLabel(`Inspection ${"xyz"[k]} (mm)`, { exact: true })
        .fill(String(point[k] * 1000));
    await page
      .getByRole("button", { name: "Probe physical point", exact: true })
      .click();
    await expect(page.getByLabel("Physical probe result")).toBeVisible();
    for (let k = 0; k < 3; k++) {
      await page
        .getByLabel(`Inspection ${"xyz"[k]} (mm)`, { exact: true })
        .fill(k === 1 ? String(point[1] * 1000) : "0");
      await page
        .getByLabel(`Section normal ${"xyz"[k]}`, { exact: true })
        .fill(k === 1 ? "1" : "0");
    }
    await page
      .getByRole("button", { name: "Generate volume section", exact: true })
      .click();
    await expect(page.getByLabel("Calculated result viewport")).toHaveAttribute(
      "data-result-section",
      "volume",
    );
    await page.getByText("Mesh refinement comparison", { exact: true }).click();
    await page
      .getByRole("button", { name: "Refresh compared runs", exact: true })
      .click();
    await page
      .getByRole("combobox", { name: "Compared completed run", exact: true })
      .selectOption(runs[1].id);
    for (let k = 0; k < 3; k++)
      await page
        .getByLabel(`Comparison ${"xyz"[k]} (mm)`, { exact: true })
        .fill(String(point[k] * 1000));
    await page
      .getByRole("combobox", { name: "Comparison body side", exact: true })
      .selectOption({ index: bond ? 1 : 0 });
    await page
      .getByLabel("Reference element side", { exact: true })
      .fill(containing(meshes[0], point));
    await page
      .getByLabel("Compared element side", { exact: true })
      .fill(containing(meshes[1], point));
    await page
      .getByRole("button", { name: "Add physical sample", exact: true })
      .click();
    const comparison = page.waitForResponse((r) =>
      r.url().endsWith(`/runs/${runs[0].id}/comparisons`),
    );
    await page
      .getByRole("button", { name: "Compare physical samples", exact: true })
      .click();
    const response = await comparison;
    expect(response.status(), await response.text()).toBe(200);
    const values = await response.json();
    await writeFile(
      info.outputPath("comparison.json"),
      JSON.stringify(values, null, 2),
    );
    expect(values.compared.elements).toBeGreaterThan(values.reference.elements);
    await page
      .getByRole("button", { name: "Add current view to report", exact: true })
      .click();
    await page
      .getByLabel("Report title", { exact: true })
      .fill(`T028 ${bond ? "bond" : "bracket"} learning report`);
    const report = page.waitForResponse(
      (r) =>
        r.url().endsWith(`/runs/${runs[0].id}/reports`) &&
        r.request().method() === "POST",
    );
    await page
      .getByRole("button", { name: "Generate A4 PDF", exact: true })
      .click();
    expect((await report).status()).toBe(201);
    const download = page.waitForEvent("download");
    await page
      .getByRole("link", { name: "Download A4 PDF", exact: true })
      .click();
    const pdf = await download;
    await pdf.saveAs(info.outputPath("tutorial.pdf"));
    expect(
      (await readFile(info.outputPath("tutorial.pdf")))
        .subarray(0, 5)
        .toString(),
    ).toBe("%PDF-");
    const panel = page.getByRole("region", {
      name: "Guided tutorials",
      exact: true,
    });
    for (const checkbox of await panel.getByRole("checkbox").all())
      await checkbox.check();
    await page.getByLabel("Measured values and errors", { exact: true }).fill(
      JSON.stringify({
        samples: values.samples,
        reference_elements: values.reference.elements,
        compared_elements: values.compared.elements,
      }),
    );
    await expect(timing).toHaveAttribute("data-mode", "setup");
    await page
      .getByRole("button", { name: "Finish learning log", exact: true })
      .click();
    const logging = page.waitForEvent("download");
    await page
      .getByRole("link", { name: "Download learning log", exact: true })
      .click();
    const log = await logging;
    await log.saveAs(info.outputPath("learning.json"));
    const record = JSON.parse(
      await readFile(info.outputPath("learning.json"), "utf8"),
    );
    expect(record.duration_ms.compute).toBeGreaterThan(0);
    expect(record.duration_ms.setup).toBeGreaterThan(0);
    expect(record.classification).toContain(
      "not usability or engineering acceptance",
    );
    await page.screenshot({
      path: info.outputPath("tutorial.png"),
      fullPage: true,
    });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    expect(failures).toEqual([]);
  });
}
