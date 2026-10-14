"""Import immutable BREP into isolated Gmsh; export checked quadratic topology."""

import hashlib
import json
import sys
from pathlib import Path

import gmsh

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from worker.geometry import match_faces
from worker.mesh_quality import mesh_quality
from worker.meshing import GMSH_TO_CCX, convert_tetra, face_nodes

assert gmsh.__version__ == "4.15.2"
assert "OCP" not in sys.modules


def build():
    global stage
    controls = (
        json.loads(Path("mesh-controls.json").read_text())
        if Path("mesh-controls.json").is_file()
        else None
    )
    stage = "input_verification"
    catalog = json.loads(Path("catalog.json").read_text())
    revision = hashlib.sha256(Path("geometry.brep").read_bytes()).hexdigest()
    if revision != catalog["revision"]:
        raise ValueError("Stale BREP revision")
    gmsh.initialize()
    if len(sys.argv) > 4:
        for option in (
            "FixDegenerated",
            "FixSmallEdges",
            "FixSmallFaces",
            "SewFaces",
            "MakeSolids",
        ):
            gmsh.option.setNumber("Geometry.OCC" + option, 0)
    gmsh.option.setNumber("General.NumThreads", 1)
    gmsh.option.setNumber("Mesh.MaxNumThreads3D", 1)
    gmsh.option.setNumber("Mesh.MeshSizeMin", float(sys.argv[1]))
    gmsh.option.setNumber("Mesh.MeshSizeMax", float(sys.argv[1]))
    gmsh.option.setNumber("Mesh.ElementOrder", 2)
    gmsh.option.setNumber("Mesh.SecondOrderLinear", 1)
    gmsh.option.setNumber("Mesh.RandomSeed", 1)
    if controls:
        profile = controls["profile"]
        if profile not in (0, 1, 2):
            raise ValueError("Unapproved mesh profile")
        gmsh.option.setNumber("Mesh.Algorithm3D", 4 if profile == 1 else 1)
        gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", controls["curvature_elements"])
        if profile == 2:
            gmsh.option.setNumber("Mesh.ElementOrder", 1)
    body_sizes = json.loads(sys.argv[3]) if len(sys.argv) > 3 else None
    if body_sizes is not None and len(body_sizes) != len(catalog["bodies"]):
        raise ValueError("Each immutable body must have its own explicit mesh size")
    for dimension in range(4):
        gmsh.model.occ.setMaxTag(dimension, int(sys.argv[2]))
    body_volumes = {}
    for body in catalog["bodies"]:
        if hashlib.sha256(Path(body["path"]).read_bytes()).hexdigest() != body["sha256"]:
            raise ValueError("Body hash mismatch")
        volumes = gmsh.model.occ.importShapes(body["path"], highestDimOnly=True)
        assert len(volumes) == 1 and volumes[0][0] == 3
        body_volumes[body["id"]] = volumes[0][1]
    gmsh.model.occ.synchronize()
    if body_sizes is not None:
        gmsh.option.setNumber("Mesh.MeshSizeMin", min(body_sizes))
        gmsh.option.setNumber("Mesh.MeshSizeMax", max(body_sizes))
        for (_body, volume), size in zip(body_volumes.items(), body_sizes, strict=True):
            points = gmsh.model.getBoundary([(3, volume)], recursive=True, oriented=False)
            gmsh.model.mesh.setSize(points, size)
    imported = []
    for body, volume in body_volumes.items():
        surfaces = gmsh.model.getBoundary([(3, volume)], oriented=False)
        edges = {
            tag: {e[1] for e in gmsh.model.getBoundary([(2, tag)], oriented=False)}
            for dim, tag in surfaces
        }
        for _dim, tag in surfaces:
            if gmsh.model.getType(2, tag) not in (
                ("Plane", "Cylinder") if controls else ("Plane",)
            ):
                raise ValueError("Unresolved: only planar synthetic faces are validated")
            imported.append(
                {
                    "body": body,
                    "tag": tag,
                    "area": gmsh.model.occ.getMass(2, tag),
                    "center": gmsh.model.occ.getCenterOfMass(2, tag),
                    "bounds": gmsh.model.getBoundingBox(2, tag),
                    "neighbors": sorted(
                        other for other in edges if other != tag and edges[other] & edges[tag]
                    ),
                }
            )
    stage = "face_mapping"
    mapping = match_faces(catalog, imported, revision)
    curved = any(gmsh.model.getType(2, tag) != "Plane" for tag in mapping.values())
    if controls:
        gmsh.option.setNumber("Mesh.SecondOrderLinear", 0 if curved else 1)
        fields = []
        if controls["face_sizes_m"]:
            for index, (_body, volume) in enumerate(body_volumes.items()):
                size = body_sizes[index]
                constant = gmsh.model.mesh.field.add("MathEval")
                gmsh.model.mesh.field.setString(constant, "F", str(size))
                restrict = gmsh.model.mesh.field.add("Restrict")
                gmsh.model.mesh.field.setNumber(restrict, "InField", constant)
                gmsh.model.mesh.field.setNumbers(restrict, "VolumesList", [volume])
                fields.append(restrict)
            for ref, size in controls["face_sizes_m"].items():
                tag = mapping[ref]
                body = next(f["body"] for f in catalog["faces"] if f["id"] == ref)
                index = list(body_volumes).index(body)
                distance = gmsh.model.mesh.field.add("Distance")
                gmsh.model.mesh.field.setNumbers(distance, "FacesList", [tag])
                gmsh.model.mesh.field.setNumber(distance, "Sampling", 30)
                threshold = gmsh.model.mesh.field.add("Threshold")
                for name, value in {
                    "InField": distance,
                    "SizeMin": size,
                    "SizeMax": body_sizes[index],
                    "DistMin": 0,
                    "DistMax": 2 * body_sizes[index],
                }.items():
                    gmsh.model.mesh.field.setNumber(threshold, name, value)
                restrict = gmsh.model.mesh.field.add("Restrict")
                gmsh.model.mesh.field.setNumber(restrict, "InField", threshold)
                gmsh.model.mesh.field.setNumbers(restrict, "VolumesList", [body_volumes[body]])
                fields.append(restrict)
            background = gmsh.model.mesh.field.add("Min")
            gmsh.model.mesh.field.setNumbers(background, "FieldsList", fields)
            gmsh.model.mesh.field.setAsBackgroundMesh(background)
            gmsh.option.setNumber(
                "Mesh.MeshSizeMin", min(*body_sizes, *controls["face_sizes_m"].values())
            )
    if controls and curved and controls["curvature_elements"]:
        # The global/body requested size is a maximum. Let curvature refine it;
        # clamping MeshSizeMin to that maximum would silently disable curvature.
        gmsh.option.setNumber("Mesh.MeshSizeMin", 1e-9)
    for index, (ref, tag) in enumerate(sorted(mapping.items()), 1):
        gmsh.model.addPhysicalGroup(2, [tag], index)
        gmsh.model.setPhysicalName(2, index, ref)
    for index, (body, volume) in enumerate(sorted(body_volumes.items()), 1):
        gmsh.model.addPhysicalGroup(3, [volume], index)
        gmsh.model.setPhysicalName(3, index, body)
    stage = "native_generation"
    gmsh.model.mesh.generate(3)
    if controls and controls["profile"] == 2:
        gmsh.model.mesh.optimize("Netgen")
        gmsh.model.mesh.setOrder(2)
    if len(sys.argv) > 4:
        _types, _tags, _connectivity = gmsh.model.mesh.getElements(3)
        if sum(len(tags) for tags in _tags) > int(sys.argv[4]):
            if controls:
                Path("mesh-status.json").write_text(
                    json.dumps(
                        {
                            "status": "oversized",
                            "elements": sum(len(tags) for tags in _tags),
                            "message": "Mesh exceeds 3,000 elements; "
                            "explicitly save coarser settings",
                        }
                    )
                )
                gmsh.finalize()
                sys.exit(0)
            raise ValueError("Preview mesh exceeds the fixed element cap; no automatic coarsening")
    tags, xyz, _ = gmsh.model.mesh.getNodes()
    nodes = {int(n): tuple(float(v) for v in xyz[3 * i : 3 * i + 3]) for i, n in enumerate(tags)}
    elements = {}
    owners = {}
    for body, volume in body_volumes.items():
        types, element_tags, connectivity = gmsh.model.mesh.getElements(3, volume)
        assert list(types) == [11], "Only Gmsh type 11 tetra10 is allowed"
        for i, tag in enumerate(element_tags[0]):
            native = [int(n) for n in connectivity[0][10 * i : 10 * i + 10]]
            elements[int(tag)] = (
                tuple(native[j] for j in GMSH_TO_CCX) if controls else convert_tetra(native, nodes)
            )
            owners[int(tag)] = body
    all_faces = {}
    for eid, element in elements.items():
        for face in range(1, 5):
            ns = face_nodes(element, face)
            all_faces.setdefault(tuple(sorted(ns[:3])), []).append((eid, face, ns))
    boundary = {}
    for ref, tag in mapping.items():
        types, triangle_tags, connectivity = gmsh.model.mesh.getElements(2, tag)
        assert list(types) == [9], "Only quadratic boundary triangles are allowed"
        values = []
        for i in range(len(triangle_tags[0])):
            triangle = [int(n) for n in connectivity[0][6 * i : 6 * i + 6]]
            matches = all_faces.get(tuple(sorted(triangle[:3])), [])
            assert len(matches) == 1, "Surface triangle is not an exterior tetra face"
            eid, face, ns = matches[0]
            assert set(ns) == set(triangle), "Quadratic surface midsides disagree"
            assert owners[eid] == next(f["body"] for f in catalog["faces"] if f["id"] == ref)
            values.append({"element": eid, "face": face, "nodes": ns})
        assert values
        boundary[ref] = values
    stage = "output_validation"
    quality = (
        mesh_quality({"nodes": nodes, "elements": elements, "owners": owners}) if controls else None
    )
    gmsh.write("mesh.msh")
    Path("mesh.json").write_text(
        json.dumps(
            {
                "schema": 1,
                "revision": revision,
                "units": "m",
                "nodes": nodes,
                "elements": elements,
                "owners": owners,
                "boundary": boundary,
                "face_tags": mapping,
                "gmsh_version": gmsh.__version__,
                "build_info": gmsh.option.getString("General.BuildInfo"),
                "mesh_size_m": float(sys.argv[1]),
                "body_mesh_sizes_m": body_sizes,
                **({"quality": quality, "mesh_controls": controls} if controls else {}),
            },
            indent=2,
        )
        + "\n"
    )
    expected_tetrahedra = len(elements)
    boundary_nodes = {n for values in boundary.values() for face in values for n in face["nodes"]}
    Path("mesh-summary.json").write_text(
        json.dumps(
            {
                "nodes": len(nodes),
                "elements": expected_tetrahedra,
                "dofs": 3 * len(nodes),
                "free_equations": 3 * (len(nodes) - len(boundary_nodes)),
                "equation_scope": "B01 full exterior prescribed-displacement patch only",
                "mesh_json_bytes": Path("mesh.json").stat().st_size,
                "mesh_msh_bytes": Path("mesh.msh").stat().st_size,
                "mesh_sha256": hashlib.sha256(Path("mesh.json").read_bytes()).hexdigest(),
            },
            indent=2,
        )
        + "\n"
    )
    gmsh.clear()
    gmsh.open("mesh.msh")
    saved_types, saved_tags, _saved_connectivity = gmsh.model.mesh.getElements(3)
    assert list(saved_types) == [11] and len(saved_tags[0]) == expected_tetrahedra
    gmsh.finalize()

    if controls:
        Path("mesh-status.json").write_text(
            json.dumps(
                {
                    "status": "passed" if quality["accepted"] else "quality_failed",
                    "elements": len(elements),
                    "nodes": len(nodes),
                    "quality": {k: v for k, v in quality.items() if k != "cells"},
                },
                allow_nan=False,
            )
        )


stage = "input_verification"
try:
    build()
except Exception as failure:
    if Path("mesh-controls.json").is_file():
        Path("mesh-status.json").write_text(
            json.dumps(
                {"status": stage, "message": "Native mesh stage failed; inspect the retained log"}
            )
        )
    raise failure
