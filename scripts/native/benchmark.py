"""Selected benchmark command; unsigned manifests support explicit diagnostics only."""

import argparse
import json
from pathlib import Path

from worker.benchmark import run_case
from worker.runtime import ROOT


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "case", choices=["B01", "B02", "B03", "B04", "B05", "B06", "B07", "B08", "B09"]
    )
    parser.add_argument("--development", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        print(
            json.dumps(
                run_case(
                    args.case,
                    args.output or ROOT / f".local/native/benchmarks/{args.case}",
                    args.development,
                ),
                indent=2,
            )
        )
    except (ValueError, RuntimeError) as error:
        parser.exit(2, f"BLOCKED/FAILED: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
