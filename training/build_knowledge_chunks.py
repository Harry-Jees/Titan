#!/usr/bin/env python3
"""Convert successful crawl pages into source-attributed bounded chunks without a teacher API."""
import hashlib, json, re, os
from pathlib import Path
PAGES = Path(os.getenv('TITAN_CYCLE_PAGES', 'training/crawled_pages_cycle.jsonl'))
OUT = Path(os.getenv('TITAN_KNOWLEDGE_CHUNKS', 'training/knowledge_chunks_cycle.jsonl'))
def main():
    if not PAGES.exists(): raise SystemExit(f'Cycle pages not found: {PAGES}')
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pages = chunks = 0
    with PAGES.open(encoding='utf-8') as src, OUT.open('w', encoding='utf-8') as dst:
        for line in src:
            try: page = json.loads(line)
            except ValueError: continue
            url = str(page.get('url') or '')
            text = re.sub(r'\s+', ' ', str(page.get('text') or '')).strip()
            if not url.startswith(('https://', 'http://')) or len(text) < 200: continue
            pages += 1
            for start in range(0, len(text), 2000):
                content = text[start:start + 2400].strip()
                if len(content) < 200: continue
                dst.write(json.dumps({'url':url,'title':str(page.get('title') or ''),'chunk':content,
                    'content_sha256':hashlib.sha256((url+'\n'+content).encode()).hexdigest(),
                    'crawled_at':page.get('crawled_at','')}, ensure_ascii=False)+'\n')
                chunks += 1
    print(json.dumps({'pages_converted':pages,'chunks_created':chunks,'output':str(OUT)}))
if __name__ == '__main__': main()
