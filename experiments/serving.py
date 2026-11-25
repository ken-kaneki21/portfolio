"""Benchmark the synthetic decoder's actual streaming ASGI endpoint."""
import argparse
import asyncio
from concurrent.futures import ThreadPoolExecutor
import hashlib
import http.client
import json
from pathlib import Path
import socket
import statistics
from threading import Thread
from time import perf_counter,sleep

import psutil
import torch
import uvicorn
from adaptation import quality
from tiny_decoder import decode,read_model,template

def wire(kind,**fields):
    return (json.dumps({'kind':kind,**fields},separators=(',',':'))+'\n').encode()

def make_app(model,codec,limit=2):
    active=0
    async def app(scope,receive,send):
        nonlocal active
        if scope['type']!='http':return
        async def headers(status):
            await send({'type':'http.response.start','status':status,
                        'headers':[(b'content-type',b'application/x-ndjson')]})
        async def write(data,more=False):
            await send({'type':'http.response.body','body':data,'more_body':more})
        incoming=await receive()
        try:
            args=json.loads(incoming.get('body',b''))
            prompt=args['prompt']; budget=args['max_new']
            if (scope['method']!='POST' or scope['path']!='/generate' or incoming.get('more_body')
                or not isinstance(prompt,str) or type(budget) is not int or not 1<=budget<=40
                or not 1<=len(codec.encode(prompt))<=model.context-budget):
                raise ValueError('invalid route, prompt or budget')
        except (ValueError,KeyError,TypeError):
            await headers(400);await write(wire('error',reason='invalid request'));return
        if active>=limit:
            await headers(429);await write(wire('error',reason='admission limit'));return
        active+=1
        try:
            await headers(200)
            tokens=0
            for item in decode(model,codec,prompt,budget):
                tokens+=1
                await write(wire('token',text=item),True)
                await asyncio.sleep(0)
            await write(wire('done',input_tokens=len(codec.encode(prompt)),output_tokens=tokens))
        finally:
            active-=1
    return app

def base_row(row,budget):
    return {'prompt':template(row),'max_new':budget}

def collect(status,start,chunks,expected=None):
    tokens=[];done=None;first=None
    for seen,chunk in chunks:
        for line in chunk.splitlines():
            event=json.loads(line)
            if event['kind']=='token':
                first=first or seen;tokens.append(event['text'])
            elif event['kind']=='done':done=event
    end=perf_counter()
    raw=''.join(tokens)
    assert not done or done['output_tokens']==len(tokens)
    return {'status':status,'ttft_ms':(first-start)*1000 if first else None,
            'e2e_ms':(end-start)*1000,'input_tokens':None if not done else done['input_tokens'],
            'output_tokens':len(tokens),'output_rate_tokens_s':len(tokens)/(end-start),
            'decode_rate_tokens_s':(len(tokens)-1)/(end-first) if first and len(tokens)>1 and end>first else None,
            'output':raw,'quality':quality(raw,expected) if expected and status==200 else None,
            'rss_bytes':psutil.Process().memory_info().rss}

def real_client(port,args,expected=None,timeout=8):
    conn=http.client.HTTPConnection('127.0.0.1',port,timeout=timeout)
    start=perf_counter()
    try:
        conn.request('POST','/generate',json.dumps(args),{'Content-Type':'application/json'})
        resp=conn.getresponse()
        def chunks():
            while line:=resp.readline():
                yield perf_counter(),line
        return collect(resp.status,start,chunks(),expected)
    finally:
        conn.close()

async def asgi_client(app,args,expected=None):
    start=perf_counter()
    chunks=[];status=None
    async def receive():return {'type':'http.request','body':json.dumps(args).encode(),'more_body':False}
    async def send(event):
        nonlocal status
        if event['type']=='http.response.start':status=event['status']
        else:chunks.append((perf_counter(),event.get('body',b'')))
    await app({'type':'http','path':'/generate','method':'POST'},receive,send)
    return collect(status,start,chunks,expected)

def drive(*calls):
    """Drive the fixture ASGI coroutines without opening an event-loop socket.

    The in-memory receive/send callables complete synchronously. Sleep(0)
    in the app yields None once per token to make scheduling explicit.
    """
    outstanding=dict(enumerate(calls)); results=[None]*len(calls)
    try:
        while outstanding:
            for i,task in list(outstanding.items()):
                try:
                    if task.send(None) is not None:
                        raise RuntimeError('ASGI fixture unexpectedly requested external I/O')
                except StopIteration as done:
                    results[i]=done.value
                    del outstanding[i]
    finally:
        for task in outstanding.values():task.close()
    return results

def asgi_workload(app,pairs):
    for r in pairs[:2]:drive(asgi_client(app,base_row(r,40)))
    serial=[drive(asgi_client(app,base_row(r,40),r['expected']))[0] for r in pairs]
    parallel=[]
    for i in range(0,len(pairs),2):
        parallel.extend(drive(*(asgi_client(app,base_row(r,40),r['expected']) for r in pairs[i:i+2])))
    overload=drive(*(asgi_client(app,base_row(r,40)) for r in pairs[:3]))
    invalid,=drive(asgi_client(app,{'prompt':'job','max_new':500}))
    return serial,parallel,[r['status'] for r in overload],invalid['status']

def benchmark(app,pairs,force_asgi):
    if force_asgi:
        return 'in-process-asgi-send-events','explicit in-process mode',asgi_workload(app,pairs)
    server=None;thread=None
    try:
        with socket.socket() as s:
            s.bind(('127.0.0.1',0));s.set_inheritable(True)
            port=s.getsockname()[1]
            server=uvicorn.Server(uvicorn.Config(app,log_level='error',lifespan='off',ws='none'))
            thread=Thread(target=server.run,kwargs={'sockets':[s]},daemon=True);thread.start()
            for _ in range(100):
                if server.started:break
                sleep(.025)
            if not server.started:raise OSError('loopback server startup timeout')
            try:
                for r in pairs[:2]:real_client(port,base_row(r,40))
                serial=[real_client(port,base_row(r,40),r['expected']) for r in pairs]
                with ThreadPoolExecutor(max_workers=2) as pool:
                    parallel=list(pool.map(lambda r:real_client(port,base_row(r,40),r['expected']),pairs))
                with ThreadPoolExecutor(max_workers=3) as pool:
                    overload=list(pool.map(lambda r:real_client(port,base_row(r,40)),pairs[:3]))
                invalid=real_client(port,{'prompt':'job','max_new':500})
                return 'loopback-http','none',(serial,parallel,[r['status'] for r in overload],invalid['status'])
            finally:
                server.should_exit=True;thread.join(8)
    except OSError as exc:
        return 'in-process-asgi-send-events',str(exc),asgi_workload(app,pairs)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--model-dir',type=Path,required=True);p.add_argument('--fixture',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--asgi-only',action='store_true')
    a=p.parse_args()
    torch.set_num_threads(1)
    before=psutil.Process().memory_info().rss
    model,codec=read_model(a.model_dir)
    pairs=[r for r in json.loads(a.fixture.read_bytes())['rows'] if r['split']=='holdout']
    app=make_app(model,codec)
    mode,reason,(one,two,overload,invalid)=benchmark(app,pairs,a.asgi_only)
    assert invalid==400 and sorted(overload)==[200,200,429],(invalid,overload)
    def summarize(rows):
        ok=[r for r in rows if r['status']==200]
        return {'n':len(rows),'errors':len(rows)-len(ok),
                'median_e2e_ms':statistics.median(r['e2e_ms'] for r in ok),
                'median_ttft_ms':statistics.median(r['ttft_ms'] for r in ok if r['ttft_ms'] is not None),
                'median_decode_tokens_s':statistics.median(r['decode_rate_tokens_s'] for r in ok if r['decode_rate_tokens_s']),
                'min_input_tokens':min(r['input_tokens'] for r in ok),'max_input_tokens':max(r['input_tokens'] for r in ok),
                'actual_output_tokens':sum(r['output_tokens'] for r in ok),
                'min_output_tokens':min(r['output_tokens'] for r in ok),'max_output_tokens':max(r['output_tokens'] for r in ok),
                'schema_valid':sum(r['quality']['schema_valid'] for r in ok),'exact':sum(r['quality']['exact'] for r in ok),
                'sampled_max_rss_bytes':max(r['rss_bytes'] for r in rows)}
    report={'runtime':'PyTorch '+torch.__version__,'uvicorn':uvicorn.__version__,'precision':'CPU FP32',
       'model_revision':hashlib.sha256((a.model_dir/'base.pt').read_bytes()).hexdigest(),
       'tokenizer_revision':hashlib.sha256(json.dumps(codec.tokens).encode()).hexdigest(),
       'fixture_sha256':hashlib.sha256(a.fixture.read_bytes()).hexdigest(),
       'transport':mode,'fallback_reason':reason,'warmup_requests':2,'decode':'greedy, EOS or 40 tokens',
       'admission_limit':2,'overload_statuses':overload,'invalid_budget_status':invalid,
       'rss_before_model_bytes':before,'serial':summarize(one),'concurrent_2':summarize(two),
       'rows':{'serial':one,'concurrent_2':two},
       'timing_note':'Single CPU inference thread; concurrent streams interleave token steps. TTFT at first token event. ASGI timing observes response messages before socket transport. No tail percentiles. RSS sampled at request completion.'}
    with a.out.open('x',encoding='utf-8') as f:json.dump(report,f,indent=2)
    print(json.dumps({k:report[k] for k in ('transport','fallback_reason','serial','concurrent_2','overload_statuses')},indent=2))

if __name__=='__main__':main()
