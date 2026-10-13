import { useEffect, useRef, useState } from "react";
import "@kitware/vtk.js/Rendering/Profiles/Geometry";
import vtkGenericRenderWindow, {
  type vtkGenericRenderWindow as Window,
} from "@kitware/vtk.js/Rendering/Misc/GenericRenderWindow";
import vtkActor, {
  type vtkActor as Actor,
} from "@kitware/vtk.js/Rendering/Core/Actor";
import vtkMapper from "@kitware/vtk.js/Rendering/Core/Mapper";
import vtkPolyData from "@kitware/vtk.js/Common/DataModel/PolyData";
import vtkCellPicker from "@kitware/vtk.js/Rendering/Core/CellPicker";
import type { Display, LoadMarker } from "./api";
import { glyph, type Point } from "../loads/glyph";

type Props = {
  display: Display;
  revision: string;
  selected: Set<string>;
  visible: Set<string>;
  toggle: (face: string) => void;
  markers: LoadMarker[];
};

export function Viewport({
  display,
  revision,
  selected,
  visible,
  toggle,
  markers,
}: Props) {
  const container = useRef<HTMLDivElement>(null);
  const scene = useRef<Window | null>(null);
  const actors = useRef(new Map<Actor, { id: string; body: string }>());
  const [hover, setHover] = useState<string | null>(null);
  const [error, setError] = useState("");
  const toggleRef = useRef(toggle);
  toggleRef.current = toggle;
  const first = useRef(true);
  const releaseActors = useRef<() => void>(() => {});
  const releaseGlyphs = useRef<() => void>(() => {});

  useEffect(() => {
    if (!container.current) return;
    const view = vtkGenericRenderWindow.newInstance({
      background: [0.94, 0.96, 0.98],
      listenWindowResize: false,
    });
    view.setContainer(container.current);
    scene.current = view;
    first.current = true;
    const resize = new ResizeObserver(() => view.resize());
    resize.observe(container.current);
    return () => {
      resize.disconnect();
      releaseGlyphs.current();
      releaseActors.current();
      view.delete();
      scene.current = null;
    };
  }, [revision]);

  useEffect(() => {
    const view = scene.current;
    if (!view || !container.current) return;
    const renderer = view.getRenderer();
    const picker = vtkCellPicker.newInstance({
      tolerance: 0.0005,
      pickFromList: true,
    });
    const cleanup: Array<() => void> = [];
    const center = [0, 1, 2].map(
      (axis) =>
        (Math.min(...display.bodies.map((b) => b.bounds_m[axis])) +
          Math.max(...display.bodies.map((b) => b.bounds_m[axis + 3]))) /
        2,
    );
    for (const face of display.faces) {
      const poly = vtkPolyData.newInstance();
      const mapper = vtkMapper.newInstance({ scalarVisibility: false });
      const actor = vtkActor.newInstance();
      poly
        .getPoints()
        .setData(
          new Float32Array(
            face.points_m.flatMap((p) => p.map((v, axis) => v - center[axis])),
          ),
          3,
        );
      poly
        .getPolys()
        .setData(new Uint32Array(face.triangles.flatMap((t) => [3, ...t])));
      mapper.setInputData(poly);
      actor.setMapper(mapper);
      actor.getProperty().setColor(0.48, 0.65, 0.76);
      actor.getProperty().setEdgeVisibility(true);
      actor.getProperty().setEdgeColor(0.2, 0.3, 0.4);
      renderer.addActor(actor);
      actors.current.set(actor, { id: face.id, body: face.body_id });
      picker.addPickList(actor);
      cleanup.push(() => {
        renderer.removeActor(actor);
        actor.delete();
        mapper.delete();
        poly.delete();
      });
    }
    if (first.current) {
      renderer.getActiveCamera().setPosition(1, 1, 1);
      renderer.getActiveCamera().setViewUp(0, 0, 1);
      renderer.resetCamera();
      first.current = false;
    }
    try {
      view.resize();
      view.getRenderWindow().render();
    } catch {
      setError("3D rendering failed. Check browser WebGL support.");
    }
    const element = container.current;
    let down: [number, number] | null = null;
    const pick = (event: PointerEvent) => {
      const canvas = element.querySelector("canvas");
      if (!canvas) return null;
      const rect = canvas.getBoundingClientRect();
      picker.pick(
        [
          ((event.clientX - rect.left) * canvas.width) / rect.width,
          ((rect.bottom - event.clientY) * canvas.height) / rect.height,
          0,
        ],
        renderer,
      );
      return picker.getCellId() < 0
        ? null
        : (actors.current.get(picker.getActors()[0])?.id ?? null);
    };
    const move = (event: PointerEvent) => {
      if (!event.buttons) setHover(pick(event));
    };
    const press = (event: PointerEvent) => {
      down = [event.clientX, event.clientY];
    };
    const release = (event: PointerEvent) => {
      if (
        down &&
        Math.hypot(event.clientX - down[0], event.clientY - down[1]) < 4
      ) {
        const face = pick(event);
        if (face) toggleRef.current(face);
      }
      down = null;
    };
    element.addEventListener("pointermove", move);
    element.addEventListener("pointerdown", press);
    element.addEventListener("pointerup", release);
    let released = false;
    const dispose = () => {
      if (released) return;
      released = true;
      element.removeEventListener("pointermove", move);
      element.removeEventListener("pointerdown", press);
      element.removeEventListener("pointerup", release);
      cleanup.forEach((remove) => remove());
      actors.current.clear();
      picker.delete();
    };
    releaseActors.current = dispose;
    return dispose;
  }, [display, revision]);

  useEffect(() => {
    for (const [actor, face] of actors.current) {
      actor.setVisibility(visible.has(face.body));
      const color: [number, number, number] = selected.has(face.id)
        ? [0.95, 0.58, 0.16]
        : hover === face.id
          ? [0.25, 0.8, 0.65]
          : [0.48, 0.65, 0.76];
      actor.getProperty().setColor(color);
    }
    scene.current?.getRenderWindow().render();
  }, [selected, visible, hover, display]);

  function camera(front: boolean) {
    const renderer = scene.current?.getRenderer();
    if (!renderer) return;
    renderer.getActiveCamera().setFocalPoint(0, 0, 0);
    renderer.getActiveCamera().setPosition(front ? 0 : 1, front ? 0 : 1, 1);
    renderer.getActiveCamera().setViewUp(0, front ? 1 : 0, front ? 0 : 1);
    renderer.resetCamera();
    scene.current?.getRenderWindow().render();
  }
  useEffect(() => {
    const view = scene.current;
    if (!view) return;
    const renderer = view.getRenderer();
    const center = [0, 1, 2].map(
      (axis) =>
        (Math.min(...display.bodies.map((b) => b.bounds_m[axis])) +
          Math.max(...display.bodies.map((b) => b.bounds_m[axis + 3]))) /
        2,
    );
    const length =
      Math.max(
        ...[0, 1, 2].map(
          (axis) =>
            Math.max(...display.bodies.map((b) => b.bounds_m[axis + 3])) -
            Math.min(...display.bodies.map((b) => b.bounds_m[axis])),
        ),
      ) * 0.18;
    const cleanup: Array<() => void> = [];
    for (const marker of markers) {
      if (!visible.has(marker.body_id)) continue;
      const poly = vtkPolyData.newInstance();
      const mapper = vtkMapper.newInstance({ scalarVisibility: false });
      const actor = vtkActor.newInstance({ pickable: false });
      const lines = glyph(
        marker.position_m.map(
          (v, i) =>
            v -
            center[i] -
            (marker.tip_on_face ? marker.direction[i] * length : 0),
        ) as Point,
        marker.direction,
        length,
        marker.kind === "fixed",
      );
      poly.getPoints().setData(new Float32Array(lines.flat(2)), 3);
      let offset = 0;
      poly.getLines().setData(
        new Uint32Array(
          lines.flatMap((line) => {
            const indices = line.map((_, i) => offset + i);
            offset += line.length;
            return [line.length, ...indices];
          }),
        ),
      );
      mapper.setInputData(poly);
      actor.setMapper(mapper);
      actor
        .getProperty()
        .setColor(
          ...(marker.kind === "fixed"
            ? ([0.1, 0.55, 0.25] as Point)
            : ([0.85, 0.1, 0.15] as Point)),
        );
      actor.getProperty().setLineWidth(3);
      renderer.addActor(actor);
      cleanup.push(() => {
        renderer.removeActor(actor);
        actor.delete();
        mapper.delete();
        poly.delete();
      });
    }
    view.getRenderWindow().render();
    let released = false;
    const dispose = () => {
      if (released) return;
      released = true;
      cleanup.forEach((remove) => remove());
    };
    releaseGlyphs.current = dispose;
    return dispose;
  }, [markers, visible, display, revision]);
  return (
    <section className="viewport-shell">
      <div className="viewport-toolbar">
        <button
          onClick={() => {
            scene.current?.getRenderer().resetCamera();
            scene.current?.getRenderWindow().render();
          }}
        >
          Fit
        </button>
        <button onClick={() => camera(true)}>Front</button>
        <button onClick={() => camera(false)}>Isometric</button>
        <span>Drag to rotate · Scroll to zoom · Click a face</span>
      </div>
      {error && <p role="alert">{error}</p>}
      <div
        ref={container}
        className="viewport"
        aria-label="Geometry viewport"
        data-revision={revision}
        data-load-markers={markers.filter((m) => visible.has(m.body_id)).length}
      />
      <p className="viewport-caption">
        {display.bodies.length} bodies · {display.faces.length} faces ·{" "}
        {display.faces.reduce((n, f) => n + f.triangles.length, 0)} display
        triangles
      </p>
    </section>
  );
}
