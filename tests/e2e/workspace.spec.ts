import { expect, test, type Page } from "@playwright/test";
import { resolve } from "node:path";

async function workspace(page: Page) {
  await page.goto("/");
  await page.getByLabel("New project name").fill("T017 workspace");
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
  await page.getByLabel("New analysis name").fill("Original setup");
  await page
    .getByRole("button", {
      name: "Create analysis for this geometry",
      exact: true,
    })
    .click();
  await expect(page.getByLabel("Material body")).toBeVisible();
  await expect(page.getByLabel("Save state", { exact: true })).toContainText(
    "Saved",
  );
  await expect(page.getByLabel(/Global mesh size/)).toBeEnabled();
  return page.getByLabel("Open analysis").inputValue();
}
const saveState = (page: Page) =>
  page.getByLabel("Save state", { exact: true });

test("checklist actions, keyboard multiselection and persisted light/dark at target viewports", async ({
  page,
}, info) => {
  test.setTimeout(30_000);
  await page.setViewportSize({ width: 1280, height: 720 });
  await workspace(page);
  const checklist = page.getByRole("navigation", { name: "Model checklist" });
  await expect(checklist).toContainText(
    "Assign and confirm material for 1 bodies",
  );
  await checklist.getByRole("button", { name: /Materials/ }).click();
  await expect(
    page.getByLabel("Analysis materials", { exact: true }),
  ).toBeFocused();
  await page.locator(".body-tree summary").click();
  const faces = page.locator("button[data-face-id]");
  await faces.first().focus();
  await page.keyboard.press("Space");
  await expect(faces.first()).toHaveAttribute("aria-pressed", "true");
  await page.keyboard.press("ArrowDown");
  await expect(faces.nth(1)).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("heading", { name: "2 selected faces", exact: true }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("heading", { name: "0 selected faces", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("combobox", { name: "Theme", exact: true })
    .selectOption("dark");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({ path: info.outputPath("workspace-dark-1280.png") });
  await page.setViewportSize({ width: 1366, height: 768 });
  await page
    .getByRole("combobox", { name: "Theme", exact: true })
    .selectOption("light");
  await page.screenshot({ path: info.outputPath("workspace-light-1366.png") });
  await page.getByRole("combobox", { name: "Theme", exact: true }).focus();
  await page.keyboard.press("Tab");
  await expect(
    checklist.getByRole("button", { name: /Geometry/ }),
  ).toBeFocused();
  await page
    .getByRole("combobox", { name: "Theme", exact: true })
    .selectOption("dark");
  await page.reload();
  await expect(
    page.getByRole("combobox", { name: "Theme", exact: true }),
  ).toHaveValue("dark");
});

test("autosave waits for acknowledgement, retains failed edits, retries and session undo", async ({
  page,
}) => {
  test.setTimeout(30_000);
  const id = await workspace(page);
  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route(`**/api/v1/analyses/${id}`, async (route) => {
    if (route.request().method() === "PATCH") {
      await gate;
      await route.continue();
    } else await route.continue();
  });
  await page.getByLabel("Analysis name (autosaves)").fill("Renamed setup");
  await expect(saveState(page)).toContainText("Unsaved");
  await expect(saveState(page)).toHaveText("Saving…");
  expect(
    (await (await page.request.get(`/api/v1/analyses/${id}`)).json()).name,
  ).toBe("Original setup");
  release();
  await expect(saveState(page)).toHaveText("Saved · revision 2");
  await page.unroute(`**/api/v1/analyses/${id}`);
  await page.route(`**/api/v1/analyses/${id}`, (route) =>
    route.request().method() === "PATCH"
      ? route.abort("failed")
      : route.continue(),
  );
  await page.getByLabel("Analysis name (autosaves)").fill("Recovered setup");
  await expect(saveState(page)).toContainText("Save failed");
  await expect(page.getByLabel("Analysis name (autosaves)")).toHaveValue(
    "Recovered setup",
  );
  await page.unroute(`**/api/v1/analyses/${id}`);
  await page.getByRole("button", { name: "Retry unacknowledged edit" }).click();
  await expect(saveState(page)).toHaveText("Saved · revision 3");
  await page.getByRole("button", { name: "Undo last setup edit" }).click();
  await expect(saveState(page)).toHaveText("Saved · revision 4");
  await expect(page.getByLabel("Analysis name (autosaves)")).toHaveValue(
    "Renamed setup",
  );
  await page.getByRole("button", { name: "Undo last setup edit" }).click();
  await expect(saveState(page)).toHaveText("Saved · revision 5");
  await expect(page.getByLabel("Analysis name (autosaves)")).toHaveValue(
    "Original setup",
  );
  await expect(
    page.getByRole("button", { name: "Undo last setup edit" }),
  ).toBeDisabled();
});

test("real stale edit offers reload or conflict copy without overwriting the other session", async ({
  page,
}) => {
  test.setTimeout(30_000);
  const id = await workspace(page);
  const session = await (await page.request.get("/api/v1/session")).json();
  const changed = await page.request.patch(`/api/v1/analyses/${id}`, {
    headers: { "X-CSRF-Token": session.csrf_token, "If-Match": '"1"' },
    data: { name: "Other session" },
  });
  expect(changed.status()).toBe(200);
  await page.getByLabel("Analysis name (autosaves)").fill("My recovered edit");
  await expect(saveState(page)).toContainText("Conflict");
  await page
    .getByRole("button", { name: "Duplicate my conflicting edit" })
    .click();
  await expect(page.getByLabel("Open analysis")).not.toHaveValue(id);
  await expect(page.getByLabel("Analysis name (autosaves)")).toHaveValue(
    "My recovered edit",
  );
  await expect(saveState(page)).toContainText("Saved");
  expect(
    (await (await page.request.get(`/api/v1/analyses/${id}`)).json()).name,
  ).toBe("Other session");
  const copyId = await page.getByLabel("Open analysis").inputValue();
  await page
    .getByLabel("Analysis name (autosaves)")
    .fill("Session undo invalidation");
  await expect(saveState(page)).toHaveText("Saved · revision 3");
  expect(
    (
      await page.request.patch(`/api/v1/analyses/${copyId}`, {
        headers: { "X-CSRF-Token": session.csrf_token, "If-Match": '"3"' },
        data: { name: "Newer external head" },
      })
    ).status(),
  ).toBe(200);
  await page.getByRole("button", { name: "Undo last setup edit" }).click();
  await expect(saveState(page)).toContainText("Conflict");
  await expect(
    page.getByRole("button", { name: "Undo last setup edit" }),
  ).toBeDisabled();
  await page
    .getByRole("button", { name: "Reload saved workspace (discard drafts)" })
    .click();
  await expect(page.getByLabel("Analysis name (autosaves)")).toHaveValue(
    "Newer external head",
  );
  await expect(saveState(page)).toHaveText("Saved · revision 4");
});

test("draft blockers and cancellation protect other edits; undo restores saved material prerequisites", async ({
  page,
}) => {
  test.setTimeout(30_000);
  const id = await workspace(page);
  await page.getByLabel(/Global mesh size/).fill("500");
  await expect(saveState(page)).toContainText("Unsaved");
  await page.getByLabel("Material example").selectOption("al-6061-t6-rod");
  await page
    .getByLabel("I confirm the properties, condition and assumptions")
    .check();
  await page
    .getByRole("button", { name: "Apply material", exact: true })
    .click();
  await expect(
    page.getByText(/other unsaved drafts first: mesh/),
  ).toBeVisible();
  expect(
    (await (await page.request.get(`/api/v1/analyses/${id}/materials`)).json())
      .setup.assignments,
  ).toEqual([]);
  await page
    .getByRole("button", { name: "Cancel mesh edits", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Apply material", exact: true })
    .click();
  await expect(saveState(page)).toHaveText("Saved · revision 2");
  await expect(
    page.getByRole("navigation", { name: "Model checklist" }),
  ).toContainText("Materials — Complete");
  await page
    .getByRole("button", { name: "Undo last setup edit", exact: true })
    .click();
  await expect(saveState(page)).toHaveText("Saved · revision 3");
  await expect(
    page.getByRole("navigation", { name: "Model checklist" }),
  ).toContainText("Assign and confirm material for 1 bodies");
  expect(
    (await (await page.request.get(`/api/v1/analyses/${id}/materials`)).json())
      .setup.assignments,
  ).toEqual([]);
});

test("failed conflict-copy application keeps the rejected draft and exposes the created copy", async ({
  page,
}) => {
  test.setTimeout(30_000);
  const id = await workspace(page);
  const session = await (await page.request.get("/api/v1/session")).json();
  expect(
    (
      await page.request.patch(`/api/v1/analyses/${id}`, {
        headers: { "X-CSRF-Token": session.csrf_token, "If-Match": '"1"' },
        data: { name: "Other head" },
      })
    ).status(),
  ).toBe(200);
  await page.getByLabel("Analysis name (autosaves)").fill("Retain my draft");
  await expect(saveState(page)).toContainText("Conflict");
  await page.route("**/api/v1/analyses/*", (route) => {
    if (
      route.request().method() === "PATCH" &&
      !route.request().url().endsWith(id)
    )
      return route.fulfill({
        status: 422,
        json: {
          code: "invalid_request",
          message: "Controlled application refusal",
        },
      });
    return route.continue();
  });
  await page
    .getByRole("button", { name: "Duplicate my conflicting edit" })
    .click();
  await expect(page.getByText(/Controlled application refusal/)).toBeVisible();
  await expect(page.getByLabel("Open analysis")).toHaveValue(id);
  await expect(page.getByLabel("Analysis name (autosaves)")).toHaveValue(
    "Retain my draft",
  );
  await expect(saveState(page)).toContainText("Conflict");
  await page
    .getByRole("button", { name: "Open created copy (discard rejected draft)" })
    .click();
  await expect(page.getByLabel("Open analysis")).not.toHaveValue(id);
  await expect(page.getByLabel("Analysis name (autosaves)")).toHaveValue(
    "Original setup (conflict copy)",
  );
});
