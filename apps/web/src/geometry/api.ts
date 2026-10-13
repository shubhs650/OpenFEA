import type { components } from "../../../../packages/contracts/api";

export type Project = components["schemas"]["Project"];
export type Geometry = components["schemas"]["GeometryRevision"];
export type Display = components["schemas"]["GeometryDisplay"];
export type Inspection = components["schemas"]["GeometryImport"];
export type Upload = components["schemas"]["Upload"];
export type Analysis = components["schemas"]["Analysis"];
export type MaterialState = components["schemas"]["MaterialState"];
export type MaterialSnapshot = components["schemas"]["MaterialSnapshot"];
export type MaterialExample = components["schemas"]["MaterialExample"];
export type MaterialAssignment = components["schemas"]["MaterialAssignment"];
export type UnitPreset = components["schemas"]["UnitPreset"];
export type LoadState = components["schemas"]["LoadState"];
export type LoadMarker = components["schemas"]["LoadMarker"];
export type DeckExport = components["schemas"]["DeckExport"];
export type LocalJob = components["schemas"]["LocalJob"];
export type MeshPreview = components["schemas"]["MeshPreview"];
export type ResultView = components["schemas"]["ResultView"];
export class RequestError extends Error {
  constructor(
    message: string,
    public status: number,
    public code?: string,
  ) {
    super(message);
  }
}
let csrfToken = "";

export async function api<T>(
  path: string,
  method = "GET",
  payload?: unknown,
): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    method,
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
    body: payload === undefined ? undefined : JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok)
    throw new RequestError(
      data.message ?? "Request failed. Reload the local session.",
      response.status,
      data.code,
    );
  return data as T;
}

export async function mutate<T>(
  path: string,
  revision: number,
  payload?: unknown,
  method = "POST",
): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": csrfToken,
      "If-Match": `"${revision}"`,
    },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok)
    throw new RequestError(
      data.message ?? "This setup changed. Reload before saving.",
      response.status,
      data.code,
    );
  return data as T;
}

export async function session() {
  const result = await api<components["schemas"]["LocalSession"]>("/session");
  csrfToken = result.csrf_token;
  return result;
}

export async function submitJob(
  path: string,
  revision: number,
  key: string,
  payload: unknown,
): Promise<LocalJob> {
  const response = await fetch(`/api/v1${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": csrfToken,
      "If-Match": `"${revision}"`,
      "Idempotency-Key": key,
    },
    body: JSON.stringify(payload),
  });
  const result = await response.json();
  if (!response.ok)
    throw new RequestError(
      result.message ?? "Job submission failed.",
      response.status,
      result.code,
    );
  return result as LocalJob;
}

export async function upload(
  project: Project,
  file: File,
  progress: (percent: number) => void,
): Promise<Upload> {
  if (file.size === 0 || file.size > 16 * 1024 * 1024)
    throw new Error("Choose a STEP file up to 16 MiB.");
  const hash = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  const digest = Array.from(new Uint8Array(hash), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
  const ticket = await api<Upload>(
    `/projects/${project.id}/geometry-uploads`,
    "POST",
    { size_bytes: file.size, sha256: digest },
  );
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", `/api/v1/geometry-uploads/${ticket.id}/content`);
    xhr.setRequestHeader("X-CSRF-Token", csrfToken);
    xhr.setRequestHeader("Content-Type", "application/step");
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable)
        progress(Math.round((100 * event.loaded) / event.total));
    };
    xhr.onerror = () =>
      reject(new Error("Upload connection failed. Start a new upload."));
    xhr.onload = () => {
      const result = JSON.parse(xhr.responseText);
      if (xhr.status === 200) resolve(result as Upload);
      else reject(new Error(result.message ?? "Upload failed."));
    };
    xhr.send(file);
  });
}
