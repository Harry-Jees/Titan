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
  return !!env.TITAN_ADMIN_TOKEN && request.headers.get("authorization") === `Bearer ${env.TITAN_ADMIN_TOKEN}`;
}

/** Hash bearer capabilities into isolated namespaces; never store raw tokens. */
export async function memoryScope(request: Request, env: Env): Promise<string | null> {
  const header = request.headers.get("authorization") || "";
  if (isAdmin(request, env)) {
    const bytes = new TextEncoder().encode(`admin:${header.slice(7)}`);
    const hash = await crypto.subtle.digest("SHA-256", bytes);
    return [...new Uint8Array(hash)].map(b => b.toString(16).padStart(2, "0")).join("");
  }
  const match = header.match(/^Bearer\s+([A-Za-z0-9._~-]{24,512})$/i);
  if (!match) return null;
  const token = match[1];

  // Optional compatibility with the live Titan auth map. Unknown tokens fail closed.
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
  const bytes = new TextEncoder().encode(`user:${token}`);
  const hash = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(hash)].map(b => b.toString(16).padStart(2, "0")).join("");
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

export async function readJson<T = unknown>(request: Request, maxBytes = 20000): Promise<T> {
  const declared = Number(request.headers.get("content-length") || "0");
  if (Number.isFinite(declared) && declared > maxBytes) throw new Error("Request body too large");
  const body = await request.text();
  if (new TextEncoder().encode(body).length > maxBytes) throw new Error("Request body too large");
  try { return JSON.parse(body) as T; }
  catch { throw new Error("Invalid JSON body"); }
}
