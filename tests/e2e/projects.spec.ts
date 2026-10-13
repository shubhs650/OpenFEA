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
