import { useEffect, useSyncExternalStore } from "react";

export type Command = {
  path: string;
  revision: number;
  payload: unknown;
  method: string;
};
type EditState = {
  id: string;
  revision: number;
  phase: "loading" | "saved" | "saving" | "error" | "conflict";
  dirty: string[];
  history: number[];
  pending: Command | null;
};
const initial: EditState = {
  id: "",
  revision: 0,
  phase: "loading",
  dirty: [],
  history: [],
  pending: null,
};
let state = initial;
const listeners = new Set<() => void>();
function update(next: EditState) {
  state = next;
  for (const listener of listeners) listener();
}
export function editSnapshot() {
  return state;
}
export function useEdits() {
  return useSyncExternalStore((listener) => {
    listeners.add(listener);
    return () => listeners.delete(listener);
  }, editSnapshot);
}
export function resetEdits(id: string, revision = 0) {
  update({ ...initial, id, revision, phase: revision ? "saved" : "loading" });
}
export function observeRevision(id: string, revision: number) {
  if (id !== state.id) return;
  if (!state.revision) update({ ...state, revision, phase: "saved" });
  else if (state.revision !== revision && state.phase !== "saving")
    invalidateEdits(id);
}
export function invalidateEdits(id: string) {
  if (id === state.id) update({ ...state, phase: "conflict", history: [] });
}
export function draft(key: string, dirty: boolean) {
  if (state.dirty.includes(key) === dirty) return;
  update({
    ...state,
    dirty: dirty
      ? [...state.dirty, key]
      : state.dirty.filter((item) => item !== key),
  });
}
export function useDraft(key: string, dirty: boolean) {
  useEffect(() => {
    draft(key, dirty);
    return () => draft(key, false);
  }, [key, dirty]);
}
export function tracked(command: Command) {
  const match = /^\/analyses\/([^/]+)(.*)$/.exec(command.path);
  return (
    !!match &&
    match[1] === state.id &&
    ((match[2] === "" && command.method === "PATCH") ||
      match[2] === "/display-units" ||
      /^\/materials\/[^/]+$/.test(match[2]) ||
      (match[2] === "/mesh-controls" && command.method === "PUT") ||
      /^\/loads(?:\/[^/]+(?:\/(?:faces|bodies|direction))?)?$/.test(match[2]))
  );
}
export function beginEdit(command: Command) {
  update({ ...state, phase: "saving", pending: command });
}
export function acknowledgeEdit(command: Command, revision: number) {
  if (!tracked(command)) return;
  update({
    ...state,
    revision,
    phase: "saved",
    pending: null,
    history: [...state.history, command.revision].slice(-50),
  });
}
export function failEdit(command: Command, conflict: boolean) {
  if (!tracked(command)) return;
  update({
    ...state,
    phase: conflict ? "conflict" : "error",
    pending: command,
    history: conflict ? [] : state.history,
  });
}
export function undoAcknowledged(revision: number) {
  update({
    ...state,
    revision,
    phase: "saved",
    history: state.history.slice(0, -1),
    pending: null,
  });
}
export function saveLabel(value: EditState) {
  if (value.phase === "loading")
    return value.id ? "Loading saved analysis…" : "No analysis selected";
  if (value.phase === "saving") return "Saving…";
  if (value.phase === "conflict")
    return "Conflict — edits were not saved. Reload or duplicate your edit.";
  if (value.phase === "error")
    return "Save failed — edits were not acknowledged. Retry or reload.";
  if (value.dirty.length) return "Unsaved edits — review and Apply, or Cancel.";
  return `Saved · revision ${value.revision}`;
}

export function assertDraftScope(command: Command) {
  const suffix = command.path.replace(/^\/analyses\/[^/]+/, "");
  const owner = suffix.startsWith("/materials/")
    ? "material"
    : suffix.startsWith("/loads")
      ? "loads"
      : suffix === "/mesh-controls"
        ? "mesh"
        : "analysis-name";
  const foreign = state.dirty.filter(
    (key) =>
      key !== owner && !(suffix === "/display-units" && key === "material"),
  );
  if (foreign.length)
    throw new Error(
      `Review and Apply/Save or Cancel the other unsaved drafts first: ${foreign.join(", ")}.`,
    );
}
