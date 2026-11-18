#!/usr/bin/env python3
"""Resumable, robots-aware sitemap crawler with per-host pacing and bounded downloads."""
from __future__ import annotations
import gzip, hashlib, ipaddress, io, json, os, re, sys, time, zlib
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
MAX_TOTAL_BYTES=CONFIG.max_total_bytes
MAX_RUN_SECONDS=CONFIG.max_run_seconds
MAX_HOSTS=CONFIG.max_hosts_per_run
RECRAWL_INTERVAL=CONFIG.recrawl_interval_seconds
MAX_QUEUE_SIZE=CONFIG.max_queue_size
TOTAL_BYTES=0
STARTED_AT=time.monotonic()
REQUESTED_HOSTS:set[str]=set()
BUDGET_EXHAUSTED=False

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
        except (OSError, EOFError, ValueError, zlib.error) as exc:
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
    if budget <= 0:
        return [], []
    payload = _read_sitemap_payload(body, final_url or sitemap_url)
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


def build_frontier(
    discovered_urls,
    state: dict,
    *,
    now: float | None = None,
    refresh_interval_seconds: int | None = None,
    max_queue_size: int | None = None,
):
    """Resume pending URLs, prioritize new discoveries, then refresh stale pages."""
    current_time = time.time() if now is None else now
    refresh_after = RECRAWL_INTERVAL if refresh_interval_seconds is None else refresh_interval_seconds
    queue_limit = MAX_QUEUE_SIZE if max_queue_size is None else max_queue_size
    seen = {clean_url(url) for url in state.get("seen_urls", []) if isinstance(url, str)}
    last_crawled = state.get("last_crawled_at", {})
    if not isinstance(last_crawled, dict):
        last_crawled = {}

    queue = deque()
    queued: set[str] = set()

    def add(value: str) -> None:
        normalized = clean_url(value)
        if normalized and normalized not in queued and len(queue) < queue_limit:
            queue.append(normalized)
            queued.add(normalized)

    pending = state.get("remaining_queue", [])
    if isinstance(pending, list):
        for value in pending:
            if isinstance(value, str):
                add(value)

    for value in discovered_urls:
        normalized = clean_url(value) if isinstance(value, str) else ""
        if normalized and normalized not in seen:
            add(normalized)

    stale = []
    for url in seen:
        if not url or url in queued:
            continue
        try:
            last_seen = float(last_crawled.get(url, 0))
        except (TypeError, ValueError):
            last_seen = 0
        if current_time - last_seen >= refresh_after:
            stale.append((last_seen, url))
    for _, url in sorted(stale):
        add(url)

    return queue


def request_once(url:str):
    global TOTAL_BYTES, BUDGET_EXHAUSTED

    if BUDGET_EXHAUSTED or time.monotonic() - STARTED_AT >= MAX_RUN_SECONDS:
        BUDGET_EXHAUSTED = True
        return None, None, "budget-exhausted"
    if TOTAL_BYTES >= MAX_TOTAL_BYTES:
        BUDGET_EXHAUSTED = True
        return None, None, "budget-exhausted"

    host=(urlparse(url).hostname or "").lower()
    if host and host not in REQUESTED_HOSTS:
        if len(REQUESTED_HOSTS) >= MAX_HOSTS:
            BUDGET_EXHAUSTED = True
            return None, None, "budget-exhausted"
        REQUESTED_HOSTS.add(host)

    wait=PER_HOST_DELAY-(time.monotonic()-LAST_HIT.get(host,0))
    if wait>0:
        if time.monotonic() - STARTED_AT + wait >= MAX_RUN_SECONDS:
            BUDGET_EXHAUSTED = True
            return None, None, "budget-exhausted"
        time.sleep(wait)
    LAST_HIT[host]=time.monotonic()
    response=None
    try:
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
            if time.monotonic() - STARTED_AT >= MAX_RUN_SECONDS:
                response.close()
                BUDGET_EXHAUSTED=True
                return None,None,"budget-exhausted"
            total+=len(chunk)
            if total>MAX_BYTES:
                response.close(); return None,None,"too-large"
            if TOTAL_BYTES+len(chunk)>MAX_TOTAL_BYTES:
                response.close()
                BUDGET_EXHAUSTED=True
                return None,None,"budget-exhausted"
            TOTAL_BYTES+=len(chunk)
            chunks.append(chunk)
        final=response.url
        response.close()
        return b"".join(chunks),final,200
    except (requests.RequestException,UnsafeCrawlerURL,ValueError,OSError) as exc:
        if response is not None: response.close()
        return None,None,type(exc).__name__

def allowed(url:str)->bool:
    if BUDGET_EXHAUSTED: return False
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
                        if link and urlparse(link).netloc==p.netloc and len(queue)<MAX_SITEMAP_LOCATIONS: queue.append(link)
        else: queue.append(candidate)
    seen_maps=set(); found=[]
    while queue and len(found)<budget and len(seen_maps)<500 and not BUDGET_EXHAUSTED:
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
    state={"seen_urls":[],"seen_hashes":[],"last_crawled_at":{},"remaining_queue":[]}
    if STATE.exists():
        try:
            loaded=json.loads(STATE.read_text(encoding="utf-8"))
            if isinstance(loaded,dict): state.update(loaded)
        except (OSError,ValueError):
            print("Ignoring unreadable crawler checkpoint; starting with a bounded fresh frontier.",file=sys.stderr)

    seen_urls=set(state.get("seen_urls",[]))
    seen_hashes=set(state.get("seen_hashes",[]))
    last_crawled_at=dict(state.get("last_crawled_at",{})) if isinstance(state.get("last_crawled_at",{}),dict) else {}
    discovered=[]
    per_seed=max(100,min(5000,TARGET//max(1,len(seeds))*3))
    for seed in seeds:
        if BUDGET_EXHAUSTED: break
        if not public_url(seed): continue
        discovered.extend(sitemap_urls(seed,per_seed))

    queue=build_frontier(discovered,state,now=time.time())
    OUT.parent.mkdir(parents=True,exist_ok=True); CYCLE_OUT.parent.mkdir(parents=True,exist_ok=True)
    fetched_count=0
    new_count=0
    with OUT.open("a",encoding="utf-8") as corpus,CYCLE_OUT.open("w",encoding="utf-8") as cycle:
        while queue and fetched_count<TARGET and not BUDGET_EXHAUSTED:
            url=queue.popleft()
            if not allowed(url): continue
            body,final,status=request_once(url)
            if status=="budget-exhausted": break
            if not body or status!=200 or not final: continue

            seen_urls.add(url)
            last_crawled_at[url]=time.time()
            fetched_count+=1
            item=extract(url,body,final)
            if not item or item["content_sha256"] in seen_hashes:
                continue
            seen_hashes.add(item["content_sha256"])
            line=json.dumps(item,ensure_ascii=False)+"\n"
            corpus.write(line); corpus.flush(); cycle.write(line); cycle.flush(); new_count+=1
            if fetched_count%100==0:
                print(f"Fetched {fetched_count}/{TARGET}; new={new_count}; queue={len(queue)}")

    remaining=list(queue)
    summary={
        "fetched_pages":fetched_count,
        "new_pages":new_count,
        "target_pages":TARGET,
        "target_met":fetched_count>=TARGET,
        "unique_urls_seen":len(seen_urls),
        "unique_content_hashes":len(seen_hashes),
        "queue_remaining":len(remaining),
        "total_bytes":TOTAL_BYTES,
        "hosts_touched":len(REQUESTED_HOSTS),
        "budget_exhausted":BUDGET_EXHAUSTED,
    }
    STATE.write_text(json.dumps({
        "seen_urls":sorted(seen_urls),
        "seen_hashes":sorted(seen_hashes),
        "last_crawled_at":last_crawled_at,
        "last_run":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
        "fetched_pages":fetched_count,
        "new_pages":new_count,
        "target_pages":TARGET,
        "target_met":fetched_count>=TARGET,
        "remaining_queue":remaining,
        "total_bytes":TOTAL_BYTES,
        "hosts_touched":sorted(REQUESTED_HOSTS),
        "budget_exhausted":BUDGET_EXHAUSTED,
    }),encoding="utf-8")
    print(json.dumps(summary,sort_keys=True))
    if fetched_count<TARGET:
        print("Fetch target not met: source availability, robots rules, queue depth or an aggregate budget may constrain this cycle.",file=sys.stderr)


if __name__=="__main__":
    main()
