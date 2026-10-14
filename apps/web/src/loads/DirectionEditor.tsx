import { useEffect, useRef, useState } from "react";
import type { components } from "../../../../packages/contracts/api";
import { mutate, type Geometry } from "../geometry/api";

export type DirectionSelection = components["schemas"]["DirectionSelection"];
export type DirectionSnapshot = components["schemas"]["DirectionSnapshot"];
export type DirectionSource = "global" | DirectionSelection["kind"];
export type DraftDirection = {
  analysis_id: string;
  geometry_revision_id: string;
  body_id: string;
  position_m: [number, number, number];
  direction: [number, number, number];
};

type Props = {
  analysisId: string;
  revision: number;
  geometry: Geometry | null;
  selected: Set<string>;
  source: DirectionSource;
  setSource: (source: DirectionSource) => void;
  globalAllowed: boolean;
  symmetry: boolean;
  disabled: boolean;
  resolved: (
    choice: DirectionSelection | null,
    values: DirectionSnapshot[],
  ) => void;
  preview: (values: DraftDirection[]) => void;
};

export function DirectionEditor({
  analysisId,
  revision,
  geometry,
  selected,
  source,
  setSource,
  globalAllowed,
  symmetry,
  disabled,
  resolved,
  preview,
}: Props) {
  const [reference, setReference] = useState("");
  const [reverse, setReverse] = useState(false);
  const [snapshots, setSnapshots] = useState<DirectionSnapshot[]>([]);
  const [error, setError] = useState("");
  const onResolved = useRef(resolved);
  const onPreview = useRef(preview);
  onResolved.current = resolved;
  onPreview.current = preview;
  const selectionKey = [...selected].sort().join(",");
  useEffect(() => {
    setReference("");
    setReverse(false);
  }, [geometry?.id]);
  useEffect(() => {
    let current = true;
    setSnapshots([]);
    setError("");
    onResolved.current(null, []);
    onPreview.current([]);
    if (!geometry || disabled || (!symmetry && source === "global")) return;
    const choice: DirectionSelection | null =
      source !== "global" && reference
        ? { kind: source, reference_id: reference, reverse }
        : null;
    const directions: DirectionSelection[] = symmetry
      ? [...selected].sort().map((ref) => ({
          kind: "plane_normal",
          reference_id: ref,
          reverse: false,
        }))
      : choice
        ? [choice]
        : [];
    if (!directions.length) return;
    void mutate<DirectionSnapshot[]>(
      `/analyses/${analysisId}/direction-previews`,
      revision,
      { geometry_revision_id: geometry.id, directions },
    )
      .then((values) => {
        if (!current) return;
        setSnapshots(values);
        onResolved.current(choice, values);
        onPreview.current(
          values.map((value) => {
            const body =
              value.kind === "straight_edge"
                ? geometry.edges?.find((edge) => edge.id === value.reference_id)
                    ?.body_id
                : geometry.faces.find((face) => face.id === value.reference_id)
                    ?.body_id;
            return {
              body_id: body!,
              analysis_id: analysisId,
              geometry_revision_id: geometry.id,
              position_m: value.origin_m,
              direction: value.vector,
            };
          }),
        );
      })
      .catch((e: Error) => {
        if (current) setError(e.message);
      });
    return () => {
      current = false;
    };
  }, [
    analysisId,
    revision,
    geometry?.id,
    source,
    reference,
    reverse,
    selectionKey,
    symmetry,
    disabled,
  ]);
  useEffect(
    () => () => {
      onPreview.current([]);
    },
    [],
  );
  const options = geometry
    ? source === "straight_edge"
      ? (geometry.edges ?? [])
          .filter((edge) => edge.curve_type.endsWith("GeomAbs_Line"))
          .map((edge, index) => ({
            id: edge.id,
            label: `Straight edge ${index + 1}`,
          }))
      : geometry.faces
          .filter((face) =>
            String(face.signature.surface_type).endsWith(
              source === "cylinder_axis" ? "GeomAbs_Cylinder" : "GeomAbs_Plane",
            ),
          )
          .map((face, index) => ({
            id: face.id,
            label: `${source === "cylinder_axis" ? "Cylindrical face" : "Planar face"} ${index + 1}`,
          }))
    : [];
  return (
    <fieldset aria-label="Geometry direction">
      <legend>
        {symmetry ? "Planar symmetry normals" : "Direction and sign"}
      </legend>
      {!symmetry && (
        <>
          <label>
            Direction source
            <select
              value={source}
              disabled={disabled}
              onChange={(e) => {
                setReference("");
                setReverse(false);
                setSource(e.target.value as DirectionSource);
              }}
            >
              {globalAllowed && (
                <option value="global">Global component</option>
              )}
              <option value="plane_normal">Planar outward normal</option>
              <option value="straight_edge">Straight edge</option>
              <option value="cylinder_axis">Cylindrical axis</option>
            </select>
          </label>
          {source !== "global" && (
            <>
              <label>
                Direction reference
                <select
                  value={reference}
                  disabled={disabled}
                  onChange={(e) => setReference(e.target.value)}
                >
                  <option value="">Choose a direction reference</option>
                  {options.map((option) => (
                    <option key={option.id} value={option.id}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="check">
                <input
                  type="checkbox"
                  disabled={disabled}
                  checked={reverse}
                  onChange={(e) => setReverse(e.target.checked)}
                />
                Reverse selected direction
              </label>
              {!options.length && (
                <p>
                  No native reference of this type is available. Legacy
                  edge/axis catalogs require reimport.
                </p>
              )}
            </>
          )}
        </>
      )}
      {symmetry && (
        <p>
          Zero displacement along each selected planar face's native outward
          normal. Other translations remain free. Curved symmetry is refused.
        </p>
      )}
      {snapshots.length > 0 && (
        <div aria-label="Resolved direction basis">
          <p>
            Right-handed orthonormal basis in global coordinates. X′ is the
            signed selected direction; Y′ and Z′ complete the basis. Purple
            arrows show the draft direction.
          </p>
          {snapshots.map((value) => (
            <div
              key={value.reference_id}
              data-direction-reference={value.reference_id}
            >
              <p>
                {value.reverse
                  ? "Reversed direction"
                  : "Native positive direction"}
              </p>
              <table>
                <thead>
                  <tr>
                    <th>Basis axis</th>
                    <th>Global X</th>
                    <th>Global Y</th>
                    <th>Global Z</th>
                  </tr>
                </thead>
                <tbody>
                  {value.basis.map((axis, index) => (
                    <tr key={index}>
                      <th>{["X′", "Y′", "Z′"][index]}</th>
                      {axis.map((component, i) => (
                        <td key={i}>{component.toPrecision(7)}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      )}
      {error && <p role="alert">{error}</p>}
    </fieldset>
  );
}
