"""Robots-aware public-web exploration. Downloaded content is never executed."""
from __future__ import annotations
import argparse, ipaddress, json, logging, re, socket, time, urllib.robotparser
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from html import unescape
from pathlib import Path
from typing import Iterable
from urllib.parse import urldefrag, urljoin, urlparse, parse_qsl, urlencode
import requests
from bs4 import BeautifulSoup

LOG = logging.getLogger("titan.explorer")
USER_AGENT = "TitanResearchBot/0.1 (+https://github.com/Harry-Jees/Titan; public research crawler)"
MAX_SESSION_SECONDS, MAX_PAGE_BYTES, MAX_PAGES_HARD, MAX_TEXT_CHARS = 1800, 1_500_000, 1500, 18000
HOST_DELAY_SECONDS = 1.0
BLOCKED_SUFFIXES = (".zip",".exe",".dll",".bin",".dmg",".apk",".mp4",".mp3",".png",".jpg",".jpeg",".gif",".webp",".svg",".woff",".woff2",".ttf",".css",".js",".iso",".tar",".gz",".7z")
SENSITIVE_QUERY_KEYS = {"token","access_token","api_key","apikey","key","password","passwd","secret","session","auth","code"}
STOP_WORDS = set("the a an and or but if then than this that these those with from into about have has had was were are is be been being to of in on for by as at it its their they them we you your i our can could should would may might will not no yes".split())

class ExplorationError(RuntimeError): pass

@dataclass
class PageRecord:
    url: str
    title: str
    fetched_at: str
    status: int
    text: str
    summary: str
    keywords: list[str]
    links_found: int
    content_sha256: str

def _public_host(host: str) -> bool:
    if not host or host.lower() == "localhost" or host.lower().endswith((".localhost",".local",".internal")): return False
    try: addresses = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror: return False
    return bool(addresses) and all(ipaddress.ip_address(x[4][0].split("%")[0]).is_global for x in addresses)

def _clean_url(raw: str, base: str | None = None) -> str | None:
    try:
        absolute, _ = urldefrag(urljoin(base or "", raw.strip()))
        p = urlparse(absolute)
        if p.scheme not in {"http","https"} or not p.hostname or p.username or p.password or p.port not in (None,80,443): return None
        if p.path.lower().endswith(BLOCKED_SUFFIXES): return None
        query = urlencode([(k,v) for k,v in parse_qsl(p.query,keep_blank_values=True) if k.lower() not in SENSITIVE_QUERY_KEYS])
        return p._replace(netloc=p.hostname.lower(),query=query,fragment="").geturl()[:2048]
    except (ValueError,TypeError): return None

def _extract_keywords(text: str, limit: int = 12) -> list[str]:
    counts: dict[str,int] = {}
    for w in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}",text.lower()):
        if w not in STOP_WORDS and len(w)<=40: counts[w]=counts.get(w,0)+1
    return [w for w,_ in sorted(counts.items(),key=lambda x:(-x[1],x[0]))[:limit]]

def _summarize(text: str, max_sentences: int = 4) -> str:
    sentences=re.split(r"(?<=[.!?])\\s+",re.sub(r"\\s+"," ",text).strip())
    return " ".join(s.strip() for s in sentences if len(s.strip())>=45][:max_sentences])[:1200]

class AutonomousExplorer:
    def __init__(self, output_dir="titan-exploration", duration_seconds=1800, max_pages=500, timeout_seconds=15, host_delay=1.0):
        if not 1<=duration_seconds<=MAX_SESSION_SECONDS: raise ValueError("duration_seconds must be between 1 and 1800")
        if not 1<=max_pages<=MAX_PAGES_HARD: raise ValueError(f"max_pages must be between 1 and {MAX_PAGES_HARD}")
        self.output_dir=Path(output_dir); self.duration_seconds=duration_seconds; self.max_pages=max_pages
        self.timeout_seconds=timeout_seconds; self.host_delay=max(.5,host_delay)
        self.session=requests.Session(); self.session.trust_env=False
        self.session.headers.update({"User-Agent":USER_AGENT,"Accept":"text/html,application/xhtml+xml;q=0.9"})
        self.robots={}; self.last_host_request={}; self.visited=set(); self.queued=set(); self.frontier=deque(); self.records=[]
        self.started=0.0; self.stop_reason="time_limit"
    def _remaining(self): return max(0.0,self.duration_seconds-(time.monotonic()-self.started))
    def _enqueue(self,url):
        clean=_clean_url(url)
        if clean and clean not in self.visited and clean not in self.queued: self.frontier.append(clean); self.queued.add(clean)
    def _robots_allowed(self,url):
        p=urlparse(url); origin=f"{p.scheme}://{p.netloc}"
        if origin not in self.robots:
            parser=urllib.robotparser.RobotFileParser(); parser.set_url(origin+"/robots.txt")
            try:
                r=self.session.get(parser.url,timeout=min(8,self.timeout_seconds),allow_redirects=False)
                if r.status_code>=400: parser.parse([])
                elif len(r.content)<=256000: parser.parse(r.text.splitlines())
                else: return False
            except requests.RequestException: return False
            self.robots[origin]=parser
        return self.robots[origin].can_fetch(USER_AGENT,url)
    def _pace(self,host):
        elapsed=time.monotonic()-self.last_host_request.get(host,0)
        if elapsed<self.host_delay: time.sleep(min(self.host_delay-elapsed,self._remaining()))
        self.last_host_request[host]=time.monotonic()
    def _discover_seed(self):
        try:
            r=self.session.get("https://en.wikipedia.org/w/api.php",params={"action":"query","list":"random","rnnamespace":0,"rnlimit":1,"format":"json"},timeout=min(10,self.timeout_seconds)); r.raise_for_status()
            title=r.json()["query"]["random"][0]["title"]
            return _clean_url("https://en.wikipedia.org/wiki/"+requests.utils.quote(title.replace(" ","_"),safe="()_,"))
        except (requests.RequestException,ValueError,KeyError,IndexError) as e:
            LOG.warning("Seed discovery unavailable: %s",e); return None
    def _fetch(self,url):
        p=urlparse(url)
        if not _public_host(p.hostname or ""): LOG.info("Skipped non-public host: %s",p.hostname); return None,[]
        if not self._robots_allowed(url): LOG.info("Robots disallows or unavailable: %s",url); return None,[]
        self._pace(p.hostname or ""); response=None
        try:
            response=self.session.get(url,timeout=min(self.timeout_seconds,max(2,self._remaining())),allow_redirects=False,stream=True)
            if response.status_code in {301,302,303,307,308}:
                target=_clean_url(response.headers.get("Location",""),url); return None,[target] if target else []
            if response.status_code!=200 or not any(t in response.headers.get("Content-Type","").lower() for t in ("text/html","application/xhtml+xml")): return None,[]
            length=response.headers.get("Content-Length")
            if length and int(length)>MAX_PAGE_BYTES: return None,[]
            chunks=[]; size=0
            for chunk in response.iter_content(32768):
                if self._remaining()<=0: break
                size+=len(chunk)
                if size>MAX_PAGE_BYTES: return None,[]
                chunks.append(chunk)
            soup=BeautifulSoup(b"".join(chunks),"html.parser")
            for node in soup(["script","style","noscript","svg","canvas","form","iframe","nav","footer"]): node.decompose()
            title=(soup.title.get_text(" ",strip=True) if soup.title else "")[:300]
            main=soup.find("main") or soup.find("article") or soup.body or soup
            text=unescape(re.sub(r"\\s+"," ",main.get_text(" ",strip=True)))[:MAX_TEXT_CHARS]
            if len(text)<120: return None,[]
            links=[]
            for a in soup.find_all("a",href=True):
                target=_clean_url(a.get("href",""),response.url)
                if target and target not in self.visited: links.append(target)
            record=PageRecord(response.url,title or url,datetime.now(timezone.utc).isoformat(),200,text,_summarize(text),_extract_keywords(text),len(links),sha256(text.encode()).hexdigest())
            return record,links
        except (requests.RequestException,ValueError,OSError) as e: LOG.debug("Fetch failed %s: %s",url,e); return None,[]
        finally:
            if response is not None: response.close()
    def run(self,seeds: Iterable[str]=()):
        self.output_dir.mkdir(parents=True,exist_ok=True); self.started=time.monotonic()
        for seed in seeds: self._enqueue(seed)
        if not self.frontier:
            seed=self._discover_seed()
            if seed: self._enqueue(seed)
        if not self.frontier: raise ExplorationError("No seed available; supply --seed with a public URL")
        try:
            while self._remaining()>0 and len(self.records)<self.max_pages and self.frontier:
                url=self.frontier.popleft(); self.queued.discard(url)
                if url in self.visited: continue
                self.visited.add(url); record,links=self._fetch(url)
                if record:
                    self.records.append(record); self._write_record(record)
                    LOG.info("Explored %d/%d: %s",len(self.records),self.max_pages,record.title[:90])
                    for link in links: self._enqueue(link)
            if len(self.records)>=self.max_pages: self.stop_reason="page_limit"
            elif not self.frontier: self.stop_reason="frontier_exhausted"
        except KeyboardInterrupt: self.stop_reason="user_stopped"
        return self._write_manifest()
    def _write_record(self,record):
        with (self.output_dir/"pages.jsonl").open("a",encoding="utf-8") as f: f.write(json.dumps(asdict(record),ensure_ascii=False)+"\\n")
    def _write_manifest(self):
        elapsed=min(self.duration_seconds,max(0,time.monotonic()-self.started))
        manifest={"engine":"titan-autonomous-explorer","version":"0.1.0","started_at":datetime.fromtimestamp(time.time()-elapsed,timezone.utc).isoformat(),"finished_at":datetime.now(timezone.utc).isoformat(),"duration_seconds":round(elapsed,2),"configured_duration_seconds":self.duration_seconds,"pages_read":len(self.records),"unique_urls_attempted":len(self.visited),"frontier_remaining":len(self.frontier),"stop_reason":self.stop_reason,"robots_respected":True,"source_attribution":"Each page record includes its URL and SHA-256.","model_understanding":"Extractive summaries and keywords only; no model inference is invoked.","pages_file":"pages.jsonl"}
        (self.output_dir/"session.json").write_text(json.dumps(manifest,indent=2)+"\\n",encoding="utf-8"); return manifest

def main(argv=None):
    p=argparse.ArgumentParser(description="Explore the public web for up to 30 minutes.")
    p.add_argument("--minutes",type=float,default=30); p.add_argument("--seed",action="append",default=[]); p.add_argument("--max-pages",type=int,default=500); p.add_argument("--output",default="titan-exploration"); p.add_argument("--verbose",action="store_true")
    a=p.parse_args(argv)
    if not 0<a.minutes<=30: p.error("--minutes must be greater than 0 and no more than 30")
    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING,format="%(asctime)s %(levelname)s %(message)s")
    try: result=AutonomousExplorer(a.output,int(a.minutes*60),a.max_pages).run(a.seed)
    except ExplorationError as e: p.exit(2,f"Exploration could not start: {e}\\n")
    print(json.dumps(result,indent=2)); return 0
