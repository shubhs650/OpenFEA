"""Inventory pinned artifacts, installed native binaries and their license evidence."""

import itertools
import json
import re
import shutil
import subprocess
import tomllib
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from worker.runtime import NATIVE, ROOT, sha256

COLLECT = r"""
import importlib.metadata as m,json,pathlib,hashlib,sys
root=pathlib.Path(sys.prefix)
packages=[]
for distribution in m.distributions():
    licenses=[];native=[]
    for entry in distribution.files or []:
        path=pathlib.Path(str(distribution.locate_file(entry)))
        if not path.is_file():continue
        if any(x in path.name.lower() for x in ('license','copying')):
            licenses.append({'path':str(path.relative_to(root)),
                             'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        if '.so' in path.name:
            with path.open('rb') as source: digest=hashlib.file_digest(source,'sha256').hexdigest()
            native.append({'path':str(path.relative_to(root)),'sha256':digest})
    metadata=distribution.metadata
    wheel=distribution.read_text('WHEEL') or ''
    tags=[line.removeprefix('Tag: ') for line in wheel.splitlines() if line.startswith('Tag: ')]
    packages.append({'name':metadata['Name'],'version':distribution.version,
                     'wheel_tags':tags,'license_files':licenses,'native_files':native})
print(json.dumps(packages))
"""


def wheel_tags(url: str) -> set[str]:
    filename = urllib.parse.unquote(url.rsplit("/", 1)[-1])
    python, abi, platforms = filename.removesuffix(".whl").rsplit("-", 3)[-3:]
    return {
        "-".join(parts)
        for parts in itertools.product(python.split("."), abi.split("."), platforms.split("."))
    }


def canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def main() -> int:
    components: dict[str, Any] = {}
    for component in ("cad", "mesh", "post"):
        project = ROOT / "services/worker/environments" / component
        lock = tomllib.loads((project / "uv.lock").read_text())
        indexed = {p["name"]: p for p in lock["package"] if "registry" in p["source"]}
        installed = json.loads(
            subprocess.check_output(
                [str(NATIVE / "venvs" / component / "bin/python"), "-I", "-c", COLLECT],
                text=True,
            )
        )
        for package in installed:
            pinned = indexed[canonical(package["name"])]
            assert pinned["version"] == package["version"]
            metadata_url = f"https://pypi.org/pypi/{pinned['name']}/{pinned['version']}/json"
            with urllib.request.urlopen(metadata_url, timeout=30) as response:
                metadata = json.load(response)["info"]
            package["license"] = (
                metadata.get("license_expression")
                or [c for c in metadata["classifiers"] if c.startswith("License ::")]
                or metadata.get("license")
                or "upstream metadata absent; see license files/review notes"
            )
            package["metadata_url"] = metadata_url
            package["upstream"] = metadata.get("project_urls") or metadata.get("home_page")
            package["wheel_artifacts"] = [
                w
                for w in pinned.get("wheels", [])
                if wheel_tags(w["url"]) & set(package["wheel_tags"])
            ]
            assert package["wheel_artifacts"], f"No matching locked wheel for {package['name']}"
        components[component] = {
            "lockfile_sha256": sha256(project / "uv.lock"),
            "packages": sorted(installed, key=lambda p: p["name"]),
            "functional_probe": json.loads(
                (NATIVE / "validation" / f"{component}.json").read_text()
            ),
        }
    licenses = ROOT / "docs/validation/native-licenses"
    licenses.mkdir(parents=True, exist_ok=True)
    copied: list[dict[str, str]] = []
    candidates = {
        "Gmsh-4.15.2.txt": NATIVE / "venvs/mesh/share/doc/gmsh/LICENSE.txt",
        "ARPACK-NG-debian.txt": NATIVE / "sysroot/usr/share/doc/libarpack2-dev/copyright",
        "BLAS-LAPACK-debian.txt": NATIVE / "sysroot/usr/share/doc/libblas3/copyright",
        # GCC runtime packages link their notices to the matching base-package notice.
        "GNU-runtime-debian.txt": Path("/usr/share/doc/gcc-14-base/copyright"),
        "SPOOLES-upstream.html": NATIVE / "build/spooles/spooles.2.2.html",
    }
    for name, path in candidates.items():
        destination = licenses / name
        shutil.copyfile(path.resolve(), destination)
        copied.append({"file": str(destination.relative_to(ROOT)), "sha256": sha256(destination)})
    # The OCP wheel supplies an auditwheel SBOM, which must not be mistaken for a license audit.
    sbom = next((NATIVE / "venvs/cad").rglob("auditwheel.cdx.json"))
    build = json.loads((NATIVE / "build.json").read_text())
    report = {
        "scope": "T002 private/local development inventory; public license remains deferred",
        "source_artifact_lock": "scripts/native/toolchain-lock.json",
        "source_artifact_lock_sha256": sha256(ROOT / "scripts/native/toolchain-lock.json"),
        "solver_build": build,
        "components": components,
        "license_copies": copied,
        "cad_bundled_components_sbom": json.loads(sbom.read_text()).get("components", []),
        "review_limits": [
            "CCX headers use GPLv2/GPLv2-or-later wording; "
            "review the complete source before publishing.",
            "OCCT is LGPL-2.1 with the upstream exception; OCP binding metadata is Apache-2.0.",
            "Gmsh includes the GPLv2-or-later linking exception and bundled components.",
            "Wheel metadata and SBOMs do not establish redistribution compliance.",
            "Project license deferred; preserve source/notice/relinking obligations.",
        ],
    }
    destination = ROOT / "docs/validation/native-dependencies.json"
    destination.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(
        "Recorded native artifacts, shared-library hashes and licenses: "
        f"{destination.relative_to(ROOT)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
