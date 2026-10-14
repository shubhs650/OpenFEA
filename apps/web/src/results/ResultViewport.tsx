import { useTheme } from "../workspace/theme";
import { useEffect, useRef, useState } from "react";
import "@kitware/vtk.js/Rendering/Profiles/Geometry";
import vtkGenericRenderWindow from "@kitware/vtk.js/Rendering/Misc/GenericRenderWindow";
import vtkActor from "@kitware/vtk.js/Rendering/Core/Actor";
import vtkMapper from "@kitware/vtk.js/Rendering/Core/Mapper";
import vtkPolyData from "@kitware/vtk.js/Common/DataModel/PolyData";
import vtkDataArray from "@kitware/vtk.js/Common/Core/DataArray";
import {
  color,
  isDisplacement,
  constantRange,
  deformed,
  scalar,
  type ResultPresentation,
} from "./presentation";

export function ResultViewport({
  presentation,
  visible,
}: {
  presentation: ResultPresentation;
  visible: Set<string>;
}) {
  const theme = useTheme();
  const container = useRef<HTMLDivElement>(null);
  const [error, setError] = useState("");
  const { view, field, smoothed, scale, range, preset } = presentation;
  const unit = isDisplacement(field) ? preset.length : preset.stress;
  useEffect(() => {
    if (!container.current) return;
    const window = vtkGenericRenderWindow.newInstance({
      background: theme === "dark" ? [0.07, 0.11, 0.15] : [0.94, 0.96, 0.98],
      listenWindowResize: false,
    });
    window.setContainer(container.current);
    const poly = vtkPolyData.newInstance();
    const mapper = vtkMapper.newInstance({
      scalarVisibility: true,
      colorMode: 2,
      scalarMode: 1,
    });
    const actor = vtkActor.newInstance({ pickable: false });
    const center = [0, 1, 2].map((axis) => {
      let low = Infinity,
        high = -Infinity;
      for (const vertex of view.data.vertices) {
        low = Math.min(low, vertex.position_m[axis]);
        high = Math.max(high, vertex.position_m[axis]);
      }
      return (low + high) / 2;
    });
    poly
      .getPoints()
      .setData(
        new Float32Array(
          view.data.vertices.flatMap((v) =>
            deformed(v.position_m, v.displacement_m, scale).map(
              (p, axis) => p - center[axis],
            ),
          ),
        ),
        3,
      );
    poly
      .getPolys()
      .setData(
        new Uint32Array(
          view.data.triangles
            .filter((t) => visible.has(view.data.vertices[t[0]].body_id))
            .flatMap((t) => [3, ...t]),
        ),
      );
    const colors = vtkDataArray.newInstance({
      name: "ResultColors",
      numberOfComponents: 3,
      values: new Uint8Array(
        view.data.vertices.flatMap((v) =>
          color(scalar(v, field, smoothed), range),
        ),
      ),
    });
    poly.getPointData().setScalars(colors);
    mapper.setInputData(poly);
    actor.setMapper(mapper);
    actor.getProperty().setAmbient(1);
    actor.getProperty().setDiffuse(0);
    window.getRenderer().addActor(actor);
    window.getRenderer().getActiveCamera().setPosition(1, 1, 1);
    window.getRenderer().getActiveCamera().setViewUp(0, 0, 1);
    window.getRenderer().resetCamera();
    const resize = new ResizeObserver(() => window.resize());
    resize.observe(container.current);
    try {
      window.resize();
      window.getRenderWindow().render();
    } catch {
      setError("Result rendering failed. Check browser WebGL support.");
    }
    return () => {
      resize.disconnect();
      window.getRenderer().removeActor(actor);
      actor.delete();
      mapper.delete();
      poly.delete();
      colors.delete();
      window.delete();
    };
  }, [theme, view, field, smoothed, scale, range, visible]);
  return (
    <section
      className="result-viewport"
      aria-label="Calculated result viewport"
      data-result-job={view.job_id}
      data-deformation-scale={scale}
      data-result-field={field}
      data-stress-smoothing={
        smoothed && !isDisplacement(field) ? "smoothed" : "unaveraged"
      }
    >
      <div ref={container} className="viewport" aria-label="Result 3D canvas" />
      <div className="result-legend" aria-label="Result legend">
        <strong>
          {view.data.fields.find((f) => f.key === field)?.label} ({unit.label})
        </strong>
        <div
          className="contour-bar"
          style={
            constantRange(range)
              ? { background: "rgb(128,190,128)" }
              : undefined
          }
        />
        <span>
          {(range[0] / unit.to_si).toPrecision(6)} —{" "}
          {(range[1] / unit.to_si).toPrecision(6)} {unit.label}
        </span>
        {constantRange(range) && (
          <p>Constant field within display precision; uniform color.</p>
        )}
        <p>
          Deformation ×{scale} ·{" "}
          {scale === 0 ? "undeformed geometry" : "display exaggeration"}.
          Numerical values are unchanged.
        </p>
        <p>
          {isDisplacement(field)
            ? "Native DAT nodal displacement. Quadratic boundary faces use all six nodes."
            : smoothed
              ? "Smoothed nodal stress: tensor average within each body/material, then invariants. No averaging across body/material boundaries."
              : "Derived element-node contour from raw DAT tensors. Vertices retain each element side; no stress averaging."}
        </p>
        <p>
          All-body range and extrema remain visible when bodies are hidden. Raw
          IP extrema can differ from extrapolated contour peaks.
        </p>
      </div>
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
