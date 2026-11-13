import type { Env } from "./types";
export type ResearchPage={url:string;canonicalUrl:string;title:string;text:string;contentHash:string;links:string[]};
export const RESEARCH_SEEDS=["https://arxiv.org/","https://docs.python.org/3/","https://developer.mozilla.org/","https://kubernetes.io/docs/","https://docs.github.com/","https://developers.cloudflare.com/","https://huggingface.co/docs","https://pytorch.org/docs/stable/","https://scikit-learn.org/stable/","https://www.tensorflow.org/learn","https://www.rfc-editor.org/","https://www.w3.org/TR/","https://www.nist.gov/","https://www.noaa.gov/","https://www.nasa.gov/","https://www.who.int/","https://www.worldbank.org/","https://ourworldindata.org/","https://plato.stanford.edu/","https://ocw.mit.edu/","https://www.britannica.com/"];
const USER_AGENT="TitanKnowledgeBot",MAX_BYTES=250_000,MAX_TEXT=8_000;
export function isSafePublicUrl(value:string):boolean{
 try{const u=new URL(value);if(!["http:","https:"].includes(u.protocol)||u.username||u.password)return false;if(u.port&&!["80","443"].includes(u.port))return false;
 const h=u.hostname.toLowerCase().replace(/\.$/,"");if(!h||h==="localhost"||h.endsWith(".localhost")||h.endsWith(".local")||h.endsWith(".internal")||h.endsWith(".lan"))return false;
 if(h.includes(":")||/^\d+(?:\.\d+){0,3}$/.test(h))return false;return h.includes(".")&&!h.startsWith(".")&&!h.endsWith(".");
 }catch{return false;}
}
export function normalizeResearchUrl(value:string,base?:string):string{
 try{const u=base?new URL(value,base):new URL(value);if(!isSafePublicUrl(u.href))return "";u.hash="";u.search="";u.username="";u.password="";return u.href.replace(/\/$/,"");}catch{return "";}
}
export function robotsAllows(body:string,path:string):boolean{
 const lines=body.split(/\r?\n/).map(x=>x.split("#",1)[0].trim()).filter(Boolean),groups:{agents:string[];rules:{allow:boolean;path:string}[]}[]=[];
 let current:{agents:string[];rules:{allow:boolean;path:string}[]}|null=null;
 for(const line of lines){const i=line.indexOf(":");if(i<0)continue;const key=line.slice(0,i).trim().toLowerCase(),value=line.slice(i+1).trim();
 if(key==="user-agent"){if(!current||current.rules.length){current={agents:[],rules:[]};groups.push(current);}current.agents.push(value.toLowerCase());}
 else if((key==="allow"||key==="disallow")&&current&&value)current.rules.push({allow:key==="allow",path:value});}
 const rules=groups.filter(g=>g.agents.some(a=>a==="*"||USER_AGENT.toLowerCase().includes(a))).flatMap(g=>g.rules);
 const matches=rules.filter(rule=>{const anchored=rule.path.endsWith("$"),pattern=anchored?rule.path.slice(0,-1):rule.path;const escaped=pattern.split("*").map(part=>part.replace(/[.+?^${}()|[\\]\\\\]/g,"\\\\ const rules=groups.filter(g=>g.agents.some(a=>a==="*"||USER_AGENT.toLowerCase().includes(a))).flatMap(g=>g.rules);
 const match=rules.filter(r=>path.startsWith(r.path)).sort((a,b)=>b.path.length-a.path.length);return !match.length||match[0].allow;")).join(".*");return new RegExp("^"+escaped+(anchored?"$":"")).test(path);}).sort((a,b)=>b.path.replace(/\\*/g,"").length-a.path.replace(/\\*/g,"").length||Number(b.allow)-Number(a.allow));
 return !matches.length||matches[0].allow;
}
function decodeEntities(s:string):string{return s.replace(/&nbsp;/gi," ").replace(/&amp;/gi,"&").replace(/&lt;/gi,"<").replace(/&gt;/gi,">").replace(/&quot;/gi,'"').replace(/&#39;/gi,"'").replace(/&#(\d+);/g,(_,n)=>String.fromCodePoint(Number(n))).replace(/&#x([0-9a-f]+);/gi,(_,n)=>String.fromCodePoint(parseInt(n,16)));}
function plainText(html:string):string{return decodeEntities(html.replace(/<\s*(script|style|noscript|svg|nav|footer|header|form|aside)[^>]*>[\s\S]*?<\/\s*\1\s*>/gi," ").replace(/<!--([\s\S]*?)-->/g," ").replace(/<[^>]+>/g," ").replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g," ").replace(/\s+/g," ")).trim();}
export function extractResearchPage(html:string,url:string):Omit<ResearchPage,"contentHash">|null{
 const titleMatch=html.match(/<title[^>]*>([\s\S]*?)<\/title>/i),title=titleMatch?plainText(titleMatch[1]).slice(0,400):"";
 const main=html.match(/<(main|article)[^>]*>([\s\S]*?)<\/\1\s*>/i),body=main?main[2]:html;
 const paragraphs=[...body.matchAll(/<(p|h1|h2|h3|li)[^>]*>([\s\S]*?)<\/\1\s*>/gi)].map(m=>({tag:m[1].toLowerCase(),text:plainText(m[2])})).filter(item=>item.text.length>35||/^h[1-3]$/.test(item.tag)).map(item=>item.text);
 const text=(paragraphs.length>=2?paragraphs.join("\n"):plainText(body)).slice(0,MAX_TEXT);if(text.length<250)return null;
 const links:string[]=[],seen=new Set<string>();for(const m of html.matchAll(/<a\b[^>]*href\s*=\s*["']([^"'#]+)["'][^>]*>/gi)){const link=normalizeResearchUrl(m[1],url);if(link&&link!==normalizeResearchUrl(url)&&!seen.has(link)){seen.add(link);links.push(link);if(links.length>=40)break;}}
 let canonicalUrl=normalizeResearchUrl(url);const canonical=html.match(/<link[^>]+rel=["']canonical["'][^>]+href=["']([^"']+)["']/i);if(canonical)canonicalUrl=normalizeResearchUrl(canonical[1],url)||canonicalUrl;
 return {url:normalizeResearchUrl(url),canonicalUrl,title,text,links};
}
async function sha256(value:string):Promise<string>{const hash=await crypto.subtle.digest("SHA-256",new TextEncoder().encode(value));return [...new Uint8Array(hash)].map(b=>b.toString(16).padStart(2,"0")).join("");}
async function robotsBody(env:Env,origin:string):Promise<string>{
 const cached=await env.DB.prepare("SELECT body FROM research_robots WHERE origin=? AND expires_at>CURRENT_TIMESTAMP").bind(origin).first<{body:string}>();if(cached)return cached.body;
 let body="User-agent: *\nDisallow: /";try{const r=await fetch(origin+"/robots.txt",{headers:{"user-agent":USER_AGENT},redirect:"manual",signal:AbortSignal.timeout(8000)});if(r.status===404)body="User-agent: *\nAllow: /";else if(r.status===200)body=(await r.text()).slice(0,100000);}catch{/* fail closed */}
 await env.DB.prepare("INSERT INTO research_robots(origin,body,expires_at) VALUES(?,?,datetime('now','+1 day')) ON CONFLICT(origin) DO UPDATE SET body=excluded.body,expires_at=excluded.expires_at").bind(origin,body).run();return body;
}
export async function fetchResearchPage(env:Env,inputUrl:string):Promise<ResearchPage|null>{
 const url=normalizeResearchUrl(inputUrl);if(!url||!isSafePublicUrl(url))return null;const parsed=new URL(url),policy=await robotsBody(env,parsed.origin);if(!robotsAllows(policy,parsed.pathname))return null;
 let response:Response;try{response=await fetch(url,{headers:{"user-agent":USER_AGENT,"accept":"text/html,application/xhtml+xml"},redirect:"manual",signal:AbortSignal.timeout(12000)});}catch{return null;}
 if(response.status!==200||response.headers.get("content-type")?.toLowerCase().includes("html")!==true){response.body?.cancel();return null;}
 if(Number(response.headers.get("content-length")||"0")>MAX_BYTES){response.body?.cancel();return null;}if(!response.body)return null;
 const reader=response.body.getReader(),chunks:Uint8Array[]=[];let total=0;while(true){const part=await reader.read();if(part.done)break;total+=part.value.length;if(total>MAX_BYTES){await reader.cancel();return null;}chunks.push(part.value);}
 const bytes=new Uint8Array(total);let offset=0;for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.length;}
 const extracted=extractResearchPage(new TextDecoder().decode(bytes),response.url||url);if(!extracted)return null;return {...extracted,contentHash:await sha256(extracted.text)};
}
