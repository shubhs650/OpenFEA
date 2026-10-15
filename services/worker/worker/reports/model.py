"""One report model feeds PDF and the future editable Word adapter."""

import json
from typing import Any

from app.domain.jobs import JobInput, LocalJob
from app.domain.loads import LoadState
from app.domain.reports import ReportTable
from app.domain.results import ResultView
from app.domain.units import PRESETS, PresetID


def value(v: Any, factor: float = 1) -> str:
    if v is None:
        return "Unavailable"
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(value(x, factor) for x in v) + "]"
    return f"{v / factor:.7g}"


def tables(
    inputs: JobInput,
    job: LocalJob,
    view: ResultView,
    loads: LoadState,
    mesh: dict[str, Any],
    units: PresetID,
) -> list[ReportTable]:
    snapshot, data = inputs.snapshot, view.data
    preset = PRESETS[units]
    length, stress, force = preset.length, preset.stress, preset.force
    result = []

    def table(title: str, columns: list[str], rows: list[list[str]]) -> None:
        result.append(ReportTable(title=title, columns=columns, rows=rows))

    bounds = [min(v.position_m[a] for v in data.vertices) for a in range(3)] + [
        max(v.position_m[a] for v in data.vertices) for a in range(3)
    ]
    table(
        "Geometry and source units",
        ["Fact", "Frozen value"],
        [
            ["Geometry revision", str(snapshot.geometry.id)],
            ["Source length unit", snapshot.geometry.units.source_length_unit],
            [f"Bounds ({length.label})", value(bounds, length.to_si)],
            [
                f"Dimensions ({length.label})",
                value([bounds[i + 3] - bounds[i] for i in range(3)], length.to_si),
            ],
            ["Bodies / faces", f"{len(snapshot.geometry.bodies)} / {len(snapshot.geometry.faces)}"],
            ["Geometry SHA-256", snapshot.geometry.brep_sha256],
        ],
    )
    table(
        "Material properties",
        [
            "Body / material",
            f"E ({stress.label}) / Poisson ratio",
            f"Density ({preset.density.label})",
            f"Yield ({stress.label})",
        ],
        [
            [
                a.body_id + " / " + a.material.provenance.name,
                value(a.material.properties.young_modulus_pa, stress.to_si)
                + " / "
                + value(a.material.properties.poisson_ratio),
                value(a.material.properties.density_kg_m3, preset.density.to_si),
                value(a.material.properties.yield_strength_pa, stress.to_si),
            ]
            for a in snapshot.materials.assignments
        ],
    )
    provenance = []
    for a in snapshot.materials.assignments:
        p = a.material.provenance
        provenance += [
            [a.body_id, "Grade / condition", p.grade + " / " + p.condition],
            [a.body_id, "Temperature / assumptions", p.temperature_note + " / " + p.assumptions],
            [
                a.body_id,
                "Library / original units",
                f"{a.material.library_id} / {a.material.library_version} / "
                f"{a.material.source_units}",
            ],
        ]
        provenance += [
            [
                a.body_id,
                s.title,
                f"{s.url or 'No URL supplied'}; accessed {s.accessed_on or 'not supplied'}",
            ]
            for s in p.sources
        ]
    table("Material provenance", ["Body", "Detail", "Source / assumption"], provenance)
    load_rows = []
    for load in snapshot.loads.assignments:
        details = []
        for label, v, factor in [
            (f"Pressure {stress.label}", load.pressure_pa, stress.to_si),
            (f"Total force {force.label}", load.force_n, force.to_si),
            (f"Displacement {length.label}", load.displacement_m, length.to_si),
            (
                f"Gravity {preset.acceleration.label}",
                load.acceleration_m_s2,
                preset.acceleration.to_si,
            ),
        ]:
            if v is not None:
                details.append(label + ": " + value(v, factor))
        if load.axis:
            details.append("Global component " + load.axis)
        if load.direction:
            details.append("Global direction " + value(load.direction.vector))
        details += (
            [
                "Symmetry basis "
                + json.dumps(
                    {k: v.model_dump(mode="json") for k, v in load.symmetry_directions.items()}
                )
            ]
            if load.symmetry_directions
            else []
        )
        load_rows.append(
            [
                load.name + " / " + load.kind,
                ", ".join(load.face_ids + load.body_ids),
                "; ".join(details) or "All translations fixed",
            ]
        )
    table(
        "Loads and supports",
        ["Assignment", "Immutable targets", "Physical value / direction"],
        load_rows,
    )
    table(
        "Setup figure markers",
        ["Marker", "Assignment / kind", f"Position ({length.label}) / global direction"],
        [
            [
                str(i),
                str(m.assignment_id) + " / " + m.kind,
                value(m.position_m, length.to_si) + " / " + value(m.direction),
            ]
            for i, m in enumerate(loads.markers, 1)
        ],
    )
    table(
        "Bond review and gaps",
        ["Connection", "Master / slave", "Approved gap / review"],
        [
            [
                a.name,
                a.master_face_id + " / " + a.slave_face_id,
                f"Measured {a.pair.gap_m:g} m; tolerance {a.gap_tolerance_m:g} m; "
                f"gap approved {a.gap_approved}; "
                f"assumptions confirmed {a.assumptions_confirmed}; "
                f"policy {a.policy}; review SHA-256 {a.review_sha256}",
            ]
            for a in snapshot.bonds.assignments
        ]
        or [["None", "No bonded connections", "Single body or disconnected setup as frozen"]],
    )
    # Preserve complete quality/policy data in the model; expose a bounded readable summary.
    table(
        "Mesh and solver",
        ["Fact", "Frozen value"],
        [
            [
                "Element / node count",
                f"C3D10 / {len(mesh['elements'])} elements / {len(mesh['nodes'])} nodes",
            ],
            [
                "Quality",
                json.dumps(
                    {k: v for k, v in mesh.get("quality", {}).items() if k != "cells"},
                    ensure_ascii=False,
                ),
            ],
            ["Mesh controls", json.dumps(snapshot.mesh_setup.model_dump(mode="json"))],
            ["Solver", f"CalculiX {inputs.policy.get('calculix', 'unavailable')}"],
            ["Solver binary SHA-256", str(inputs.policy.get("ccx_sha256", "Unavailable"))],
            [
                "Original solve CPU/RAM/thread inventory",
                (
                    "Not recorded in this legacy local run; resource policy and "
                    "measured usage are retained in run artifacts."
                ),
            ],
            [
                "Native build SHA-256",
                str(inputs.policy.get("native_build_manifest_sha256", "unavailable")),
            ],
            [
                "Numerical method",
                "Linear static / small deformation / global Cartesian / C3D10; no stabilization",
            ],
        ],
    )

    def sample(s: Any) -> str:
        return (
            f"{s.location}; node {s.node_id}; element {s.element_id}; "
            f"IP {s.integration_point_id}; body {s.body_id}; material {s.material_id}; "
            f"position {value(s.position_m, length.to_si)} {length.label}"
        )

    table(
        "Raw native extrema — all bodies",
        ["Field / location", "Minimum", "Maximum / identity"],
        [
            [
                f.label
                + f" ({length.label if f.unit == 'm' else stress.label}); "
                + f.raw_location,
                value(f.extrema.minimum.value, length.to_si if f.unit == "m" else stress.to_si)
                + "; "
                + sample(f.extrema.minimum),
                value(f.extrema.maximum.value, length.to_si if f.unit == "m" else stress.to_si)
                + "; "
                + sample(f.extrema.maximum),
            ]
            for f in data.fields
        ],
    )
    table(
        "Yield assessment — frozen supplied strength / raw integration-point von Mises",
        ["Body / material", f"Yield ({stress.label})", "Factor / critical location"],
        [
            [
                f.body_id + " / " + f.material_name,
                value(f.yield_strength_pa, stress.to_si),
                (
                    value(f.minimum)
                    if f.state == "finite"
                    else (
                        "Unavailable — missing yield"
                        if f.state == "unavailable"
                        else "Unbounded/undefined — zero stress"
                    )
                )
                + "; "
                + sample(f.critical_sample),
            ]
            for f in data.yield_factors
        ],
    )
    table(
        "External reactions about global origin",
        [
            "Body / constrained nodes / DOFs",
            f"Force ({force.label})",
            f"Moment ({force.label}·{length.label})",
        ],
        [
            [
                f"{r.body_id} / {r.node_count} / {r.constrained_dof_count}",
                value(r.force_n, force.to_si),
                value(r.moment_nm, force.to_si * length.to_si),
            ]
            for r in data.reactions
        ],
    )
    balance_rows = []
    for name in ("force", "moment"):
        b = getattr(data.equilibrium, name)
        factor = force.to_si * (length.to_si if name == "moment" else 1)
        label = force.label + ("·" + length.label if name == "moment" else "")
        balance_rows.append(
            [
                name + " (" + label + ")",
                value(b.residual, factor) + "; norm " + value(b.residual_norm, factor),
                value(b.reference, factor),
                b.criterion
                + "; relative "
                + value(b.relative_residual)
                + "; allowed "
                + value(b.tolerance, factor),
                "Passed" if b.passed else "Failed",
            ]
        )
    table(
        "Force and moment equilibrium",
        ["Balance", "Residual", "Reference", "Criterion / limit", "Outcome"],
        balance_rows,
    )
    table(
        "Equilibrium method and actions",
        ["Fact", "Value"],
        [
            ["Method", data.equilibrium.method],
            ["Reaction method", data.reaction_method],
            ["Moment origin (m)", value(data.equilibrium.moment_origin_m)],
            [
                f"Applied force ({force.label})",
                value(data.equilibrium.applied_force_n, force.to_si),
            ],
            [
                f"Applied moment ({force.label}·{length.label})",
                value(data.equilibrium.applied_moment_nm, force.to_si * length.to_si),
            ],
            ["Stress / extrema method", data.stress_method + "; " + data.extrema_method],
        ],
    )
    return result
