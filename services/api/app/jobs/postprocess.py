"""Result validation entry point inside the bounded, networkless parser sandbox."""

import errno
import json
from pathlib import Path
from typing import Any

from app.domain.assembly import validate_solution
from app.domain.deck_service import canonical
from app.domain.errors import DomainError
from app.domain.jobs import JobInput
from app.domain.loads import load_state
from worker.actions import external_balance
from worker.local_solve import SolverSingularity, result_mesh, validate_outputs


class ValidationFailure(DomainError):
    def __init__(self, code: str, summary: dict[str, Any]) -> None:
        super().__init__(422, code, "Raw outputs did not pass result validation")
        self.summary = summary


def process(
    output: Path, inputs: JobInput, input_hash: str, execution: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    snapshot = inputs.snapshot
    assert inputs.mesh is not None and inputs.deck_sha256 is not None
    raw_mesh = (output / "mesh.json").read_bytes()
    materials = {body.id: f"M{i}" for i, body in enumerate(snapshot.geometry.bodies, 1)}
    result, summary = validate_outputs(
        output,
        json.loads(raw_mesh),
        materials,
        execution,
        input_hash,
        inputs.deck_sha256,
        inputs.mesh.sha256,
    )
    assembly = validate_solution(
        snapshot,
        json.loads(raw_mesh),
        (output / "analysis.inp").read_text(),
        result,
        summary,
    )
    result["assembly"] = assembly
    summary["assembly"] = assembly
    reference = load_state(
        snapshot.analysis,
        snapshot.geometry,
        snapshot.materials,
        snapshot.loads,
        inputs.display,
        snapshot.bonds,
    ).model_dump(mode="json")
    reference["equilibrium_policy"] = inputs.policy["equilibrium"]
    equilibrium, _ = external_balance(
        result["dat"],
        result_mesh(json.loads(raw_mesh), materials),
        json.loads(raw_mesh)["boundary"],
        (output / "analysis.inp").read_text(),
        reference,
    )
    summary["equilibrium"] = equilibrium
    if not equilibrium["passed"]:
        raise ValidationFailure("equilibrium_failed", summary)
    result["equilibrium"] = equilibrium
    summary["warnings"] = list(dict.fromkeys([*inputs.warnings, *summary["warnings"]]))
    result["warnings"] = summary["warnings"]
    return result, summary


def main() -> None:
    output = Path("/work/out")
    request = json.loads((output / "request.json").read_bytes())
    try:
        result, summary = process(
            output,
            JobInput.model_validate(request["inputs"]),
            request["input_hash"],
            request["execution"],
        )
        outcome: dict[str, Any] = {"result": result, "summary": summary}
    except ValidationFailure as error:
        outcome = {"error": error.code, "summary": error.summary}
    except SolverSingularity:
        outcome = {"error": "solver_singular"}
    except DomainError as error:
        outcome = {"error": error.code}
    except (ValueError, KeyError, TypeError, AssertionError):
        outcome = {"error": "invalid_output"}
    except OSError as error:
        outcome = {"error": "disk_full" if error.errno == errno.ENOSPC else "worker_failed"}
    (output / "outcome.json").write_bytes(canonical(outcome))


if __name__ == "__main__":
    main()
