"""Exercise native VTK geometry/data I/O without a display or remote renderer."""

import json

from vtkmodules.vtkCommonCore import vtkPoints, vtkVersion
from vtkmodules.vtkCommonDataModel import vtkTetra, vtkUnstructuredGrid
from vtkmodules.vtkFiltersVerdict import vtkCellSizeFilter
from vtkmodules.vtkIOXML import vtkXMLUnstructuredGridReader, vtkXMLUnstructuredGridWriter

assert vtkVersion.GetVTKVersion() == "9.7.1"
points = vtkPoints()
for point in ((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)):
    points.InsertNextPoint(*point)
cell = vtkTetra()
for index in range(4):
    cell.GetPointIds().SetId(index, index)
grid = vtkUnstructuredGrid()
grid.SetPoints(points)
grid.InsertNextCell(cell.GetCellType(), cell.GetPointIds())
writer = vtkXMLUnstructuredGridWriter()
writer.SetFileName("tetra.vtu")
writer.SetInputData(grid)
assert writer.Write() == 1
reader = vtkXMLUnstructuredGridReader()
reader.SetFileName("tetra.vtu")
reader.Update()
assert reader.GetOutput().GetNumberOfCells() == 1
volumes = vtkCellSizeFilter()
volumes.SetInputData(reader.GetOutput())
volumes.Update()
volume = volumes.GetOutput().GetCellData().GetArray("Volume").GetTuple1(0)
assert abs(volume - 1 / 6) <= 1e-12
print(
    "OPENFEA_PROBE="
    + json.dumps(
        {
            "component": "post",
            "vtk_version": vtkVersion.GetVTKVersion(),
            "volume_m3": volume,
            "vtu_roundtrip": True,
        }
    )
)
