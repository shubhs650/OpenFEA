import type { Locator, Page, TestInfo } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

// Optional reference artifacts from the ordinary tested public workflow. No UI
// state, response, numerical result, timeout or retry is changed by this helper.
export async function reference(
  page: Page,
  info: TestInfo,
  name: string,
  title: string,
  target?: Locator,
) {
  const root = process.env.FEA_REFERENCE_DIR;
  if (!root) return;
  const directory = resolve(root, info.project.name || "chromium");
  await mkdir(directory, { recursive: true });
  if (target) await target.scrollIntoViewIfNeeded();
  const bytes = target
    ? await target.screenshot()
    : await page.screenshot({ fullPage: false });
  const file = `${name}.png`;
  await writeFile(resolve(directory, file), bytes);
  const observation = await page.evaluate(() => ({
    userAgent: navigator.userAgent,
    platform: navigator.platform,
    viewport: { width: innerWidth, height: innerHeight },
    theme: document.documentElement.dataset.theme ?? "light",
    renderers: Array.from(document.querySelectorAll("canvas")).map((canvas) => {
      const gl = canvas.getContext("webgl2") ?? canvas.getContext("webgl");
      if (!gl) return { renderer: null };
      const ext = gl.getExtension("WEBGL_debug_renderer_info");
      return {
        renderer: String(
          gl.getParameter(ext?.UNMASKED_RENDERER_WEBGL ?? gl.RENDERER),
        ),
      };
    }),
  }));
  await writeFile(
    resolve(directory, `${name}.json`),
    JSON.stringify(
      {
        title,
        file,
        sha256: createHash("sha256").update(bytes).digest("hex"),
        code_commit: execFileSync("git", ["rev-parse", "HEAD"], {
          encoding: "utf8",
        }).trim(),
        test: info.title,
        project: info.project.name,
        host_platform: process.platform,
        captured_at: new Date().toISOString(),
        ...observation,
        classification:
          "Automated real-UI reference; not human usability or engineering-owner acceptance",
      },
      null,
      2,
    ) + "\n",
  );
}
