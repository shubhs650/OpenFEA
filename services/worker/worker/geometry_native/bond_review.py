"""Read-only OCCT body intersections and complete trimmed planar-face projections."""

import importlib.util
import itertools
import json
from pathlib import Path

from OCP.BRep import BRep_Builder, BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.BRepTools import BRepTools
from OCP.GeomAbs import GeomAbs_Line
from OCP.gp import gp_Trsf, gp_Vec
from OCP.GProp import GProp_GProps
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_SOLID, TopAbs_VERTEX
from OCP.TopoDS import TopoDS, TopoDS_Shape

spec = importlib.util.spec_from_file_location("cad_export", "/import.py")
cad = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cad)

COINCIDENCE_M = 1e-8
MAX_GAP_M = 1e-5
AREA_TOLERANCE_M2 = 1e-8
VOLUME_TOLERANCE_M3 = 1e-12


def mass(shape, surface=False):
    props = GProp_GProps()
    if surface:
        BRepGProp.SurfaceProperties_s(shape, props)
    else:
        BRepGProp.VolumeProperties_s(shape, props)
    return abs(props.Mass())


def common(a, b, surface=False):
    operation = BRepAlgoAPI_Common(a, b)
    operation.Build()
    if not operation.IsDone() or not BRepCheck_Analyzer(operation.Shape()).IsValid():
        raise ValueError("Native intersection could not be verified")
    return mass(operation.Shape(), surface)


def unit_square(face):
    edges = cad.explore(face, TopAbs_EDGE)
    if len(edges) != 4 or any(
        BRepAdaptor_Curve(TopoDS.Edge(e)).GetType() != GeomAbs_Line for e in edges
    ):
        return False
    points = sorted(
        {BRep_Tool.Pnt_s(TopoDS.Vertex(v)).Coord() for v in cad.explore(face, TopAbs_VERTEX)}
    )
    if len(points) != 4:
        return False
    lengths = sorted(
        sum((a - b) ** 2 for a, b in zip(p, q, strict=True))
        for p, q in itertools.combinations(points, 2)
    )
    return max(abs(a - b) for a, b in zip(lengths, [1, 1, 1, 1, 2, 2], strict=True)) <= 1e-8


def review():
    if cad.importlib.metadata.version("cadquery-ocp") != "8.0.1.1.0":
        raise RuntimeError("Unpinned CAD binding")
    metadata = json.loads(Path("/work/metadata.json").read_text())
    source = Path("/work/source.step")
    if cad.digest(source) != metadata["brep_sha256"]:
        raise ValueError("Stale BREP")
    if len(metadata["faces"]) > 100:
        raise ValueError("Bond review is bounded to 100 CAD faces")
    shape = TopoDS_Shape()
    if (
        not BRepTools.Read_s(shape, str(source), BRep_Builder())
        or not BRepCheck_Analyzer(shape).IsValid()
    ):
        raise ValueError("Invalid BREP")
    solids = cad.explore(shape, TopAbs_SOLID)
    if len(solids) != len(metadata["bodies"]):
        raise ValueError("Body catalog mismatch")
    faces = {}
    overlaps = []
    for i, solid in enumerate(solids):
        body = metadata["bodies"][i]["id"]
        selected = [f for f in metadata["faces"] if f["body_id"] == body]
        native = cad.explore(solid, TopAbs_FACE)
        if len(selected) != len(native):
            raise ValueError("Face catalog mismatch")
        for fi, (face, record) in enumerate(zip(native, selected, strict=True), 1):
            if record["id"] != f"{body}:f{fi}":
                raise ValueError("Face identity mismatch")
            if abs(mass(face, True) - record["signature"]["area_m2"]) > AREA_TOLERANCE_M2:
                raise ValueError("Face identity mismatch")
            faces[record["id"]] = face
    for i, j in itertools.combinations(range(len(solids)), 2):
        volume = common(solids[i], solids[j])
        if volume > VOLUME_TOLERANCE_M3:
            overlaps.append(
                {"body_ids": [metadata["bodies"][k]["id"] for k in (i, j)], "volume_m3": volume}
            )
    pairs = []
    for a, b in itertools.combinations(metadata["faces"], 2):
        if a["body_id"] == b["body_id"]:
            continue
        sa, sb = a["signature"], b["signature"]
        na, nb = sa.get("outward_normal"), sb.get("outward_normal")
        if na is None or nb is None:
            continue
        normal_dot = sum(x * y for x, y in zip(na, nb, strict=True))
        if normal_dot > -1 + 1e-10:
            continue
        gap = sum((y - x) * n for x, y, n in zip(sa["center_m"], sb["center_m"], na, strict=True))
        # Include up to 1 mm for excessive-gap diagnosis, never for approval.
        if gap < -COINCIDENCE_M or gap > 0.001:
            continue
        transform = gp_Trsf()
        transform.SetTranslation(gp_Vec(*(-gap * n for n in na)))
        projected = BRepBuilderAPI_Transform(faces[b["id"]], transform, True).Shape()
        area = common(faces[a["id"]], projected, True)
        if area <= AREA_TOLERANCE_M2:
            continue
        full = max(abs(area - sa["area_m2"]), abs(area - sb["area_m2"])) <= AREA_TOLERANCE_M2
        unit = unit_square(faces[a["id"]]) and unit_square(faces[b["id"]])
        gap = max(0.0, gap)
        reason = None
        if overlaps:
            reason = "Body volume overlap blocks all connection approval."
        elif not full:
            reason = "Partial projected coverage is unsupported; select complete matching faces."
        elif not unit:
            reason = "Development bond policy is limited to complete planar unit-square interfaces."
        elif gap > MAX_GAP_M + 1e-12:
            reason = "Gap exceeds the B08 development bound of 10 µm."
        pairs.append(
            {
                "master_face_id": a["id"],
                "slave_face_id": b["id"],
                "gap_m": gap,
                "normal_dot": normal_dot,
                "overlap_area_m2": area,
                "master_coverage": area / sa["area_m2"],
                "slave_coverage": area / sb["area_m2"],
                "master_normal": na,
                "slave_normal": nb,
                "master_center_m": sa["center_m"],
                "slave_center_m": sb["center_m"],
                "eligible": reason is None,
                "blocker": reason,
            }
        )
    return {
        "status": "bond_review",
        "report": {
            "pairs": pairs,
            "overlaps": overlaps,
            "policy": {
                "name": "planar-unit-complete-b08-v1",
                "coincidence_m": COINCIDENCE_M,
                "max_gap_m": MAX_GAP_M,
                "gap_comparison_roundoff_m": 1e-12,
                "area_tolerance_m2": AREA_TOLERANCE_M2,
                "volume_overlap_tolerance_m3": VOLUME_TOLERANCE_M3,
                "search_gap_m": 0.001,
                "max_faces": 100,
                "normal_dot_tolerance": 1e-10,
                "unit_square_squared_length_tolerance_m2": 1e-8,
                "scope": "Complete planar unit-square face setup; "
                "mesh-dependent assembly admission is T020",
            },
        },
    }


if __name__ == "__main__":
    try:
        cad.write_json("inspection.json", review())
    except (ValueError, RuntimeError) as error:
        cad.write_json("inspection.json", {"status": "failed", "error_message": str(error)})
