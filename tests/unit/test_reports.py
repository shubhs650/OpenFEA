"""Report boundary validation and independent scalar colour/projection references."""

import math
from typing import Any

import pytest
from pydantic import ValidationError

from app.domain.reports import ReportRequest
from worker.reports.figures import rgb


def request() -> dict[str, Any]:
    return {
        "title": "Report",
        "units": "mm-N-MPa",
        "views": [
            {
                "field": "sxx",
                "smoothed": False,
                "deformation_scale": 0,
                "range_si": [-1000, 0],
                "visible_body_ids": ["body"],
                "camera": {
                    "position": [2, 2, 2],
                    "focal": [0, 0, 0],
                    "up": [0, 0, 1],
                    "parallel": False,
                    "parallel_scale": 1,
                    "angle": 30,
                },
            }
        ],
    }


@pytest.mark.parametrize(
    "fault", ["nan", "scale", "range", "bodies", "camera", "views", "image", "conclusion"]
)
def test_report_requests_refuse_untrusted_or_invalid_definitions(fault: str) -> None:
    data = request()
    view = data["views"][0]
    if fault == "nan":
        view["camera"]["position"][0] = math.nan
    elif fault == "scale":
        view["deformation_scale"] = -1
    elif fault == "range":
        view["range_si"] = [10, -10]
    elif fault == "bodies":
        view["visible_body_ids"] *= 2
    elif fault == "camera":
        view["camera"]["up"] = [0, 0, 0]
    elif fault == "views":
        data["views"] *= 5
    elif fault == "image":
        view["image_url"] = "file:///etc/passwd"
    else:
        data["user_conclusion"] = "x" * 4001
    with pytest.raises(ValidationError):
        ReportRequest.model_validate(data)


def test_signed_and_constant_contour_colour_references() -> None:
    assert rgb(-1000, (-1000, 0)) == "rgb(0,0,255)"
    assert rgb(-500, (-1000, 0)) == "rgb(128,190,128)"
    assert rgb(0, (-1000, 0)) == "rgb(255,0,0)"
    assert rgb(1000, (-1000, 0)) == "rgb(255,0,0)"
    assert rgb(0, (0, 0)) == "rgb(128,190,128)"


@pytest.mark.parametrize("parallel,angle,x", [(True, 30, 500), (False, 90, 400)])
def test_camera_projection_matches_independent_orthographic_and_perspective_reference(
    parallel: bool, angle: float, x: float
) -> None:
    from types import SimpleNamespace
    from typing import cast

    from app.domain.results import ResultView
    from worker.reports.figures import projection

    data = request()
    data["views"][0]["camera"].update(
        position=[0, 0, 2], up=[0, 1, 0], parallel=parallel, angle=angle
    )
    definition = ReportRequest.model_validate(data).views[0]
    # Symmetric reference box fixes model centre at zero; +x points screen-right.
    view = cast(
        ResultView,
        SimpleNamespace(
            data=SimpleNamespace(
                vertices=[
                    SimpleNamespace(position_m=(-1, -1, -1)),
                    SimpleNamespace(position_m=(1, 1, 1)),
                ]
            )
        ),
    )
    assert projection(view, definition)([1, 0, 0]) == pytest.approx((x, 200, 2))
    assert projection(view, definition)([0, 1, 0])[1] < 200
    with pytest.raises(ValueError):
        projection(view, definition)([0, 0, 3])
