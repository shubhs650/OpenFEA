import type { Locator, Page, TestInfo } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

// Optional artifacts from the tested public workflow. Only viewport/scroll
// changes for capture; responses, numerical state, timeouts and retries stay real.
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
  const originalViewport = page.viewportSize();
  let expanded = false;
  try {
    // A tall region inside the independently scrolling model tree is clipped by
    // its parent. Fit the actual region in a real taller viewport before capture;
    // do not remove CSS, alter the DOM or composite a fabricated panel image.
    const bounds = target ? await target.boundingBox() : null;
    if (
      originalViewport &&
      bounds &&
      bounds.height > originalViewport.height - 180
    ) {
      await page.setViewportSize({
        width: originalViewport.width,
        height: Math.ceil(bounds.height + 220),
      });
      expanded = true;
    }
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
      renderers: Array.from(document.querySelectorAll("canvas")).map(
        (canvas) => {
          const gl = canvas.getContext("webgl2") ?? canvas.getContext("webgl");
          if (!gl) return { renderer: null };
          const ext = gl.getExtension("WEBGL_debug_renderer_info");
          return {
            renderer: String(
              gl.getParameter(ext?.UNMASKED_RENDERER_WEBGL ?? gl.RENDERER),
            ),
          };
        },
      ),
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
  } finally {
    if (expanded && originalViewport)
      await page.setViewportSize(originalViewport);
  }
}
