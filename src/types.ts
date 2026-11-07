export interface Env {
  DB: D1Database;
  AI: Ai;
  TITAN_API_BASE?: string;
  TITAN_API_KEY?: string;
  TITAN_MODEL?: string;
  TITAN_FALLBACK_MODEL?: string;
  TITAN_PROVIDER_TIMEOUT_MS?: string;
  TITAN_ADMIN_TOKEN?: string;
  TITAN_AUTH_MAP_B64?: string;
  TITAN_KNOWLEDGE_CONTEXT_LIMIT?: string;
}
export type ChatMessage = { role: "system" | "user" | "assistant"; content: string };
