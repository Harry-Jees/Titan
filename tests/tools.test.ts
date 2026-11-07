import { afterEach, describe, expect, it, vi } from "vitest";
import { encryptCredential, decryptCredential, validToolTarget, consumeDailyQuota } from "../src/tools";

afterEach(() => vi.unstubAllGlobals());

describe("registered API tool safety", () => {
  it("accepts only fixed public HTTPS targets", () => {
    expect(validToolTarget("https://api.example.org", "/v1/status")).toBe(true);
    for (const [base, path] of [
      ["http://api.example.org", "/v1/status"],
      ["https://localhost", "/status"],
      ["https://127.0.0.1", "/status"],
      ["https://api.example.org:8443", "/status"],
      ["https://api.example.org", "//evil.example/path"],
      ["https://api.example.org", "/v1/../admin"],
      ["https://user:pass@api.example.org", "/status"],
    ]) expect(validToolTarget(base, path)).toBe(false);
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
