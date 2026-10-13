"""Record lockfile artifact hashes and authoritative package license metadata."""

import hashlib
import importlib.metadata
import json
import tomllib
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    with (ROOT / "uv.lock").open("rb") as source:
        lock = tomllib.load(source)
    python = []
    for package in lock["package"]:
        if "registry" not in package["source"]:
            continue
        name, version = package["name"], package["version"]
        metadata_url = f"https://pypi.org/pypi/{name}/{version}/json"
        with urllib.request.urlopen(metadata_url, timeout=30) as response:
            info = json.load(response)["info"]
        licenses = [c for c in info["classifiers"] if c.startswith("License ::")]
        license_value = info.get("license_expression") or licenses or info.get("license")
        license_evidence: list[dict[str, str]] = []
        if not license_value:
            try:
                installed = importlib.metadata.distribution(name)
                if installed.version == version:
                    for file in installed.files or []:
                        if Path(str(file)).name == "LICENSE":
                            contents = Path(str(installed.locate_file(file))).read_bytes()
                            license_value = contents.decode()
                            license_evidence.append(
                                {
                                    "installed_wheel_path": str(file),
                                    "sha256": hashlib.sha256(contents).hexdigest(),
                                }
                            )
            except importlib.metadata.PackageNotFoundError:
                pass
        python.append(
            {
                "name": name,
                "version": version,
                "license": license_value or "UNKNOWN",
                "license_evidence": license_evidence,
                "upstream": info.get("project_urls") or info.get("home_page"),
                "metadata_url": metadata_url,
                "artifacts": [package["sdist"]] + package.get("wheels", [])
                if "sdist" in package
                else package.get("wheels", []),
            }
        )
    npm = []
    packages = json.loads((ROOT / "package-lock.json").read_text())["packages"]
    for location, package in sorted(packages.items()):
        if "resolved" not in package or package.get("link"):
            continue
        name = location.rsplit("node_modules/", 1)[-1]
        npm.append(
            {
                "name": name,
                "version": package["version"],
                "location": location,
                "license": package.get("license", "UNKNOWN"),
                "upstream": f"https://www.npmjs.com/package/{name}/v/{package['version']}",
                "artifact_url": package["resolved"],
                "integrity": package.get("integrity"),
            }
        )
    report = {
        "scope": "T001 locked development dependencies; not a redistribution approval",
        "python": python,
        "npm": npm,
    }
    destination = ROOT / "docs/validation/dependencies.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(
        f"Recorded {len(python)} Python and {len(npm)} npm lock entries "
        f"in {destination.relative_to(ROOT)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
