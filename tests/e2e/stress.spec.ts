import { expect, test } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const output = resolve(".local/native/browser/T004");
test.beforeAll(() => {
  execFileSync(
    resolve(".venv/bin/python"),
    ["scripts/native/benchmark.py", "B09", "--development", "--output", output],
    {
      cwd: process.cwd(),
      env: { ...process.env, PYTHONPATH: resolve("services/worker") },
      timeout: 90_000,
      stdio: "pipe",
    },
  );
});

test("real native material jump stays separate in the display fixture", async ({
  page,
}) => {
  await page.goto(pathToFileURL(resolve(output, "stress.html")).href);
  await expect(
    page.getByRole("heading", {
      name: "Stress provenance: material interface",
    }),
  ).toBeVisible();
  await expect(
    page.getByText(
      "Development diagnostic — engineering-owner acceptance pending.",
    ),
  ).toBeVisible();
  const upper = page.locator('[data-side="UPPER"]');
  const lower = page.locator('[data-side="LOWER"]');
  const native = page.locator('[data-side="FRD"]');
  expect(Number(await upper.getAttribute("data-value"))).toBeCloseTo(210e6, 0);
  expect(Number(await lower.getAttribute("data-value"))).toBeCloseTo(70e6, 0);
  expect(Number(await native.getAttribute("data-value"))).toBe(139999000);
  expect(
    await page.locator('polygon[data-element="1"]').getAttribute("fill"),
  ).not.toBe(
    await page.locator('polygon[data-element="2"]').getAttribute("fill"),
  );
  await expect(page.locator("#raw tr")).toHaveCount(8);
  await expect(native).toContainText("may smear material interfaces");
  await page.screenshot({
    path: resolve(output, "interface.png"),
    fullPage: true,
  });
});

test("field and interface-node selection retain location and source semantics", async ({
  page,
}) => {
  await page.goto(pathToFileURL(resolve(output, "stress.html")).href);
  const payload = JSON.parse(
    readFileSync(resolve(output, "stress.json"), "utf8"),
  ) as {
    element_nodes: {
      element_id: number;
      node_id: number;
      tensor_pa: number[];
      von_mises_pa: number;
    }[];
  };
  await page.getByLabel("Shared interface node").selectOption("6");
  await page.getByLabel("Stress field").selectOption("von_mises");
  for (const [element, material] of [
    [1, "UPPER"],
    [2, "LOWER"],
  ] as const) {
    const sample = payload.element_nodes.find(
      (p) => p.element_id === element && p.node_id === 6,
    );
    expect(sample).toBeDefined();
    expect(
      Number(
        await page
          .locator(`[data-side="${material}"]`)
          .getAttribute("data-value"),
      ),
    ).toBe(sample?.von_mises_pa);
  }
  await page.getByLabel("Stress field").selectOption("yz");
  await expect(page.locator("#location")).toContainText(
    "Element-node extrapolation from raw DAT",
  );
  await expect(page.locator('[data-side="UPPER"]')).toContainText(
    "node 6; derived from DAT IPs 1–4",
  );
  await expect(page.locator("#provenance")).toContainText(
    "ccx-2.23-single-static-ascii-v1",
  );
});
