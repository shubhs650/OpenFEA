"""Verify Make propagates real tool failures; remove temporary probes on every exit."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    probes = [
        ("lint", "services/api/app/_failure_probe.py", "undefined_probe_name\n"),
        ("typecheck", "services/api/app/_failure_probe.py", 'probe: int = "wrong type"\n'),
        (
            "test-unit",
            "tests/unit/test_failure_probe.py",
            "def test_probe() -> None:\n    assert False\n",
        ),
        ("lint", "apps/web/src/_failure_probe.ts", "const unusedProbe = 1;\n"),
        (
            "typecheck",
            "apps/web/src/_failure_probe.ts",
            'export const probe: number = "wrong type";\n',
        ),
        (
            "test-unit",
            "apps/web/src/failure_probe.test.ts",
            "import { expect, it } from 'vitest';\nit('failure probe', () => expect(1).toBe(2));\n",
        ),
    ]
    log_root = ROOT / ".local" / "failure-probes"
    log_root.mkdir(parents=True, exist_ok=True)
    for index, (target, filename, contents) in enumerate(probes, 1):
        path = ROOT / filename
        if path.exists():
            raise RuntimeError(f"Refusing to overwrite {filename}")
        try:
            path.write_text(contents)
            result = subprocess.run(["make", target], cwd=ROOT, capture_output=True, text=True)
            (log_root / f"{index}-{target}.log").write_text(result.stdout + result.stderr)
            if result.returncode == 0:
                raise RuntimeError(f"{target} incorrectly passed with {filename}")
            # Verify the intended file triggered the failure, not an unrelated broken prerequisite.
            if path.name not in result.stdout + result.stderr:
                raise RuntimeError(f"{target} failed without diagnosing {filename}; inspect log")
            print(
                f"PASS: make {target} propagates failure in {filename} (exit {result.returncode})"
            )
        finally:
            path.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
