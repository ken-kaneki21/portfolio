"""Freeze synthetic JD split families before any training or scoring."""
import argparse
import json
from pathlib import Path
import random

FAMILIES={
 'base':[
  ('heading','Requirements:\n{r}\nPreferred:\n{p}\nMinimum {n} years of experience.'),
  ('inline','Required: {r}. Preferred: {p}. At least {n} years of experience.'),
  ('bullets','Required skills:\n- {r}\nNice to have:\n- {p}\nMinimum {n} years of experience.')],
 'adapt':[
  ('priority','Must have: {r}. Desirable: {p}. Minimum of {n} years of experience.'),
  ('reverse','Nice to have: {p}. Required: {r}. At least {n} years of experience.')],
 'holdout':[
  ('prose','{p} is a plus. Candidates must know {r}. Minimum {n} years of experience.'),
  ('sections','Qualifications:\n{r}\nOptional:\n{p}\nExperience: {n} years.'),
  ('contrast','At least {n} years of experience. {r} is required. {p} is preferred.')]}
ROLES={'Data Engineer':['python','sql','dbt','airflow','spark'],
       'Backend Engineer':['python','fastapi','postgresql','docker','sql'],
       'AI Engineer':['python','fastapi','sql','docker','spark']}
COUNTS={'base':24,'adapt':18,'holdout':6}

def build():
    rows=[]
    for split,seed in [('base',89),('adapt',218),('holdout',617)]:
        rng=random.Random(seed)
        for family,template in FAMILIES[split]:
            used=set()
            while len(used)<COUNTS[split]:
                role=rng.choice(list(ROLES))
                required,preferred=rng.sample(ROLES[role],2)
                years=rng.randint(2,5)
                key=(required,preferred,years)
                if key in used: continue
                used.add(key)
                rows.append({'id':f'{family}-{len(used):02}','split':split,'family':family,
                    'title':role,'text':template.format(r=required,p=preferred,n=years),
                    'expected':{'required':[required],'preferred':[preferred],'min_years':years}})
    assert len({r['text'] for r in rows})==len(rows)
    return {'version':'synthetic-jd-extraction-v1','provenance':'Original synthetic assistant-authored inputs and labels. No external dataset or inherited dataset licence.',
            'split_seeds':{'base':89,'adapt':218,'holdout':617},'rows':rows}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    with a.out.open('x',encoding='utf-8') as f:json.dump(build(),f,indent=2)
