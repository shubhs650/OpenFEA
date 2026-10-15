import { useEffect, useRef, useState } from "react";
import type { components } from "../../../../packages/contracts/api";
import { api } from "../geometry/api";
type Word = components["schemas"]["WordExport"];
export function WordExport({ reportId }: { reportId: string }) {
  const [exports, setExports] = useState<Word[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const sequence = useRef(0);
  useEffect(() => {
    const current = ++sequence.current;
    setExports([]);
    setError("");
    setBusy(false);
    api<Word[]>(`/reports/${reportId}/exports/word`)
      .then((items) => {
        if (sequence.current === current) setExports(items);
      })
      .catch((e) => {
        if (sequence.current === current) setError((e as Error).message);
      });
    return () => {
      sequence.current++;
    };
  }, [reportId]);
  async function generate() {
    const current = sequence.current;
    setBusy(true);
    setError("");
    try {
      const result = await api<Word>(
        `/reports/${reportId}/exports/word`,
        "POST",
        {},
      );
      if (sequence.current === current)
        setExports((items) => [result, ...items]);
    } catch (e) {
      if (sequence.current === current) setError((e as Error).message);
    } finally {
      if (sequence.current === current) setBusy(false);
    }
  }
  return (
    <div aria-label="Editable Word output" data-report-id={reportId}>
      <button disabled={busy} onClick={() => void generate()}>
        {busy ? "Generating editable Word…" : "Generate editable Word"}
      </button>
      <p>
        Uses this saved PDF’s exact report model. Paragraphs, captions and
        tables are editable; figures are embedded images. Provenance identifies
        the generated version and does not certify later edits.
      </p>
      {error && <p role="alert">{error}</p>}
      {exports.length > 0 && (
        <ul>
          {exports.map((item) => (
            <li key={item.id}>
              <a href={`/api/v1/word-exports/${item.id}/docx`}>
                Download editable Word
              </a>
              {" · "}
              <time dateTime={item.created_at}>
                {new Date(item.created_at).toLocaleString()}
              </time>
              {" · "}
              <a href={`/api/v1/word-exports/${item.id}`}>
                Word export provenance
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
