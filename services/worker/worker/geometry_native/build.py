"""Generate synthetic SI BREP revisions and face-labelled display triangles."""

import hashlib
import importlib.metadata
import json
import sys
from pathlib import Path

from OCP.BRep import BRep_Builder, BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.BRepTools import BRepTools
from OCP.GeomAbs import GeomAbs_Plane
from OCP.gp import gp_Pnt
from OCP.GProp import GProp_GProps
from OCP.IFSelect import IFSelect_RetDone
from OCP.Interface import Interface_Static
from OCP.STEPControl import (
    STEPControl_AsIs,
    STEPControl_Controller,
    STEPControl_Reader,
    STEPControl_Writer,
)
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_REVERSED, TopAbs_SOLID, TopAbs_VERTEX
from OCP.TopExp import TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS, TopoDS_Compound


def explore(shape, kind):
    explorer = TopExp_Explorer(shape, kind)
    values = []
    while explorer.More():
        values.append(explorer.Current())
        explorer.Next()
    return values


def vertices(shape):
    return sorted(
        {
            tuple(round(v, 12) for v in BRep_Tool.Pnt_s(TopoDS.Vertex(p)).Coord())
            for p in explore(shape, TopAbs_VERTEX)
        }
    )


kind = sys.argv[1]
assert importlib.metadata.version("cadquery-ocp") == "8.0.1.1.0"
assert "gmsh" not in sys.modules
box = BRepPrimAPI_MakeBox(1.0, 1.0, 1.0).Shape()
if kind == "box":
    bodies = [box]
elif kind == "bracket":
    cut = BRepAlgoAPI_Cut(box, BRepPrimAPI_MakeBox(gp_Pnt(0.4, 0.4, 0), 0.6, 0.6, 1.0).Shape())
    cut.Build()
    assert cut.IsDone()
    bodies = [cut.Shape()]
elif kind == "two":
    bodies = [box, BRepPrimAPI_MakeBox(gp_Pnt(2, 0, 0), 1.0, 1.0, 1.0).Shape()]
elif kind in ("bonded", "gap-probe"):
    offset = 1.0 if kind == "bonded" else 1.00001
    bodies = [box, BRepPrimAPI_MakeBox(gp_Pnt(offset, 0, 0), 1.0, 1.0, 1.0).Shape()]
elif kind == "long-box":
    bodies = [BRepPrimAPI_MakeBox(2.0, 1.0, 1.0).Shape()]
elif kind == "beam":
    bodies = [BRepPrimAPI_MakeBox(1.0, 0.1, 0.1).Shape()]
else:
    raise ValueError("Only allowlisted synthetic fixtures are supported")
compound = TopoDS_Compound()
builder = BRep_Builder()
builder.MakeCompound(compound)
for body in bodies:
    assert BRepCheck_Analyzer(body).IsValid()
    builder.Add(compound, body)
STEPControl_Controller.Init_s()
assert Interface_Static.SetCVal_s("xstep.cascade.unit", "M")
assert Interface_Static.SetCVal_s("write.step.unit", "M")
writer = STEPControl_Writer()
assert writer.Transfer(compound, STEPControl_AsIs) == IFSelect_RetDone
assert writer.Write("input.step") == IFSelect_RetDone
assert "SI_UNIT($,.METRE.)" in Path("input.step").read_text()
reader = STEPControl_Reader()
assert reader.ReadFile("input.step") == IFSelect_RetDone
assert reader.TransferRoots() > 0
compound = reader.OneShape()
restored_bodies = explore(compound, TopAbs_SOLID)
assert len(restored_bodies) == len(bodies)
bodies = restored_bodies
assert BRepCheck_Analyzer(compound).IsValid()
assert BRepTools.Write_s(compound, "geometry.brep")
revision = hashlib.sha256(Path("geometry.brep").read_bytes()).hexdigest()
faces = []
body_catalog = []
for body_index, body in enumerate(bodies, 1):
    body_id = f"{revision}:b{body_index}"
    path = f"body{body_index}.brep"
    assert BRepTools.Write_s(body, path)
    body_catalog.append(
        {"id": body_id, "path": path, "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()}
    )
    BRepMesh_IncrementalMesh(body, 0.02, False, 0.2, False).Perform()
    local_faces = []
    for index, raw_face in enumerate(explore(body, TopAbs_FACE), 1):
        face = TopoDS.Face(raw_face)
        assert BRepAdaptor_Surface(face).GetType() == GeomAbs_Plane
        properties = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face, properties)
        points = vertices(face)
        bounds = [min(p[k] for p in points) for k in range(3)]
        bounds += [max(p[k] for p in points) for k in range(3)]
        edge_keys = {tuple(vertices(e)) for e in explore(face, TopAbs_EDGE)}
        location = TopLoc_Location()
        triangles = BRep_Tool.Triangulation_s(face, location)
        assert triangles is not None
        display = []
        for i in range(1, triangles.NbTriangles() + 1):
            ids = list(triangles.Triangle(i).Get())
            if face.Orientation() == TopAbs_REVERSED:
                ids[1], ids[2] = ids[2], ids[1]
            display.append(
                [triangles.Node(n).Transformed(location.Transformation()).Coord() for n in ids]
            )
        local_faces.append(
            {
                "id": f"{body_id}:f{index}",
                "body": body_id,
                "area": properties.Mass(),
                "center": properties.CentreOfMass().Coord(),
                "bounds": bounds,
                "triangles": display,
                "edges": edge_keys,
            }
        )
    for face in local_faces:
        face["neighbors"] = sorted(
            other["id"]
            for other in local_faces
            if other is not face and face["edges"] & other["edges"]
        )
    for face in local_faces:
        del face["edges"]
    faces.extend(local_faces)
Path("catalog.json").write_text(
    json.dumps(
        {
            "schema": 1,
            "units": "m",
            "fixture": kind,
            "ocp_version": importlib.metadata.version("cadquery-ocp"),
            "revision": revision,
            "bodies": body_catalog,
            "faces": faces,
        },
        indent=2,
    )
    + "\n"
)
