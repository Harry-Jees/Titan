import { afterEach, describe, expect, it, vi } from "vitest";
import { encryptCredential, decryptCredential, validToolTarget, consumeDailyQuota, consumePendingToolCall, provisionTool } from "../src/tools";

afterEach(() => vi.unstubAllGlobals());

describe("registered API tool safety", () => {
  it("accepts only fixed public HTTPS targets on an exact host allowlist", () => {
    const allowedHosts = new Set(["api.example.org"]);
    expect(validToolTarget("https://api.example.org", "/v1/status", allowedHosts)).toBe(true);
    for (const [base, path] of [
      ["http://api.example.org", "/v1/status"],
      ["https://localhost", "/status"],
      ["https://127.0.0.1", "/status"],
      ["https://api.example.org:8443", "/status"],
      ["https://api.example.org", "//evil.example/path"],
      ["https://api.example.org", "/v1/../admin"],
      ["https://user:pass@api.example.org", "/status"],
    ]) expect(validToolTarget(base, path, allowedHosts)).toBe(false);
    expect(validToolTarget("https://other.example.org", "/v1/status", allowedHosts)).toBe(false);
    expect(validToolTarget("https://api.example.org", "/v1/status", new Set())).toBe(false);
  });

  it("fails closed when the tool host allowlist is missing", async () => {
    const prepare = vi.fn();
    const result = await provisionTool({ DB: { prepare } } as any, "user-a", {
      name: "example_tool", description: "Read a status", method: "GET",
      baseUrl: "https://api.example.org", path: "/v1/status", allowedQuery: [], allowedBodyKeys: []
    });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.status).toBe(503);
    expect(prepare).not.toHaveBeenCalled();
  });

  it("consumes a pending approval with one atomic, user-scoped DELETE RETURNING", async () => {
    const row = { id: "12345678-abcd-1234-abcd-123456789abc", tool_name: "write_item",
      input_json: JSON.stringify({ item: "safe" }), tool_fingerprint: "f".repeat(64) };
    const first = vi.fn(async () => row);
    const bind = vi.fn(() => ({ first }));
    const prepare = vi.fn((_sql: string) => ({ bind }));
    const env: any = { DB: { prepare } };
    const result = await consumePendingToolCall(env, "scope-a", row.id);
    expect(prepare).toHaveBeenCalledOnce();
    expect(prepare.mock.calls[0][0]).toContain("DELETE FROM pending_tool_calls");
    expect(prepare.mock.calls[0][0]).toContain("RETURNING");
    expect(bind).toHaveBeenCalledWith(row.id, "scope-a");
    expect(result).toEqual({ id: row.id, name: "write_item", input: { item: "safe" }, fingerprint: row.tool_fingerprint });
  });

  it("encrypts and decrypts credentials with AES-GCM", async () => {
    const raw = new Uint8Array(32).fill(7);
    const env: any = { TITAN_VAULT_KEY_B64: btoa(String.fromCharCode(...raw)) };
    const encrypted = await encryptCredential(env, "private-test-credential");
    expect(encrypted.ciphertext).not.toContain("private-test-credential");
    expect(await decryptCredential(env, encrypted.ciphertext, encrypted.iv)).toBe("private-test-credential");
  });

  it("fails closed when the vault key is absent", async () => {
    await expect(encryptCredential({} as any, "secret")).rejects.toThrow("Vault key unavailable");
  });

  it("uses an atomic per-user daily quota statement", async () => {
    const first = vi.fn(async () => ({ requests: 1 }));
    const bind = vi.fn(() => ({ first }));
    const prepare = vi.fn((_sql: string) => ({ bind }));
    const env: any = { DB: { prepare } };
    expect(await consumeDailyQuota(env, "user-scope")).toBe(true);
    expect(prepare).toHaveBeenCalledOnce();
    expect(prepare).toHaveBeenCalledWith(expect.stringContaining("ON CONFLICT(user_id,day)"));
    expect(prepare).toHaveBeenCalledWith(expect.stringContaining("RETURNING requests"));
    expect(bind).toHaveBeenCalledWith("user-scope", expect.any(String), 200);
  });
});
