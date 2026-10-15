"""Offline vector figures from verified element-owned data and explicit cameras."""

import math
from collections.abc import Callable
from html import escape
from typing import Any

from app.domain.reports import ReportViewDefinition
from app.domain.results import ResultView
from worker.postprocess.comparison import scalar


def vector(a: list[float], b: list[float]) -> list[float]:
    return [x - y for x, y in zip(a, b, strict=True)]


def unit(a: list[float]) -> list[float]:
    length = math.hypot(*a)
    if length < 1e-20 or not math.isfinite(length):
        raise ValueError("Degenerate report camera")
    return [v / length for v in a]


def dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def projection(
    view: ResultView, definition: ReportViewDefinition
) -> Callable[[list[float]], tuple[float, float, float]]:
    camera = definition.camera
    origin = [
        (
            min(v.position_m[a] for v in view.data.vertices)
            + max(v.position_m[a] for v in view.data.vertices)
        )
        / 2
        for a in range(3)
    ]
    forward = unit(vector(list(camera.focal), list(camera.position)))
    up = list(camera.up)
    right = unit(
        [
            forward[1] * up[2] - forward[2] * up[1],
            forward[2] * up[0] - forward[0] * up[2],
            forward[0] * up[1] - forward[1] * up[0],
        ]
    )
    up = [
        right[1] * forward[2] - right[2] * forward[1],
        right[2] * forward[0] - right[0] * forward[2],
        right[0] * forward[1] - right[1] * forward[0],
    ]

    def project(point: list[float]) -> tuple[float, float, float]:
        relative = vector(vector(point, origin), list(camera.position))
        depth = dot(relative, forward)
        height = (
            camera.parallel_scale
            if camera.parallel
            else depth * math.tan(math.radians(camera.angle) / 2)
        )
        if depth <= 0 or height <= 0 or not math.isfinite(height):
            raise ValueError("Selected report view lies behind the camera; reset the result camera")
        x, y = 300 + 200 * dot(relative, right) / height, 200 - 200 * dot(relative, up) / height
        if not all(math.isfinite(v) for v in (x, y, depth)) or max(abs(x), abs(y)) > 1e7:
            raise ValueError(
                "Selected report view exceeds projection bounds; reset the result camera"
            )
        return x, y, depth

    return project


def rgb(value: float, limits: tuple[float, float]) -> str:
    low, high = limits
    constant = high - low <= max(1e-14, max(abs(low), abs(high)) * 1e-12)
    t = 0.5 if constant else min(1, max(0, (value - low) / (high - low)))
    # Match the existing boundary colour map (round half upward).
    values = (255 * t, 190 * (1 - abs(2 * t - 1)), 255 * (1 - t))
    return "rgb(" + ",".join(str(math.floor(v + 0.5)) for v in values) + ")"


def figure(
    view: ResultView,
    definition: ReportViewDefinition,
    geometry: dict[str, Any],
    *,
    markers: list[dict[str, Any]] | None = None,
) -> str:
    project = projection(view, definition)
    vertices = geometry["vertices"]
    if len(geometry["triangles"]) > 40000:
        raise ValueError("Report figures are limited to 40,000 triangles")
    points = [
        project(
            [
                p + definition.deformation_scale * u
                for p, u in zip(v["position_m"], v["displacement_m"], strict=True)
            ]
        )
        for v in vertices
    ]
    faces = []
    for triangle in geometry["triangles"]:
        if vertices[triangle[0]]["body_id"] not in definition.visible_body_ids:
            continue
        projected = [points[i] for i in triangle]
        value = (
            sum(scalar(vertices[i], definition.field, definition.smoothed) for i in triangle) / 3
        )
        fill = "#dce4eb" if markers is not None else rgb(value, definition.range_si)
        coords = " ".join(f"{x:.3f},{y:.3f}" for x, y, _ in projected)
        faces.append(
            (sum(p[2] for p in projected) / 3, f'<polygon points="{coords}" fill="{fill}"/>')
        )
    if not faces:
        raise ValueError("Selected report view has no visible triangles")
    drawing = "".join(text for _, text in sorted(faces, key=lambda p: -p[0]))
    if markers is not None:
        extent = max(
            max(v.position_m[a] for v in view.data.vertices)
            - min(v.position_m[a] for v in view.data.vertices)
            for a in range(3)
        )
        for index, marker in enumerate(markers, 1):
            x, y, _ = project(marker["position_m"])
            direction = marker["direction"]
            if math.hypot(*direction) > 0:
                d = unit(direction)
                end = [p + extent * 0.12 * a for p, a in zip(marker["position_m"], d, strict=True)]
                ex, ey, _ = project(end)
                drawing += (
                    f'<path d="M{x:.2f},{y:.2f} L{ex:.2f},{ey:.2f}" '
                    'stroke="#172e46" stroke-width="2" marker-end="url(#arrow)"/>'
                )
            else:
                drawing += (
                    f'<rect x="{x - 4:.2f}" y="{y - 4:.2f}" width="8" height="8" fill="#172e46"/>'
                )
            drawing += (
                f'<text x="{x + 6:.2f}" y="{y - 6:.2f}" font-size="11" fill="#111">{index}</text>'
            )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 400" role="img">'
        '<rect width="600" height="400" fill="white"/><defs><clipPath id="bounds">'
        '<rect width="600" height="400"/></clipPath><marker id="arrow" markerWidth="8" '
        'markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L0,6 L7,3 z" '
        'fill="#172e46"/></marker></defs><g clip-path="url(#bounds)">' + drawing + "</g></svg>"
    )


def legend(label: str, unit_label: str, limits: tuple[float, float], factor: float) -> str:
    text = escape(f"{label} ({unit_label}): {limits[0] / factor:.6g} to {limits[1] / factor:.6g}")
    constant = limits[1] - limits[0] <= max(1e-14, max(abs(v) for v in limits) * 1e-12)
    bars = "".join(
        (
            f'<rect x="{i * 5}" y="25" width="5" height="15" '
            f'fill="{rgb(limits[0] + (limits[1] - limits[0]) * i / 99, limits)}"/>'
        )
        for i in range(100)
    )
    note = (
        "Constant field; uniform colour."
        if constant
        else "Colour limits clamp display only; raw extrema remain independent."
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 65">'
        f'<text x="0" y="16" font-size="14">{text}</text>{bars}'
        f'<text x="0" y="59" font-size="11">{note}</text></svg>'
    )
