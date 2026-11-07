#!/usr/bin/env python3
"""Resumable, robots-aware sitemap crawler with per-host pacing and bounded downloads."""
from __future__ import annotations
import gzip, hashlib, ipaddress, json, os, re, sys, time
from collections import deque
from pathlib import Path
from urllib.parse import urljoin, urlparse, urldefrag
import urllib.robotparser
import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parent
SEEDS=Path(os.getenv("TITAN_CRAWL_SEEDS",ROOT/"crawl_sources.txt"))
OUT=Path(os.getenv("TITAN_CRAWL_OUT",ROOT/"crawled_pages.jsonl"))
CYCLE_OUT=Path(os.getenv("TITAN_CYCLE_OUT",ROOT/"crawled_pages_cycle.jsonl"))
STATE=Path(os.getenv("TITAN_CRAWL_STATE",ROOT/"crawl_state.json"))
TARGET=max(1,int(os.getenv("TITAN_PAGE_TARGET","10000")))
TIMEOUT=int(os.getenv("TITAN_FETCH_TIMEOUT","20"))
PER_HOST_DELAY=max(1.0,float(os.getenv("TITAN_PER_HOST_DELAY","1.0")))
MAX_BYTES=min(4_000_000,max(100_000,int(os.getenv("TITAN_MAX_PAGE_BYTES","4000000"))))
CONTACT=os.getenv("TITAN_CRAWLER_CONTACT","").strip()
UA=os.getenv("TITAN_CRAWLER_UA",f"TitanKnowledgeBot/0.1 (+contact: {CONTACT})" if CONTACT else "TitanKnowledgeBot/0.1 (configure contact before large-scale crawling)")
SESSION=requests.Session()
SESSION.headers.update({"User-Agent":UA,"Accept":"text/html,application/xhtml+xml,application/xml,text/plain;q=0.8"})
ROBOTS:dict[str,urllib.robotparser.RobotFileParser]={}
LAST_HIT:dict[str,float]={}

def public_url(value:str)->bool:
    try:
        p=urlparse(value); host=(p.hostname or "").lower().rstrip(".")
        if p.scheme not in {"http","https"} or not host or p.username or p.password: return False
        if p.port is not None and p.port not in {80,443}: return False
        if host=="localhost" or host.endswith((".localhost",".local",".internal",".lan")): return False
        try: return ipaddress.ip_address(host).is_global
        except ValueError: return "." in host and not host.startswith(".") and not host.endswith(".")
    except ValueError: return False

def clean_url(value:str)->str:
    value,_=urldefrag(value.strip())
    if not public_url(value): return ""
    p=urlparse(value)
    return p._replace(fragment="",query="").geturl().rstrip("/")

def request_once(url:str):
    host=urlparse(url).netloc
    wait=PER_HOST_DELAY-(time.monotonic()-LAST_HIT.get(host,0))
    if wait>0: time.sleep(wait)
    LAST_HIT[host]=time.monotonic()
    try:
        response=SESSION.get(url,timeout=TIMEOUT,stream=True,allow_redirects=False)
        # Redirects are not followed: each new host would need its own URL and robots check.
        if response.is_redirect:
            response.close(); return None,None,"redirect-skipped"
        if response.status_code!=200:
            code=response.status_code; response.close(); return None,None,code
        ctype=response.headers.get("content-type","").lower()
        if not any(x in ctype for x in ("text/html","application/xhtml+xml","application/xml","text/plain")):
            response.close(); return None,None,"non-text"
        chunks=[]; total=0
        for chunk in response.iter_content(65536):
            total+=len(chunk)
            if total>MAX_BYTES: response.close(); return None,None,"too-large"
            chunks.append(chunk)
        final=response.url; response.close()
        return b"".join(chunks),final,200
    except requests.RequestException as exc: return None,None,type(exc).__name__

def allowed(url:str)->bool:
    p=urlparse(url); origin=f"{p.scheme}://{p.netloc}"
    if origin not in ROBOTS:
        parser=urllib.robotparser.RobotFileParser(); robots_url=origin+"/robots.txt"; parser.set_url(robots_url)
        body,_,status=request_once(robots_url)
        if body and status==200: parser.parse(body.decode("utf-8","ignore").splitlines())
        else: parser.parse(["User-agent: *","Disallow: /"])
        ROBOTS[origin]=parser
    return ROBOTS[origin].can_fetch(UA,url)

def sitemap_urls(seed:str,budget:int)->list[str]:
    p=urlparse(seed); candidates=[seed.rstrip("/")+"/robots.txt",seed.rstrip("/")+"/sitemap.xml",f"{p.scheme}://{p.netloc}/sitemap.xml"]
    queue=deque()
    for candidate in candidates:
        if candidate.endswith("robots.txt"):
            body,_,status=request_once(candidate)
            if body and status==200:
                for line in body.decode("utf-8","ignore").splitlines():
                    if line.lower().startswith("sitemap:"):
                        link=clean_url(line.split(":",1)[1].strip())
                        if link and urlparse(link).netloc==p.netloc: queue.append(link)
        else: queue.append(candidate)
    seen_maps=set(); found=[]
    while queue and len(found)<budget and len(seen_maps)<500:
        sitemap=queue.popleft()
        if sitemap in seen_maps or not public_url(sitemap) or urlparse(sitemap).netloc!=p.netloc or not allowed(sitemap): continue
        seen_maps.add(sitemap); body,final,status=request_once(sitemap)
        if not body or status!=200: continue
        try: root=ET.fromstring(gzip.decompress(body) if sitemap.endswith(".gz") else body)
        except Exception:
            try: root=ET.fromstring(body)
            except Exception: continue
        for node in root.iter():
            if node.tag.rsplit("}",1)[-1].lower()!="loc" or not node.text: continue
            link=clean_url(urljoin(final or sitemap,node.text.strip()))
            if not link or urlparse(link).netloc!=p.netloc: continue
            if link.lower().endswith(".xml") or "sitemap" in link.lower().split("/")[-1]:
                if link not in seen_maps: queue.append(link)
            else:
                found.append(link)
                if len(found)>=budget: break
    return found

def extract(url:str,html:bytes,final_url:str):
    if not public_url(final_url): return None
    soup=BeautifulSoup(html,"html.parser")
    for tag in soup(["script","style","noscript","svg","nav","footer","header","form"]): tag.decompose()
    title=soup.title.get_text(" ",strip=True) if soup.title else ""
    canonical=soup.find("link",rel="canonical")
    canonical_url=clean_url(urljoin(final_url,canonical.get("href",""))) if canonical and canonical.get("href") else clean_url(final_url)
    main=soup.find("main") or soup.find("article") or soup.body or soup
    text=re.sub(r"\n{3,}","\n\n",main.get_text("\n",strip=True))
    text=re.sub(r"[ \t]+"," ",text).strip()
    if len(text)<300: return None
    return {"url":canonical_url or url,"source_url":url,"title":title[:500],"text":text[:250000],
            "content_sha256":hashlib.sha256(text.encode()).hexdigest(),
            "crawled_at":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
            "license_note":"Check source terms before reuse for training."}

def main():
    if not SEEDS.exists(): raise SystemExit(f"Seed list missing: {SEEDS}")
    seeds=[line.strip() for line in SEEDS.read_text(encoding="utf-8").splitlines() if line.strip() and not line.lstrip().startswith("#")]
    state={"seen_urls":[],"seen_hashes":[]}
    if STATE.exists():
        try: state.update(json.loads(STATE.read_text(encoding="utf-8")))
        except Exception: pass
    seen_urls=set(state.get("seen_urls",[])); seen_hashes=set(state.get("seen_hashes",[]))
    queue=deque()
    per_seed=max(100,min(5000,TARGET//max(1,len(seeds))*3))
    for seed in seeds:
        if not public_url(seed): continue
        for link in sitemap_urls(seed,per_seed):
            link=clean_url(link)
            if link and link not in seen_urls: queue.append(link)
    queue=deque(dict.fromkeys(queue))
    OUT.parent.mkdir(parents=True,exist_ok=True); CYCLE_OUT.parent.mkdir(parents=True,exist_ok=True)
    new_count=0
    with OUT.open("a",encoding="utf-8") as corpus,CYCLE_OUT.open("w",encoding="utf-8") as cycle:
        while queue and new_count<TARGET:
            url=queue.popleft()
            if url in seen_urls or not allowed(url): continue
            body,final,status=request_once(url); seen_urls.add(url)
            if not body or status!=200 or not final: continue
            item=extract(url,body,final)
            if not item or item["content_sha256"] in seen_hashes: continue
            seen_hashes.add(item["content_sha256"]); line=json.dumps(item,ensure_ascii=False)+"\n"
            corpus.write(line); corpus.flush(); cycle.write(line); cycle.flush(); new_count+=1
            if new_count%100==0: print(f"Processed {new_count}/{TARGET}; queue={len(queue)}")
    STATE.write_text(json.dumps({"seen_urls":sorted(seen_urls),"seen_hashes":sorted(seen_hashes),
        "last_run":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"new_pages":new_count,
        "target_pages":TARGET,"remaining_queue":list(queue)}),encoding="utf-8")
    print(json.dumps({"new_pages":new_count,"target_pages":TARGET,"target_met":new_count>=TARGET,
        "unique_urls_seen":len(seen_urls),"unique_content_hashes":len(seen_hashes),"queue_remaining":len(queue)}))
    if new_count<TARGET: print("Target not met: source availability, robots rules, pacing or runtime may constrain the cycle.",file=sys.stderr)

if __name__=="__main__": main()
