"""Revalidate canonical archived BREP and regenerate all trusted runtime artifacts."""

import importlib.util
import json
from pathlib import Path

from OCP.BRep import BRep_Builder
from OCP.BRepTools import BRepTools
from OCP.TopoDS import TopoDS_Shape

spec = importlib.util.spec_from_file_location("cad_export", "/import.py")
cad = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cad)

metadata = json.loads(Path("/work/metadata.json").read_text())
shape = TopoDS_Shape()
if not BRepTools.Read_s(shape, "/work/source.step", BRep_Builder()):
    raise ValueError("Invalid archived BREP")
result = cad.export_shape(
    shape,
    metadata["source_sha256"],
    metadata["units"]["source_length_unit"],
    ["archive-canonical-metre"],
    canonical_source="/work/source.step",
)
cad.write_json("inspection.json", result)
