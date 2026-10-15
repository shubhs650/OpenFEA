import { chromium } from "playwright";
import { readFile, writeFile } from "node:fs/promises";

// Paths are fixed by the private namespace, never selected by browser input.
const browser = await chromium.launch({
  executablePath: "/browser/chrome-headless-shell",
  args: ["--disable-dev-shm-usage", "--disable-gpu", "--no-zygote"],
});
try {
  const context = await browser.newContext({
    javaScriptEnabled: false,
    offline: true,
  });
  await context.route("**/*", (route) => route.abort());
  const page = await context.newPage();
  await page.setContent(await readFile("/work/report.html", "utf8"), {
    timeout: 15_000,
  });
  await page.pdf({
    path: "/work/report.pdf",
    format: "A4",
    printBackground: true,
    preferCSSPageSize: true,
    displayHeaderFooter: true,
    headerTemplate: "<div></div>",
    footerTemplate:
      '<div style="font-size:8px;width:100%;text-align:center;color:#333;padding-bottom:8px">Engineering report · <span class="pageNumber"></span> / <span class="totalPages"></span></div>',
  });
  await writeFile(
    "/work/renderer.json",
    JSON.stringify({ chromium: browser.version() }),
  );
} finally {
  await browser.close();
}
