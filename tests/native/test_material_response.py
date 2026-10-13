"""Analytical native compatibility of canonical materials; no product solve claim."""

import json
from pathlib import Path
from typing import Any

import pytest

from app.domain.materials import SAMPLES, CustomMaterial, MaterialValues, custom_snapshot
from app.domain.units import PRESETS, from_si
from worker.benchmark import solve
from worker.deck import generated_deck
from worker.meshing import Vec, norm, total_face_force
from worker.runtime import quadratic_mesh, synthetic_geometry


@pytest.mark.parametrize("ratio", [0.0, 0.3, 0.45])
def test_unit_presets_produce_equivalent_materials_and_real_axial_response(
    tmp_path: Path, ratio: float
) -> None:
    # E=200 GPa, A=1 m², L=1 m, F=1 MN, sigma=1 MPa; free lateral contraction.
    # Fixed criteria before execution: displacement 1e-11 m, raw tensor 10 Pa.
    snapshots = []
    for preset in PRESETS:
        snapshots.append(
            custom_snapshot(
                CustomMaterial(
                    kind="custom",
                    units=preset,
                    confirmed=True,
                    values=MaterialValues(
                        young_modulus=from_si(200e9, preset, "stress"),
                        poisson_ratio=ratio,
                        density=from_si(7900, preset, "density"),
                    ),
                    provenance=SAMPLES["stainless-304"].provenance,
                )
            )
        )
    assert all(s.properties.young_modulus_pa == pytest.approx(200e9, rel=2e-16) for s in snapshots)
    synthetic_geometry(tmp_path, "box")
    quadratic_mesh(tmp_path, 0.6)
    mesh: dict[str, Any] = json.loads((tmp_path / "mesh.json").read_text())
    catalog = json.loads((tmp_path / "catalog.json").read_text())
    nodes: dict[int, Vec] = {int(n): tuple(p) for n, p in mesh["nodes"].items()}
    supports = {(n, 1): 0.0 for n, p in nodes.items() if abs(p[0]) < 1e-9}
    origin = next(n for n, p in nodes.items() if norm(p) < 1e-9)
    edge = next(n for n, p in nodes.items() if norm((p[0], p[1] - 1, p[2])) < 1e-9)
    supports.update({(origin, 2): 0.0, (origin, 3): 0.0, (edge, 3): 0.0})
    face = next(f["id"] for f in catalog["faces"] if abs(f["center"][0] - 1) < 1e-9)
    loads = total_face_force(
        [tuple(f["nodes"]) for f in mesh["boundary"][face]], nodes, (1e6, 0, 0)
    )
    measurements = []
    for preset, snapshot in zip(PRESETS, snapshots, strict=True):
        props = snapshot.properties
        deck = generated_deck(mesh, supports, loads, props.young_modulus_pa, props.poisson_ratio)
        directory = tmp_path / preset
        directory.mkdir()
        displacement, stress, _ = solve(directory, deck)
        expected = {
            n: (5e-6 * p[0], -ratio * 5e-6 * p[1], -ratio * 5e-6 * p[2]) for n, p in nodes.items()
        }
        displacement_error = max(
            abs(displacement[n][k] - expected[n][k]) for n in nodes for k in range(3)
        )
        tensor_error = max(
            abs(row[k + 2] - (1e6 if k == 0 else 0)) for row in stress for k in range(6)
        )
        assert displacement_error <= 1e-11
        assert tensor_error <= 10
        measurements.append(
            {
                "preset": preset,
                "poisson_ratio": ratio,
                "max_displacement_error_m": displacement_error,
                "max_raw_tensor_error_pa": tensor_error,
            }
        )
    output = Path(".local/native/validation/T009")
    output.mkdir(parents=True, exist_ok=True)
    (output / f"axial-{ratio}.json").write_text(json.dumps(measurements, indent=2) + "\n")
