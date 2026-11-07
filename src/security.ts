import type { Env } from "./types";

export function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      "access-control-allow-origin": "*",
      "access-control-allow-methods": "GET, POST, DELETE, OPTIONS",
      "access-control-allow-headers": "Authorization, Content-Type, X-Titan-Cron",
      "access-control-max-age": "86400"
    }
  });
}

export function isAdmin(request: Request, env: Env): boolean {
  return !!env.TITAN_ADMIN_TOKEN && request.headers.get("authorization") === "Bearer " + env.TITAN_ADMIN_TOKEN;
}

async function sha256(value: string): Promise<string> {
  const hash = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return [...new Uint8Array(hash)].map(byte => byte.toString(16).padStart(2, "0")).join("");
}

function encodeBase64Url(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

async function ensurePublicTables(env: Env): Promise<void> {
  await env.DB.prepare("CREATE TABLE IF NOT EXISTS public_sessions (token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, expires_at TEXT NOT NULL)").run();
  await env.DB.prepare("CREATE TABLE IF NOT EXISTS public_session_issuance (ip_hash TEXT NOT NULL, day TEXT NOT NULL, sessions INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (ip_hash, day))").run();
  await env.DB.prepare("CREATE TABLE IF NOT EXISTS public_ip_usage (ip_hash TEXT NOT NULL, day TEXT NOT NULL, requests INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (ip_hash, day))").run();
  await env.DB.prepare("CREATE TABLE IF NOT EXISTS knowledge_chunks (id TEXT PRIMARY KEY, source_url TEXT NOT NULL, title TEXT NOT NULL, content TEXT NOT NULL, content_hash TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)").run();
  await env.DB.prepare("CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_created ON knowledge_chunks(created_at DESC)").run();
}

/** Create an anonymous, isolated visitor session without requiring account registration. */
export async function issuePublicSession(request: Request, env: Env): Promise<
  { ok: true; accessToken: string; expiresAt: string } |
  { ok: false; status: number; error: string }
> {
  const ip = request.headers.get("cf-connecting-ip") || "";
  if (!ip) return { ok: false, status: 503, error: "Public sessions require a Cloudflare client address." };
  await ensurePublicTables(env);
  const day = new Date().toISOString().slice(0, 10);
  const ipHash = await sha256("titan-public-ip:" + ip);
  const issued = await env.DB.prepare(
    "INSERT INTO public_session_issuance(ip_hash,day,sessions) VALUES(?,?,1) ON CONFLICT(ip_hash,day) DO UPDATE SET sessions=sessions+1 WHERE sessions < 8 RETURNING sessions"
  ).bind(ipHash, day).first<{ sessions: number }>();
  if (!issued) return { ok: false, status: 429, error: "This network has reached today's anonymous session limit. Please try again tomorrow." };

  const random = crypto.getRandomValues(new Uint8Array(32));
  const accessToken = "pub_" + encodeBase64Url(random);
  const tokenHash = await sha256("titan-public-session:" + accessToken);
  const userId = "public_" + crypto.randomUUID().replace(/-/g, "");
  const expiresAt = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString();
  await env.DB.prepare("INSERT INTO public_sessions(token_hash,user_id,expires_at) VALUES(?,?,?)")
    .bind(tokenHash, userId, expiresAt).run();
  return { ok: true, accessToken, expiresAt };
}

/** Per-network cap prevents unlimited session rotation from bypassing anonymous quotas. */
export async function consumePublicIpQuota(request: Request, env: Env): Promise<boolean> {
  const ip = request.headers.get("cf-connecting-ip") || "";
  if (!ip) return false;
  await ensurePublicTables(env);
  const ipHash = await sha256("titan-public-ip:" + ip);
  const day = new Date().toISOString().slice(0, 10);
  const row = await env.DB.prepare(
    "INSERT INTO public_ip_usage(ip_hash,day,requests) VALUES(?,?,1) ON CONFLICT(ip_hash,day) DO UPDATE SET requests=requests+1 WHERE requests < 60 RETURNING requests"
  ).bind(ipHash, day).first<{ requests: number }>();
  return !!row;
}

/** Hash bearer capabilities into isolated namespaces; never store raw tokens. */
export async function memoryScope(request: Request, env: Env): Promise<string | null> {
  const header = request.headers.get("authorization") || "";
  if (isAdmin(request, env)) return sha256("admin:" + header.slice(7));
  const match = header.match(/^Bearer\s+([A-Za-z0-9._~-]{24,512})$/i);
  if (!match) return null;
  const token = match[1];

  // Anonymous public sessions are random, revocable, time-limited capabilities.
  if (token.startsWith("pub_")) {
    try {
      await ensurePublicTables(env);
      const tokenHash = await sha256("titan-public-session:" + token);
      const row = await env.DB.prepare("SELECT user_id FROM public_sessions WHERE token_hash=? AND expires_at>CURRENT_TIMESTAMP")
        .bind(tokenHash).first<{ user_id: string }>();
      return row?.user_id || null;
    } catch {
      return null;
    }
  }

  // Optional compatibility with the existing Titan auth map. Unknown tokens fail closed.
  if (env.TITAN_AUTH_MAP_B64) {
    try {
      const map: unknown = JSON.parse(atob(env.TITAN_AUTH_MAP_B64));
      if (!map || typeof map !== "object" || Array.isArray(map)) return null;
      const userId = (map as Record<string, unknown>)[token];
      return typeof userId === "string" && /^[A-Za-z0-9_-]{1,80}$/.test(userId) ? userId : null;
    } catch {
      return null;
    }
  }

  if (token.length < 32) return null;
  return sha256("user:" + token);
}

/** Validate an attribution URL without fetching it; reject local/private literals. */
export function isPublicSourceUrl(value: string): boolean {
  let url: URL;
  try { url = new URL(value); } catch { return false; }
  if (url.protocol !== "https:" && url.protocol !== "http:") return false;
  if (url.username || url.password) return false;
  if (url.port && url.port !== "80" && url.port !== "443") return false;

  const host = url.hostname.toLowerCase().replace(/\.$/, "");
  if (!host || host === "localhost" || host.endsWith(".localhost") ||
      host.endsWith(".local") || host.endsWith(".internal") || host.endsWith(".lan")) return false;
  if (host.startsWith("[") || host.includes(":")) return false;
  if (/^\d+(?:\.\d+){0,3}$/.test(host)) {
    const parts = host.split(".").map(Number);
    if (parts.length !== 4 || parts.some(n => !Number.isInteger(n) || n < 0 || n > 255)) return false;
    const [a, b] = parts;
    if (a === 0 || a === 10 || a === 127 || a >= 224 ||
        (a === 100 && b >= 64 && b <= 127) ||
        (a === 169 && b === 254) ||
        (a === 172 && b >= 16 && b <= 31) ||
        (a === 192 && b === 168) ||
        (a === 192 && b === 0) ||
        (a === 198 && (b === 18 || b === 19))) return false;
  }
  return true;
}

export class RequestBodyError extends Error {
  constructor(message: string, readonly status: number) { super(message); this.name = "RequestBodyError"; }
}

export async function readJson<T = unknown>(request: Request, maxBytes = 20000): Promise<T> {
  const declared = Number(request.headers.get("content-length") || "0");
  if (Number.isFinite(declared) && declared > maxBytes) throw new RequestBodyError("Request body too large", 413);
  const body = await request.text();
  if (new TextEncoder().encode(body).length > maxBytes) throw new RequestBodyError("Request body too large", 413);
  try { return JSON.parse(body) as T; }
  catch { throw new RequestBodyError("Invalid JSON body", 400); }
}
