import { afterEach, describe, expect, it, vi } from "vitest";
import { getHealth } from "./health";

afterEach(() => vi.unstubAllGlobals());
describe("API health client", () => {
  it("accepts the bootstrap health contract", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        Response.json({
          status: "ok",
          service: "openfea-api",
          stage: "bootstrap",
        }),
      ),
    );
    await expect(getHealth()).resolves.toEqual({
      status: "ok",
      service: "openfea-api",
      stage: "bootstrap",
    });
  });
  it("rejects failed HTTP responses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("", { status: 503 })),
    );
    await expect(getHealth()).rejects.toThrow("API health request failed");
  });
  it.each([
    null,
    {},
    { status: "ok", service: "another-api", stage: "bootstrap" },
    { status: "ok", service: "openfea-api", stage: "solver" },
  ])("rejects a malformed or unrelated response %j", async (body) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json(body)));
    await expect(getHealth()).rejects.toThrow("Invalid API health response");
  });
  it("propagates network failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new TypeError("network unavailable")),
    );
    await expect(getHealth()).rejects.toThrow("network unavailable");
  });
});
