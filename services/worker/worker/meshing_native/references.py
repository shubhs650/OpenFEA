"""Original allowlisted reference solids; offline only, never an uploaded deck path."""

import hashlib
import json
import sys
from pathlib import Path

import gmsh

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from worker.meshing import convert_tetra, face_nodes

case, size = sys.argv[1], float(sys.argv[2])
if case not in ("B10", "B12", "B13", "B14") or not 0.002 <= size <= 0.5:
    raise ValueError("Unsupported reference/size")
gmsh.initialize()
for option, value in {
    "General.NumThreads": 1,
    "Mesh.MaxNumThreads3D": 1,
    "Mesh.RandomSeed": 1,
    "Mesh.MeshSizeMin": size,
    "Mesh.MeshSizeMax": size,
    "Mesh.ElementOrder": 2,
    # Explicit straight-sided approximation, including the B10 cylinder.
    "Mesh.SecondOrderLinear": 1,
}.items():
    gmsh.option.setNumber(option, value)
occ = gmsh.model.occ
if case == "B12":
    occ.addBox(0, 0, 0, 1, 1, 1)
elif case == "B13":
    occ.addBox(0, 0, 0, 0.5, 0.5, 3)
elif case == "B14":
    wires = []
    for y, half in ((0, 0.0254), (0.254, 0.0127)):
        points = [
            occ.addPoint(x, y, z)
            for x, z in ((-half, -half), (half, -half), (half, half), (-half, half))
        ]
        lines = [occ.addLine(points[i], points[(i + 1) % 4]) for i in range(4)]
        wires.append(occ.addWire(lines))
    occ.addThruSections(wires, makeSolid=True, makeRuled=True)
else:
    points = [
        occ.addPoint(x, 0, z)
        for x, z in (
            (0, 0),
            (0.08, 0),
            (0.08, 0.01),
            (0.015, 0.01),
            (0.01, 0.015),
            (0.01, 0.06),
            (0, 0.06),
        )
    ]
    center = occ.addPoint(0.015, 0, 0.015)
    lines = [
        occ.addCircleArc(points[i], center, points[i + 1])
        if i == 3
        else occ.addLine(points[i], points[(i + 1) % 7])
        for i in range(7)
    ]
    surface = occ.addPlaneSurface([occ.addWire(lines)])
    occ.extrude([(2, surface)], 0, 0.02, 0)
occ.synchronize()
gmsh.write("source.brep")
gmsh.model.mesh.generate(3)
tags, xyz, _ = gmsh.model.mesh.getNodes()
nodes = {int(n): tuple(float(v) for v in xyz[3 * i : 3 * i + 3]) for i, n in enumerate(tags)}
types, tags, connectivity = gmsh.model.mesh.getElements(3)
assert list(types) == [11]
if len(tags[0]) > 10000:
    raise ValueError("Offline reference exceeds fixed 10000-element bound")
elements = {
    int(e): convert_tetra([int(n) for n in connectivity[0][10 * i : 10 * i + 10]], nodes)
    for i, e in enumerate(tags[0])
}
used = {n for element in elements.values() for n in element}
# OCC construction points (e.g. arc centre) are not volume result entities.
nodes = {n: p for n, p in nodes.items() if n in used}
all_faces = {}
for e, ns in elements.items():
    for face in range(1, 5):
        local = face_nodes(ns, face)
        all_faces.setdefault(tuple(sorted(local[:3])), []).append(
            {"element": e, "face": face, "nodes": local}
        )
boundary = {}
for _, tag in gmsh.model.getEntities(2):
    types, tags, conn = gmsh.model.mesh.getElements(2, tag)
    assert list(types) == [9]
    faces = []
    for i in range(len(tags[0])):
        tri = [int(n) for n in conn[0][6 * i : 6 * i + 6]]
        match = all_faces[tuple(sorted(tri[:3]))]
        assert len(match) == 1 and set(match[0]["nodes"]) == set(tri)
        faces.append(match[0])
    boundary[f"{case}:surface{tag}"] = faces
revision = hashlib.sha256(Path("source.brep").read_bytes()).hexdigest()
Path("mesh.json").write_text(
    json.dumps(
        {
            "revision": revision,
            "nodes": nodes,
            "elements": elements,
            "owners": {e: "reference" for e in elements},
            "boundary": boundary,
        },
        allow_nan=False,
    )
    + "\n"
)
gmsh.write("mesh.msh")
gmsh.finalize()
