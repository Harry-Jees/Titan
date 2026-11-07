import { describe, expect, it } from "vitest";
import { isAdmin, json, memoryScope, isPublicSourceUrl, readJson, RequestBodyError } from "../src/security";

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
});
