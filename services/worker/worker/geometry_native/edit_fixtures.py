"""Public synthetic STEP cleanup fixtures; run with pinned CAD Python in a scratch dir."""

import re
from pathlib import Path

from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
from OCP.BRepFeat import BRepFeat_SplitShape
from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
from OCP.BRepGProp import BRepGProp
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
from OCP.GProp import GProp_GProps
from OCP.IFSelect import IFSelect_RetDone
from OCP.Interface import Interface_Static
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Controller, STEPControl_Writer
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS

STEPControl_Controller.Init_s()
assert Interface_Static.SetCVal_s("xstep.cascade.unit", "M")
assert Interface_Static.SetCVal_s("write.step.unit", "M")
box = BRepPrimAPI_MakeBox(1.0, 1.0, 1.0).Shape()
hole = BRepAlgoAPI_Cut(
    box,
    BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0.5, 0.5, -0.1), gp_Dir(0, 0, 1)), 0.1, 1.2).Shape(),
).Shape()
shapes = [("hole-m", hole)]
for radius, name in ((0.1, "fillet-m"), (0.2, "fillet-unsupported-m")):
    fillet = BRepFilletAPI_MakeFillet(box)
    fillet.Add(radius, TopoDS.Edge(TopExp_Explorer(box, TopAbs_EDGE).Current()))
    fillet.Build()
    assert fillet.IsDone()
    shapes.append((name, fillet.Shape()))
explorer = TopExp_Explorer(hole, TopAbs_FACE)
while explorer.More():
    face = TopoDS.Face(explorer.Current())
    properties = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, properties)
    if abs(properties.CentreOfMass().X()) < 1e-12:
        break
    explorer.Next()
assert explorer.More()
split = BRepFeat_SplitShape(hole)
split.Add(BRepBuilderAPI_MakeEdge(gp_Pnt(0, 0.5, 0), gp_Pnt(0, 0.5, 1)).Edge(), face)
split.Build()
assert split.IsDone()
shapes.append(("hole-split-m", split.Shape()))
for name, shape in shapes:
    writer = STEPControl_Writer()
    assert writer.Transfer(shape, STEPControl_AsIs) == IFSelect_RetDone
    path = Path(name + ".step")
    assert writer.Write(str(path)) == IFSelect_RetDone
    path.write_text(
        re.sub(r"'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d'", "'2026-10-14T00:00:00'", path.read_text())
    )
