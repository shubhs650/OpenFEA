"""Authored public two-block STEP fixtures; no user CAD or native healing."""

from OCP.BRep import BRep_Builder
from OCP.BRepBuilderAPI import (
    BRepBuilderAPI_MakeEdge,
    BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_MakeWire,
    BRepBuilderAPI_Transform,
)
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakePrism
from OCP.collections import Array1_gp_Pnt as TColgp_Array1OfPnt
from OCP.Geom import Geom_BezierCurve
from OCP.gp import gp_Pnt, gp_Trsf, gp_Vec
from OCP.IFSelect import IFSelect_RetDone
from OCP.Interface import Interface_Static
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Controller, STEPControl_Writer
from OCP.TopoDS import TopoDS_Compound

STEPControl_Controller.Init_s()
assert Interface_Static.SetCVal_s("xstep.cascade.unit", "M")
assert Interface_Static.SetCVal_s("write.step.unit", "M")
for name, x, y in (
    ("bond-zero", 1, 0),
    ("bond-gap", 1.00001, 0),
    ("bond-excess", 1.0001, 0),
    ("bond-partial", 1, 0.5),
    ("bond-unrelated", 1.00001, 2),
    ("bond-overlap", 0.999, 0),
):
    builder, compound = BRep_Builder(), TopoDS_Compound()
    builder.MakeCompound(compound)
    builder.Add(compound, BRepPrimAPI_MakeBox(1.0, 1.0, 1.0).Shape())
    builder.Add(compound, BRepPrimAPI_MakeBox(gp_Pnt(x, y, 0), 1.0, 1.0, 1.0).Shape())
    writer = STEPControl_Writer()
    assert writer.Transfer(compound, STEPControl_AsIs) == IFSelect_RetDone
    assert writer.Write(name + "-m.step") == IFSelect_RetDone

# Equal-area planar interfaces with four square corner vertices but curved
# trimmed edges: these must not masquerade as validated unit-square faces.


def arc(points):
    array = TColgp_Array1OfPnt(1, 3)
    for i, (y, z) in enumerate(points, 1):
        array.SetValue(i, gp_Pnt(0, y, z))
    return BRepBuilderAPI_MakeEdge(Geom_BezierCurve(array)).Edge()


wire = BRepBuilderAPI_MakeWire()
wire.Add(arc([(0, 0), (0.5, 0.1), (1, 0)]))
wire.Add(BRepBuilderAPI_MakeEdge(gp_Pnt(0, 1, 0), gp_Pnt(0, 1, 1)).Edge())
wire.Add(arc([(1, 1), (0.5, 1.1), (0, 1)]))
wire.Add(BRepBuilderAPI_MakeEdge(gp_Pnt(0, 0, 1), gp_Pnt(0, 0, 0)).Edge())
face = BRepBuilderAPI_MakeFace(wire.Wire()).Face()
left = BRepPrimAPI_MakePrism(face, gp_Vec(1, 0, 0)).Shape()
transform = gp_Trsf()
transform.SetTranslation(gp_Vec(1, 0, 0))
right = BRepBuilderAPI_Transform(left, transform, True).Shape()
compound = TopoDS_Compound()
builder = BRep_Builder()
builder.MakeCompound(compound)
builder.Add(compound, left)
builder.Add(compound, right)
writer = STEPControl_Writer()
assert writer.Transfer(compound, STEPControl_AsIs) == IFSelect_RetDone
assert writer.Write("bond-curved-boundary-m.step") == IFSelect_RetDone
