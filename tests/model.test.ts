import { describe, expect, it } from "vitest";
import { complete } from "../src/model";

describe("Titan local-only inference boundary", () => {
  it("never calls Workers AI or a hosted model provider", async () => {
    let calls = 0;
    const env = {
      AI: { run: async () => { calls++; return { response: "should never run" }; } },
      TITAN_API_BASE: "https://provider.example/v1",
      TITAN_API_KEY: "test-only-key",
      TITAN_MODEL: "remote-model"
    } as any;
    await expect(complete(env, [{ role: "user", content: "hello" }]))
      .rejects.toThrow("No cloud model was called");
    expect(calls).toBe(0);
  });

  it("fails closed even when no local model runtime is configured", async () => {
    await expect(complete({} as any, [{ role: "user", content: "hello" }]))
      .rejects.toThrow("Titan's own local model is not connected yet");
  });
});
