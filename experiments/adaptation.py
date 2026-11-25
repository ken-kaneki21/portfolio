"""CPU baseline, prompted decoder and low-rank update on a frozen holdout."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import statistics
import sys
from time import perf_counter

import psutil
import torch
from torch.nn import functional as F
from tiny_decoder import Codec,Decoder,generate,read_model,target,template

ARCH={'width':48,'heads':4,'layers':2,'context':128}
RANK=4
SEED=1907

def digest(blob):return hashlib.sha256(blob).hexdigest()

def batches(rows,codec,few_shot=False):
    items=[]
    for i,row in enumerate(rows):
        example=rows[(i+7)%len(rows)] if few_shot and i%3==0 else None
        prompt=codec.encode(template(row,example))
        ids=prompt+codec.encode(target(row))+[2]
        targets=[-100]*(len(prompt)-1)+ids[len(prompt):]
        assert len(ids)<=ARCH['context'] and len(ids)-1==len(targets)
        items.append((ids[:-1],targets))
    return items

def train(model,items,steps,batch,lr,seed):
    rng=random.Random(seed)
    opt=torch.optim.AdamW((v for v in model.parameters() if v.requires_grad),lr=lr)
    rss=psutil.Process()
    trace=[];t=perf_counter();peak=0
    for step in range(steps):
        selected=rng.choices(items,k=batch)
        n=max(len(x) for x,_ in selected)
        x=torch.tensor([a+[0]*(n-len(a)) for a,_ in selected])
        y=torch.tensor([b+[-100]*(n-len(b)) for _,b in selected])
        f=model(x)
        loss=F.cross_entropy(f.flatten(0,1),y.flatten())
        opt.zero_grad(set_to_none=True)
        loss.backward()
        opt.step()
        if step==0 or (step+1)%25==0 or step+1==steps:
            trace.append({'step':step+1,'batch_loss':float(loss.detach())})
            peak=max(peak,rss.memory_info().rss)
    return {'elapsed_s':perf_counter()-t,'sampled_peak_process_rss_bytes':peak,'trace':trace}

def quality(raw,want):
    try:
        value=json.loads(raw)
    except (ValueError,TypeError):
        value=None
    valid=(isinstance(value,dict) and set(value)==set(want) and
           all(isinstance(value[k],list) and all(isinstance(a,str) for a in value[k])
               for k in ('required','preferred')) and type(value['min_years']) is int)
    if not valid: value={}
    result={k:(set(value[k])==set(want[k]) if k in value and isinstance(want[k],list)
               else value.get(k)==want[k]) for k in want}
    swaps=(len(set(value.get('required',[]))&set(want['preferred']))+
           len(set(value.get('preferred',[]))&set(want['required'])))
    return {'schema_valid':valid,'fields':result,'exact':valid and all(result.values()),'required_preferred_swaps':swaps}

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--fixture',type=Path,required=True)
    p.add_argument('--job-repo',type=Path,required=True)
    p.add_argument('--model-dir',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    a.model_dir.mkdir(parents=True,exist_ok=False)
    sys.path.insert(0,str(a.job_repo.resolve()/'src'))
    from jobintel.enrichment.extractor import extract_job_enrichment
    torch.manual_seed(SEED);torch.set_num_threads(1)
    fixture=a.fixture.read_bytes()
    rows=json.loads(fixture)['rows']
    splits={s:[r for r in rows if r['split']==s] for s in ('base','adapt','holdout')}
    families=[{r['family'] for r in v} for v in splits.values()]
    assert not any(x&y for i,x in enumerate(families) for y in families[i+1:])
    training=splits['base']
    codec=Codec.fit([template(r)+target(r) for r in training+splits['adapt']]+['example'])
    base=Decoder(len(codec.tokens),**ARCH)
    total=sum(v.numel() for v in base.parameters())
    params={'base_steps':450,'adapter_steps':160,'batch_size':12,'base_lr':.003,'adapter_lr':.008,
            'seed':SEED,'adapter_rank':RANK,'architecture':ARCH,'threads':1,'max_new':40}
    base_stats=train(base,batches(training,codec,True),450,12,.003,SEED)
    torch.save({'tokens':codec.tokens,'architecture':ARCH,'adapter_rank':RANK,'weights':base.state_dict()},a.model_dir/'base.pt')
    adapted,_=read_model(a.model_dir)
    adapted.add_lora(RANK)
    trainable=sum(v.numel() for v in adapted.parameters() if v.requires_grad)
    adapter_stats=train(adapted,batches(splits['adapt'],codec),160,12,.008,SEED+1)
    state={k:v for k,v in adapted.state_dict().items() if '.lora_' in k}
    torch.save(state,a.model_dir/'adapter.pt')
    reloaded,_=read_model(a.model_dir,True)
    probe=template(splits['adapt'][0])
    assert generate(adapted.eval(),codec,probe,40)==generate(reloaded,codec,probe,40)
    result=[]
    for row in splits['holdout']:
        for mode in ('deterministic','base','few_shot','lora'):
            t=perf_counter(); output_count=None
            if mode=='deterministic':
                v=extract_job_enrichment(title=row['title'],description=row['text'])
                raw=json.dumps({'required':[x.lower() for x in v.required_skills],
                                'preferred':[x.lower() for x in v.preferred_skills],'min_years':v.minimum_experience_years})
            else:
                model=reloaded if mode=='lora' else base.eval()
                raw,output_count=generate(model,codec,template(row,training[0] if mode=='few_shot' else None),40)
            result.append({'id':row['id'],'family':row['family'],'method':mode,'actual':raw,'expected':row['expected'],
                           'output_tokens':output_count,'latency_ms':(perf_counter()-t)*1000}|quality(raw,row['expected']))
    summary={}
    for mode in ('deterministic','base','few_shot','lora'):
        rs=[r for r in result if r['method']==mode]
        summary[mode]={'n':len(rs),'schema_valid':sum(r['schema_valid'] for r in rs),'exact':sum(r['exact'] for r in rs),
            'fields':{k:sum(r['fields'][k] for r in rs) for k in rs[0]['fields']},
            'required_preferred_swaps':sum(r['required_preferred_swaps'] for r in rs),
            'median_ms':statistics.median(r['latency_ms'] for r in rs)}
    report={'dataset_sha256':digest(fixture),'split_sizes':{k:len(v) for k,v in splits.items()},
       'split_sha256':{k:digest(json.dumps(v,sort_keys=True).encode()) for k,v in splits.items()},
       'base_model_revision':digest((a.model_dir/'base.pt').read_bytes()),
       'adapter_revision':digest((a.model_dir/'adapter.pt').read_bytes()),
       'tokenizer_revision':digest(json.dumps(codec.tokens).encode()),'vocab':len(codec.tokens),
       'base_model':'from-scratch synthetic causal decoder; no external pretrained weights',
       'torch':torch.__version__,'total_base_parameters':total,'adapter_trainable_parameters':trainable,
       'settings':params,'base_training':base_stats,'adapter_training':adapter_stats,'adapter_reload_match':True,
       'scope':'CPU synthetic extraction holdout. Required/preferred swaps count when a valid schema predicts opposite labels. No deployment.',
       'summary':summary,'rows':result}
    with a.out.open('x',encoding='utf-8') as f:json.dump(report,f,indent=2)
    print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
