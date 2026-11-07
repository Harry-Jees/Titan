import type { Env, ChatMessage } from "./types";

type Completion = { text: string; model: string };

class ProviderFailure extends Error {
  constructor(message: string, readonly fallbackAllowed: boolean) {
    super(message);
    this.name = "ProviderFailure";
  }
}

function textFrom(data: any): string | undefined {
  const content = data?.choices?.[0]?.message?.content;
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    const text = content.map(part => typeof part === "string" ? part : part?.text)
      .filter((part): part is string => typeof part === "string").join("");
    if (text) return text;
  }
  if (typeof data?.response === "string") return data.response;
  return undefined;
}

function timeoutMs(env: Env): number {
  const parsed = Number(env.TITAN_PROVIDER_TIMEOUT_MS || "20000");
  return Number.isFinite(parsed) ? Math.max(1000, Math.min(60000, Math.floor(parsed))) : 20000;
}

async function configuredProvider(env: Env, messages: ChatMessage[]): Promise<Completion> {
  const base = (env.TITAN_API_BASE || "").replace(/\/+$/, "");
  const model = env.TITAN_MODEL || "";
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs(env));
  try {
    const response = await fetch(`${base}/chat/completions`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: `Bearer ${env.TITAN_API_KEY}`
      },
      body: JSON.stringify({ model, messages, temperature: 0.2, max_tokens: 1200 }),
      signal: controller.signal
    });

    if (!response.ok) {
      const status = response.status;
      const fallbackAllowed = status === 408 || status === 425 || status === 429 || status >= 500;
      throw new ProviderFailure(`Configured model provider returned ${status}`, fallbackAllowed);
    }

    let data: any;
    try { data = await response.json(); }
    catch { throw new ProviderFailure("Configured model provider returned invalid JSON", true); }
    const text = textFrom(data);
    if (typeof text !== "string" || !text.trim())
      throw new ProviderFailure("Configured model provider returned no assistant text", true);
    return { text, model };
  } catch (error) {
    if (error instanceof ProviderFailure) throw error;
    throw new ProviderFailure("Configured model provider request failed or timed out", true);
  } finally {
    clearTimeout(timer);
  }
}

async function workersAiFallback(env: Env, messages: ChatMessage[]): Promise<Completion> {
  const model = env.TITAN_FALLBACK_MODEL || "@cf/zai-org/glm-4.7-flash";
  const result = await env.AI.run(model, { messages } as any) as any;
  const text = textFrom(result);
  if (typeof text !== "string" || !text.trim()) throw new Error("Workers AI returned no assistant text");
  return { text, model };
}

/** Primary OpenAI-compatible route with bounded timeout and safe Workers AI failover. */
export async function complete(env: Env, messages: ChatMessage[]): Promise<Completion> {
  const primaryConfigured = !!(env.TITAN_API_BASE && env.TITAN_API_KEY && env.TITAN_MODEL);
  let primaryFailure: ProviderFailure | undefined;

  if (primaryConfigured) {
    try { return await configuredProvider(env, messages); }
    catch (error) {
      if (!(error instanceof ProviderFailure)) throw new Error("Configured model provider failed");
      if (!error.fallbackAllowed) throw new Error(error.message);
      primaryFailure = error;
    }
  }

  try { return await workersAiFallback(env, messages); }
  catch {
    if (primaryFailure) throw new Error("Configured provider and Workers AI fallback both failed");
    throw new Error("Workers AI fallback failed");
  }
}
