import { useEffect, useRef, useState } from "react";
import type { components } from "../../../../packages/contracts/api";
import { api, uploadArchive, type Project } from "../geometry/api";
type Bundle = components["schemas"]["BundleRecord"];
type Imported = components["schemas"]["ImportedArchive"];

export function PortableArchives({
  projectId,
  disabled,
  onImport,
}: {
  projectId?: string;
  disabled: boolean;
  onImport: (project: Project) => void;
}) {
  const [outputs, setOutputs] = useState(false);
  const [geometry, setGeometry] = useState(false);
  const [results, setResults] = useState(false);
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [imports, setImports] = useState<Imported[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const epoch = useRef(0);
  useEffect(() => {
    const current = ++epoch.current;
    setBundle(null);
    setImports([]);
    setError("");
    setBusy(false);
    setOutputs(false);
    setGeometry(false);
    setResults(false);
    if (projectId)
      void api<Imported[]>(`/projects/${projectId}/archive-imports`)
        .then((items) => {
          if (epoch.current === current) setImports(items);
        })
        .catch((e) => {
          if (epoch.current === current) setError((e as Error).message);
        });
    return () => {
      epoch.current++;
    };
  }, [projectId]);
  async function preview(kind: "archive" | "diagnostic") {
    const current = epoch.current;
    setBusy(true);
    setError("");
    setBundle(null);
    try {
      const result = await api<Bundle>(
        `/projects/${projectId}/${kind === "archive" ? "exports" : "diagnostic-previews"}`,
        "POST",
        kind === "archive"
          ? { include_outputs: outputs }
          : { include_geometry: geometry, include_results: results },
      );
      if (epoch.current === current) setBundle(result);
    } catch (e) {
      if (epoch.current === current) setError((e as Error).message);
    } finally {
      if (epoch.current === current) setBusy(false);
    }
  }
  async function restore() {
    if (!file) return;
    const current = epoch.current;
    setBusy(true);
    setError("");
    try {
      // The existing local session cookie and CSRF token protect raw archive uploads.
      const restored = await uploadArchive(file);
      if (epoch.current === current) onImport(restored.project);
    } catch (e) {
      if (epoch.current === current) setError((e as Error).message);
    } finally {
      if (epoch.current === current) setBusy(false);
    }
  }
  return (
    <section
      className="portable-archives"
      aria-label="Portable archives and diagnostics"
    >
      <h2>Portable archives</h2>
      <p>
        Import creates a new private project. Historical files stay read-only;
        re-solving creates a fresh run.
      </p>
      <label>
        Project archive ZIP
        <input
          type="file"
          accept=".zip"
          disabled={disabled || busy}
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
      </label>
      <button
        disabled={disabled || busy || !file || file.size > 64 * 1024 * 1024}
        onClick={() => void restore()}
      >
        Import project archive
      </button>
      {projectId && (
        <>
          <label>
            <input
              type="checkbox"
              checked={outputs}
              disabled={busy}
              onChange={(e) => {
                setOutputs(e.target.checked);
                setBundle(null);
              }}
            />
            Include available meshes, results and reports
          </label>
          <button
            disabled={disabled || busy}
            onClick={() => void preview("archive")}
          >
            Preview project archive
          </button>
          <h3>Diagnostic bundle</h3>
          <p>
            Defaults omit names, setup, raw logs, geometry and results. Nothing
            is uploaded to support.
          </p>
          <label>
            <input
              type="checkbox"
              checked={geometry}
              disabled={busy}
              onChange={(e) => {
                setGeometry(e.target.checked);
                setBundle(null);
              }}
            />
            Include geometry (reveals coordinates)
          </label>
          <label>
            <input
              type="checkbox"
              checked={results}
              disabled={busy}
              onChange={(e) => {
                setResults(e.target.checked);
                setBundle(null);
              }}
            />
            Include results (reveals coordinates)
          </label>
          <button
            disabled={disabled || busy}
            onClick={() => void preview("diagnostic")}
          >
            Preview diagnostic bundle
          </button>
        </>
      )}
      {busy && (
        <p role="status">
          Preparing archive; native validation may take up to two minutes.
        </p>
      )}
      {error && <p role="alert">{error}</p>}
      {bundle && (
        <div aria-label="Bundle content preview">
          <p>{bundle.notice}</p>
          <p>
            {bundle.size_bytes} bytes · SHA-256 {bundle.sha256}
          </p>
          <ul>
            {Object.entries(bundle.manifest.files).map(([name, item]) => (
              <li key={name}>
                {bundle.manifest.labels?.[name] ?? name} · {item.size_bytes}{" "}
                bytes · {item.sha256}
              </li>
            ))}
          </ul>
          <ul>
            {(bundle.manifest.omitted ?? []).map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
          <a href={`/api/v1/portable-bundles/${bundle.id}/zip`}>
            Download reviewed{" "}
            {bundle.kind === "project"
              ? "project archive"
              : "diagnostic bundle"}
          </a>
        </div>
      )}
      {imports.map((item) => (
        <div key={item.id} aria-label="Imported read-only history">
          <p>{item.notice}</p>
          {item.history.map((history) => (
            <details key={history.id}>
              <summary>
                Historical {history.kind} · {history.id}
              </summary>
              {Object.keys(history.files ?? {}).map((name) => (
                <p key={name}>
                  <a
                    href={`/api/v1/archive-imports/${item.id}/history/${history.id}/${name}`}
                  >
                    Download historical {name}
                  </a>
                </p>
              ))}
              {Object.entries(history.omitted ?? {}).map(([name, reason]) => (
                <p key={name}>
                  {name}: {reason}
                </p>
              ))}
            </details>
          ))}
        </div>
      ))}
    </section>
  );
}
