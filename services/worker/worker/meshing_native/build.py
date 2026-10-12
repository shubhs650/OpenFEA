"""Import immutable BREP into isolated Gmsh; export checked quadratic topology."""

import hashlib
import json
import sys
from pathlib import Path

import gmsh

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from worker.geometry import match_faces
from worker.meshing import convert_tetra, face_nodes

assert gmsh.__version__ == "4.15.2"
assert "OCP" not in sys.modules

catalog = json.loads(Path("catalog.json").read_text())
revision = hashlib.sha256(Path("geometry.brep").read_bytes()).hexdigest()
if revision != catalog["revision"]:
    raise ValueError("Stale BREP revision")
gmsh.initialize()
gmsh.option.setNumber("General.NumThreads", 1)
gmsh.option.setNumber("Mesh.MaxNumThreads3D", 1)
gmsh.option.setNumber("Mesh.MeshSizeMin", float(sys.argv[1]))
gmsh.option.setNumber("Mesh.MeshSizeMax", float(sys.argv[1]))
gmsh.option.setNumber("Mesh.ElementOrder", 2)
gmsh.option.setNumber("Mesh.SecondOrderLinear", 1)
gmsh.option.setNumber("Mesh.RandomSeed", 1)
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
        if gmsh.model.getType(2, tag) != "Plane":
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
mapping = match_faces(catalog, imported, revision)
for index, (ref, tag) in enumerate(sorted(mapping.items()), 1):
    gmsh.model.addPhysicalGroup(2, [tag], index)
    gmsh.model.setPhysicalName(2, index, ref)
for index, (body, volume) in enumerate(sorted(body_volumes.items()), 1):
    gmsh.model.addPhysicalGroup(3, [volume], index)
    gmsh.model.setPhysicalName(3, index, body)
gmsh.model.mesh.generate(3)
tags, xyz, _ = gmsh.model.mesh.getNodes()
nodes = {int(n): tuple(float(v) for v in xyz[3 * i : 3 * i + 3]) for i, n in enumerate(tags)}
elements = {}
owners = {}
for body, volume in body_volumes.items():
    types, element_tags, connectivity = gmsh.model.mesh.getElements(3, volume)
    assert list(types) == [11], "Only Gmsh type 11 tetra10 is allowed"
    for i, tag in enumerate(element_tags[0]):
        elements[int(tag)] = convert_tetra(
            [int(n) for n in connectivity[0][10 * i : 10 * i + 10]], nodes
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
        },
        indent=2,
    )
    + "\n"
)
expected_tetrahedra = len(elements)
gmsh.clear()
gmsh.open("mesh.msh")
saved_types, saved_tags, _saved_connectivity = gmsh.model.mesh.getElements(3)
assert list(saved_types) == [11] and len(saved_tags[0]) == expected_tetrahedra
gmsh.finalize()
