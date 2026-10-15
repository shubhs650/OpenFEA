"""Namespace-isolated Chromium with one bounded process tree and no network."""

import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import time
from importlib.metadata import version
from pathlib import Path

from worker.resources import process_tree_rss
from worker.runtime import ROOT, sha256


def tools() -> tuple[Path, Path, Path]:
    node, bwrap = shutil.which("node"), shutil.which("bwrap")
    manifest = json.loads((ROOT / "node_modules/playwright-core/browsers.json").read_bytes())
    revision = next(
        b["revision"] for b in manifest["browsers"] if b["name"] == "chromium-headless-shell"
    )
    browser = (
        ROOT
        / ".local/browsers"
        / f"chromium_headless_shell-{revision}"
        / "chrome-headless-shell-linux64/chrome-headless-shell"
    )
    if not node or not bwrap or not browser.is_file():
        raise RuntimeError("Pinned Playwright Chromium, Node and Bubblewrap are required")
    return Path(node).resolve(), Path(bwrap), browser


def generator() -> dict[str, str]:
    node, _, browser = tools()
    sources = [
        "services/api/app/domain/reports.py",
        "services/api/app/domain/report_service.py",
        "services/worker/worker/reports/model.py",
        "services/worker/worker/reports/figures.py",
        "services/worker/worker/reports/html.py",
        "services/worker/worker/reports/content.py",
        "services/worker/worker/reports/render.py",
        "scripts/reports/pdf.mjs",
        "package-lock.json",
        "uv.lock",
    ]
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=3,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=3,
    ).stdout
    fonts = Path("/usr/share/fonts/truetype/dejavu")
    if not (fonts / "DejaVuSans.ttf").is_file():
        raise RuntimeError("DejaVu Sans report fonts are required")
    return {
        "version": "report-v1",
        "source_commit": commit,
        "source_dirty": str(bool(dirty)).lower(),
        "generator_python": sys.version.split()[0],
        "generator_platform": platform.platform(),
        "generator_cpu_count": str(os.cpu_count()),
        "font_dejavu_regular_sha256": sha256(fonts / "DejaVuSans.ttf"),
        "chromium_binary_sha256": sha256(browser),
        "node_binary_sha256": sha256(node),
        **{name: sha256(ROOT / name) for name in sources},
    }


def _render(directory: Path, *, word: bool = False) -> dict[str, str]:
    node, bwrap, browser = tools()
    temporary = directory / "tmp"
    temporary.mkdir()
    command = [
        str(bwrap),
        "--unshare-all",
        "--new-session",
        "--die-with-parent",
        "--cap-drop",
        "ALL",
    ]
    for path in ("/usr", "/lib", "/lib64", "/etc/fonts", "/etc/ld.so.cache"):
        if Path(path).exists():
            command += ["--ro-bind", path, path]
    if word:
        for host, target in (
            (Path(sys.base_prefix).resolve(), Path(sys.base_prefix).resolve()),
            (ROOT / ".venv", ROOT / ".venv"),
            (ROOT / "services", Path("/app/services")),
            (ROOT / "scripts/reports/word.py", Path("/app/word.py")),
        ):
            command += ["--ro-bind", str(host), str(target)]
    script = "word.mjs" if word else "pdf.mjs"
    entry = [str(ROOT / ".venv/bin/python"), "/app/word.py"] if word else ["/node", "/app/pdf.mjs"]
    command += [
        "--ro-bind",
        str(node),
        "/node",
        "--ro-bind",
        str(browser.parent),
        "/browser",
        "--ro-bind",
        str(ROOT / "node_modules"),
        "/app/node_modules",
        "--ro-bind",
        str(ROOT / "scripts/reports" / script),
        f"/app/{script}",
        "--dev",
        "/dev",
        "--proc",
        "/proc",
        "--bind",
        str(directory),
        "/work",
        "--symlink",
        "/work/tmp",
        "/tmp",
        "--chdir",
        "/work",
        *entry,
    ]
    started = time.monotonic()
    peak = disk = 0
    with (directory / "render.log").open("wb") as log:
        process = subprocess.Popen(
            command,
            env={
                "PATH": "/usr/bin:/bin",
                "HOME": "/tmp",
                "LANG": "C.UTF-8",
                "PYTHONPATH": "/app/services/api:/app/services/worker",
            },
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )
        try:
            while process.poll() is None:
                peak = max(peak, process_tree_rss(process.pid))
                disk = max(disk, sum(p.stat().st_size for p in directory.rglob("*") if p.is_file()))
                if time.monotonic() - started > 45 or peak > 1024**3 or disk > 64 * 1024**2:
                    raise RuntimeError("Report rendering exceeded its resource budget")
                time.sleep(0.05)
            if process.returncode != 0:
                raise RuntimeError("Report renderer failed; check local renderer prerequisites")
        finally:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=3)
    disk = max(disk, sum(p.stat().st_size for p in directory.rglob("*") if p.is_file()))
    if disk > 64 * 1024**2:
        raise RuntimeError("Report rendering exceeded its final scratch budget")
    info: dict[str, str] = json.loads((directory / "renderer.json").read_bytes())
    info.update(
        wall_seconds=f"{time.monotonic() - started:.3f}",
        peak_rss_bytes=str(peak),
        peak_scratch_bytes=str(disk),
        isolation="bubblewrap-unshare-all; offline; scripts-disabled",
        limits="45 s / 1024 MiB sampled RSS / 64 MiB sampled scratch; no retries",
    )
    return info


def render_pdf(directory: Path) -> dict[str, str]:
    return _render(directory)


def render_word(directory: Path) -> dict[str, str]:
    return _render(directory, word=True)


def word_generator() -> dict[str, str]:
    names = (
        "services/worker/worker/reports/docx.py",
        "scripts/reports/word.py",
        "scripts/reports/word.mjs",
        "services/api/app/domain/word_service.py",
        "services/api/app/domain/words.py",
    )
    return {
        **generator(),
        "version": "word-v1",
        "python_docx": version("python-docx"),
        "lxml": version("lxml"),
        **{name: sha256(ROOT / name) for name in names},
    }
