import type { Env, ChatMessage } from "./types";

export type Completion = { text: string; model: string };

/**
 * Titan is deliberately fail-closed while its own local model runtime is being built.
 * Do not add Workers AI, hosted inference, or an automatic remote fallback here.
 * The eventual inference implementation must execute the Titan-owned model locally
 * (in the visitor's browser/device or on an explicitly self-hosted machine).
 */
export async function complete(_env: Env, _messages: ChatMessage[]): Promise<Completion> {
  throw new Error("Titan's own local model is not connected yet. No cloud model was called.");
}
