"""Compare frozen physical setup while allowing names, units and mesh sizing to differ."""

import hashlib
from typing import Any

from app.domain.deck_service import canonical
from app.domain.jobs import JobInput


def physics(input: JobInput) -> dict[str, Any]:
    snapshot = input.snapshot
    loads = []
    for assignment in snapshot.loads.assignments:
        value = assignment.model_dump(mode="json", exclude={"id", "name"})
        value = {k: v for k, v in value.items() if not k.startswith("source_")}
        value["face_ids"] = sorted(value["face_ids"])
        value["body_ids"] = sorted(value["body_ids"])
        loads.append(value)
    bonds = [
        a.model_dump(mode="json", exclude={"id", "name", "review_report", "review_sha256"})
        for a in snapshot.bonds.assignments
    ]
    sources = input.policy.get("sources", {})
    if not isinstance(sources, dict):
        raise ValueError("Invalid frozen numerical source policy")
    numerical_sources = {
        k: v
        for k, v in sources.items()
        if k.startswith("services/worker/worker/")
        and not any(
            part in k
            for part in (
                "meshing_native",
                "mesh_quality",
                "geometry",
                "local_process",
                "runtime",
                "resources",
            )
        )
    }
    return {
        "geometry": snapshot.geometry.model_dump(mode="json"),
        "materials": sorted(
            [
                {
                    "body_id": a.body_id,
                    "material": a.material.model_dump(
                        mode="json", exclude={"source_units", "source_values"}
                    ),
                }
                for a in snapshot.materials.assignments
            ],
            key=lambda a: a["body_id"],
        ),
        "loads_and_supports": sorted(loads, key=lambda v: canonical(v)),
        "bonds": sorted(bonds, key=lambda v: canonical(v)),
        "solver_policy": {k: v for k, v in input.policy.items() if k != "sources"}
        | {"numerical_sources": numerical_sources},
    }


def signature(value: dict[str, Any]) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()
