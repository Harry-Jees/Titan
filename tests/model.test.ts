import { afterEach, describe, expect, it, vi } from "vitest";
import { complete } from "../src/model";

afterEach(() => vi.unstubAllGlobals());

function env(overrides: Record<string, unknown> = {}) {
  return {
    AI: { run: vi.fn(async () => ({ response: "fallback answer" })) },
    TITAN_API_BASE: "https://provider.example/v1",
    TITAN_API_KEY: "test-key-not-real",
    TITAN_MODEL: "test-primary",
    TITAN_FALLBACK_MODEL: "test-fallback",
    ...overrides
  } as any;
}

describe("model routing", () => {
  it("uses configured primary on success", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ choices: [{ message: { content: "primary answer" } }] }), { status: 200 })));
    expect(await complete(env(), [{ role: "user", content: "hello" }])).toEqual({ text: "primary answer", model: "test-primary" });
  });
  it("fails over on retryable provider errors", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("unavailable", { status: 503 })));
    const e = env();
    expect(await complete(e, [{ role: "user", content: "hello" }])).toEqual({ text: "fallback answer", model: "test-fallback" });
    expect(e.AI.run).toHaveBeenCalledOnce();
  });
  it("does not mask invalid credentials", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("unauthorized", { status: 401 })));
    const e = env();
    await expect(complete(e, [{ role: "user", content: "hello" }])).rejects.toThrow("returned 401");
    expect(e.AI.run).not.toHaveBeenCalled();
  });
  it("uses Workers AI when no primary is configured", async () => {
    const e = env({ TITAN_API_BASE: undefined, TITAN_API_KEY: undefined, TITAN_MODEL: undefined });
    expect((await complete(e, [{ role: "user", content: "hello" }])).model).toBe("test-fallback");
  });
});
