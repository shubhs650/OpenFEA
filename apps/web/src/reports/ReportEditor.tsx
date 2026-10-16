import { useComputeActivity } from "../help/compute";
import { WordExport } from "./WordExport";
import { useEffect, useRef, useState } from "react";
import type { components } from "../../../../packages/contracts/api";
import { api } from "../geometry/api";
import type { ResultPresentation } from "../results/presentation";

type View = components["schemas"]["ReportViewDefinition"];
type Record = components["schemas"]["ReportRecord"];
export type ReportCamera = components["schemas"]["ReportCamera"];
export function ReportEditor({
  presentation,
  visible,
  camera,
}: {
  presentation: ResultPresentation;
  visible: Set<string>;
  camera: () => ReportCamera | null;
}) {
  const { view, section, field, smoothed, scale, range, preset, comparison } =
    presentation;
  const [views, setViews] = useState<View[]>([]);
  const [reports, setReports] = useState<Record[]>([]);
  const [title, setTitle] = useState("Engineering analysis report");
  const [conclusion, setConclusion] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useComputeActivity(busy);
  const [includeComparison, setIncludeComparison] = useState(false);
  const sequence = useRef(0);
  useEffect(() => {
    const current = ++sequence.current;
    setViews([]);
    setReports([]);
    setBusy(false);
    setError("");
    setConclusion("");
    api<Record[]>(`/runs/${view.job_id}/reports`)
      .then((r) => {
        if (sequence.current === current) setReports(r);
      })
      .catch((e) => {
        if (sequence.current === current) setError((e as Error).message);
      });
    return () => {
      sequence.current++;
    };
  }, [view.job_id]);
  async function generate() {
    const current = sequence.current;
    setBusy(true);
    setError("");
    try {
      const result = await api<Record>(`/runs/${view.job_id}/reports`, "POST", {
        title,
        units: preset.id,
        views,
        user_conclusion: conclusion,
        comparison: includeComparison ? (comparison ?? null) : null,
      });
      if (current === sequence.current) setReports((r) => [result, ...r]);
    } catch (e) {
      if (current === sequence.current) setError((e as Error).message);
    } finally {
      if (current === sequence.current) setBusy(false);
    }
  }
  return (
    <section className="report-editor" aria-label="Report export">
      <h3>A4 PDF report</h3>
      <p>
        Report the open frozen run, revision {view.analysis_revision}. Add up to
        four result views with their camera, field, units, range, body
        visibility, section and deformation settings. All warnings and native
        extrema remain included.
      </p>
      <label>
        Report title
        <input
          value={title}
          maxLength={200}
          onChange={(e) => setTitle(e.target.value)}
        />
      </label>
      <button
        disabled={views.length >= 4 || busy}
        onClick={() => {
          const savedCamera = camera();
          if (
            !savedCamera ||
            visible.size === 0 ||
            (section && !section.triangles.length)
          ) {
            setError(
              "Choose a visible, nonempty result view before adding it.",
            );
            return;
          }
          setViews((v) => [
            ...v,
            {
              field,
              smoothed,
              deformation_scale: scale,
              range_si: [...range],
              visible_body_ids: [...visible].sort(),
              camera: savedCamera,
              section: section
                ? { point_m: section.point_m, normal: section.normal! }
                : null,
            },
          ]);
          setError("");
        }}
      >
        Add current view to report
      </button>
      <ol>
        {views.map((v, i) => (
          <li key={i}>
            {v.field} · {v.section ? "volume section" : "boundary"} ·
            deformation ×{v.deformation_scale} ·{" "}
            {v.smoothed ? "partitioned smoothing" : "unaveraged"}{" "}
            <button
              disabled={busy}
              onClick={() => setViews((rows) => rows.filter((_, n) => n !== i))}
            >
              Remove view {i + 1}
            </button>
          </li>
        ))}
      </ol>
      <label>
        User-written conclusion
        <textarea
          value={conclusion}
          maxLength={4000}
          onChange={(e) => setConclusion(e.target.value)}
        />
      </label>
      <p>
        Your conclusion is attributed separately from numerical facts. The
        report includes supplied-material assumptions and limitations.
      </p>
      {comparison && (
        <label>
          <input
            type="checkbox"
            checked={includeComparison}
            onChange={(e) => setIncludeComparison(e.target.checked)}
          />
          Include current physical refinement comparison
        </label>
      )}
      <button
        disabled={!views.length || !title.trim() || busy}
        onClick={() => void generate()}
      >
        {busy ? "Generating A4 PDF…" : "Generate A4 PDF"}
      </button>
      {error && <p role="alert">{error}</p>}
      {reports.length > 0 && (
        <>
          <h4>Saved reports for this run</h4>
          <ul>
            {reports.map((r) => (
              <li key={r.id}>
                {r.title} · {new Date(r.created_at).toLocaleString()} ·{" "}
                <code>{r.id}</code>
                <br />
                <a
                  href={`/api/v1/reports/${r.id}/html`}
                  target="_blank"
                  rel="noreferrer"
                >
                  Preview light report
                </a>
                {" · "}
                <a href={`/api/v1/reports/${r.id}/pdf`}>Download A4 PDF</a>
                {" · "}
                <a href={`/api/v1/reports/${r.id}/model`}>
                  Download shared report model
                </a>
                <WordExport reportId={r.id} />
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
