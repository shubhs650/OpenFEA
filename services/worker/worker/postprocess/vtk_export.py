"""Isolated native VTK export of element-owned quadratic volumes and raw IPs."""

import json
from pathlib import Path

import vtk

payload = json.loads(Path("stress.json").read_text())
mesh = payload["mesh"]
points = vtk.vtkPoints()
points.SetDataTypeToDouble()
grid = vtk.vtkUnstructuredGrid()
records = payload["element_nodes"]
by_key = {(p["element_id"], p["node_id"]): p for p in records}
arrays = {}
for name in ("element_id", "node_id"):
    arr = vtk.vtkIntArray()
    arr.SetName(name)
    arrays[name] = arr
stress = vtk.vtkDoubleArray()
stress.SetName("stress_pa_xx_yy_zz_xy_yz_zx")
stress.SetNumberOfComponents(6)
for i, name in enumerate(payload["components"]):
    stress.SetComponentName(i, name)
material = vtk.vtkStringArray()
material.SetName("material_id")
body = vtk.vtkStringArray()
body.SetName("body_id")
cell_material = vtk.vtkStringArray()
cell_material.SetName("material_id")
for eid, ns in sorted(mesh["elements"].items(), key=lambda p: int(p[0])):
    ids = vtk.vtkIdList()
    for node in ns:
        sample = by_key[int(eid), node]
        ids.InsertNextId(points.InsertNextPoint(*sample["position_m"]))
        arrays["element_id"].InsertNextValue(int(eid))
        arrays["node_id"].InsertNextValue(node)
        stress.InsertNextTuple(sample["tensor_pa"])
        material.InsertNextValue(sample["material_id"])
        body.InsertNextValue(sample["body_id"])
    grid.InsertNextCell(vtk.VTK_QUADRATIC_TETRA, ids)
    cell_material.InsertNextValue(mesh["materials"][eid])
grid.SetPoints(points)
for array in (*arrays.values(), stress, material, body):
    grid.GetPointData().AddArray(array)
grid.GetCellData().AddArray(cell_material)
metadata = vtk.vtkStringArray()
metadata.SetName("stress_provenance")
metadata.InsertNextValue(
    json.dumps(
        {
            "location": "element_node",
            "components": payload["components"],
            "frame": payload["frame"],
            "units": payload["units"],
            "sources": payload["source_sha256"],
            "parser": payload["parser"],
            "method": "linear extrapolation from raw DAT IPs; no averaging",
        }
    )
)
grid.GetFieldData().AddArray(metadata)
writer = vtk.vtkXMLUnstructuredGridWriter()
writer.SetFileName("element_nodes.vtu")
writer.SetInputData(grid)
assert writer.Write() == 1
reader = vtk.vtkXMLUnstructuredGridReader()
reader.SetFileName("element_nodes.vtu")
reader.Update()
restored = reader.GetOutput()
assert restored.GetNumberOfPoints() == len(records)
assert restored.GetNumberOfCells() == len(mesh["elements"])
for i in range(restored.GetNumberOfPoints()):
    eid = int(restored.GetPointData().GetArray("element_id").GetValue(i))
    nid = int(restored.GetPointData().GetArray("node_id").GetValue(i))
    sample = by_key[eid, nid]
    assert restored.GetPointData().GetArray(stress.GetName()).GetTuple(i) == tuple(
        sample["tensor_pa"]
    )
    assert (
        restored.GetPointData().GetAbstractArray("material_id").GetValue(i) == sample["material_id"]
    )
volumes = vtk.vtkCellSizeFilter()
volumes.SetInputData(restored)
volumes.ComputeVolumeOn()
volumes.Update()
volume = volumes.GetOutput().GetCellData().GetArray("Volume")
assert all(abs(volume.GetValue(i) - 1 / 6) < 1e-12 for i in range(restored.GetNumberOfCells()))
ip_data = vtk.vtkPolyData()
ip_points = vtk.vtkPoints()
ip_points.SetDataTypeToDouble()
vertices = vtk.vtkCellArray()
ip_stress = vtk.vtkDoubleArray()
ip_stress.SetName(stress.GetName())
ip_stress.SetNumberOfComponents(6)
for i, name in enumerate(payload["components"]):
    ip_stress.SetComponentName(i, name)
ip_ownership = {}
for name in ("body_id", "material_id"):
    array = vtk.vtkStringArray()
    array.SetName(name)
    ip_ownership[name] = array
ip_arrays = {}
for name in ("element_id", "integration_point_id"):
    arr = vtk.vtkIntArray()
    arr.SetName(name)
    ip_arrays[name] = arr
for sample in payload["integration_points"]:
    point = ip_points.InsertNextPoint(*sample["position_m"])
    vertices.InsertNextCell(1)
    vertices.InsertCellPoint(point)
    ip_stress.InsertNextTuple(sample["tensor_pa"])
    for name, arr in ip_arrays.items():
        arr.InsertNextValue(sample[name])
    for name, arr in ip_ownership.items():
        arr.InsertNextValue(sample[name])
ip_data.SetPoints(ip_points)
ip_data.SetVerts(vertices)
for array in (ip_stress, *ip_arrays.values(), *ip_ownership.values()):
    ip_data.GetPointData().AddArray(array)
ip_metadata = vtk.vtkStringArray()
ip_metadata.SetName("stress_provenance")
ip_metadata.InsertNextValue(
    json.dumps(
        {
            "location": "integration_point",
            "components": payload["components"],
            "frame": payload["frame"],
            "units": payload["units"],
            "sources": payload["source_sha256"],
            "parser": payload["parser"],
            "method": "raw native DAT S and COORD",
        }
    )
)
ip_data.GetFieldData().AddArray(ip_metadata)
ip_writer = vtk.vtkXMLPolyDataWriter()
ip_writer.SetFileName("integration_points.vtp")
ip_writer.SetInputData(ip_data)
assert ip_writer.Write() == 1
ip_reader = vtk.vtkXMLPolyDataReader()
ip_reader.SetFileName("integration_points.vtp")
ip_reader.Update()
restored_ip = ip_reader.GetOutput()
assert restored_ip.GetNumberOfPoints() == len(payload["integration_points"])
for i, sample in enumerate(payload["integration_points"]):
    assert restored_ip.GetPoint(i) == tuple(sample["position_m"])
    assert restored_ip.GetPointData().GetArray(ip_stress.GetName()).GetTuple(i) == tuple(
        sample["tensor_pa"]
    )
    assert (
        restored_ip.GetPointData().GetAbstractArray("material_id").GetValue(i)
        == sample["material_id"]
    )
Path("vtk-report.json").write_text(
    json.dumps(
        {
            "vtk_version": vtk.vtkVersion.GetVTKVersion(),
            "cells": restored.GetNumberOfCells(),
            "element_owned_points": restored.GetNumberOfPoints(),
            "global_nodes": len(mesh["nodes"]),
            "integration_points": ip_points.GetNumberOfPoints(),
            "cell_volumes_m3": [volume.GetValue(i) for i in range(restored.GetNumberOfCells())],
            "shared_nodes_duplicated": True,
            "tensor_roundtrip": "exact",
            "status": "PASS",
        },
        indent=2,
    )
    + "\n"
)
