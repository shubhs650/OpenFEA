import { expect, test } from "@playwright/test";

test("workspace connects to the real API through Vite", async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "FEA development" }),
  ).toBeVisible();
  await expect(page.getByRole("status")).toHaveText("API connected");
  await expect(
    page.getByText("Solving and calculated results are not available yet.", {
      exact: false,
    }),
  ).toBeVisible();
});

test("page reports a health network failure without claiming readiness", async ({
  page,
}) => {
  await page.route("**/api/v1/health", (route) => route.abort("failed"));
  await page.goto("/");
  await expect(page.getByRole("status")).toHaveText("API unavailable");
});
