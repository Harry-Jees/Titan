import type { Env } from "./types";

export type ToolDefinition = {
  name: string;
  description: string;
  baseUrl: string;
  path: string;
  method: "GET" | "POST";
  allowedQuery: string[];
  allowedBodyKeys: string[];
  secretEnv?: string;
  secretHeader?: string;
  credential_ciphertext?: string | null;
  credential_iv?: string | null;
  credential_header?: string;
  source: "provisioned" | "server-config";
};

export type ToolResult = { ok: true; status: number; data: unknown } | { ok: false; error: string };

function allowedToolHosts(env: Env): Set<string> {
  const hosts = new Set<string>();
  for (const raw of (env.TITAN_TOOL_HOST_ALLOWLIST || "").split(",")) {
    const value = raw.trim();
    if (!value || /[/:@?#\\]/.test(value)) continue;
    try {
      const parsed = new URL("https://" + value);
      const host = parsed.hostname.toLowerCase().replace(/\.$/, "");
      const numeric = /^\d+(?:\.\d+){0,3}$/.test(host);
      if (parsed.port || parsed.pathname !== "/" || parsed.search || parsed.hash ||
          parsed.username || parsed.password || !host.includes(".") || numeric ||
          host.includes(":") || /(^|\.)(localhost|local|internal|test|invalid|example)$/.test(host)) continue;
      hosts.add(host);
    } catch {}
  }
  return hosts;
}

function decodeBase64Url(value: string): Uint8Array {
  const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
  const padded = normalized + "=".repeat((4 - normalized.length % 4) % 4);
  const raw = atob(padded);
  return Uint8Array.from(raw, char => char.charCodeAt(0));
}
function encodeBase64Url(value: Uint8Array): string {
  let raw = "";
  for (const byte of value) raw += String.fromCharCode(byte);
  return btoa(raw).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
async function vaultKey(env: Env): Promise<CryptoKey> {
  const raw = decodeBase64Url(env.TITAN_VAULT_KEY_B64 || "");
  if (raw.length !== 32) throw new Error("Vault key unavailable");
  return crypto.subtle.importKey("raw", raw, { name: "AES-GCM" }, false, ["encrypt", "decrypt"]);
}
export async function encryptCredential(env: Env, value: string): Promise<{ ciphertext: string; iv: string }> {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const encrypted = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, await vaultKey(env), new TextEncoder().encode(value));
  return { ciphertext: encodeBase64Url(new Uint8Array(encrypted)), iv: encodeBase64Url(iv) };
}
export async function decryptCredential(env: Env, ciphertext: string, iv: string): Promise<string> {
  const plaintext = await crypto.subtle.decrypt({ name: "AES-GCM", iv: decodeBase64Url(iv) }, await vaultKey(env), decodeBase64Url(ciphertext));
  return new TextDecoder().decode(plaintext);
}

export function validToolTarget(baseUrl: unknown, path: unknown, allowedHosts: ReadonlySet<string> = new Set()): boolean {
  if (typeof baseUrl !== "string" || baseUrl.length > 300 || typeof path !== "string" ||
      path.length > 500 || !path.startsWith("/") || path.startsWith("//") ||
      path.includes("\\") || path.split("/").some(part => part === "." || part === "..")) return false;
  try {
    const base = new URL(baseUrl);
    const host = base.hostname.toLowerCase().replace(/\.$/, "");
    const numeric = /^\d+(?:\.\d+){0,3}$/.test(host);
    if (base.protocol !== "https:" || base.pathname !== "/" || base.search || base.hash ||
        base.username || base.password || base.port || !host.includes(".") || numeric ||
        host.includes(":") || /(^|\.)(localhost|local|internal|test|invalid|example)$/.test(host) ||
        !allowedHosts.has(host)) return false;
    const target = new URL(path, base);
    return target.origin === base.origin && target.pathname === path && !target.search && !target.hash;
  } catch { return false; }
}
function validKeys(value: unknown): value is string[] {
  return Array.isArray(value) && value.length <= 40 &&
    value.every(key => typeof key === "string" && /^[A-Za-z][A-Za-z0-9_.-]{0,63}$/.test(key)) &&
    new Set(value).size === value.length;
}
function parseServerTools(env: Env): Record<string, ToolDefinition> {
  try {
    const input = JSON.parse(env.TITAN_TOOL_REGISTRY || "{}");
    if (!input || typeof input !== "object" || Array.isArray(input)) return {};
    const output: Record<string, ToolDefinition> = {};
    const hosts = allowedToolHosts(env);
    for (const [name, value] of Object.entries(input)) {
      const item = value as any;
      if (!/^[a-z][a-z0-9_-]{1,63}$/.test(name) || !item ||
          !validToolTarget(item.baseUrl, item.path, hosts) || !["GET", "POST"].includes(item.method) ||
          typeof item.description !== "string" || item.description.length > 240 ||
          !validKeys(item.allowedQuery || []) || !validKeys(item.allowedBodyKeys || [])) continue;
      if (item.method === "GET" && (item.allowedBodyKeys || []).length) continue;
      if (item.method === "POST" && (item.allowedQuery || []).length) continue;
      const secretHeader = typeof item.secretHeader === "string" ? item.secretHeader.toLowerCase() : "authorization";
      if (!/^[a-z][a-z0-9-]{0,63}$/.test(secretHeader) ||
          ["host", "content-length", "cookie", "set-cookie", "proxy-authorization"].includes(secretHeader)) continue;
      const secretEnv = typeof item.secretEnv === "string" && item.secretEnv ? item.secretEnv : undefined;
      if (secretEnv && !/^TITAN_TOOL_SECRET_[A-Z0-9_]{1,48}$/.test(secretEnv)) continue;
      output[name] = { name, description: item.description, baseUrl: item.baseUrl, path: item.path,
        method: item.method, allowedQuery: item.allowedQuery || [], allowedBodyKeys: item.allowedBodyKeys || [],
        secretEnv, secretHeader, source: "server-config" };
    }
    return output;
  } catch { return {}; }
}

export async function listTools(env: Env, userId: string) {
  const rows = await env.DB.prepare("SELECT name,description,method,allowed_query,allowed_body_keys,credential_ciphertext FROM api_tools WHERE user_id=? ORDER BY name LIMIT 100")
    .bind(userId).all<any>();
  const provisioned = (rows.results || []).map(row => ({
    name: row.name, description: row.description, method: row.method,
    parameters: JSON.parse(row.method === "GET" ? row.allowed_query : row.allowed_body_keys),
    confirmationRequired: row.method === "POST", requiresCredential: !!row.credential_ciphertext, source: "provisioned"
  }));
  const provisionedNames = new Set(provisioned.map(tool => tool.name));
  const server = Object.values(parseServerTools(env)).filter(tool => !provisionedNames.has(tool.name)).map(tool => ({
    name: tool.name, description: tool.description, method: tool.method,
    parameters: tool.method === "GET" ? tool.allowedQuery : tool.allowedBodyKeys,
    confirmationRequired: tool.method === "POST", requiresCredential: !!tool.secretEnv, source: "server-config"
  }));
  return [...provisioned, ...server];
}

export async function provisionTool(env: Env, userId: string, body: any) {
  const name = body?.name;
  const description = typeof body?.description === "string" ? body.description.trim() : "";
  const method = body?.method;
  const hosts = allowedToolHosts(env);
  if (!hosts.size) return { ok: false as const, status: 503, error: "Tool provisioning is disabled until TITAN_TOOL_HOST_ALLOWLIST contains exact trusted hostnames." };
  if (typeof name !== "string" || !/^[a-z][a-z0-9_-]{1,63}$/.test(name) ||
      !description || description.length > 240 || !["GET", "POST"].includes(method) ||
      !validToolTarget(body.baseUrl, body.path, hosts) || !validKeys(body.allowedQuery || []) ||
      !validKeys(body.allowedBodyKeys || []) ||
      (method === "GET" && (body.allowedBodyKeys || []).length) ||
      (method === "POST" && (body.allowedQuery || []).length)) {
    return { ok: false as const, status: 400, error: "Invalid tool definition. Use a public HTTPS base URL, fixed absolute path, and only allowed GET query keys or POST body keys." };
  }
  if (body.credential !== undefined && (typeof body.credential !== "string" || body.credential.length > 4000))
    return { ok: false as const, status: 400, error: "Credential must be a string up to 4000 characters" };
  const header = typeof body.credentialHeader === "string" ? body.credentialHeader.toLowerCase() : "authorization";
  if (!/^[a-z][a-z0-9-]{0,63}$/.test(header) ||
      ["host", "content-length", "cookie", "set-cookie", "proxy-authorization"].includes(header))
    return { ok: false as const, status: 400, error: "Invalid credential header" };

  let ciphertext: string | null = null;
  let iv: string | null = null;
  if (typeof body.credential === "string" && body.credential.length) {
    try {
      const encrypted = await encryptCredential(env, body.credential);
      ciphertext = encrypted.ciphertext; iv = encrypted.iv;
    } catch {
      return { ok: false as const, status: 503, error: "Credential vault is not configured; set TITAN_VAULT_KEY_B64 as a Worker secret." };
    }
  } else if (body.credential === undefined) {
    const old = await env.DB.prepare("SELECT credential_ciphertext,credential_iv FROM api_tools WHERE user_id=? AND name=?")
      .bind(userId, name).first<any>();
    if (old) { ciphertext = old.credential_ciphertext; iv = old.credential_iv; }
  }

  await env.DB.prepare("INSERT INTO api_tools(id,user_id,name,description,base_url,path,method,allowed_query,allowed_body_keys,credential_ciphertext,credential_iv,credential_header,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(user_id,name) DO UPDATE SET description=excluded.description,base_url=excluded.base_url,path=excluded.path,method=excluded.method,allowed_query=excluded.allowed_query,allowed_body_keys=excluded.allowed_body_keys,credential_ciphertext=excluded.credential_ciphertext,credential_iv=excluded.credential_iv,credential_header=excluded.credential_header,updated_at=CURRENT_TIMESTAMP")
    .bind(crypto.randomUUID(), userId, name, description, body.baseUrl, body.path, method,
      JSON.stringify(body.allowedQuery || []), JSON.stringify(body.allowedBodyKeys || []),
      ciphertext, iv, header).run();
  return { ok: true as const, name, credentialStoredEncrypted: !!ciphertext };
}

export async function deleteTool(env: Env, userId: string, name: string) {
  if (!/^[a-z][a-z0-9_-]{1,63}$/.test(name)) return { ok: false, status: 400, error: "Valid tool name is required" };
  const result = await env.DB.prepare("DELETE FROM api_tools WHERE user_id=? AND name=?").bind(userId, name).run();
  return { ok: true, deleted: (result.meta.changes || 0) > 0 };
}

async function loadTool(env: Env, userId: string, name: string): Promise<ToolDefinition | null> {
  const row = await env.DB.prepare("SELECT * FROM api_tools WHERE user_id=? AND name=?").bind(userId, name).first<any>();
  if (row) return {
    name: row.name, description: row.description, baseUrl: row.base_url, path: row.path, method: row.method,
    allowedQuery: JSON.parse(row.allowed_query || "[]"), allowedBodyKeys: JSON.parse(row.allowed_body_keys || "[]"),
    credential_ciphertext: row.credential_ciphertext, credential_iv: row.credential_iv,
    credential_header: row.credential_header, source: "provisioned"
  };
  return parseServerTools(env)[name] || null;
}

async function fingerprintTool(tool: ToolDefinition): Promise<string> {
  const canonical = JSON.stringify({
    name: tool.name, description: tool.description, baseUrl: tool.baseUrl, path: tool.path, method: tool.method,
    allowedQuery: [...tool.allowedQuery].sort(), allowedBodyKeys: [...tool.allowedBodyKeys].sort(),
    secretEnv: tool.secretEnv || null, secretHeader: tool.secretHeader || null,
    credentialCiphertext: tool.credential_ciphertext || null, credentialIv: tool.credential_iv || null,
    credentialHeader: tool.credential_header || null
  });
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(canonical));
  return [...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2, "0")).join("");
}

export async function executeTool(env: Env, userId: string, name: string, input: unknown, confirmed = false, expectedFingerprint?: string): Promise<ToolResult> {
  const tool = await loadTool(env, userId, name);
  if (!tool) return { ok: false, error: "Tool is not registered" };
  if (expectedFingerprint !== undefined && await fingerprintTool(tool) !== expectedFingerprint)
    return { ok: false, error: "Tool definition changed after approval; prepare the action again." };
  if (tool.method === "POST" && !confirmed) return { ok: false, error: "POST tool requires explicit confirmation" };
  const args = input && typeof input === "object" && !Array.isArray(input) ? input as Record<string, unknown> : {};
  const base = new URL(tool.baseUrl);
  const url = new URL(tool.path, base);
  if (url.origin !== base.origin || url.pathname !== tool.path || !validToolTarget(tool.baseUrl, tool.path, allowedToolHosts(env)))
    return { ok: false, error: "Target rejected" };

  let body: string | undefined;
  if (tool.method === "GET") {
    const allow = new Set(tool.allowedQuery);
    for (const [key, value] of Object.entries(args)) {
      if (!allow.has(key) || !["string", "number", "boolean"].includes(typeof value))
        return { ok: false, error: "Unsupported query parameter" };
      url.searchParams.set(key, String(value).slice(0, 300));
    }
  } else {
    const allow = new Set(tool.allowedBodyKeys);
    if (Object.keys(args).length > 30 || Object.keys(args).some(key => !allow.has(key)) ||
        JSON.stringify(args).length > 8000) return { ok: false, error: "Unsupported or oversized body" };
    body = JSON.stringify(args);
  }

  const headers = new Headers({ accept: "application/json", "user-agent": "TitanAgent/1.0" });
  if (body) headers.set("content-type", "application/json");
  if (tool.secretEnv || tool.credential_ciphertext) {
    let secret: string | undefined;
    if (tool.secretEnv) secret = env[tool.secretEnv as keyof Env] as string | undefined;
    else if (tool.credential_ciphertext && tool.credential_iv) {
      try { secret = await decryptCredential(env, tool.credential_ciphertext, tool.credential_iv); }
      catch { return { ok: false, error: "Stored tool credential could not be decrypted" }; }
    }
    if (!secret) return { ok: false, error: "Tool credential is not configured" };
    const header = tool.secretEnv ? (tool.secretHeader || "authorization") : (tool.credential_header || "authorization");
    headers.set(header, header.toLowerCase() === "authorization" ? "Bearer " + secret : secret);
  }
  try {
    const response = await fetch(url, { method: tool.method, headers, body, redirect: "error", signal: AbortSignal.timeout(8000) });
    if (Number(response.headers.get("content-length") || 0) > 30000) return { ok: false, error: "Response too large" };
    const reader = response.body?.getReader();
    const chunks: Uint8Array[] = [];
    let total = 0;
    if (reader) {
      while (true) {
        const part = await reader.read();
        if (part.done) break;
        total += part.value.byteLength;
        if (total > 30000) { await reader.cancel(); return { ok: false, error: "Response too large" }; }
        chunks.push(part.value);
      }
    }
    const bytes = new Uint8Array(total);
    let offset = 0;
    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
    const raw = new TextDecoder().decode(bytes);
    let data: unknown;
    try { data = JSON.parse(raw); } catch { data = raw.slice(0, 30000); }
    if (!response.ok) return { ok: false, error: "External API returned status " + response.status };
    return { ok: true, status: response.status, data };
  } catch {
    return { ok: false, error: "External API failed or timed out" };
  }
}

export async function recordToolAudit(env: Env, userId: string, name: string, result: ToolResult) {
  await env.DB.prepare("INSERT INTO tool_audit(id,user_id,tool_name,status,success) VALUES(?,?,?,?,?)")
    .bind(crypto.randomUUID(), userId, name, result.ok ? result.status : null, result.ok ? 1 : 0).run();
}

export async function consumeDailyQuota(env: Env, userId: string): Promise<boolean> {
  const raw = Number(env.TITAN_DAILY_REQUEST_LIMIT || "200");
  const configured = Number.isFinite(raw) ? Math.max(1, Math.min(10000, Math.floor(raw))) : 200;
  const limit = userId.startsWith("public_") ? Math.min(configured, 30) : configured;
  const day = new Date().toISOString().slice(0, 10);
  const row = await env.DB.prepare("INSERT INTO usage_limits(user_id,day,requests) VALUES(?,?,1) ON CONFLICT(user_id,day) DO UPDATE SET requests=requests+1 WHERE requests < ? RETURNING requests")
    .bind(userId, day, limit).first<{ requests: number }>();
  return !!row;
}

export async function createPendingToolCall(env: Env, userId: string, name: string, input: Record<string, unknown>): Promise<string | null> {
  const tool = await loadTool(env, userId, name);
  if (!tool || tool.method !== "POST" || !validToolTarget(tool.baseUrl, tool.path, allowedToolHosts(env))) return null;
  const keys = Object.keys(input);
  if (keys.length > 30 || keys.some(key => !tool.allowedBodyKeys.includes(key)) || JSON.stringify(input).length > 8000) return null;
  const fingerprint = await fingerprintTool(tool);
  const id = crypto.randomUUID();
  await env.DB.prepare("INSERT INTO pending_tool_calls(id,user_id,tool_name,input_json,tool_fingerprint) VALUES(?,?,?,?,?)")
    .bind(id, userId, name, JSON.stringify(input), fingerprint).run();
  return id;
}

export async function consumePendingToolCall(env: Env, userId: string, id: string) {
  if (!/^[A-Za-z0-9_-]{8,80}$/.test(id)) return null;
  const row = await env.DB.prepare("DELETE FROM pending_tool_calls WHERE id=? AND user_id=? AND created_at>=datetime('now','-10 minutes') RETURNING id,tool_name,input_json,tool_fingerprint")
    .bind(id, userId).first<{ id: string; tool_name: string; input_json: string; tool_fingerprint: string }>();
  if (!row) return null;
  try {
    const input = JSON.parse(row.input_json);
    if (!input || typeof input !== "object" || Array.isArray(input)) return null;
    return { id: row.id, name: row.tool_name, input: input as Record<string, unknown>, fingerprint: row.tool_fingerprint };
  } catch { return null; }
}
