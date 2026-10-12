"""Tensor invariants in canonical order xx,yy,zz,xy,yz,zx, in Pa."""

import math
from collections.abc import Sequence

Tensor = tuple[float, float, float, float, float, float]
COMPONENTS = ("xx", "yy", "zz", "xy", "yz", "zx")


def tensor(values: Sequence[float]) -> Tensor:
    if len(values) != 6 or not all(math.isfinite(v) for v in values):
        raise ValueError("Expected six finite stress components")
    return (values[0], values[1], values[2], values[3], values[4], values[5])


def von_mises(value: Tensor) -> float:
    # Normalize first to avoid overflow/underflow for finite engineering inputs.
    value = tensor(value)
    factor = max(map(abs, value))
    if not factor:
        return 0.0
    x, y, z, xy, yz, zx = (v / factor for v in value)
    return factor * math.sqrt(
        ((x - y) ** 2 + (y - z) ** 2 + (z - x) ** 2) / 2 + 3 * (xy * xy + yz * yz + zx * zx)
    )


def principal(value: Tensor) -> tuple[float, float, float]:
    # Scaled symmetric Jacobi rotations avoid acos cancellation at repeated roots.
    value = tensor(value)
    factor = max(map(abs, value))
    if not factor:
        return (0.0, 0.0, 0.0)
    x, y, z, xy, yz, zx = (v / factor for v in value)
    matrix = [[x, xy, zx], [xy, y, yz], [zx, yz, z]]
    for _iteration in range(32):
        p, q = max(((0, 1), (0, 2), (1, 2)), key=lambda pair: abs(matrix[pair[0]][pair[1]]))
        off = matrix[p][q]
        if abs(off) <= 1e-15:
            break
        tau = (matrix[q][q] - matrix[p][p]) / (2 * off)
        tangent = math.copysign(1.0, tau) / (abs(tau) + math.hypot(1.0, tau))
        cosine = 1 / math.sqrt(1 + tangent * tangent)
        sine = tangent * cosine
        matrix[p][p] -= tangent * off
        matrix[q][q] += tangent * off
        matrix[p][q] = matrix[q][p] = 0.0
        for k in range(3):
            if k not in (p, q):
                kp, kq = matrix[k][p], matrix[k][q]
                matrix[k][p] = matrix[p][k] = cosine * kp - sine * kq
                matrix[k][q] = matrix[q][k] = sine * kp + cosine * kq
    else:
        raise ValueError("Symmetric principal-stress iteration did not converge")
    ordered = sorted((matrix[i][i] * factor for i in range(3)), reverse=True)
    return (ordered[0], ordered[1], ordered[2])
