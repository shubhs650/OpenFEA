import { useEffect, useState } from "react";
import type { components } from "../../../../packages/contracts/api";
import { api, mutate, type Geometry, type LoadState } from "../geometry/api";
import { useDraft, useEdits } from "../workspace/edits";
import type { DraftDirection } from "../loads/DirectionEditor";

type State = components["schemas"]["BondState"];
type Candidates = components["schemas"]["BondCandidates"];
type Props = {
  analysisId: string;
  revision: number;
  geometry: Geometry;
  selected: Set<string>;
  busy: boolean;
  setBusy: (value: boolean) => void;
  saved: (revision: number) => void;
  preview: (values: DraftDirection[]) => void;
};

export function ConnectionsEditor({
  analysisId,
  revision,
  geometry,
  selected,
  busy,
  setBusy,
  saved,
  preview,
}: Props) {
  const edits = useEdits();
  const [loads, setLoads] = useState<LoadState | null>(null);
  const [state, setState] = useState<State | null>(null);
  const [candidates, setCandidates] = useState<Candidates | null>(null);
  const [master, setMaster] = useState("");
  const [slave, setSlave] = useState("");
  const [name, setName] = useState("");
  const [tolerance, setTolerance] = useState("0");
  const [gapApproved, setGapApproved] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState("");
  useDraft("bonds", Boolean(master || slave || name));
  useEffect(() => {
    let current = true;
    setState(null);
    setLoads(null);
    setCandidates(null);
    setMaster("");
    setSlave("");
    setConfirmed(false);
    setGapApproved(false);
    setName("");
    setTolerance("0");
    setError("");
    preview([]);
    void Promise.all([
      api<State>(`/analyses/${analysisId}/bonds`),
      api<LoadState>(`/analyses/${analysisId}/loads`),
    ])
      .then(([value, loadState]) => {
        if (current) {
          setState(value);
          setLoads(loadState);
        }
      })
      .catch((e: Error) => {
        if (current) setError(e.message);
      });
    return () => {
      current = false;
    };
  }, [analysisId, revision, geometry.id]);
  const valid = candidates?.analysis_revision === revision ? candidates : null;
  const pair = valid?.report.pairs.find(
    (p) =>
      (p.master_face_id === master && p.slave_face_id === slave) ||
      (p.master_face_id === slave && p.slave_face_id === master),
  );
  const disabled =
    busy ||
    !state ||
    state.analysis_revision !== revision ||
    edits.phase === "conflict";
  const label = (id: string) => {
    const face = geometry.faces.find((f) => f.id === id);
    return `Body ${geometry.bodies.findIndex((b) => b.id === face?.body_id) + 1} · face ${id.split(":f").pop()}`;
  };
  function clear() {
    setMaster("");
    setSlave("");
    setName("");
    setTolerance("0");
    setGapApproved(false);
    setConfirmed(false);
    preview([]);
  }
  function choose(a: string, b: string) {
    setMaster(a);
    setSlave(b);
    setGapApproved(false);
    setConfirmed(false);
    preview([]);
  }
  async function measure() {
    setBusy(true);
    setError("");
    try {
      setCandidates(
        await mutate<Candidates>(
          `/analyses/${analysisId}/bond-candidates`,
          revision,
        ),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function write(remove?: string) {
    setBusy(true);
    setError("");
    try {
      const data = await mutate<State>(
        `/analyses/${analysisId}/bonds${remove ? `/${remove}` : ""}`,
        revision,
        remove
          ? undefined
          : {
              geometry_revision_id: geometry.id,
              name,
              master_face_id: master,
              slave_face_id: slave,
              gap_tolerance_m: Number(tolerance),
              gap_approved: gapApproved,
              assumptions_confirmed: confirmed,
            },
        remove ? "DELETE" : "POST",
      );
      clear();
      setState(data);
      saved(data.analysis_revision);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function show() {
    if (!pair) return;
    preview(
      [master, slave].map((id) => ({
        analysis_id: analysisId,
        geometry_revision_id: geometry.id,
        body_id: geometry.faces.find((f) => f.id === id)!.body_id,
        position_m:
          id === pair.master_face_id
            ? pair.master_center_m
            : pair.slave_center_m,
        direction:
          id === pair.master_face_id ? pair.master_normal : pair.slave_normal,
      })),
    );
  }
  return (
    <section aria-label="Bond connections" id="connections">
      <h3>Bond connections</h3>
      <p>
        Suggestions never activate a bond. Review master/slave, complete
        projected coverage and outward normals. Physical gaps require explicit
        approval. Development review supports complete planar unit-square
        interfaces and gap review up to 10 µm. Product solving supports one
        validated zero-gap interface; physical-gap solving remains unavailable.
      </p>
      {loads?.analysis_revision === revision && (
        <div aria-label="Assembly support preflight">
          <p>
            Necessary support/connectivity checks only — not proof of stiffness
            rank or stability. No weak springs.
          </p>
          <ul>
            {loads.assembly?.components?.map((c, i) => (
              <li key={i}>
                Component {i + 1}: {c.body_ids.length} body/bodies; support rank{" "}
                {c.support_rank}/6.
              </li>
            ))}
          </ul>
          {loads.assembly?.blockers?.map((b) => (
            <p key={b}>{b}</p>
          ))}
          <p>
            Generate a mesh, then use Check assembly constraints for actual node
            coverage and dependency checks.
          </p>
        </div>
      )}
      <button
        disabled={disabled || edits.dirty.some((k) => k !== "bonds")}
        onClick={() => void measure()}
      >
        Inspect bond candidates
      </button>
      {valid && (
        <>
          <p>
            Measured {valid.report.pairs.length} opposing face pairs. Numerical
            coincidence: {valid.coincidence_m} m. Body overlap tolerance: 1e-12
            m³.
          </p>
          {valid.report.overlaps.map((o, i) => (
            <p key={i} role="alert">
              Body volume overlap: {o.volume_m3} m³. Meshing and solving are
              blocked.
            </p>
          ))}
          <ul aria-label="Bond suggestions">
            {valid.report.pairs.map((p, i) => (
              <li key={i}>
                {label(p.master_face_id)} ↔ {label(p.slave_face_id)}; gap{" "}
                {p.gap_m.toExponential(6)} m; projected overlap{" "}
                {p.overlap_area_m2.toPrecision(6)} m²;{" "}
                {p.blocker ?? "Eligible for explicit review"}
                <button
                  disabled={disabled}
                  onClick={() => choose(p.master_face_id, p.slave_face_id)}
                >
                  Review pair {i + 1}
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
      <fieldset disabled={disabled}>
        <legend>Manual face pair and review</legend>
        <label>
          Master face
          <select
            aria-label="Master face"
            value={master}
            onChange={(e) => choose(e.target.value, slave)}
          >
            <option value="">Choose master</option>
            {geometry.faces.map((f) => (
              <option key={f.id} value={f.id}>
                {label(f.id)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Slave face
          <select
            aria-label="Slave face"
            value={slave}
            onChange={(e) => choose(master, e.target.value)}
          >
            <option value="">Choose slave</option>
            {geometry.faces.map((f) => (
              <option key={f.id} value={f.id}>
                {label(f.id)}
              </option>
            ))}
          </select>
        </label>
        <button
          disabled={selected.size !== 2}
          onClick={() => {
            const [a, b] = [...selected];
            choose(a, b);
          }}
        >
          Use two selected faces
        </button>
        <button
          disabled={!master || !slave}
          onClick={() => choose(slave, master)}
        >
          Swap master/slave
        </button>
        <button disabled={!pair} onClick={show}>
          Preview pair normals
        </button>
        {pair && (
          <p aria-label="Bond pair measurements">
            Master {label(master)}; slave {label(slave)}. Gap{" "}
            {pair.gap_m.toExponential(6)} m. Normal dot {pair.normal_dot}.
            Master/slave projected coverage{" "}
            {(
              100 *
              (master === pair.master_face_id
                ? pair.master_coverage
                : pair.slave_coverage)
            ).toFixed(6)}
            % /{" "}
            {(
              100 *
              (slave === pair.slave_face_id
                ? pair.slave_coverage
                : pair.master_coverage)
            ).toFixed(6)}
            %. {pair.blocker}
          </p>
        )}
        {master && slave && valid && !pair && (
          <p>
            No verified opposing planar overlap within the 1 mm search bound.
            This pair cannot be approved.
          </p>
        )}
        <label>
          Connection name
          <input value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label>
          Approved gap tolerance (m)
          <input
            type="number"
            min="0"
            max="0.00001"
            step="any"
            value={tolerance}
            onChange={(e) => {
              setTolerance(e.target.value);
              setGapApproved(false);
            }}
          />
        </label>
        <label>
          <input
            type="checkbox"
            checked={gapApproved}
            onChange={(e) => setGapApproved(e.target.checked)}
          />
          I explicitly approve this physical gap within the entered tolerance
        </label>
        <label>
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(e) => setConfirmed(e.target.checked)}
          />
          I reviewed roles, coverage and the experimental
          displacement-continuity model: no geometry movement, adhesive
          stiffness or contact
        </label>
        <button
          disabled={
            !pair?.eligible ||
            !name.trim() ||
            !confirmed ||
            (pair.gap_m > 1e-8 &&
              (!gapApproved || Number(tolerance) + 1e-12 < pair.gap_m))
          }
          onClick={() => void write()}
        >
          Approve saved bond
        </button>
        <button onClick={clear}>Cancel bond draft</button>
      </fieldset>
      <ul aria-label="Saved bonds">
        {state?.setup.assignments?.map((a) => (
          <li key={a.id}>
            {a.name}: master {label(a.master_face_id)}, slave{" "}
            {label(a.slave_face_id)}; frozen gap {a.pair.gap_m.toExponential(6)}{" "}
            m;{" "}
            {state.review_required.includes(a.id)
              ? "Geometry review required"
              : "Explicitly reviewed setup"}
            .{" "}
            <button
              disabled={disabled || edits.dirty.length > 0}
              onClick={() => void write(a.id)}
            >
              Remove {a.name}
            </button>
          </li>
        ))}
      </ul>
      {state?.solve_blockers.map((b) => (
        <p key={b}>{b}</p>
      ))}
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
