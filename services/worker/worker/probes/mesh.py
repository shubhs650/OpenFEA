"""Exercise Gmsh's native OCC and a small quadratic mesh; mapping remains T003."""

import json
import sys

import gmsh

assert gmsh.__version__ == "4.15.2"
gmsh.initialize()
try:
    gmsh.option.setNumber("General.NumThreads", 1)
    gmsh.option.setNumber("Mesh.MaxNumThreads3D", 1)
    gmsh.option.setNumber("Mesh.MeshSizeMin", 0.7)
    gmsh.option.setNumber("Mesh.MeshSizeMax", 0.7)
    gmsh.model.add("synthetic-box")
    volume = gmsh.model.occ.addBox(0, 0, 0, 1, 1, 1)
    gmsh.model.occ.synchronize()
    assert abs(gmsh.model.occ.getMass(3, volume) - 1.0) <= 1e-12
    gmsh.model.mesh.generate(3)
    gmsh.model.mesh.setOrder(2)
    types, tags, nodes = gmsh.model.mesh.getElements(3)
    assert list(types) == [11]  # Gmsh's 10-node tetrahedron, not a proven CCX permutation.
    elements = sum(len(group) for group in tags)
    assert elements > 0 and sum(len(group) for group in nodes) == 10 * elements
    assert "OCP" not in sys.modules
    print(
        "OPENFEA_PROBE="
        + json.dumps(
            {
                "component": "mesh",
                "gmsh_version": gmsh.__version__,
                "build_info": gmsh.option.getString("General.BuildInfo"),
                "tetra10_elements": elements,
                "ocp_loaded": False,
            }
        )
    )
finally:
    gmsh.finalize()
