import type { Env, ChatMessage } from "./types";
import { reserveAiNeurons } from "./ai-budget";
export type Completion = { text: string; model: string };
export type CompletionOptions = { bucket?: string; bucketLimit?: number; maxOutputTokens?: number; jsonMode?: boolean };

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
  const inputBytes = new TextEncoder().encode(messages.map(message=>message.content).join("\\n")).length;
  const bucket = options.bucket || "chat";
  const bucketLimit = options.bucketLimit ?? (bucket==="chat"?2000:3500);
  if (!await reserveAiNeurons(env,inputBytes,maxOutputTokens,bucket,bucketLimit))
    throw new Error("Titan reached its protected daily free-inference budget. No paid fallback was attempted.");
  const input:any={messages,max_tokens:maxOutputTokens,temperature:0.2};
  if(options.jsonMode)input.response_format={type:"json_object"};
  const result = await env.AI.run("@cf/openai/gpt-oss-20b",input) as any;
  const text = extractText(result);
  if (!text) throw new Error("GPT-OSS returned no text. Check Workers AI capacity and response format.");
  return {text,model:"@cf/openai/gpt-oss-20b"};
}
