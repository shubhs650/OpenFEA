"""Round-trip a generated SI box through native OCCT STEP I/O."""

import importlib.metadata
import json
import sys

from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.GProp import GProp_GProps
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Reader, STEPControl_Writer

shape = BRepPrimAPI_MakeBox(1.0, 2.0, 3.0).Shape()
assert importlib.metadata.version("cadquery-ocp") == "8.0.1.1.0"
assert importlib.metadata.version("vtk") == "9.6.2"
assert BRepCheck_Analyzer(shape).IsValid()
writer = STEPControl_Writer()
assert writer.Transfer(shape, STEPControl_AsIs) == IFSelect_RetDone
assert writer.Write("box.step") == IFSelect_RetDone
reader = STEPControl_Reader()
assert reader.ReadFile("box.step") == IFSelect_RetDone
assert reader.TransferRoots() == 1
restored = reader.OneShape()
assert BRepCheck_Analyzer(restored).IsValid()
properties = GProp_GProps()
BRepGProp.VolumeProperties_s(restored, properties)
assert abs(properties.Mass() - 6.0) <= 1e-10
assert "gmsh" not in sys.modules
print(
    "OPENFEA_PROBE="
    + json.dumps(
        {
            "component": "cad",
            "ocp_version": importlib.metadata.version("cadquery-ocp"),
            "cad_vtk_version": importlib.metadata.version("vtk"),
            "volume_m3": properties.Mass(),
            "step_roundtrip": True,
            "gmsh_loaded": False,
        }
    )
)
