#!/usr/bin/env python3
"""Resumable, robots-aware sitemap crawler with per-host pacing and bounded downloads."""
from __future__ import annotations
import gzip, hashlib, ipaddress, io, json, os, re, sys, time
from collections import deque
from pathlib import Path
from urllib.parse import urljoin, urlparse, urldefrag
import urllib.robotparser
import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup
try:
    from .crawler_policy import CrawlerConfig
    from .pinned_http import UnsafeCrawlerURL, mount_pinned_transport, safe_get
except ImportError:  # Direct script execution from the training directory.
    from crawler_policy import CrawlerConfig
    from pinned_http import UnsafeCrawlerURL, mount_pinned_transport, safe_get

ROOT=Path(__file__).resolve().parent
SEEDS=Path(os.getenv("TITAN_CRAWL_SEEDS",ROOT/"crawl_sources.txt"))
OUT=Path(os.getenv("TITAN_CRAWL_OUT",ROOT/"crawled_pages.jsonl"))
CYCLE_OUT=Path(os.getenv("TITAN_CYCLE_OUT",ROOT/"crawled_pages_cycle.jsonl"))
STATE=Path(os.getenv("TITAN_CRAWL_STATE",ROOT/"crawl_state.json"))
CONFIG=CrawlerConfig.from_env()
TARGET=CONFIG.page_target
TIMEOUT=CONFIG.fetch_timeout
PER_HOST_DELAY=CONFIG.per_host_delay
MAX_BYTES=CONFIG.max_page_bytes
CONTACT=os.getenv("TITAN_CRAWLER_CONTACT","").strip()
UA=os.getenv("TITAN_CRAWLER_UA",f"TitanKnowledgeBot/0.1 (+contact: {CONTACT})" if CONTACT else "TitanKnowledgeBot/0.1 (configure contact before large-scale crawling)")
SESSION=requests.Session()
mount_pinned_transport(SESSION, config=CONFIG)
SESSION.headers.update({"User-Agent":UA,"Accept":"text/html,application/xhtml+xml,application/xml,text/plain;q=0.8"})
ROBOTS:dict[str,urllib.robotparser.RobotFileParser]={}
LAST_HIT:dict[str,float]={}

# Sitemap documents are untrusted input. Bound both compressed and expanded
# data, parser work and discovered locations before adding URLs to the queue.
MAX_SITEMAP_EXPANDED_BYTES = 8_000_000
MAX_SITEMAP_COMPRESSION_RATIO = 20
MAX_SITEMAP_ELEMENTS = 100_000
MAX_SITEMAP_DEPTH = 32
MAX_SITEMAP_LOCATIONS = 5_000


class SitemapLimitError(ValueError):
    """Raised when an untrusted sitemap exceeds a parser resource limit."""


def _read_sitemap_payload(body: bytes, sitemap_url: str) -> bytes:
    """Read plain or gzip sitemap bytes without allowing unbounded expansion."""
    if sitemap_url.lower().split("?", 1)[0].endswith(".gz"):
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(body)) as stream:
                expanded = stream.read(MAX_SITEMAP_EXPANDED_BYTES + 1)
        except (OSError, EOFError, ValueError) as exc:
            raise SitemapLimitError("Invalid or unreadable compressed sitemap.") from exc
        if len(expanded) > MAX_SITEMAP_EXPANDED_BYTES:
            raise SitemapLimitError("Expanded sitemap exceeds the byte limit.")
        if len(expanded) > max(1, len(body)) * MAX_SITEMAP_COMPRESSION_RATIO:
            raise SitemapLimitError("Sitemap compression ratio exceeds the safety limit.")
        return expanded

    if len(body) > MAX_SITEMAP_EXPANDED_BYTES:
        raise SitemapLimitError("Sitemap exceeds the byte limit.")
    return body


def _sitemap_locations(
    body: bytes,
    sitemap_url: str,
    final_url: str,
    budget: int,
) -> tuple[list[str], list[str]]:
    """Extract same-origin page and nested-sitemap URLs with bounded XML work."""
    payload = _read_sitemap_payload(body, sitemap_url)
    origin = urlparse(sitemap_url).netloc
    pages: list[str] = []
    nested: list[str] = []
    depth = 0
    elements = 0
    location_limit = min(max(0, budget), MAX_SITEMAP_LOCATIONS)

    for event, element in ET.iterparse(io.BytesIO(payload), events=("start", "end")):
        if event == "start":
            depth += 1
            elements += 1
            if depth > MAX_SITEMAP_DEPTH:
                raise SitemapLimitError("Sitemap XML nesting exceeds the safety limit.")
            if elements > MAX_SITEMAP_ELEMENTS:
                raise SitemapLimitError("Sitemap XML element count exceeds the safety limit.")
            continue

        if element.tag.rsplit("}", 1)[-1].lower() == "loc" and element.text:
            link = clean_url(urljoin(final_url or sitemap_url, element.text.strip()))
            if link and urlparse(link).netloc == origin:
                filename = urlparse(link).path.rsplit("/", 1)[-1].lower()
                if filename.endswith(".xml") or "sitemap" in filename:
                    nested.append(link)
                else:
                    pages.append(link)
                if len(pages) + len(nested) >= location_limit:
                    break
        element.clear()
        depth -= 1

    return pages, nested

def public_url(value:str)->bool:
    try:
        p=urlparse(value); host=(p.hostname or "").lower().rstrip(".")
        if p.scheme not in {"http","https"} or not host or p.username or p.password: return False
        if p.port is not None and p.port != (443 if p.scheme == "https" else 80): return False
        if host=="localhost" or host.endswith((".localhost",".local",".internal",".lan",".home",".test",".invalid")): return False
        if not CONFIG.host_allowed(host): return False
        try: return ipaddress.ip_address(host).is_global
        except ValueError: return "." in host and not host.startswith(".") and not host.endswith(".")
    except ValueError: return False

def clean_url(value:str)->str:
    value,_=urldefrag(value.strip())
    if not public_url(value): return ""
    p=urlparse(value)
    return p._replace(fragment="",query="").geturl().rstrip("/")

def request_once(url:str):
    host=(urlparse(url).hostname or "").lower()
    wait=PER_HOST_DELAY-(time.monotonic()-LAST_HIT.get(host,0))
    if wait>0: time.sleep(wait)
    LAST_HIT[host]=time.monotonic()
    response=None
    try:
        # safe_get validates every redirect; the mounted adapter resolves and
        # pins the exact public address used for each TCP connection.
        response=safe_get(SESSION,url,timeout=TIMEOUT,stream=True,
                          max_redirects=5,same_host_redirects=True)
        if response.status_code!=200:
            code=response.status_code; response.close(); return None,None,code
        ctype=response.headers.get("content-type","").lower()
        if not any(x in ctype for x in ("text/html","application/xhtml+xml","application/xml","text/plain")):
            response.close(); return None,None,"non-text"
        length=response.headers.get("content-length")
        if length:
            try:
                if int(length)>MAX_BYTES:
                    response.close(); return None,None,"too-large"
            except ValueError:
                response.close(); return None,None,"invalid-content-length"
        chunks=[]; total=0
        for chunk in response.iter_content(65536):
            total+=len(chunk)
            if total>MAX_BYTES:
                response.close(); return None,None,"too-large"
            chunks.append(chunk)
        final=response.url
        response.close()
        return b"".join(chunks),final,200
    except (requests.RequestException,UnsafeCrawlerURL,ValueError,OSError) as exc:
        if response is not None: response.close()
        return None,None,type(exc).__name__

def allowed(url:str)->bool:
    p=urlparse(url); origin=f"{p.scheme}://{p.netloc}"
    if origin not in ROBOTS:
        parser=urllib.robotparser.RobotFileParser(); robots_url=origin+"/robots.txt"; parser.set_url(robots_url)
        body,_,status=request_once(robots_url)
        if body and status==200: parser.parse(body.decode("utf-8","ignore").splitlines())
        elif status==404: parser.parse([])
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
        try:
            pages, nested = _sitemap_locations(body, sitemap, final or sitemap, budget - len(found))
        except (ET.ParseError, SitemapLimitError, OSError, EOFError):
            continue
        found.extend(pages[:max(0, budget - len(found))])
        for link in nested:
            if len(queue) >= MAX_SITEMAP_LOCATIONS:
                break
            if link not in seen_maps and link not in queue:
                queue.append(link)
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
