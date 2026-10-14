import { useDraft } from "../workspace/edits";
import { useEffect, useState } from "react";
import type {
  MaterialAssignment,
  MaterialSnapshot,
  MaterialExample,
  UnitPreset,
} from "../geometry/api";
import {
  displayQuantity,
  editQuantity,
  redisplay,
  type QuantityField,
} from "./units";

type Props = {
  saved: MaterialSnapshot | undefined;
  library: MaterialExample[];
  preset: UnitPreset;
  busy: boolean;
  apply: (material: MaterialAssignment) => Promise<boolean>;
  remove: () => void;
};

function draftFor(
  snapshot: MaterialSnapshot | MaterialExample | undefined,
  preset: UnitPreset,
) {
  const properties = snapshot?.properties;
  return {
    young: displayQuantity(properties?.young_modulus_pa, preset.stress),
    density: displayQuantity(properties?.density_kg_m3, preset.density),
    yield: displayQuantity(properties?.yield_strength_pa, preset.stress),
    poisson: properties?.poisson_ratio.toString() ?? "",
    provenance: snapshot?.provenance ?? {
      name: "",
      grade: "",
      condition: "",
      temperature_note: "",
      assumptions: "",
      sources: [{ title: "", url: null, accessed_on: null }],
    },
  };
}

export function MaterialForm({
  saved,
  library,
  preset,
  busy,
  apply,
  remove,
}: Props) {
  const [draft, setDraft] = useState(() => draftFor(saved, preset));
  // Applying a library ID requires deliberate selection of the current entry,
  // never an older saved sample displayed from immutable history.
  const [sample, setSample] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [dirty, setDirty] = useState(false);
  useDraft("material", dirty);
  const savedSignature = JSON.stringify(saved);
  useEffect(() => {
    const snapshot: MaterialSnapshot | undefined = savedSignature
      ? JSON.parse(savedSignature)
      : undefined;
    setDraft(draftFor(snapshot, preset));
    setSample("");
    setConfirmed(false);
    setDirty(false);
  }, [savedSignature]);
  useEffect(() => {
    setDraft((old) => ({
      ...old,
      young: redisplay(old.young, preset.stress),
      density: redisplay(old.density, preset.density),
      yield: redisplay(old.yield, preset.stress),
    }));
  }, [preset]);

  const ratio = draft.poisson.trim() === "" ? NaN : Number(draft.poisson);
  const positive = (field: QuantityField) => field.si !== null && field.si > 0;
  const optional = (field: QuantityField) =>
    field.text === "" || positive(field);
  const valid =
    positive(draft.young) &&
    Number.isFinite(ratio) &&
    ratio >= 0 &&
    ratio <= 0.45 &&
    optional(draft.density) &&
    optional(draft.yield) &&
    Object.values(draft.provenance).every(
      (value) => typeof value !== "string" || !!value.trim(),
    ) &&
    draft.provenance.sources.every(
      (source) => !!source.title.trim() && validSource(source.url),
    );
  function validSource(url: string | null | undefined) {
    if (!url) return true;
    try {
      return ["http:", "https:"].includes(new URL(url).protocol);
    } catch {
      return false;
    }
  }
  function markDirty() {
    setConfirmed(false);
    setDirty(true);
  }
  function chooseSample(id: string) {
    setSample(id);
    setDraft(
      draftFor(
        library.find((item) => item.library_id === id),
        preset,
      ),
    );
    markDirty();
  }
  async function submit() {
    if (!valid || !confirmed) return;
    if (sample) {
      const saved = await apply({
        material: {
          kind: "sample",
          sample_id: sample,
          library_version: library.find((entry) => entry.library_id === sample)!
            .library_version,
          confirmed: true,
        },
      });
      if (saved) {
        setDirty(false);
        setConfirmed(false);
      }
    } else {
      const saved = await apply({
        material: {
          kind: "custom",
          units: preset.id,
          confirmed: true,
          values: {
            young_modulus: draft.young.si! / preset.stress.to_si,
            poisson_ratio: ratio,
            density:
              draft.density.si === null
                ? null
                : draft.density.si / preset.density.to_si,
            yield_strength:
              draft.yield.si === null
                ? null
                : draft.yield.si / preset.stress.to_si,
          },
          provenance: draft.provenance,
        },
      });
      if (saved) {
        setDirty(false);
        setConfirmed(false);
      }
    }
  }
  function quantity(
    label: string,
    key: "young" | "density" | "yield",
    unit: UnitPreset["stress"],
  ) {
    return (
      <label>
        {label} ({unit.label})
        <input
          type="number"
          step="any"
          value={draft[key].text}
          disabled={busy || !!sample}
          onChange={(e) => {
            setDraft((old) => ({
              ...old,
              [key]: editQuantity(e.target.value, unit),
            }));
            markDirty();
          }}
        />
      </label>
    );
  }
  return (
    <div className="material-form">
      {saved?.library_id && (
        <p>
          Saved sample: {saved.library_id}, version {saved.library_version}.
          Selecting an example reviews the current library; editing uses this
          saved copy.
        </p>
      )}
      <label>
        Material example
        <select
          value={sample}
          disabled={busy}
          onChange={(e) => chooseSample(e.target.value)}
        >
          <option value="">Custom material</option>
          {library.map((item) => (
            <option key={item.library_id} value={item.library_id!}>
              {item.provenance.name}
            </option>
          ))}
        </select>
      </label>
      {sample && (
        <button
          disabled={busy}
          onClick={() => {
            setSample("");
            markDirty();
          }}
        >
          Edit as custom
        </button>
      )}
      {(
        [
          "name",
          "grade",
          "condition",
          "temperature_note",
          "assumptions",
        ] as const
      ).map((key) => (
        <label key={key}>
          {
            {
              name: "Material name",
              grade: "Grade",
              condition: "Condition",
              temperature_note: "Temperature applicability",
              assumptions: "Assumptions",
            }[key]
          }
          <textarea
            rows={key === "assumptions" ? 3 : 1}
            maxLength={key === "name" ? 200 : 1000}
            disabled={busy || !!sample}
            value={draft.provenance[key]}
            onChange={(e) => {
              setDraft((old) => ({
                ...old,
                provenance: { ...old.provenance, [key]: e.target.value },
              }));
              markDirty();
            }}
          />
        </label>
      ))}
      {draft.provenance.sources.map((source, index) => (
        <div key={index}>
          <label>
            Source reference {index + 1}
            <input
              value={source.title}
              maxLength={1000}
              disabled={busy || !!sample}
              onChange={(e) => {
                setDraft((old) => ({
                  ...old,
                  provenance: {
                    ...old.provenance,
                    sources: old.provenance.sources.map((s, i) =>
                      i === index ? { ...s, title: e.target.value } : s,
                    ),
                  },
                }));
                markDirty();
              }}
            />
          </label>
          <label>
            Source URL {index + 1} (optional)
            <input
              type="url"
              value={source.url ?? ""}
              maxLength={2083}
              disabled={busy || !!sample}
              onChange={(e) => {
                setDraft((old) => ({
                  ...old,
                  provenance: {
                    ...old.provenance,
                    sources: old.provenance.sources.map((s, i) =>
                      i === index
                        ? {
                            ...s,
                            url: e.target.value || null,
                            accessed_on: null,
                          }
                        : s,
                    ),
                  },
                }));
                markDirty();
              }}
            />
          </label>
          {source.url && validSource(source.url) && (
            <a href={source.url} target="_blank" rel="noreferrer">
              Open source {index + 1}
            </a>
          )}
        </div>
      ))}
      <div className="material-numbers">
        {quantity("Young's modulus E", "young", preset.stress)}
        <label>
          Poisson ratio ν (dimensionless)
          <input
            type="number"
            step="any"
            value={draft.poisson}
            disabled={busy || !!sample}
            onChange={(e) => {
              setDraft((old) => ({ ...old, poisson: e.target.value }));
              markDirty();
            }}
          />
        </label>
        {quantity(
          "Density (optional without gravity)",
          "density",
          preset.density,
        )}
        {quantity("Yield strength (optional)", "yield", preset.stress)}
      </div>
      <p className="material-notice">
        Isotropic linear elasticity. Samples are examples, not certified
        allowables. The development policy accepts 0 ≤ ν ≤ 0.45; auxetic and
        near-incompressible materials are blocked.
      </p>
      {Number.isFinite(ratio) && ratio >= 0.4 && ratio <= 0.45 && (
        <p className="material-notice">
          High Poisson ratio: displacement tetrahedra may lock. Review
          applicability.
        </p>
      )}
      {!valid && dirty && (
        <p role="alert">
          Enter positive finite E, optional positive density/yield, 0 ≤ ν ≤
          0.45, and all provenance fields.
        </p>
      )}
      <label className="check">
        <input
          type="checkbox"
          checked={confirmed}
          disabled={busy || !valid}
          onChange={(e) => setConfirmed(e.target.checked)}
        />
        I confirm the properties, condition and assumptions
      </label>
      <button
        disabled={busy || !valid || !confirmed}
        onClick={() => void submit()}
      >
        Apply material
      </button>
      <button
        disabled={busy}
        onClick={() => {
          setDraft(draftFor(saved, preset));
          setSample("");
          setConfirmed(false);
          setDirty(false);
        }}
      >
        Cancel material edits
      </button>
      <button disabled={busy || !saved} onClick={remove}>
        Remove material
      </button>
      <p aria-live="polite">
        {dirty
          ? "Material edits are not saved."
          : saved
            ? "Saved material snapshot loaded."
            : "No material assigned."}
      </p>
    </div>
  );
}
