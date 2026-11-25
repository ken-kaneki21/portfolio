"""Reproduce the synthetic Job Intelligence retrieval comparison offline."""
import argparse
from collections import Counter
from datetime import datetime, UTC
import hashlib
import json
from math import log, log2
import os
from pathlib import Path
import re
import subprocess
import sys
from time import perf_counter
from types import SimpleNamespace

import numpy as np
import psutil

HERE=Path(__file__).resolve().parent
CONFIG=HERE/'retrieval-v1.json'

def tokens(s):
    return re.findall(r'[a-z0-9]+',s.lower())

def bm25(query,corpus):
    docs=[Counter(tokens(text)) for text in corpus]
    sizes=[sum(doc.values()) for doc in docs]
    mean=sum(sizes)/len(docs)
    idf={t:log(1+(len(docs)-sum(t in d for d in docs)+.5)/(sum(t in d for d in docs)+.5))
         for t in set(tokens(query))}
    return [sum(idf[t]*d[t]*2.2/(d[t]+1.2*(.25+.75*n/mean)) for t in idf if t in d)
            for d,n in zip(docs,sizes)]

def norm(values):
    low,high=min(values),max(values)
    return [(v-low)/(high-low) if high!=low else 0 for v in values]

def metrics(ids,grades,denials,k=5):
    ranking=ids[:k]
    def gain(items):return sum((2**g-1)/log2(i+2) for i,g in enumerate(items))
    ideal=gain(sorted(grades.values(),reverse=True)[:k])
    relevant={i for i,g in grades.items() if g>=2}
    return {'ndcg_at_5':gain([grades[x] for x in ranking])/ideal,
            'recall_at_5':len(relevant.intersection(ranking))/len(relevant),
            'hard_violations_at_5':sum(x in denials for x in ranking),'returned_at_5':len(ranking)}

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--job-repo',type=Path,required=True)
    p.add_argument('--encoder',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    os.environ['HF_HUB_OFFLINE']='1'
    os.environ['TRANSFORMERS_OFFLINE']='1'
    os.environ.setdefault('OMP_NUM_THREADS','1')
    os.environ.setdefault('MKL_NUM_THREADS','1')
    sys.path.insert(0,str(a.job_repo.resolve()/'src'))
    before=psutil.Process().memory_info().rss
    import torch
    from sentence_transformers import SentenceTransformer
    from jobintel.ranking.scoring import rank_job
    from jobintel.profile.models import CandidateProfile
    torch.set_num_threads(1)
    t=perf_counter()
    model=SentenceTransformer(str(a.encoder),device='cpu',local_files_only=True)
    load_ms=(perf_counter()-t)*1000
    blob=CONFIG.read_bytes()
    config=json.loads(blob)
    groups={}
    for d in config['documents']:
        groups.setdefault(d['family'],set()).add(d['split'])
    assert all(len(x)==1 for x in groups.values())
    rows=[]
    for split in ('dev','test'):
        docs=[d for d in config['documents'] if d['split']==split]
        texts=[d['title']+' '+d['text'] for d in docs]
        t=perf_counter()
        vectors=model.encode(texts,normalize_embeddings=True,show_progress_bar=False,batch_size=16)
        index_ms=(perf_counter()-t)*1000
        for j,q in enumerate(config['queries']):
            profile=CandidateProfile(name=q['id'],target_titles=q['titles'],adjacent_titles=q['adjacent'],
                exclude_titles=['manager','director'],preferred_locations=['bengaluru'],
                allowed_countries=['india'],blocked_location_terms=['us only'],
                core_skills=q['skills'],secondary_skills=['git','docker'],
                max_preferred_experience_years=3,hard_max_experience_years=4)
            t=perf_counter()
            jobs=[rank_job(SimpleNamespace(title=d['title'],description=d['text'],department=None,
                         apply_url='https://example.invalid',location=d['location'],first_seen_at=datetime(2026,1,1,tzinfo=UTC)),
                         profile) for d in docs]
            gate_ms=(perf_counter()-t)*1000
            eligible={d['id'] for d,r in zip(docs,jobs) if r.eligible}
            denied={d['id'] for d in docs if d['denied']}
            grades={d['id']:0 if d['denied'] else d['relevance'][j] for d in docs}
            t=perf_counter()
            lexical=bm25(q['text'],texts); lexical_ms=(perf_counter()-t)*1000
            t=perf_counter()
            vec=model.encode([q['text']],normalize_embeddings=True,show_progress_bar=False)[0]
            dense=(vectors@vec).tolist(); dense_ms=(perf_counter()-t)*1000
            t=perf_counter()
            blend=[.5*l+.5*d for l,d in zip(norm(lexical),norm(dense))]
            blend_ms=(perf_counter()-t)*1000
            methods={'deterministic':([r.deterministic_score for r in jobs],0),
                     'bm25':(lexical,lexical_ms),'dense':(dense,dense_ms),
                     'hybrid':(blend,lexical_ms+dense_ms+blend_ms)}
            for method,(scores,score_ms) in methods.items():
                t=perf_counter()
                ranked=sorted(zip(docs,scores),key=lambda ds:(-ds[1],ds[0]['id']))
                raw=[d['id'] for d,_ in ranked]; ids=[i for i in raw if i in eligible]
                sort_ms=(perf_counter()-t)*1000
                rows.append({'split':split,'query':q['id'],'method':method,'metrics':metrics(ids,grades,denied),
                    'raw_violations_at_5':sum(i in denied for i in raw[:5]),
                    'latency_ms':gate_ms+score_ms+sort_ms,'index_setup_ms_shared':index_ms,
                    'ranking':ids,'raw_ranking':raw,'grades':grades,'denied':sorted(denied),
                    'missed_relevant':[i for i,g in grades.items() if g>=2 and i not in ids[:5]],
                    'gate_rejections':{d['id']:list(r.rejection_reasons) for d,r in zip(docs,jobs) if not r.eligible}})
    scores={}
    for split in ('dev','test'):
        scores[split]={}
        for method in methods:
            group=[r for r in rows if r['split']==split and r['method']==method]
            scores[split][method]={k:sum(r['metrics'][k] for r in group)/len(group) for k in group[0]['metrics']}
            scores[split][method].update(query_samples=len(group),mean_observed_ms=sum(r['latency_ms'] for r in group)/len(group))
    best=max(scores['dev'],key=lambda m:(scores['dev'][m]['ndcg_at_5'],m=='deterministic'))
    incumbent=scores['test']['deterministic']
    chosen=best if (scores['test'][best]['ndcg_at_5']>incumbent['ndcg_at_5']+.02 and
        scores['test'][best]['hard_violations_at_5']<=incumbent['hard_violations_at_5']) else 'deterministic'
    report={'fixture_sha256':hashlib.sha256(blob).hexdigest(),'encoder_snapshot':a.encoder.name,
            'job_commit':subprocess.check_output(['git','-C',str(a.job_repo),'rev-parse','HEAD'],text=True).strip(),
            'torch':torch.__version__,'encoder_load_ms':load_ms,'rss_before_bytes':before,
            'rss_after_bytes':psutil.Process().memory_info().rss,'aggregates':scores,'rows':rows,
            'documents_by_split':dict(Counter(d['split'] for d in config['documents'])),
            'dev_winner':best,'decision':chosen,
            'decision_rule':'Preselect by development nDCG@5. On holdout require >0.02 nDCG lift and no increase in violations. Ties keep incumbent.',
            'limits':'Authored fully judged pools. Ground-truth ineligible rows have zero gain. No unjudged items, no external relevance labels, no latency percentiles.'}
    with a.out.open('x',encoding='utf-8') as output: json.dump(report,output,indent=2)
    print(json.dumps(scores,indent=2))
    print('Decision:',chosen)

if __name__=='__main__': main()
