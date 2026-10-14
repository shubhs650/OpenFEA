"""Pinned OCCT STEP inspection. Executed only inside the upload namespace sandbox."""

import hashlib
import importlib.metadata
import json
import math
import os
import re
import sys
from pathlib import Path

from OCP.Bnd import Bnd_Box
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy, BRepBuilderAPI_Transform
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRepTools import BRepTools
from OCP.collections import (
    IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as IndexedMap_TopoDS_Shape,
)
from OCP.collections import Sequence_TCollection_AsciiString
from OCP.GeomAbs import GeomAbs_Plane
from OCP.gp import gp_Pnt, gp_Trsf
from OCP.GProp import GProp_GProps
from OCP.IFSelect import IFSelect_RetDone
from OCP.Interface import Interface_Static
from OCP.STEPControl import STEPControl_Controller, STEPControl_Reader
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_REVERSED, TopAbs_SOLID, TopAbs_VERTEX
from OCP.TopExp import TopExp, TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS


class InvalidModel(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message


def fail(code, message):
    raise InvalidModel(code, message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def explore(shape, kind):
    iterator = TopExp_Explorer(shape, kind)
    values = []
    while iterator.More():
        values.append(iterator.Current())
        iterator.Next()
    return values


def bounds(shape):
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, box, False, False)
    if box.IsVoid() or box.IsOpen():
        fail("invalid_geometry", "Geometry has no finite bounds")
    value = (*box.CornerMin().Coord(), *box.CornerMax().Coord())
    if not all(math.isfinite(v) for v in value):
        fail("invalid_geometry", "Geometry has no finite bounds")
    return value


def write_json(name, value):
    Path(name).write_text(json.dumps(value, allow_nan=False, separators=(",", ":")) + "\n")


def inspect():
    source = Path("/work/source.step")
    raw = source.read_bytes()
    if not raw.lstrip().startswith(b"ISO-10303-21;") or b"END-ISO-10303-21;" not in raw:
        fail("invalid_step", "Select a complete ISO STEP file (.step or .stp)")
    if len(re.findall(rb"#\d+\s*=", raw)) > 200000:
        fail("entity_limit", "STEP exceeds the 200,000 entity import limit")
    STEPControl_Controller.Init_s()
    if not Interface_Static.SetCVal_s("xstep.cascade.unit", "M"):
        raise RuntimeError("Cannot set canonical metre import")
    # Explicit empty shape-processing sequence: no optional repair/healing operation.
    Path("NoHealing").write_text("FromSTEP.exec.op :\n")
    os.environ["CSF_NoHealingDefaults"] = str(Path.cwd())
    if not (
        Interface_Static.SetCVal_s("read.step.resource.name", "NoHealing")
        and Interface_Static.SetCVal_s("read.step.sequence", "FromSTEP")
    ):
        raise RuntimeError("Cannot disable optional shape processing")
    reader = STEPControl_Reader()
    if reader.ReadFile(str(source)) != IFSelect_RetDone:
        fail("invalid_step", "STEP could not be read; the project geometry is unchanged")
    sequences = [Sequence_TCollection_AsciiString() for _ in range(3)]
    reader.FileUnits(*sequences)
    detected = sorted(
        {sequences[0].Value(i).ToCString().lower() for i in range(1, sequences[0].Length() + 1)}
    )
    names = {"metre": "m", "meter": "m", "millimetre": "mm", "millimeter": "mm", "inch": "inch"}
    choice = None if sys.argv[1] == "auto" else sys.argv[1]
    if detected and (len(detected) != 1 or detected[0] not in names):
        fail(
            "unsupported_units",
            "STEP has mixed or unsupported length units; normalize it before import",
        )
    if not detected and choice is None:
        return {
            "status": "needs_units",
            "inspection": {
                "source_length_unit": None,
                "unit_origin": None,
                "detected_length_units": [],
                "warnings": ["STEP length units are missing. Choose the source unit explicitly."],
            },
        }
    unit = names[detected[0]] if detected else choice
    if detected and choice is not None and choice != unit:
        fail("unit_conflict", "The selected unit conflicts with STEP metadata")
    if unit not in ("m", "mm", "inch"):
        fail("unsupported_units", "Choose metres, millimetres or inches")
    reader.SetSystemLengthUnit(1000.0)  # OCCT system length is expressed in millimetres.
    if reader.TransferRoots() <= 0:
        fail("invalid_geometry", "STEP contains no transferable geometry")
    shape = reader.OneShape()
    if not detected:
        # Pinned reader with metre system interprets absent-unit coordinates as metres.
        # Only an explicit user decision applies this source-unit scale; tested independently.
        transform = gp_Trsf()
        transform.SetScale(gp_Pnt(0, 0, 0), {"m": 1.0, "mm": 0.001, "inch": 0.0254}[unit])
        shape = BRepBuilderAPI_Transform(shape, transform, True).Shape()
    return export_shape(shape, digest(source), unit, detected)


def export_shape(shape, source_sha256, unit, detected):
    solids = explore(shape, TopAbs_SOLID)
    if not 1 <= len(solids) <= 10:
        fail(
            "solids_required",
            "Import requires 1–10 solid bodies; surface-only models are unsupported",
        )
    owned_faces = IndexedMap_TopoDS_Shape()
    for solid in solids:
        TopExp.MapShapes_s(solid, TopAbs_FACE, owned_faces)
    if any(not owned_faces.Contains(face) for face in explore(shape, TopAbs_FACE)):
        fail("free_surfaces", "STEP contains surfaces outside its solids; export solid bodies only")
    for kind in (TopAbs_EDGE, TopAbs_VERTEX):
        owned = IndexedMap_TopoDS_Shape()
        for solid in solids:
            TopExp.MapShapes_s(solid, kind, owned)
        if any(not owned.Contains(item) for item in explore(shape, kind)):
            fail(
                "free_geometry",
                "STEP contains wires or points outside its solids; export solid bodies only",
            )
    if owned_faces.Extent() > 2000:
        fail("face_limit", "STEP exceeds the 2,000 face preview limit")
    if not BRepCheck_Analyzer(shape).IsValid() or any(
        not BRepCheck_Analyzer(s).IsValid() for s in solids
    ):
        fail("invalid_geometry", "The imported solid is invalid; automatic repair was not applied")
    if not BRepTools.Write_s(shape, "geometry.brep"):
        raise RuntimeError("Cannot write canonical geometry")
    revision = digest(Path("geometry.brep"))
    body_display, catalog_faces, body_artifacts = [], [], []
    display = {lod: [] for lod in ("coarse", "fine")}
    counts = {lod: 0 for lod in display}
    full_bounds = bounds(shape)
    extent = max(full_bounds[i + 3] - full_bounds[i] for i in range(3))
    if extent <= 0:
        fail("invalid_geometry", "Geometry has zero size")
    for bi, solid in enumerate(solids, 1):
        body_id = f"{revision}:b{bi}"
        props = GProp_GProps()
        BRepGProp.VolumeProperties_s(solid, props)
        if not math.isfinite(props.Mass()) or props.Mass() <= 0:
            fail(
                "invalid_geometry",
                "A solid has invalid volume/orientation; export valid closed solids",
            )
        body_display.append(
            {
                "id": body_id,
                "volume_m3": props.Mass(),
                "bounds_m": bounds(solid),
                "center_m": props.CentreOfMass().Coord(),
            }
        )
        filename = f"body{bi}.brep"
        if not BRepTools.Write_s(solid, filename):
            raise RuntimeError("Cannot write body geometry")
        body_artifacts.append(filename)
        original_faces = [TopoDS.Face(f) for f in explore(solid, TopAbs_FACE)]
        edge_map = IndexedMap_TopoDS_Shape()
        local = []
        for fi, face in enumerate(original_faces, 1):
            face_id = f"{body_id}:f{fi}"
            BRepGProp.SurfaceProperties_s(face, props)
            edges = {edge_map.Add(e) for e in explore(face, TopAbs_EDGE)}
            local.append(
                {
                    "id": face_id,
                    "body_id": body_id,
                    "edges": edges,
                    "signature": {
                        "area_m2": props.Mass(),
                        "center_m": props.CentreOfMass().Coord(),
                        "bounds_m": bounds(face),
                        "surface_type": str(BRepAdaptor_Surface(face).GetType()),
                    },
                }
            )
            surface = BRepAdaptor_Surface(face)
            if surface.GetType() == GeomAbs_Plane:
                normal = surface.Plane().Axis().Direction().Coord()
                sign = -1 if face.Orientation() == TopAbs_REVERSED else 1
                local[-1]["signature"]["outward_normal"] = [sign * v for v in normal]
        for face in local:
            face["neighbors"] = sorted(
                other["id"]
                for other in local
                if other is not face and other["edges"] & face["edges"]
            )
        for face in local:
            del face["edges"]
        catalog_faces.extend(local)
        for lod, fraction, angle in (("coarse", 0.01, 0.4), ("fine", 0.002, 0.15)):
            copied = BRepBuilderAPI_Copy(solid, True, False)
            mesher = BRepMesh_IncrementalMesh(
                copied.Shape(), max(extent * fraction, 1e-12), False, angle, False
            )
            mesher.Perform()
            if not mesher.IsDone():
                fail("tessellation_failed", "Geometry could not be tessellated")
            for fi, original in enumerate(original_faces, 1):
                face = TopoDS.Face(copied.ModifiedShape(original))
                location = TopLoc_Location()
                mesh = BRep_Tool.Triangulation_s(face, location)
                if mesh is None or mesh.NbTriangles() == 0:
                    fail("tessellation_failed", "A face has no display triangles")
                counts[lod] += mesh.NbTriangles()
                if counts[lod] > 120000:
                    fail("display_limit", "Geometry exceeds the 120,000 triangle preview limit")
                points = [
                    mesh.Node(i).Transformed(location.Transformation()).Coord()
                    for i in range(1, mesh.NbNodes() + 1)
                ]
                triangles = []
                for i in range(1, mesh.NbTriangles() + 1):
                    ids = [v - 1 for v in mesh.Triangle(i).Get()]
                    # ModifiedShape returns the underlying copied face, which can
                    # lose its orientation in the owning solid. Use the original.
                    if original.Orientation() == TopAbs_REVERSED:
                        ids[1], ids[2] = ids[2], ids[1]
                    triangles.append(ids)
                display[lod].append(
                    {
                        "id": f"{body_id}:f{fi}",
                        "body_id": body_id,
                        "points_m": points,
                        "triangles": triangles,
                    }
                )
    for lod in display:
        write_json(
            f"display-{lod}.json",
            {
                "schema_version": 1,
                "brep_sha256": revision,
                "lod": lod,
                "bodies": body_display,
                "faces": display[lod],
            },
        )
    filenames = ["geometry.brep", *body_artifacts, "display-coarse.json", "display-fine.json"]
    artifacts = {
        name: {"sha256": digest(Path(name)), "size_bytes": Path(name).stat().st_size}
        for name in filenames
    }
    warning = (
        ["Length units were explicitly supplied because STEP metadata is absent."]
        if not detected
        else []
    )
    return {
        "status": "ready",
        "inspection": {
            "source_length_unit": unit,
            "unit_origin": "step_metadata" if detected else "explicit_missing_metadata",
            "detected_length_units": detected,
            "bounds_m": full_bounds,
            "body_count": len(solids),
            "face_count": len(catalog_faces),
            "coarse_triangles": counts["coarse"],
            "fine_triangles": counts["fine"],
            "warnings": warning,
        },
        "metadata": {
            "source_sha256": source_sha256,
            "brep_sha256": revision,
            "units": {"source_length_unit": unit, "canonical_length_unit": "m", "confirmed": True},
            "bodies": [{"id": b["id"]} for b in body_display],
            "faces": catalog_faces,
            "validation": {
                "ocp_version": importlib.metadata.version("cadquery-ocp"),
                "valid_solids": True,
                "shape_processing": "empty FromSTEP sequence",
                "bounds_m": full_bounds,
                "unit_origin": "step_metadata" if detected else "explicit_missing_metadata",
                "artifacts": artifacts,
                "warnings": warning,
            },
        },
    }


if __name__ == "__main__":
    try:
        if importlib.metadata.version("cadquery-ocp") != "8.0.1.1.0":
            raise RuntimeError("Unpinned CAD binding")
        result = inspect()
    except InvalidModel as failure:
        result = {"status": "failed", "error_code": failure.code, "error_message": failure.message}
    write_json("inspection.json", result)
