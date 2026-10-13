"""Generate/check the real API schema and its TypeScript client contract."""

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from app.main import create_app

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    schema = json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n"
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "openapi.json"
        target = Path(directory) / "api.d.ts"
        source.write_text(schema)
        subprocess.run(
            [str(ROOT / "node_modules/.bin/openapi-typescript"), str(source), "-o", str(target)],
            cwd=ROOT,
            check=True,
        )
        for name, contents in (("openapi.json", schema), ("api.d.ts", target.read_text())):
            destination = ROOT / "packages/contracts" / name
            if args.check:
                if not destination.exists() or destination.read_text() != contents:
                    print(f"FAIL: stale {destination.relative_to(ROOT)}; run make contracts")
                    return 1
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(contents)
    print("PASS: API OpenAPI and TypeScript contracts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
