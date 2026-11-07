import { describe, expect, it } from "vitest";
import { isAdmin, json, memoryScope, isPublicSourceUrl, readJson, RequestBodyError, issuePublicSession, consumePublicIpQuota } from "../src/security";

describe("security helpers", () => {
  it("requires the exact admin bearer token", () => {
    const env: any = { TITAN_ADMIN_TOKEN: "secret" };
    expect(isAdmin(new Request("https://titan.test", { headers: { authorization: "Bearer secret" } }), env)).toBe(true);
    expect(isAdmin(new Request("https://titan.test"), env)).toBe(false);
  });
  it("returns no-store JSON", async () => {
    const response = json({ ok: true });
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(response.headers.get("access-control-allow-origin")).toBe("*");
    expect(await response.json()).toEqual({ ok: true });
  });
  it("derives separate namespaces from bearer tokens", async () => {
    const env: any = {};
    const a = await memoryScope(new Request("https://titan.test", { headers: { authorization: `Bearer ${"a".repeat(40)}` } }), env);
    const b = await memoryScope(new Request("https://titan.test", { headers: { authorization: `Bearer ${"b".repeat(40)}` } }), env);
    expect(a).toBeTruthy();
    expect(a).not.toBe(b);
  });
  it("supports the existing Titan auth map and fails closed for unknown tokens", async () => {
    const token = "titan-token-abcdefghijklmnop";
    const env: any = { TITAN_AUTH_MAP_B64: btoa(JSON.stringify({ [token]: "user_42" })) };
    expect(await memoryScope(new Request("https://titan.test", { headers: { authorization: `Bearer ${token}` } }), env)).toBe("user_42");
    expect(await memoryScope(new Request("https://titan.test", { headers: { authorization: `Bearer ${"x".repeat(28)}` } }), env)).toBeNull();
  });
  it("rejects oversized JSON bodies before parsing", async () => {
    const request = new Request("https://titan.test", { method: "POST", body: JSON.stringify({ content: "x".repeat(100) }) });
    await expect(readJson(request, 20)).rejects.toThrow("Request body too large");
  });
  it("returns a client error for malformed JSON", async () => {
    const request = new Request("https://titan.test", { method: "POST", body: "{" });
    await expect(readJson(request)).rejects.toBeInstanceOf(RequestBodyError);
    await expect(readJson(new Request("https://titan.test", { method: "POST", body: "{" }))).rejects.toMatchObject({ status: 400 });
  });
  it("rejects weak tokens and unsafe source URLs", async () => {
    expect(await memoryScope(new Request("https://titan.test", { headers: { authorization: "Bearer weak" } }), {} as any)).toBeNull();
    expect(isPublicSourceUrl("https://example.com/article")).toBe(true);
    for (const url of ["javascript:alert(1)", "https://user:pass@example.com", "http://localhost", "http://127.0.0.1", "http://10.0.0.1", "http://example.com:8080"]) expect(isPublicSourceUrl(url)).toBe(false);
  });
  it("issues isolated anonymous public sessions without weakening legacy auth", async () => {
    let insertedTokenHash = "";
    const db: any = {
      prepare(sql: string) {
        return {
          run: async () => ({ meta: { changes: 0 } }),
          bind(...args: any[]) {
            return {
              run: async () => { if (sql.startsWith("INSERT INTO public_sessions")) insertedTokenHash = args[0]; return { meta: { changes: 1 } }; },
              first: async () => {
                if (sql.startsWith("INSERT INTO public_session_issuance")) return { sessions: 1 };
                if (sql.startsWith("SELECT user_id FROM public_sessions")) return { user_id: "public_isolated_1" };
                if (sql.startsWith("INSERT INTO public_ip_usage")) return { requests: 1 };
                return null;
              }
            };
          }
        };
      }
    };
    const env: any = { DB: db, TITAN_AUTH_MAP_B64: btoa(JSON.stringify({ existing: "legacy_user" })) };
    const issued = await issuePublicSession(new Request("https://titan.test/public/session", {
      method: "POST", headers: { "cf-connecting-ip": "203.0.113.10" }
    }), env);
    expect(issued.ok).toBe(true);
    if (!issued.ok) return;
    expect(issued.accessToken.startsWith("pub_")).toBe(true);
    expect(insertedTokenHash).toBeTruthy();
    const scope = await memoryScope(new Request("https://titan.test/chat", {
      headers: { authorization: "Bearer " + issued.accessToken }
    }), env);
    expect(scope).toBe("public_isolated_1");
    expect(await memoryScope(new Request("https://titan.test/chat", {
      headers: { authorization: "Bearer existing" }
    }), env)).toBe("legacy_user");
    expect(await consumePublicIpQuota(new Request("https://titan.test/chat", {
      headers: { "cf-connecting-ip": "203.0.113.10" }
    }), env)).toBe(true);
  });

  it("rejects anonymous session issuance without a Cloudflare client IP", async () => {
    const result = await issuePublicSession(new Request("https://titan.test/public/session", { method: "POST" }), {} as any);
    expect(result).toMatchObject({ ok: false, status: 503 });
  });

});
