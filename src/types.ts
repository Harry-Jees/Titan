export interface Env {
 DB: D1Database;
 AI: Ai;
 RESEARCH_WORKFLOW: { create(options:{id:string;params:{runId:string;scheduledAt:number;durationSeconds:number}}): Promise<unknown> };
 TITAN_ADMIN_TOKEN?:string;
 TITAN_AUTH_MAP_B64?:string;
 TITAN_TOOL_REGISTRY?:string;
 TITAN_TOOL_HOST_ALLOWLIST?:string;
 TITAN_VAULT_KEY_B64?:string;
 TITAN_DAILY_REQUEST_LIMIT?:string;
 TITAN_TRAINING_MODEL?:string;
 TITAN_TRAINING_CRON_SECRET?:string;
 TITAN_KNOWLEDGE_CONTEXT_LIMIT?:string;
}
export type ChatMessage={role:"system"|"user"|"assistant";content:string};
