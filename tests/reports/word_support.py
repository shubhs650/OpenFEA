"""Actual isolated LibreOffice conversion; required QA, never a successful mock."""

import shutil
import subprocess
from pathlib import Path


def convert_word(directory: Path) -> Path:
    command = shutil.which("soffice") or shutil.which("libreoffice")
    bwrap = shutil.which("bwrap")
    if not command or not bwrap:
        raise RuntimeError("LibreOffice Writer and Bubblewrap are required for Word QA")
    roots = [
        Path("/usr/lib/libreoffice"),
        Path(command).resolve().parents[2] / "native/libreoffice-headless/libreoffice",
    ]
    office = next((p for p in roots if (p / "program/soffice.bin").is_file()), None)
    if office is None:
        raise RuntimeError("LibreOffice Writer installation could not be resolved")
    args = [bwrap, "--unshare-all", "--new-session", "--die-with-parent", "--cap-drop", "ALL"]
    for path in ("/usr", "/lib", "/lib64", "/etc/fonts", "/etc/ld.so.cache", "/etc/libreoffice"):
        if Path(path).exists():
            args += ["--ro-bind", path, path]
    args += [
        "--symlink",
        "/usr/bin",
        "/bin",
        "--ro-bind",
        str(office),
        str(office),
        "--dev",
        "/dev",
        "--proc",
        "/proc",
        "--tmpfs",
        "/tmp",
        "--bind",
        str(directory.resolve()),
        "/work",
        "--chdir",
        "/work",
        str(office / "program/soffice"),
        "-env:UserInstallation=file:///tmp/word-qa",
        "--headless",
        "--norestore",
        "--nodefault",
        "--convert-to",
        "pdf:writer_pdf_Export",
        "--outdir",
        "/work",
        "/work/report.docx",
    ]
    result = subprocess.run(
        args,
        env={
            "PATH": "/usr/bin:/bin",
            "HOME": "/tmp",
            "LANG": "C.UTF-8",
            "SAL_USE_VCLPLUGIN": "svp",
        },
        capture_output=True,
        timeout=45,
    )
    (directory / "conversion.log").write_bytes(result.stdout + result.stderr)
    if result.returncode or not (directory / "report.pdf").is_file():
        raise RuntimeError(
            "Actual LibreOffice Word conversion failed: "
            + result.stderr.decode()[:2500]
            + "\n...\n"
            + result.stderr.decode()[-1500:]
        )
    return directory / "report.pdf"
