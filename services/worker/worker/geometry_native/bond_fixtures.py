"""Authored public two-block STEP fixtures; no user CAD or native healing."""

from OCP.BRep import BRep_Builder
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.gp import gp_Pnt
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
