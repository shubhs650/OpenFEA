import { useEffect, useState } from "react";
import {
  api,
  mutate,
  RequestError,
  type DeckExport,
  type LoadState,
  type UnitPreset,
} from "../geometry/api";

type Props = {
  analysisId: string;
  revision: number;
  geometryId: string;
  selected: Set<string>;
  preset: UnitPreset;
  busy: boolean;
  setBusy: (value: boolean) => void;
  saved: (revision: number) => void;
  preview: (state: LoadState | null) => void;
};

export function LoadsEditor({
  analysisId,
  revision,
  geometryId,
  selected,
  preset,
  busy,
  setBusy,
  saved,
  preview,
}: Props) {
  const [state, setState] = useState<LoadState | null>(null);
  const [exports, setExports] = useState<DeckExport[]>([]);
  const [kind, setKind] = useState("fixed");
  const [name, setName] = useState("");
  const [pressure, setPressure] = useState("");
  const [force, setForce] = useState(["", "", ""]);
  const [combine, setCombine] = useState(false);
  const [error, setError] = useState("");
  const [conflict, setConflict] = useState(false);
  const [status, setStatus] = useState("");
  // A unit change must not reinterpret an unsaved numeric draft.
  useEffect(() => {
    setPressure("");
    setForce(["", "", ""]);
  }, [preset.id]);
  useEffect(() => {
    let current = true;
    setState(null);
    preview(null);
    void Promise.all([
      api<LoadState>(`/analyses/${analysisId}/loads`),
      api<DeckExport[]>(`/analyses/${analysisId}/deck-exports`),
    ])
      .then(([data, outputs]) => {
        if (current) {
          setState(data);
          setExports(outputs);
          preview(data);
          const stale = data.analysis_revision !== revision;
          setConflict(stale);
          setError(
            stale
              ? "This analysis changed. Reload the saved analysis before applying again."
              : "",
          );
        }
      })
      .catch((e: Error) => {
        if (current) setError(e.message);
      });
    return () => {
      current = false;
    };
  }, [analysisId, revision]);

  const aligned =
    state?.analysis_revision === revision &&
    state.geometry_revision_id === geometryId;
  const overlap =
    !!state?.setup.assignments?.some(
      (a) => a.kind !== "fixed" && a.face_ids.some((f) => selected.has(f)),
    ) && kind !== "fixed";
  const valid =
    kind === "fixed" ||
    (kind === "pressure"
      ? pressure.trim() !== "" &&
        Number.isFinite(Number(pressure)) &&
        Number(pressure) !== 0
      : force.every((v) => v.trim() !== "" && Number.isFinite(Number(v))) &&
        force.some((v) => Number(v) !== 0));
  async function change(path: string, payload?: unknown, method = "POST") {
    if (!aligned) return;
    setBusy(true);
    setError("");
    setStatus("Saving face assignment…");
    try {
      const next = await mutate<LoadState>(
        `/analyses/${analysisId}${path}`,
        revision,
        payload,
        method,
      );
      setState(next);
      preview(next);
      saved(next.analysis_revision);
      setStatus("Face assignments saved in a new analysis revision.");
      setCombine(false);
    } catch (e) {
      setStatus("Assignment was not saved.");
      setConflict(e instanceof RequestError && e.code === "stale_revision");
      setError(
        (e as Error).message +
          (e instanceof RequestError && e.code === "stale_revision"
            ? " Reload the saved analysis before applying again."
            : ""),
      );
    } finally {
      setBusy(false);
    }
  }
  async function generate() {
    if (!aligned) return;
    setBusy(true);
    setError("");
    setStatus("Generating a bounded coarse mesh and checking loads…");
    try {
      const result = await mutate<DeckExport>(
        `/analyses/${analysisId}/deck-exports`,
        revision,
      );
      setExports((old) => [result, ...old.filter((e) => e.id !== result.id)]);
      setStatus("Checked deck saved. Download the immutable input below.");
    } catch (e) {
      setStatus("No deck was published.");
      setError((e as Error).message);
      setConflict(e instanceof RequestError && e.code === "stale_revision");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section aria-label="Face loads" className="loads-panel">
      <h2>Fixed faces and loads</h2>
      <p>
        Global X, Y, Z directions. Positive pressure acts inward; negative
        pressure acts outward. Total force is spread over the entire selected
        area once.
      </p>
      <p>
        {selected.size} selected faces · pinned geometry{" "}
        <code>{geometryId}</code>
      </p>
      <label>
        Assignment name
        <input
          value={name}
          maxLength={200}
          disabled={busy}
          onChange={(e) => setName(e.target.value)}
        />
      </label>
      <label>
        Face assignment
        <select
          value={kind}
          disabled={busy}
          onChange={(e) => {
            setKind(e.target.value);
            setCombine(false);
          }}
        >
          <option value="fixed">Fixed (all translations)</option>
          <option value="pressure">Uniform pressure</option>
          <option value="force">Total distributed force</option>
        </select>
      </label>
      {kind === "pressure" && (
        <label>
          Pressure ({preset.stress.label})
          <input
            type="number"
            step="any"
            value={pressure}
            disabled={busy}
            onChange={(e) => setPressure(e.target.value)}
          />
        </label>
      )}
      {kind === "force" && (
        <div className="force-inputs">
          {["X", "Y", "Z"].map((axis, index) => (
            <label key={axis}>
              Total force {axis} ({preset.force.label})
              <input
                type="number"
                step="any"
                value={force[index]}
                disabled={busy}
                onChange={(e) =>
                  setForce((old) =>
                    old.map((v, i) => (i === index ? e.target.value : v)),
                  )
                }
              />
            </label>
          ))}
        </div>
      )}
      {overlap && (
        <label className="check">
          <input
            type="checkbox"
            checked={combine}
            disabled={busy}
            onChange={(e) => setCombine(e.target.checked)}
          />
          I confirm these overlapping loads combine with the saved loads
        </label>
      )}
      <button
        disabled={
          busy ||
          conflict ||
          !aligned ||
          !name.trim() ||
          !selected.size ||
          !valid ||
          (overlap && !combine)
        }
        onClick={() =>
          void change("/loads", {
            assignment: {
              kind,
              name,
              geometry_revision_id: geometryId,
              face_ids: [...selected],
              ...(kind === "pressure"
                ? {
                    units: preset.id,
                    pressure: Number(pressure),
                    combine_confirmed: combine,
                  }
                : kind === "force"
                  ? {
                      units: preset.id,
                      force: force.map(Number),
                      combine_confirmed: combine,
                    }
                  : {}),
            },
          })
        }
      >
        Save face assignment
      </button>
      {state && (
        <>
          <p>
            Saved resultant (N):{" "}
            {state.total_force_n.map((v) => v.toPrecision(6)).join(", ")} ·
            Moment about global origin (N·m):{" "}
            {state.total_moment_nm.map((v) => v.toPrecision(6)).join(", ")}
          </p>
          <p>
            Arrow lengths are illustrative. Arrows show applied load directions;
            fixed glyphs constrain all translations.
          </p>
          <ul>
            {state.setup.assignments?.map((a) => (
              <li key={a.id} data-assignment-id={a.id}>
                <strong>{a.name}</strong> · {a.kind} · {a.face_ids.length} faces
                {a.pressure_pa !== null &&
                  a.pressure_pa !== undefined &&
                  ` · ${(a.pressure_pa / preset.stress.to_si).toPrecision(6)} ${preset.stress.label} (${a.pressure_pa > 0 ? "inward" : "outward"})`}
                {a.force_n &&
                  ` · [${a.force_n.map((v) => (v / preset.force.to_si).toPrecision(6)).join(", ")}] ${preset.force.label}`}
                <button
                  disabled={busy || conflict || !aligned}
                  onClick={() =>
                    void change(`/loads/${a.id}`, undefined, "DELETE")
                  }
                >
                  Remove {a.name}
                </button>
              </li>
            ))}
          </ul>
          {state.warnings.map((w) => (
            <p key={w}>{w}</p>
          ))}
          <ul aria-label="Deck blockers">
            {state.blockers.map((b) => (
              <li key={b}>{b}</li>
            ))}
          </ul>
        </>
      )}
      <button
        disabled={busy || conflict || !aligned || !!state?.blockers.length}
        onClick={() => void generate()}
      >
        Generate checked deck
      </button>
      <p>
        Coarse planar C3D10 preview: at most 3,000 elements and 60 seconds.
        Bodies remain independent and each needs a fixed face. Export can reject
        an ambiguous mapping, unsuitable mesh or force on fixed degrees of
        freedom. Solving and calculated results follow in later tasks.
      </p>
      <ul aria-label="Saved deck exports">
        {exports.map((e) => (
          <li key={e.id}>
            Revision {e.analysis_revision} · {String(e.summary.elements)} C3D10
            elements ·{" "}
            <a href={`/api/v1/deck-exports/${e.id}/input`}>
              Download analysis.inp
            </a>{" "}
            ·{" "}
            <a href={`/api/v1/deck-exports/${e.id}/snapshot`}>
              Download frozen snapshot
            </a>
            <p>
              Deck SHA-256: <code>{e.deck_sha256}</code>
            </p>
          </li>
        ))}
      </ul>
      {error && <p role="alert">{error}</p>}
      <p aria-live="polite">{status}</p>
    </section>
  );
}
