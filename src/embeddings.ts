import type { Env } from "./types";
import { reserveAiNeurons } from "./ai-budget";
export const EMBEDDING_MODEL = "@cf/baai/bge-m3";
export const EMBEDDING_DIMENSIONS = 1024;
export async function embedTexts(env:Env,texts:string[],bucket="chat",bucketLimit=2000):Promise<number[][]>{
 if(!texts.length)return [];
 if(!env.AI)throw new Error("Titan AI binding is missing; semantic embeddings are unavailable.");
 const length=texts.reduce((sum,text)=>sum+text.length,0);
 if(!await reserveAiNeurons(env,length,0,bucket,bucketLimit,true))throw new Error("Titan reached its protected daily embedding budget. No paid fallback was attempted.");
 const result=await env.AI.run(EMBEDDING_MODEL,{text:texts} as any) as any;
 const rows=result?.data??result?.embeddings??result?.vectors??result?.embedding;
 if(!Array.isArray(rows))throw new Error("Embedding model returned an unsupported response shape.");
 const vectors=Array.isArray(rows[0])?rows:[rows],normalized=vectors.map((row:unknown[])=>row.map(Number));
 if(normalized.length!==texts.length||normalized.some((v:number[])=>v.length!==EMBEDDING_DIMENSIONS||v.some(x=>!Number.isFinite(x))))
  throw new Error("Embedding model returned an unexpected vector count or dimension.");
 return normalized;
}
export function encodeVector(vector:number[]):string{
 const bytes=new Uint8Array(vector.length*4),view=new DataView(bytes.buffer);
 vector.forEach((value,index)=>view.setFloat32(index*4,value,true));
 let binary="";for(const byte of bytes)binary+=String.fromCharCode(byte);return btoa(binary);
}
export function decodeVector(encoded:string):number[]{
 const binary=atob(encoded);if(binary.length!==EMBEDDING_DIMENSIONS*4)return [];
 const bytes=Uint8Array.from(binary,c=>c.charCodeAt(0)),view=new DataView(bytes.buffer);
 return Array.from({length:EMBEDDING_DIMENSIONS},(_,i)=>view.getFloat32(i*4,true));
}
export function cosineSimilarity(a:number[],b:number[]):number{
 if(!a.length||a.length!==b.length)return 0;let dot=0,an=0,bn=0;
 for(let i=0;i<a.length;i++){dot+=a[i]*b[i];an+=a[i]*a[i];bn+=b[i]*b[i];}
 return an&&bn?dot/Math.sqrt(an*bn):0;
}
