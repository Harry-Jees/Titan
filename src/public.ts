const PAGE = String.raw\`<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#111216">
<meta name="description" content="Titan — a public AI agent for thinking, research and getting things done.">
<title>Titan — Personal AI Agent</title>
<style>
:root{color-scheme:dark;--bg:#111216;--panel:#191a20;--panel2:#202129;--line:#30313a;--text:#f3f1ec;--muted:#a4a3ad;--accent:#c5b5ff;--accent2:#9f89f4;--good:#9dd8b0}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at 50% -20%,#29243b 0,transparent 55%),var(--bg);color:var(--text);font:15px/1.55 Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;min-height:100vh}
.shell{max-width:900px;margin:0 auto;min-height:100vh;display:flex;flex-direction:column;padding:0 22px}
header{height:72px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #ffffff12}
.brand{display:flex;align-items:center;gap:11px;font-weight:700;letter-spacing:.02em}.mark{width:34px;height:34px;border-radius:12px;background:linear-gradient(145deg,#d8cbff,#8b73e8);display:grid;place-items:center;color:#17131f;font-size:18px;font-weight:900;box-shadow:0 4px 24px #9f89f433}
.status{font-size:12px;color:var(--good);display:flex;align-items:center;gap:7px}.dot{width:7px;height:7px;border-radius:50%;background:var(--good);box-shadow:0 0 10px #9dd8b088}
main{flex:1;display:flex;flex-direction:column;width:100%;max-width:760px;margin:0 auto;padding:46px 0 22px}
.welcome{text-align:center;margin:16px 0 36px}.eyebrow{color:var(--accent);font-size:11px;letter-spacing:.2em;text-transform:uppercase;font-weight:700}.welcome h1{font-size:clamp(32px,6vw,48px);line-height:1.1;letter-spacing:-.045em;margin:12px 0}.welcome p{color:var(--muted);margin:0 auto;max-width:490px}
.suggestions{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin:0 0 26px}.suggestion{background:#ffffff06;border:1px solid var(--line);border-radius:14px;padding:13px 15px;color:#d5d2df;text-align:left;cursor:pointer;font:inherit;font-size:13px;transition:border-color .2s,background .2s}.suggestion:hover{border-color:#9582d9;background:#b5a4ff0c}
#messages{display:flex;flex-direction:column;gap:18px;margin:0 0 22px}.message{max-width:90%;padding:14px 16px;border-radius:17px;white-space:pre-wrap;overflow-wrap:anywhere}.user{align-self:flex-end;background:#39314f;border:1px solid #66588d;color:#fff;border-bottom-right-radius:5px}.assistant{align-self:flex-start;background:var(--panel);border:1px solid var(--line);border-bottom-left-radius:5px}.meta{font-size:11px;color:var(--muted);margin-top:9px}.sources{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}.sources a{font-size:11px;color:var(--accent);text-decoration:none;border:1px solid #51476b;border-radius:999px;padding:4px 9px}.sources a:hover{text-decoration:underline}
.composer{position:sticky;bottom:0;background:linear-gradient(180deg,transparent,var(--bg) 20%);padding:16px 0 12px}.composebox{background:var(--panel);border:1px solid #45434f;border-radius:18px;padding:10px;box-shadow:0 12px 40px #0005}.composebox:focus-within{border-color:#8d7bc7;box-shadow:0 0 0 3px #9b86ef20,0 12px 40px #0005}textarea{display:block;width:100%;resize:none;min-height:54px;max-height:180px;border:0;outline:0;background:transparent;color:var(--text);font:inherit;padding:8px 9px}textarea::placeholder{color:#85838e}.composefoot{display:flex;align-items:center;justify-content:space-between;padding:3px 4px 1px 9px}.hint{font-size:11px;color:#85838e}.send{border:0;border-radius:11px;background:var(--accent);color:#1a1722;font-weight:700;padding:9px 16px;cursor:pointer}.send:hover{background:#d4c8ff}.send:disabled{opacity:.45;cursor:wait}.bottom{display:flex;align-items:center;justify-content:space-between;color:#777681;font-size:11px;padding:10px 0 22px}.newchat{background:none;border:0;color:#bdb4dd;cursor:pointer;font:inherit}.newchat:hover{color:#fff}
@media(max-width:560px){.shell{padding:0 14px}main{padding-top:28px}.welcome{margin:18px 0 28px}.suggestions{grid-template-columns:1fr}.message{max-width:96%}.bottom{gap:12px;align-items:flex-start}.hint{max-width:220px}}
</style>
</head>
<body>
<div class="shell">
<header><div class="brand"><div class="mark">T</div><span>Titan</span></div><div class="status"><span class="dot"></span><span id="state">Connecting</span></div></header>
<main>
<section class="welcome" id="welcome"><div class="eyebrow">Your AI agent</div><h1>Think beyond<br>the obvious.</h1><p>Ask questions, explore ideas, research a topic or work through a problem. Titan is ready.</p></section>
<section class="suggestions" id="suggestions">
<button class="suggestion">Help me understand a difficult technical concept.</button>
<button class="suggestion">Research the latest developments in AI.</button>
<button class="suggestion">Help me plan and break down a project.</button>
<button class="suggestion">Review an idea and find its weak points.</button>
</section>
<section id="messages" aria-live="polite"></section>
<div class="composer"><div class="composebox"><textarea id="prompt" rows="2" placeholder="Message Titan…" aria-label="Message Titan"></textarea><div class="composefoot"><span class="hint">Enter to send · Shift + Enter for a new line</span><button class="send" id="send">Send ↗</button></div></div></div>
</main>
<footer class="bottom"><span>Anonymous session · Your chats stay in this browser session</span><button class="newchat" id="newchat">＋ New conversation</button></footer>
</div>
<script>
const $=id=>document.getElementById(id);
const tokenKey="titan.public.access.v1", conversationKey="titan.public.conversation.v1";
let token=localStorage.getItem(tokenKey)||"", conversationId=localStorage.getItem(conversationKey)||"", busy=false;
function setState(value){$("state").textContent=value}
async function bootstrap(force=false){
  if(token&&!force)return token;
  setState("Starting a private session");
  const response=await fetch("/public/session",{method:"POST"});
  const data=await response.json().catch(()=>({}));
  if(!response.ok||!data.accessToken)throw new Error(data.error||"Could not start a public session.");
  token=data.accessToken;localStorage.setItem(tokenKey,token);setState("Ready");return token;
}
function addMessage(role,text,model,sources){
  const node=document.createElement("article");node.className="message "+role;node.textContent=text;
  if(model||sources?.length){const meta=document.createElement("div");meta.className="meta";meta.textContent=model?"Titan · "+model:"";
    if(sources?.length){const links=document.createElement("div");links.className="sources";sources.forEach((source,i)=>{try{const url=new URL(source.url);if(!["https:","http:"].includes(url.protocol))return;const a=document.createElement("a");a.href=url.href;a.target="_blank";a.rel="noopener noreferrer";a.textContent=source.title||"Source "+(i+1);links.append(a)}catch{}});meta.append(links)}
    node.append(meta)}
  $("messages").append(node);node.scrollIntoView({behavior:"smooth",block:"end"});return node;
}
async function sendMessage(text){
  if(busy||!text.trim())return;busy=true;$("send").disabled=true;$("prompt").disabled=true;
  $("welcome").hidden=true;$("suggestions").hidden=true;addMessage("user",text.trim());const pending=addMessage("assistant","Thinking…");setState("Thinking");
  try{
    await bootstrap();
    let response=await fetch("/chat",{method:"POST",headers:{"content-type":"application/json","authorization":"Bearer "+token},body:JSON.stringify({message:text.trim(),conversationId:conversationId||undefined})});
    if(response.status===401){await bootstrap(true);response=await fetch("/chat",{method:"POST",headers:{"content-type":"application/json","authorization":"Bearer "+token},body:JSON.stringify({message:text.trim(),conversationId:conversationId||undefined})})}
    const data=await response.json().catch(()=>({}));
    if(!response.ok)throw new Error(data.error||"Titan could not complete that request.");
    pending.textContent=data.reply||"Titan returned an empty response.";
    if(data.model||data.sources?.length){const meta=document.createElement("div");meta.className="meta";meta.textContent=data.model?"Titan · "+data.model:"";if(data.sources?.length){const links=document.createElement("div");links.className="sources";data.sources.forEach((source,i)=>{try{const url=new URL(source.url);if(!["https:","http:"].includes(url.protocol))return;const a=document.createElement("a");a.href=url.href;a.target="_blank";a.rel="noopener noreferrer";a.textContent=source.title||"Source "+(i+1);links.append(a)}catch{}});meta.append(links)}pending.append(meta)}
    if(data.conversationId){conversationId=data.conversationId;localStorage.setItem(conversationKey,conversationId)}
    setState("Ready");
  }catch(error){pending.textContent=error instanceof Error?error.message:"Unexpected error";setState("Connection issue")}
  finally{busy=false;$("send").disabled=false;$("prompt").disabled=false;$("prompt").focus()}
}
$("send").addEventListener("click",()=>{const text=$("prompt").value;$("prompt").value="";sendMessage(text)});
$("prompt").addEventListener("keydown",event=>{if(event.key==="Enter"&&!event.shiftKey){event.preventDefault();$("send").click()}});
$("suggestions").addEventListener("click",event=>{const button=event.target.closest("button");if(button){$("prompt").value=button.textContent;$("send").click()}});
$("newchat").addEventListener("click",()=>{if(busy)return;conversationId="";localStorage.removeItem(conversationKey);$("messages").replaceChildren();$("welcome").hidden=false;$("suggestions").hidden=false;$("prompt").focus()});
bootstrap().then(()=>setState("Ready")).catch(error=>setState(error.message));
</script>
</body>
</html>\`;
export function publicHome(): Response {
  return new Response(PAGE, {
    status: 200,
    headers: {
      "content-type": "text/html; charset=utf-8",
      "cache-control": "no-store",
      "x-content-type-options": "nosniff",
      "referrer-policy": "no-referrer",
      "content-security-policy": "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    }
  });
}
