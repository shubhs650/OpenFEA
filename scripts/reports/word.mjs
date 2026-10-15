import { chromium } from "playwright";
import { readFile, writeFile } from "node:fs/promises";
const model = JSON.parse(await readFile("/work/model.json", "utf8"));
if (model.figures.length < 1 || model.figures.length > 5)
  throw new Error("Invalid report figure count");
const browser = await chromium.launch({
  executablePath: "/browser/chrome-headless-shell",
  args: ["--disable-dev-shm-usage", "--disable-gpu", "--no-zygote"],
});
try {
  const context = await browser.newContext({
    javaScriptEnabled: false,
    offline: true,
    viewport: { width: 1200, height: 1200 },
    deviceScaleFactor: 1,
  });
  await context.route("**/*", (route) => route.abort());
  const page = await context.newPage();
  for (let index = 0; index < model.figures.length; index++) {
    const svg = model.figures[index].svg;
    await page.setContent(
      '<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; img-src \'none\'"><style>body{margin:0;background:white;font-family:DejaVu Sans,Arial,sans-serif}#figure{width:1200px}svg{display:block;width:100%;height:auto}</style><div id="figure">' +
        svg +
        "</div>",
      { timeout: 15000 },
    );
    await page
      .locator("#figure")
      .screenshot({ path: `/work/figure-${index}.png`, timeout: 15000 });
  }
  await writeFile(
    "/work/renderer.json",
    JSON.stringify({ chromium: browser.version() }),
  );
} finally {
  await browser.close();
}
