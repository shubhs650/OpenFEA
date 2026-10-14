import { expect, test, type Page } from "@playwright/test";
import type { components } from "../../packages/contracts/api";
import { prepared, mesh, solve } from "./support/runs";

type Geometry = components["schemas"]["GeometryRevision"];
const radians = (d: number) => (d * Math.PI) / 180;
const [sx, cx, sy, cy, sz, cz] = [
  Math.sin(radians(23)),
  Math.cos(radians(23)),
  Math.sin(radians(37)),
  Math.cos(radians(37)),
  Math.sin(radians(19)),
  Math.cos(radians(19)),
];
const rotation = [
  [cz * cy, sz * cy, -sy],
  [cz * sy * sx - sz * cx, sz * sy * sx + cz * cx, cy * sx],
  [cz * sy * cx + sz * sx, sz * sy * cx - cz * sx, cy * cx],
];
function face(geometry: Geometry, axis: number, side: number) {
  return geometry.faces.find((f) => {
    const p = f.signature.center_m as number[];
    return (
      Math.abs(
        p.reduce(
          (sum, v, i) => sum + (v - [0.25, -0.4, 0.15][i]) * rotation[axis][i],
          0,
        ) - side,
      ) < 1e-10
    );
  })!;
}
async function selected(page: Page, ids: string[]) {
  await page
    .getByRole("button", { name: "Clear selection", exact: true })
    .click();
  for (const id of ids) await page.locator(`[data-face-id="${id}"]`).click();
}
async function save(page: Page, name: string) {
  const refreshed = page.waitForResponse(
    (r) => r.url().endsWith("/loads") && r.request().method() === "GET",
  );
  await page.getByLabel("Assignment name", { exact: true }).fill(name);
  await page
    .getByRole("button", { name: "Save face assignment", exact: true })
    .click();
  await refreshed;
  await expect(
    page.getByRole("button", { name: `Remove ${name}`, exact: true }),
  ).toBeVisible();
}

test("native rotated symmetry and edge sign preview drive real immutable global results", async ({
  page,
}, testInfo) => {
  test.setTimeout(60_000);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const { projectId, analysisId } = await prepared(
    page,
    "T016 rotated directions",
    false,
    null,
    "rotated-cube-m.step",
    false,
  );
  const geometry: Geometry = (
    await (
      await page.request.get(`/api/v1/projects/${projectId}/geometry`)
    ).json()
  ).items[0];
  await page
    .getByRole("spinbutton", { name: /Young's modulus E/ })
    .fill("210000");
  await page.getByRole("spinbutton", { name: /Poisson ratio/ }).fill("0.3");
  await page
    .getByRole("textbox", { name: "Assumptions", exact: true })
    .fill(
      "Exact synthetic T016 rotation patch, E=210 GPa, nu=0.3. No certified allowable.",
    );
  await page
    .getByLabel("I confirm the properties, condition and assumptions")
    .check();
  const material = page.waitForResponse(
    (r) => r.url().includes("/materials/") && r.request().method() === "PUT",
  );
  await page
    .getByRole("button", { name: "Apply material", exact: true })
    .click();
  expect((await material).status()).toBe(200);
  await selected(
    page,
    [0, 1, 2].map((axis) => face(geometry, axis, 0).id),
  );
  await page
    .getByRole("combobox", { name: "Face assignment", exact: true })
    .selectOption("symmetry");
  await expect(
    page.getByLabel("Resolved direction basis", { exact: true }),
  ).toContainText("Right-handed orthonormal");
  await save(page, "Three native symmetry planes");
  await selected(page, [face(geometry, 0, 1).id]);
  await page
    .getByRole("combobox", { name: "Face assignment", exact: true })
    .selectOption("directional_force");
  await page
    .getByRole("combobox", { name: "Direction source", exact: true })
    .selectOption("straight_edge");
  const edge = geometry.edges!.find((e) => {
    if (!e.start_m || !e.end_m) return false;
    const v = e.end_m.map((p, i) => p - e.start_m![i]);
    return (
      Math.abs(
        v.reduce((sum, p, i) => sum + p * rotation[0][i], 0) / Math.hypot(...v),
      ) >
      1 - 1e-10
    );
  })!;
  await page
    .getByRole("combobox", { name: "Direction reference", exact: true })
    .selectOption(edge.id);
  await expect(
    page.getByLabel("Resolved direction basis", { exact: true }),
  ).toBeVisible();
  const getDraft = async () =>
    page
      .getByLabel("Resolved direction basis", { exact: true })
      .locator("tbody tr")
      .first()
      .locator("td")
      .allTextContents();
  const before = (await getDraft()).map(Number);
  await page.getByLabel("Reverse selected direction", { exact: true }).check();
  await expect(
    page.getByLabel("Resolved direction basis", { exact: true }),
  ).toContainText("Reversed direction");
  const after = (await getDraft()).map(Number);
  after.forEach((v, i) => expect(v).toBeCloseTo(-before[i], 6));
  const points = edge.end_m!.map((v, i) => v - edge.start_m![i]);
  const nativeSign =
    points.reduce((sum, v, i) => sum + v * rotation[0][i], 0) < 0;
  await page
    .getByLabel("Reverse selected direction", { exact: true })
    .setChecked(nativeSign);
  await expect(
    page.getByLabel("Geometry viewport", { exact: true }),
  ).toHaveAttribute("data-direction-markers", "1");
  await page.getByRole("button", { name: "Fit", exact: true }).click();
  const image = await page
    .getByLabel("Geometry viewport", { exact: true })
    .screenshot({ path: testInfo.outputPath("direction-arrow.png") });
  const purple = await page.evaluate(async (encoded) => {
    const image = new Image();
    image.src = `data:image/png;base64,${encoded}`;
    await image.decode();
    const canvas = document.createElement("canvas");
    canvas.width = image.width;
    canvas.height = image.height;
    const context = canvas.getContext("2d")!;
    context.drawImage(image, 0, 0);
    const data = context.getImageData(0, 0, image.width, image.height).data;
    let count = 0;
    for (let i = 0; i < data.length; i += 4)
      if (
        data[i] > 120 &&
        data[i] < 195 &&
        data[i + 1] > 25 &&
        data[i + 1] < 100 &&
        data[i + 2] > 150 &&
        data[i + 2] < 220
      )
        count++;
    return count;
  }, image.toString("base64"));
  expect(purple).toBeGreaterThan(10);
  await page
    .getByLabel("Resolved direction basis", { exact: true })
    .screenshot({ path: testInfo.outputPath("direction-basis.png") });
  await page
    .getByLabel("Directed total force (N)", { exact: true })
    .fill("1000");
  await save(page, "Edge axial load");
  const saved = (
    await (
      await page.request.get(`/api/v1/analyses/${analysisId}/loads`)
    ).json()
  ).setup;
  const force = saved.assignments.find(
    (a: { kind: string }) => a.kind === "directional_force",
  );
  force.force_n.forEach((v: number, i: number) =>
    expect(v).toBeCloseTo(1000 * rotation[0][i], 7),
  );
  await mesh(page);
  const run = await solve(page);
  await expect(page.locator(`[data-job-id="${run.id}"]`)).toHaveAttribute(
    "data-job-status",
    "succeeded",
  );
  const raw = await (
    await page.request.get(`/api/v1/jobs/${run.id}/artifacts/results.json`)
  ).json();
  expect(raw.equilibrium.passed).toBe(true);
  raw.equilibrium.reaction_force_n.forEach((v: number, i: number) =>
    expect(v).toBeCloseTo(-1000 * rotation[0][i], 3),
  );
  await page
    .getByRole("combobox", { name: "Completed solve", exact: true })
    .selectOption(run.id);
  await page
    .getByRole("button", { name: "View selected results", exact: true })
    .click();
  await expect(
    page.getByLabel("External equilibrium", { exact: true }),
  ).toContainText("Passed");
  await page
    .getByLabel("External equilibrium", { exact: true })
    .screenshot({ path: testInfo.outputPath("direction-equilibrium.png") });
  const frozen = await (
    await page.request.get(`/api/v1/runs/${run.id}/results`)
  ).json();
  await page
    .getByRole("combobox", { name: "Display units", exact: true })
    .selectOption("inch-lbf-psi");
  expect(
    (
      await (
        await page.request.get(`/api/v1/analyses/${analysisId}/loads`)
      ).json()
    ).setup,
  ).toEqual(saved);
  expect(
    await (await page.request.get(`/api/v1/runs/${run.id}/results`)).json(),
  ).toEqual(frozen);
  await page.reload();
  await page.getByLabel("Open project").selectOption(projectId);
  await page.getByLabel("Open analysis").selectOption(analysisId);
  await expect(
    page.getByLabel("Saved direction Edge axial load", { exact: true }),
  ).toContainText("straight_edge");
  expect(errors).toEqual([]);
});

test("native cylinder axis can be saved while curved symmetry and solving refuse", async ({
  page,
}, testInfo) => {
  test.setTimeout(45_000);
  const { projectId, analysisId } = await prepared(
    page,
    "T016 cylinder directions",
    false,
    null,
    "cylinder-m.step",
    false,
  );
  const geometry: Geometry = (
    await (
      await page.request.get(`/api/v1/projects/${projectId}/geometry`)
    ).json()
  ).items[0];
  const side = geometry.faces.find((f) =>
    String(f.signature.surface_type).endsWith("GeomAbs_Cylinder"),
  )!;
  const base = geometry.faces.find(
    (f) => (f.signature.center_m as number[])[2] === 0,
  )!;
  const top = geometry.faces.find(
    (f) => (f.signature.center_m as number[])[2] === 1,
  )!;
  await selected(page, [base.id]);
  await save(page, "Fixed cylinder base");
  await selected(page, [top.id]);
  await page
    .getByRole("combobox", { name: "Face assignment", exact: true })
    .selectOption("directional_force");
  await page
    .getByRole("combobox", { name: "Direction source", exact: true })
    .selectOption("cylinder_axis");
  await page
    .getByRole("combobox", { name: "Direction reference", exact: true })
    .selectOption(side.id);
  await expect(
    page.getByLabel("Resolved direction basis", { exact: true }),
  ).toContainText("Right-handed orthonormal");
  await page.getByLabel("Directed total force (N)", { exact: true }).fill("55");
  await save(page, "Cylinder axis source");
  await page
    .getByLabel("Saved direction Cylinder axis source", { exact: true })
    .screenshot({ path: testInfo.outputPath("cylinder-axis.png") });
  const state = (
    await (
      await page.request.get(`/api/v1/analyses/${analysisId}/loads`)
    ).json()
  ).setup;
  expect(
    state.assignments.find(
      (a: { kind: string }) => a.kind === "directional_force",
    ).force_n,
  ).toEqual([0, 0, 55]);
  await page
    .getByRole("button", { name: "Generate checked deck", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText("planar faces");
  await selected(page, [side.id]);
  await page
    .getByRole("combobox", { name: "Face assignment", exact: true })
    .selectOption("symmetry");
  await expect(
    page.getByLabel("Geometry direction", { exact: true }),
  ).toContainText("declared type");
  await expect(
    page.getByRole("button", { name: "Save face assignment", exact: true }),
  ).toBeDisabled();
  expect(
    (
      await (
        await page.request.get(`/api/v1/analyses/${analysisId}/loads`)
      ).json()
    ).setup,
  ).toEqual(state);
});
