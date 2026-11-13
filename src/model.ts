import type { Env, ChatMessage } from "./types";
import { reserveAiNeurons } from "./ai-budget";
export type Completion = { text: string; model: string };
export type CompletionOptions = { bucket?: string; bucketLimit?: number; maxOutputTokens?: number };

function extractText(result: any): string {
  const content = result?.choices?.[0]?.message?.content ?? result?.response ?? result?.output_text;
  if (typeof content === "string") return content.trim();
  if (Array.isArray(content)) return content.map((part:any)=>typeof part==="string"?part:String(part?.text||"")).join("").trim();
  return "";
}

/** Titan's reasoning engine: OpenAI's open-weight GPT-OSS-20B through its Workers AI binding. */
export async function complete(env: Env, messages: ChatMessage[], options: CompletionOptions = {}): Promise<Completion> {
  if (!env.AI) throw new Error("Titan AI binding is missing. Deploy the Workers AI binding before using GPT-OSS.");
  const maxOutputTokens = Math.max(128,Math.min(2048,options.maxOutputTokens??1200));
  const inputCharacters = messages.reduce((sum,message)=>sum+message.content.length,0);
  const bucket = options.bucket || "chat";
  const bucketLimit = options.bucketLimit ?? (bucket==="chat"?2000:3500);
  if (!await reserveAiNeurons(env,inputCharacters,maxOutputTokens,bucket,bucketLimit))
    throw new Error("Titan reached its protected daily free-inference budget. No paid fallback was attempted.");
  const result = await env.AI.run("@cf/openai/gpt-oss-20b",{
    messages,max_tokens:maxOutputTokens,temperature:0.2,
  } as any) as any;
  const text = extractText(result);
  if (!text) throw new Error("GPT-OSS returned no text. Check Workers AI capacity and response format.");
  return {text,model:"@cf/openai/gpt-oss-20b"};
}
