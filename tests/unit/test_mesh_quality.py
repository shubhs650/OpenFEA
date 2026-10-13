"""Independent analytic quadratic maps; whole-domain positivity beats IP-only sampling."""

import math
from typing import cast

import pytest

from worker.mesh_quality import (
    JACOBIAN_FLOOR,
    bernstein_bounds,
    cell_quality,
    determinant,
    jacobian,
)
from worker.meshing import EDGES, Vec

CORNERS = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)]
REFERENCE = CORNERS + [
    tuple((CORNERS[a][i] + CORNERS[b][i]) / 2 for i in range(3)) for a, b in EDGES
]


@pytest.mark.parametrize("alpha", [0.0, 0.2, -0.4])
def test_quadratic_isoparametric_jacobian_matches_independent_polynomial(alpha: float) -> None:
    # x=r*(1+alpha*s), y=s, z=t. Exact det(J)=1+alpha*s everywhere.
    points = [(r * (1 + alpha * s), s, t) for r, s, t in REFERENCE]
    for r, s, t in ((0.1, 0.2, 0.3), (0.25, 0.25, 0.25), (0, 1, 0), (1, 0, 0)):
        actual = jacobian(points, [1 - r - s - t, r, s, t])
        assert determinant(actual) == pytest.approx(1 + alpha * s, abs=1e-13)
        assert actual[0] == pytest.approx((1 + alpha * s, 0, 0), abs=1e-13)
        assert actual[1] == pytest.approx((alpha * r, 1, 0), abs=1e-13)
    vertices = [jacobian(points, [float(i == j) for i in range(4)]) for j in range(4)]
    lower, upper = bernstein_bounds(vertices)
    assert lower <= min(1, 1 + alpha) and upper >= max(1, 1 + alpha)
    assert abs(lower - min(1, 1 + alpha)) < 1e-12
    assert cell_quality(points)["accepted"]


def test_positive_corners_and_all_four_gauss_points_do_not_hide_folded_midsides() -> None:
    alpha = -1.5
    points = [(r * (1 + alpha * s), s, t) for r, s, t in REFERENCE]
    # Corners are exactly the regular reference tetra; their linear det is 1.
    assert points[:4] == CORNERS
    b = (5 - math.sqrt(5)) / 20
    a = 1 - 3 * b
    for gauss_s in (a, b, b, b):
        assert 1 + alpha * gauss_s > 0
    assert 1 + alpha < 0  # Negative near the s=1 boundary despite positive IP samples.
    result = cell_quality(points)
    assert not result["accepted"] and result["reason"] == "jacobian_unresolved"
    assert float(result["jacobian_lower_m3"]) < 0


def test_regular_tetra_mean_ratio_and_translation_invariance() -> None:
    corners = [
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.5, math.sqrt(3) / 2, 0.0),
        (0.5, math.sqrt(3) / 6, math.sqrt(2 / 3)),
    ]
    points = corners + [
        tuple((corners[a][i] + corners[b][i]) / 2 for i in range(3)) for a, b in EDGES
    ]
    result = cell_quality(cast(list[Vec], points))
    assert result["mean_ratio"] == pytest.approx(1, abs=1e-14)
    translated = cell_quality([(p[0] + 10, p[1] - 20, p[2] + 30) for p in points])
    assert translated["mean_ratio"] == pytest.approx(result["mean_ratio"], abs=1e-12)
    assert translated["jacobian_lower_m3"] == pytest.approx(result["jacobian_lower_m3"], abs=1e-12)


def test_sliver_and_degenerate_cells_fail_without_coordinate_correction() -> None:
    thin = [(x, y, 0.001 * z) for x, y, z in REFERENCE]
    assert cell_quality(thin)["reason"] == "poor_shape"
    degenerate = [(x, y, 0.0) for x, y, z in REFERENCE]
    assert not cell_quality(degenerate)["accepted"]
    assert JACOBIAN_FLOOR == 1e-15
