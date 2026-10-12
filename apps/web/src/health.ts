import type { paths } from "../../../packages/contracts/api";

export type Health =
  paths["/api/v1/health"]["get"]["responses"]["200"]["content"]["application/json"];

export async function getHealth(signal?: AbortSignal): Promise<Health> {
  const response = await fetch("/api/v1/health", { signal });
  if (!response.ok) throw new Error("API health request failed");
  const data: unknown = await response.json();
  if (
    typeof data !== "object" ||
    data === null ||
    !("status" in data) ||
    data.status !== "ok" ||
    !("service" in data) ||
    data.service !== "openfea-api" ||
    !("stage" in data) ||
    data.stage !== "bootstrap"
  )
    throw new Error("Invalid API health response");
  return { status: data.status, service: data.service, stage: data.stage };
}
