import { expect, test } from "@playwright/test";

test("workspace connects to the real API through Vite", async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "FEA development" }),
  ).toBeVisible();
  await expect(page.getByRole("status", { name: "API connection" })).toHaveText(
    "API connected",
  );
  await expect(
    page.getByText(
      "Calculated displacement and stress results are available.",
      {
        exact: false,
      },
    ),
  ).toBeVisible();
});

test("page reports a health network failure without claiming readiness", async ({
  page,
}) => {
  await page.route("**/api/v1/health", (route) => route.abort("failed"));
  await page.goto("/");
  await expect(page.getByRole("status", { name: "API connection" })).toHaveText(
    "API unavailable",
  );
});
