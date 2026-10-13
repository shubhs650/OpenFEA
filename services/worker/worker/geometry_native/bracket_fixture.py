"""Self-generated public synthetic planar L bracket; no external CAD source."""

from pathlib import Path

from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
from OCP.gp import gp_Pnt, gp_Vec
from OCP.IFSelect import IFSelect_RetDone
from OCP.Interface import Interface_Static
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Controller, STEPControl_Writer

STEPControl_Controller.Init_s()
assert Interface_Static.SetCVal_s("xstep.cascade.unit", "M")
assert Interface_Static.SetCVal_s("write.step.unit", "M")
polygon = BRepBuilderAPI_MakePolygon()
for x, z in ((0, 0), (0.08, 0), (0.08, 0.01), (0.01, 0.01), (0.01, 0.06), (0, 0.06)):
    polygon.Add(gp_Pnt(x, 0, z))
polygon.Close()
shape = BRepPrimAPI_MakePrism(
    BRepBuilderAPI_MakeFace(polygon.Wire()).Face(), gp_Vec(0, 0.02, 0)
).Shape()
assert BRepCheck_Analyzer(shape).IsValid()
writer = STEPControl_Writer()
assert writer.Transfer(shape, STEPControl_AsIs) == IFSelect_RetDone
assert writer.Write("bracket-m.step") == IFSelect_RetDone
assert "SI_UNIT($,.METRE.)" in Path("bracket-m.step").read_text()
