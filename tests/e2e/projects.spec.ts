import { expect, test } from "@playwright/test";
import type { components } from "../../packages/contracts/api";

test("real browser project CRUD uses local session, CSRF and revisions through Vite", async ({
  page,
}) => {
  await page.goto("/");
  const results = await page.evaluate(async () => {
    const session: components["schemas"]["LocalSession"] = await fetch(
      "/api/v1/session",
    ).then((r) => r.json());
    const noCsrf = await fetch("/api/v1/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "Rejected browser write" }),
    });
    const created = await fetch("/api/v1/projects", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": session.csrf_token,
      },
      body: JSON.stringify({ name: "Browser bracket" }),
    });
    const project: components["schemas"]["Project"] = await created.json();
    if (created.status !== 201)
      throw new Error(
        `Project creation failed: ${created.status} ${JSON.stringify(project)}`,
      );
    const path = `/api/v1/projects/${project.id}`;
    try {
      const edited = await fetch(path, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": session.csrf_token,
          "If-Match": '"1"',
        },
        body: JSON.stringify({ name: "Saved browser bracket" }),
      });
      const changed: components["schemas"]["Project"] = await edited.json();
      const stale = await fetch(path, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": session.csrf_token,
          "If-Match": '"1"',
        },
        body: JSON.stringify({ name: "Stale browser edit" }),
      });
      const reloaded: components["schemas"]["Project"] = await fetch(path).then(
        (r) => r.json(),
      );
      return {
        noCsrf: noCsrf.status,
        created: created.status,
        edited: edited.status,
        stale: stale.status,
        revision: changed.revision,
        name: reloaded.name,
        owner: project.owner_id === session.owner_id,
      };
    } finally {
      await fetch(path, {
        method: "DELETE",
        headers: { "X-CSRF-Token": session.csrf_token, "If-Match": '"2"' },
      });
    }
  });
  expect(results).toEqual({
    noCsrf: 403,
    created: 201,
    edited: 200,
    stale: 409,
    revision: 2,
    name: "Saved browser bracket",
    owner: true,
  });
});

test("project creation waits for the real local session before enabling writes", async ({
  page,
}) => {
  let releaseSession = () => {};
  const sessionGate = new Promise<void>((resolve) => {
    releaseSession = resolve;
  });
  await page.route("**/api/v1/session", async (route) => {
    await sessionGate;
    await route.continue();
  });
  try {
    await page.goto("/");
    await page.getByLabel("New project name").fill("Session readiness fixture");
    const create = page.getByRole("button", {
      name: "Create project",
      exact: true,
    });
    await expect(create).toBeDisabled();
    releaseSession();
    await expect(create).toBeEnabled();
    const created = page.waitForResponse(
      (response) =>
        response.url().endsWith("/api/v1/projects") &&
        response.request().method() === "POST",
    );
    await create.click();
    expect((await created).status()).toBe(201);
    await expect(page.getByLabel("STEP file")).toBeVisible();
    await expect(page.getByRole("alert")).toHaveCount(0);
  } finally {
    releaseSession();
  }
});
