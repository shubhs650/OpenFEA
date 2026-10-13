"""Native OCCT defeaturing on a copy, with immutable selected-face references."""

import hashlib
import importlib.metadata
import json
import math
import sys
from pathlib import Path

from OCP.BRep import BRep_Builder, BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Defeaturing
from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
from OCP.BRepGProp import BRepGProp
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
from OCP.BRepTools import BRepTools
from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
from OCP.GProp import GProp_GProps
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_REVERSED, TopAbs_SOLID, TopAbs_VERTEX
from OCP.TopExp import TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS, TopoDS_Shape


def explore(shape, kind):
    explorer = TopExp_Explorer(shape, kind)
    values = []
    while explorer.More():
        values.append(explorer.Current())
        explorer.Next()
    return values


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def volume(shape):
    properties = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, properties)
    return properties.Mass()


def vertex_key(shape):
    return tuple(
        sorted(
            {
                tuple(round(v, 12) for v in BRep_Tool.Pnt_s(TopoDS.Vertex(p)).Coord())
                for p in explore(shape, TopAbs_VERTEX)
            }
        )
    )


def export(shape, kind):
    if not BRepCheck_Analyzer(shape).IsValid() or len(explore(shape, TopAbs_SOLID)) != 1:
        raise ValueError("Edit must retain one valid solid")
    assert BRepTools.Write_s(shape, "geometry.brep")
    revision = digest(Path("geometry.brep"))
    assert BRepTools.Write_s(shape, "body1.brep")
    BRepMesh_IncrementalMesh(shape, 0.005, False, 0.1, False).Perform()
    faces = []
    body_id = f"{revision}:b1"
    for index, raw in enumerate(explore(shape, TopAbs_FACE), 1):
        face = TopoDS.Face(raw)
        surface = BRepAdaptor_Surface(face)
        surface_type = surface.GetType()
        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face, props)
        location = TopLoc_Location()
        mesh = BRep_Tool.Triangulation_s(face, location)
        if mesh is None:
            raise ValueError("Preview tessellation missing")
        triangles = []
        for i in range(1, mesh.NbTriangles() + 1):
            ids = list(mesh.Triangle(i).Get())
            if face.Orientation() == TopAbs_REVERSED:
                ids[1], ids[2] = ids[2], ids[1]
            triangles.append(
                [mesh.Node(n).Transformed(location.Transformation()).Coord() for n in ids]
            )
        points = [p for triangle in triangles for p in triangle]
        faces.append(
            {
                "id": f"{body_id}:f{index}",
                "body": body_id,
                "surface": "cylinder"
                if surface_type == GeomAbs_Cylinder
                else "plane"
                if surface_type == GeomAbs_Plane
                else "unsupported",
                "area": props.Mass(),
                "center": props.CentreOfMass().Coord(),
                "bounds": [min(p[k] for p in points) for k in range(3)]
                + [max(p[k] for p in points) for k in range(3)],
                "triangles": triangles,
                "edges": {vertex_key(e) for e in explore(face, TopAbs_EDGE)},
            }
        )
    for face in faces:
        face["neighbors"] = sorted(
            other["id"] for other in faces if other is not face and face["edges"] & other["edges"]
        )
    for face in faces:
        del face["edges"]
    catalog = {
        "schema": 1,
        "units": "m",
        "fixture": kind,
        "ocp_version": importlib.metadata.version("cadquery-ocp"),
        "revision": revision,
        "volume_m3": volume(shape),
        "bodies": [{"id": body_id, "path": "body1.brep", "sha256": digest(Path("body1.brep"))}],
        "faces": faces,
    }
    Path("catalog.json").write_text(json.dumps(catalog, indent=2) + "\n")
    return catalog


assert importlib.metadata.version("cadquery-ocp") == "8.0.1.1.0"
assert "gmsh" not in sys.modules
if sys.argv[1] == "create":
    kind = sys.argv[2]
    box = BRepPrimAPI_MakeBox(1.0, 1.0, 1.0).Shape()
    if kind == "hole":
        tool = BRepPrimAPI_MakeCylinder(
            gp_Ax2(gp_Pnt(0.5, 0.5, -0.1), gp_Dir(0, 0, 1)), 0.1, 1.2
        ).Shape()
        shape = BRepAlgoAPI_Cut(box, tool).Shape()
    elif kind == "fillet":
        algorithm = BRepFilletAPI_MakeFillet(box)
        algorithm.Add(0.1, TopoDS.Edge(explore(box, TopAbs_EDGE)[0]))
        algorithm.Build()
        if not algorithm.IsDone():
            raise ValueError("Fixture fillet construction failed")
        shape = algorithm.Shape()
    else:
        raise ValueError("Unsupported fixture")
    export(shape, kind)
elif sys.argv[1] == "preview":
    source = Path(sys.argv[2])
    catalog = json.loads((source / "catalog.json").read_text())
    revision = digest(source / "geometry.brep")
    if revision != catalog["revision"] or catalog["units"] != "m":
        raise ValueError("Stale or non-SI geometry")
    selected = [f for f in catalog["faces"] if f["id"] == sys.argv[3]]
    if len(selected) != 1 or selected[0]["surface"] != "cylinder":
        raise ValueError("Only the selected simple cylindrical hole/fillet is supported")
    kind = catalog["fixture"]
    if kind not in ("hole", "fillet"):
        raise ValueError("Only synthetic cleanup fixtures are supported")
    original = TopoDS_Shape()
    if not BRepTools.Read_s(original, str(source / "geometry.brep"), BRep_Builder()):
        raise ValueError("Invalid BREP")
    if not BRepCheck_Analyzer(original).IsValid():
        raise ValueError("Invalid original geometry")
    # Copy geometry as well as topology; no in-place healing of the source.
    copy = BRepBuilderAPI_Copy(original, True, False).Shape()
    faces = explore(copy, TopAbs_FACE)
    index = int(selected[0]["id"].rsplit(":f", 1)[1]) - 1
    face = TopoDS.Face(faces[index])
    if BRepAdaptor_Surface(face).GetType() != GeomAbs_Cylinder:
        raise ValueError("Selected immutable face disagrees with native topology")
    algorithm = BRepAlgoAPI_Defeaturing()
    algorithm.SetShape(copy)
    algorithm.SetRunParallel(False)
    algorithm.AddFaceToRemove(face)
    algorithm.Build()
    if not algorithm.IsDone():
        raise ValueError("Defeaturing failed")
    result = algorithm.Shape()
    delta = volume(result) - volume(original)
    expected = math.pi * 0.1**2 if kind == "hole" else (1 - math.pi / 4) * 0.1**2
    if abs(volume(result) - 1) > 1e-10 or abs(delta - expected) > 1e-10:
        raise ValueError("Cleanup changed geometry outside the supported feature")
    if len(explore(result, TopAbs_FACE)) != 6 or any(
        BRepAdaptor_Surface(TopoDS.Face(f)).GetType() != GeomAbs_Plane
        for f in explore(result, TopAbs_FACE)
    ):
        raise ValueError("Unsupported cleanup result topology")
    preview = export(result, "cleanup-" + kind)
    if preview["revision"] == revision:
        raise ValueError("Feature removal produced no change")
    Path("edit.json").write_text(
        json.dumps(
            {
                "status": "DEVELOPMENT PREVIEW; original retained; explicit apply is T013",
                "source_revision": revision,
                "preview_revision": preview["revision"],
                "selected_face": selected[0]["id"],
                "operation": "OCCT BRepAlgoAPI_Defeaturing",
                "original_volume_m3": volume(original),
                "preview_volume_m3": volume(result),
                "volume_delta_m3": delta,
                "expected_delta_m3": expected,
                "valid": True,
                "mapping_status": "all prior face/mesh/result selections invalidated",
            },
            indent=2,
        )
        + "\n"
    )
else:
    raise ValueError("Unsupported cleanup operation")
