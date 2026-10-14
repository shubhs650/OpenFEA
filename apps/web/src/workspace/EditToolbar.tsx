import { useEffect, useState } from "react";
import { api, mutate, type Analysis } from "../geometry/api";
import {
  invalidateEdits,
  observeRevision,
  resetEdits,
  saveLabel,
  undoAcknowledged,
  useDraft,
  useEdits,
} from "./edits";

export function EditToolbar({
  analysisId,
  epoch,
  busy,
  setBusy,
  reload,
  selectCopy,
}: {
  analysisId: string;
  epoch: number;
  busy: boolean;
  setBusy: (value: boolean) => void;
  reload: () => void;
  selectCopy: (id: string) => void;
}) {
  const edits = useEdits();
  const [loaded, setLoaded] = useState<Analysis | null>(null);
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [createdCopy, setCreatedCopy] = useState("");
  const [notice, setNotice] = useState("");
  useEffect(() => {
    let current = true;
    setLoaded(null);
    if (analysisId)
      void api<Analysis>(`/analyses/${analysisId}`)
        .then((a) => {
          if (current) {
            setLoaded(a);
            setName(a.name);
            observeRevision(a.id, a.revision);
          }
        })
        .catch((e: Error) => {
          if (current) setError(e.message);
        });
    return () => {
      current = false;
    };
  }, [analysisId, epoch]);
  useEffect(() => {
    const check = () => {
      if (!analysisId) return;
      void api<Analysis>(`/analyses/${analysisId}`)
        .then((a) => observeRevision(a.id, a.revision))
        .catch(() => {});
    };
    window.addEventListener("focus", check);
    return () => window.removeEventListener("focus", check);
  }, [analysisId]);
  const dirty = loaded?.id === analysisId && name !== loaded.name;
  useDraft("analysis-name", !!dirty);
  useEffect(() => {
    if (
      !dirty ||
      !name.trim() ||
      busy ||
      edits.id !== analysisId ||
      edits.dirty.some((key) => key !== "analysis-name") ||
      edits.phase !== "saved"
    )
      return;
    const timer = setTimeout(() => {
      setBusy(true);
      setError("");
      void mutate<Analysis>(
        `/analyses/${analysisId}`,
        edits.revision,
        { name },
        "PATCH",
      )
        .then((a) => {
          setLoaded(a);
          setName(a.name);
        })
        .catch((e: Error) => setError(e.message))
        .finally(() => setBusy(false));
    }, 700);
    return () => clearTimeout(timer);
  }, [
    name,
    loaded,
    busy,
    edits.phase,
    edits.dirty,
    edits.revision,
    analysisId,
  ]);

  async function undo() {
    const target = edits.history.at(-1);
    if (!target) return;
    setBusy(true);
    setError("");
    try {
      const a = await mutate<Analysis>(
        `/analyses/${analysisId}/restores`,
        edits.revision,
        { target_revision: target },
      );
      undoAcknowledged(a.revision);
      reload();
      setNotice(
        "Edit undone in a new revision. Mesh preview cleared; completed runs keep their frozen inputs.",
      );
    } catch (e) {
      setError((e as Error).message);
      invalidateEdits(analysisId);
    } finally {
      setBusy(false);
    }
  }
  async function duplicate() {
    const command = edits.pending;
    if (!command) return;
    setBusy(true);
    setError("");
    let copy: Analysis | null = null;
    let applied = false;
    try {
      const head = await api<Analysis>(`/analyses/${analysisId}`);
      copy = await mutate<Analysis>(
        `/analyses/${analysisId}/conflict-copies`,
        head.revision,
        {
          source_revision: command.revision,
          name: `${loaded?.name ?? "Analysis"} (conflict copy)`.slice(0, 200),
        },
      );
      await mutate(
        command.path.replace(`/analyses/${analysisId}`, `/analyses/${copy.id}`),
        1,
        command.payload,
        command.method,
      );
      applied = true;
      setCreatedCopy("");
      setNotice(
        "Your edit was saved in a separate conflict copy. The original analysis is unchanged.",
      );
    } catch (e) {
      if (copy) setCreatedCopy(copy.id);
      setError(
        `${(e as Error).message}${copy ? " The copy exists but the edit was not acknowledged; review it before applying again." : ""}`,
      );
    } finally {
      if (copy && applied) selectCopy(copy.id);
      setBusy(false);
    }
  }
  return (
    <section className="edit-toolbar panel" aria-label="Workspace edit state">
      <p role="status" aria-label="Save state">
        {saveLabel(edits)}
      </p>
      {analysisId && (
        <>
          <label>
            Analysis name (autosaves)
            <input
              value={loaded?.id === analysisId ? name : ""}
              maxLength={200}
              disabled={
                !loaded ||
                busy ||
                edits.phase === "conflict" ||
                edits.phase === "loading"
              }
              onChange={(e) => {
                setName(e.target.value);
                setError("");
              }}
            />
          </label>
          {dirty && !name.trim() && (
            <p role="alert">Enter a nonempty analysis name before autosave.</p>
          )}
          {dirty && (
            <button disabled={busy} onClick={() => setName(loaded!.name)}>
              Cancel name edit
            </button>
          )}
          <button
            disabled={
              busy ||
              !edits.history.length ||
              !!edits.dirty.length ||
              edits.phase !== "saved"
            }
            onClick={() => void undo()}
          >
            Undo last setup edit
          </button>
          <button
            disabled={busy}
            onClick={() => {
              resetEdits(analysisId);
              reload();
            }}
          >
            Reload saved workspace (discard drafts)
          </button>
          {edits.phase === "error" && (
            <button
              disabled={busy}
              onClick={() => {
                // Retrying is deliberate. The original If-Match still protects an ambiguous response.
                if (!edits.pending) return;
                const c = edits.pending;
                setBusy(true);
                void mutate(c.path, c.revision, c.payload, c.method)
                  .then(() => reload())
                  .catch((e: Error) => setError(e.message))
                  .finally(() => setBusy(false));
              }}
            >
              Retry unacknowledged edit
            </button>
          )}
          {edits.phase === "conflict" && (
            <div className="confirmation">
              <p>
                Another session changed this analysis. Reload discards local
                drafts; duplicate saves the rejected edit against your
                previously observed setup in a separate analysis.
              </p>
              <button
                disabled={busy || !edits.pending}
                onClick={() => void duplicate()}
              >
                Duplicate my conflicting edit
              </button>
              {!edits.pending && (
                <p>
                  No rejected command is available to duplicate. Reload the
                  saved workspace.
                </p>
              )}
            </div>
          )}
        </>
      )}
      {createdCopy && (
        <button
          disabled={busy}
          onClick={() => {
            selectCopy(createdCopy);
            setCreatedCopy("");
          }}
        >
          Open created copy (discard rejected draft)
        </button>
      )}
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      <small>
        Engineering drafts require explicit review and Apply/Save. Undo covers
        the last 50 acknowledged setup commands in this session; reload,
        analysis switches and geometry changes clear it.
      </small>
    </section>
  );
}
