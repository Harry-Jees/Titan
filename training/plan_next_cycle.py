#!/usr/bin/env python3
"""Create measurable next-cycle learning goals from corpus coverage gaps."""
import collections, json, re, time
from pathlib import Path
CORPUS = Path('training/crawled_pages.jsonl')
OUT = Path('training/next_learning_goals.json')
TOPICS = {
 'AI and machine learning': r'\b(ai|artificial intelligence|machine learning|neural|deep learning|llm|transformer|model training)\b',
 'Computer science and software': r'\b(software|programming|algorithm|database|operating system|compiler|api|developer)\b',
 'Cybersecurity and privacy': r'\b(security|cyber|cryptograph|privacy|vulnerability|threat|authentication)\b',
 'Mathematics and statistics': r'\b(math|mathemat|statistic|probability|calculus|algebra|theorem)\b',
 'Physics and space': r'\b(physics|quantum|particle|astronomy|space|nasa|cosmology)\b',
 'Biology and health science': r'\b(biology|biolog|genetic|medicine|health|clinical|cell|organism)\b',
 'Climate and environment': r'\b(climate|environment|ecology|energy|weather|ocean|biodiversity)\b',
 'Economics and finance': r'\b(econom|finance|market|inflation|trade|bank|fiscal|monetary)\b',
 'History, culture and philosophy': r'\b(history|historical|culture|philosophy|ethic|civilization|literature)\b',
 'Law, governance and society': r'\b(law|legal|policy|government|governance|society|rights|regulation)\b',
 'Education and learning science': r'\b(education|learning|pedagog|curriculum|teaching|school|university)\b',
 'Engineering and applied technology': r'\b(engineer|robot|electronics|manufactur|materials|architecture|infrastructure)\b',
}
def main():
    counts = collections.Counter(); domains = collections.Counter(); pages = 0
    if CORPUS.exists():
        with CORPUS.open(encoding='utf-8') as f:
            for line in f:
                try: item = json.loads(line)
                except Exception: continue
                pages += 1
                domain = re.sub(r'^www\.', '', __import__('urllib.parse').parse.urlparse(item.get('url','')).netloc)
                if domain: domains[domain] += 1
                text = (item.get('title','') + ' ' + item.get('text','')[:6000]).lower()
                matched = False
                for topic, pattern in TOPICS.items():
                    if re.search(pattern, text): counts[topic] += 1; matched = True
                if not matched: counts['Unclassified / cross-disciplinary'] += 1
    ranked = sorted(TOPICS, key=lambda t: counts[t])
    goals = [{'topic':topic,'goal':'Discover new high-quality primary sources and improve coverage with citations.',
              'success_metric':'At least 500 unique relevant pages if available; record source/date and deduplicate.','priority':'high'} for topic in ranked[:5]]
    goals += [
      {'topic':'Source diversity and freshness','goal':'Increase coverage across research, official documentation, educational resources and reputable reporting.','success_metric':'At least 10 distinct source domains and crawl dates where available.','priority':'high'},
      {'topic':'Knowledge quality','goal':'Create source-grounded Q&A examples from reviewed pages; preserve citations and uncertainty.','success_metric':'Evaluate held-out cases; never fine-tune on unreviewed raw crawl text.','priority':'high'}]
    queries = [{'topic':topic,'query':f'{topic} open-access research, official documentation and educational resources'} for topic in ranked[:5]]
    result={'generated_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'corpus_pages_seen':pages,'topic_counts':dict(counts),'top_domains':domains.most_common(25),'next_cycle_goals':goals,'next_cycle_search_queries':queries,'note':'Coverage counts are heuristic; queries are advisory until connected to a discovery provider.'}
    OUT.write_text(json.dumps(result,indent=2,ensure_ascii=False))
    print(json.dumps({'corpus_pages_seen':pages,'next_cycle_goals':len(goals),'output':str(OUT)}))
if __name__ == '__main__': main()
