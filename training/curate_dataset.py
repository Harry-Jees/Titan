"""Deterministic prefilter for source-grounded candidates; not a full safety guarantee."""
import json, re, sys
from pathlib import Path
src=Path(sys.argv[1] if len(sys.argv)>1 else 'training/cycle_candidates.jsonl')
dst=Path(sys.argv[2] if len(sys.argv)>2 else 'training/curated.jsonl')
seen=set(); accepted=rejected=0
secret_patterns=[r'(?i)api[_ -]?key\s*[:=]\s*\S{12,}',r'(?i)-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',r'\bsk-[A-Za-z0-9]{20,}\b']
with src.open(encoding='utf-8') as inp,dst.open('w',encoding='utf-8') as out:
    for line in inp:
        try: x=json.loads(line)
        except ValueError: rejected+=1; continue
        instruction=str(x.get('instruction','')).strip(); response=str(x.get('response','')).strip()
        source=str(x.get('source_url','')).strip(); quote=str(x.get('supporting_quote','')).strip()
        if len(instruction)<12 or len(response)<30 or len(response)>6000 or not source.startswith(('https://','http://')) or len(quote)<12:
            rejected+=1; continue
        combined=instruction+'\n'+response
        if any(re.search(p,combined) for p in secret_patterns): rejected+=1; continue
        key=re.sub(r'\W+',' ',instruction.lower()).strip()
        if key in seen: rejected+=1; continue
        seen.add(key); out.write(json.dumps(x,ensure_ascii=False)+'\n'); accepted+=1
print(f'Accepted {accepted}; rejected {rejected}. Source-grounding checks are heuristic, not proof of truth.')
if accepted < 20: raise SystemExit('Not enough curated examples to train.')
