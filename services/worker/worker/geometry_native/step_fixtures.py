"""Self-generated public synthetic STEP fixtures for T008 (no external CAD sources)."""

import re
from pathlib import Path

from OCP.BRep import BRep_Builder
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
from OCP.gp import gp_Pnt
from OCP.IFSelect import IFSelect_RetDone
from OCP.Interface import Interface_Static
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Controller, STEPControl_Writer
from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS_Compound

STEPControl_Controller.Init_s()
assert Interface_Static.SetCVal_s("xstep.cascade.unit", "M")
box = BRepPrimAPI_MakeBox(1.0, 1.0, 1.0).Shape()
two = TopoDS_Compound()
builder = BRep_Builder()
builder.MakeCompound(two)
builder.Add(two, box)
builder.Add(two, BRepPrimAPI_MakeBox(gp_Pnt(2, 0, 0), 1.0, 1.0, 1.0).Shape())
many = TopoDS_Compound()
builder.MakeCompound(many)
for i in range(11):
    builder.Add(many, BRepPrimAPI_MakeBox(gp_Pnt(i * 2, 0, 0), 1.0, 1.0, 1.0).Shape())
surface = TopExp_Explorer(box, TopAbs_FACE).Current()
mixed = TopoDS_Compound()
builder.MakeCompound(mixed)
builder.Add(mixed, box)
builder.Add(mixed, BRepBuilderAPI_MakeEdge(gp_Pnt(4, 0, 0), gp_Pnt(5, 0, 0)).Edge())
for name, shape, unit in (
    ("cube-m", box, "M"),
    ("cube-mm", box, "MM"),
    ("cube-inch", box, "INCH"),
    ("two-m", two, "M"),
    ("cylinder-m", BRepPrimAPI_MakeCylinder(0.5, 1.0).Shape(), "M"),
    ("surface-m", surface, "M"),
    ("mixed-wire-m", mixed, "M"),
    ("eleven-m", many, "M"),
):
    assert Interface_Static.SetCVal_s("write.step.unit", unit)
    writer = STEPControl_Writer()
    assert writer.Transfer(shape, STEPControl_AsIs) == IFSelect_RetDone
    assert writer.Write(name + ".step") == IFSelect_RetDone
raw = Path("cube-m.step").read_text()
missing = re.sub(r"GLOBAL_UNIT_ASSIGNED_CONTEXT\s*\(\([^)]*\)\)", "", raw)
assert missing != raw
Path("cube-missing.step").write_text(missing)
Path("invalid.step").write_text(
    "ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\n#1=INVALID(;\nENDSEC;\nEND-ISO-10303-21;\n"
)
