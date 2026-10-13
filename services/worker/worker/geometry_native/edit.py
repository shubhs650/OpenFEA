"""Isolated selected defeaturing, restricted to the two analytical M0 solids."""

import importlib.util
import json
import math
import sys
from pathlib import Path

from OCP.BRep import BRep_Builder
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Defeaturing
from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
from OCP.BRepGProp import BRepGProp
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
from OCP.BRepTools import BRepTools
from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
from OCP.GProp import GProp_GProps
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_SOLID
from OCP.TopoDS import TopoDS, TopoDS_Shape

spec = importlib.util.spec_from_file_location("cad_export", "/import.py")
cad = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cad)


def mass(shape, surface=False):
    props = GProp_GProps()
    if surface:
        BRepGProp.SurfaceProperties_s(shape, props)
    else:
        BRepGProp.VolumeProperties_s(shape, props)
    return props.Mass()


def cut_mass(a, b, surface=False):
    cut = BRepAlgoAPI_Cut(a, b)
    cut.Build()
    if not cut.IsDone() or not BRepCheck_Analyzer(cut.Shape()).IsValid():
        raise ValueError("Cannot verify the native geometry difference")
    return abs(mass(cut.Shape(), surface))


def same_face(a, b):
    # Full trimmed face difference, not just area/centroid or transient entity ID.
    if BRepAdaptor_Surface(a).GetType() != BRepAdaptor_Surface(b).GetType():
        return False
    if abs(mass(a, True) - mass(b, True)) > 1e-10:
        return False
    if max(abs(x - y) for x, y in zip(cad.bounds(a), cad.bounds(b), strict=True)) > 1e-10:
        return False
    if BRepAdaptor_Surface(a).GetType() != GeomAbs_Plane:
        return False
    if a.Orientation() != b.Orientation():
        return False
    an = BRepAdaptor_Surface(a).Plane().Axis().Direction().Coord()
    bn = BRepAdaptor_Surface(b).Plane().Axis().Direction().Coord()
    if max(abs(x - y) for x, y in zip(an, bn, strict=True)) > 1e-10:
        return False
    return cut_mass(a, b, True) <= 1e-10 and cut_mass(b, a, True) <= 1e-10


def preview():
    if cad.importlib.metadata.version("cadquery-ocp") != "8.0.1.1.0":
        raise RuntimeError("Unpinned CAD binding")
    metadata = json.loads(Path("/work/metadata.json").read_text())
    source = Path("/work/source.step")  # read-only canonical BREP, not re-imported STEP
    if cad.digest(source) != metadata["brep_sha256"]:
        raise ValueError("Source BREP hash changed")
    original = TopoDS_Shape()
    if not BRepTools.Read_s(original, str(source), BRep_Builder()):
        raise ValueError("Cannot read original BREP")
    solids = cad.explore(original, TopAbs_SOLID)
    if len(solids) != 1 or not BRepCheck_Analyzer(original).IsValid():
        raise ValueError("Cleanup supports one valid M0 solid only")
    old_faces = [TopoDS.Face(f) for f in cad.explore(solids[0], TopAbs_FACE)]
    catalog = metadata["faces"]
    if len(catalog) != len(old_faces) or len(metadata["bodies"]) != 1:
        raise ValueError("Source catalog/topology differs")
    selected = [i for i, f in enumerate(catalog) if f["id"] == sys.argv[1]]
    if (
        len(selected) != 1
        or BRepAdaptor_Surface(old_faces[selected[0]]).GetType() != GeomAbs_Cylinder
    ):
        raise ValueError("Select the simple cylindrical hole or straight-edge fillet face")
    if any(f["id"] != f"{metadata['brep_sha256']}:b1:f{i}" for i, f in enumerate(catalog, 1)):
        raise ValueError("Source face ordering is unverified")
    # Recognize the exact M0 support scope using native symmetric solid difference.
    box = BRepPrimAPI_MakeBox(1.0, 1.0, 1.0).Shape()
    hole = BRepAlgoAPI_Cut(
        box,
        BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0.5, 0.5, -0.1), gp_Dir(0, 0, 1)), 0.1, 1.2).Shape(),
    ).Shape()
    fillet = BRepFilletAPI_MakeFillet(box)
    fillet.Add(0.1, TopoDS.Edge(cad.explore(box, TopAbs_EDGE)[0]))
    fillet.Build()
    candidates = [
        ("hole", hole, math.pi * 0.1**2),
        ("fillet", fillet.Shape(), (1 - math.pi / 4) * 0.1**2),
    ]
    matches = [
        (kind, expected)
        for kind, shape, expected in candidates
        if len(cad.explore(shape, TopAbs_FACE)) == len(old_faces)
        and abs(mass(original) - mass(shape)) <= 1e-10
        and cut_mass(original, shape) <= 1e-10
        and cut_mass(shape, original) <= 1e-10
    ]
    if len(matches) != 1:
        raise ValueError(
            "Unsupported cleanup: only the two M0 unit-solid features are validated; "
            "original retained"
        )
    kind, expected = matches[0]
    copied = BRepBuilderAPI_Copy(original, True, False)
    algorithm = BRepAlgoAPI_Defeaturing()
    algorithm.SetShape(copied.Shape())
    algorithm.SetRunParallel(False)
    algorithm.AddFaceToRemove(TopoDS.Face(copied.ModifiedShape(old_faces[selected[0]])))
    algorithm.Build()
    if not algorithm.IsDone():
        raise ValueError("Native feature removal failed; original retained")
    result = algorithm.Shape()
    new_faces = [TopoDS.Face(f) for f in cad.explore(result, TopAbs_FACE)]
    delta = mass(result) - mass(original)
    if (
        not BRepCheck_Analyzer(result).IsValid()
        or len(cad.explore(result, TopAbs_SOLID)) != 1
        or len(new_faces) != 6
        or any(BRepAdaptor_Surface(f).GetType() != GeomAbs_Plane for f in new_faces)
        or abs(mass(result) - 1) > 1e-10
        or abs(delta - expected) > 1e-10
        or cut_mass(result, box) > 1e-10
        or cut_mass(box, result) > 1e-10
    ):
        raise ValueError("Cleanup result exceeds the validated feature scope")
    output = cad.export_shape(
        result, metadata["source_sha256"], metadata["units"]["source_length_unit"], ["metre"]
    )
    mappings = []
    for i, old in enumerate(old_faces):
        targets = [
            output["metadata"]["faces"][j]["id"]
            for j, new in enumerate(new_faces)
            if same_face(old, new)
        ]
        mappings.append(
            {
                "source_face_id": catalog[i]["id"],
                "target_face_id": targets[0] if len(targets) == 1 else None,
                "status": "unchanged"
                if len(targets) == 1
                else "removed"
                if i == selected[0]
                else "changed_or_ambiguous",
            }
        )
    # Many-to-one is uncertain, even if an upstream operation returned duplicates.
    for mapping in mappings:
        target = mapping["target_face_id"]
        if target and sum(m["target_face_id"] == target for m in mappings) != 1:
            mapping.update(target_face_id=None, status="changed_or_ambiguous")
    output["edit"] = {
        "feature": kind,
        "original_volume_m3": mass(original),
        "preview_volume_m3": mass(result),
        "volume_delta_m3": delta,
        "expected_delta_m3": expected,
        "mappings": mappings,
    }
    output["metadata"]["edit_recipe"] = {
        "operation": "selected_defeaturing",
        "feature": kind,
        "source_brep_sha256": metadata["brep_sha256"],
        "selected_face_id": sys.argv[1],
    }
    output["metadata"]["validation"]["shape_processing"] = (
        "OCCT BRepAlgoAPI_Defeaturing on deep copy"
    )
    output["metadata"]["validation"]["warnings"] = [
        "Bounded M0 unit-solid cleanup only; automatic healing is unavailable.",
        "Changed, removed, split or merged face assignments require explicit reselection.",
    ]
    return output


try:
    output = preview()
except (ValueError, RuntimeError) as failure:
    output = {"status": "failed", "error_code": "unsupported_edit", "error_message": str(failure)}
cad.write_json("inspection.json", output)
