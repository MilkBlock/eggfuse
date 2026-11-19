"""Evaluate fixed single-row checkpoints at multiple physical schedule widths."""
import argparse
import json
from pathlib import Path
import statistics
import time
import numpy as np
import torch

from model import WidthSystem
from study import SEEDS,INPUTS,templates,dataset,fresh_panel,array_digest
from audit import metrics,paired_layouts
from fit import EClassSchema,device,digest,transfer

PRIMARY=((1,1),(2,2),(4,4))
CASES=([(i,j,'parallel') for i,j in (*PRIMARY,(1,2),(2,1),(1,4),(4,1))]
       +[(i,j,'zero_history') for i,j in PRIMARY]
       +[(2,2,'serial_lanes'),(4,4,'serial_lanes')])


def host(output):
    stages,token,rel=output
    data=[{k:s[k].cpu().numpy() for k in ('active','pointers','rows')} for s in stages]
    tokens=token.cpu().numpy();scores=rel.cpu().numpy()
    if not np.isfinite(tokens).all() or not np.isfinite(scores).all():
        raise ValueError('nonfinite GPU output')
    return data,tokens,scores


def merge(chunks):
    return ([{k:np.concatenate([ss[i][k] for ss,_,_ in chunks]) for k in chunks[0][0][i]} for i in (0,1)],
            np.concatenate([t for _,t,_ in chunks]),np.concatenate([p for _,_,p in chunks]))


def subset(d,idx):
    return {k:v[idx] if isinstance(v,np.ndarray) else v for k,v in d.items()}


def compact(report):
    ans={f'r{i}':{k:v for k,v in report[name].items() if k!='per_graph'}
         for i,name in ((1,'run1'),(2,'run2'))}
    ans.update(complete_by_graph=[int(x['complete']) for x in report['run2']['per_graph']],
               parent_ready=[int(x['parent_ready']) for x in report['run2']['per_graph']],
               origin_switch=report['origin_switch'],both_complete_graphs=report['both_complete_graphs'])
    return ans


def key(seed,case):
    i,j,mode=case
    return f'{seed}-{i}x{j}-{mode}'


def check_trace(d, stages, token):
    first=stages[0];g=np.arange(len(token))[:,None]
    assert token.shape==(len(d['a']),8,56)
    np.testing.assert_array_equal(token[...,50:55],first['rows'])
    np.testing.assert_array_equal(token[...,55],d['a_port'][g,first['pointers'][...,0]])
    for start,end,wanted in ((32,34,first['active']),(34,42,first['pointers'][...,0]),(42,50,first['pointers'][...,1])):
        np.testing.assert_array_equal(token[...,start:end],np.eye(end-start)[wanted])


def get_output(model,case,d,idx,dev,table):
    return model(*transfer(d,idx,dev),table,rows=case[:2],schedule=case[-1])


def main():
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);a=parser.parse_args()
    dev=device();ts=templates();held=[t for t in ts if t['split']=='heldout']
    schema=EClassSchema([t for t in ts if t['split']=='train'])
    models={};fits={};traces=a.root/'traces';traces.mkdir(exist_ok=True)
    for seed in SEEDS:
        folder=a.root/str(seed);fit=json.loads((folder/'fit.json').read_text())
        if fit['model_sha256']!=digest(folder/'final.pt'):raise ValueError('model hash mismatch')
        m=WidthSystem(schema,seed);m.load_state_dict(torch.load(folder/'final.pt',map_location='cpu',weights_only=True))
        models[seed]=m.to(dev).eval();fits[seed]=fit
    panels={};older={};comparisons={};timings={};inputs={};controls={};strata={}
    with torch.inference_mode():
        for ti,t in enumerate(held):
            tid=t['id'];d=fresh_panel(t);inputs[tid]=array_digest(d)
            tables={seed:m.encoder.frozen_bank(schema.bank(t,'pairwise',dev)) for seed,m in models.items()}
            cases_by_seed={};outputs={};panels[tid]={};older[tid]={};comparisons[tid]={};timings[tid]={};controls[tid]={};strata[tid]={}
            for seed,m in models.items():
                saved={}
                for case in CASES:
                    label=key(seed,case)
                    out=merge([host(get_output(m,case,d,slice(i,i+64),dev,tables[seed])) for i in range(0,len(d['a']),64)])
                    stages,tok,rel=out;check_trace(d,stages,tok)
                    np.savez_compressed(traces/f'{tid}-{label}.npz',token=tok,rel=rel,**{f'{i}_{k}':v for i,s in enumerate(stages) for k,v in s.items()})
                    outputs[label]=out
                    report=metrics(d,*stages,case[:2],rel);saved[label]=report;panels[tid][label]=compact(report)
                    g=report['run2']['per_graph']
                    strata[tid][label]={}
                    for group,mask in [('blind',d['blind']!=0),('targeted',d['blind']==0)]+[(state,d['state']==i) for i,state in enumerate(('pre','post','nonmerge','external'))]:
                        rr=[v for v,ok in zip(g,mask) if ok]
                        strata[tid][label][group]=dict(graphs=len(rr),complete=sum(x['complete'] for x in rr),duplicates=sum(x['duplicates'] for x in rr),missing=sum(x['missing'] for x in rr))
                baseline=key(seed,(1,1,'parallel'))
                for case in CASES:
                    label=key(seed,case);comparisons[tid][label]=paired_layouts(saved[baseline],saved[label])
                    if case[-1]=='serial_lanes':
                        other=outputs[key(seed,(*case[:2],'parallel'))]
                        st,tok,rel=outputs[label]
                        def difference(stage):
                            return int(np.logical_or.reduce([(st[stage][k]!=other[0][stage][k]).reshape(len(tok),-1).any(1) for k in st[stage]]).sum())
                        controls[tid][label]=dict(make_different_graphs=difference(0),finish_different_graphs=difference(1),
                             token_max_abs=float(np.abs(tok-other[1]).max()),gpu_completed=True)
                    if case[-1]=='parallel':
                        i,j=case[:2];reference=outputs[key(seed,(i,i,'parallel'))]
                        np.testing.assert_array_equal(outputs[label][1],reference[1])
                        # A shared producer layout must produce an identical token tensor for every consumer width.
                old=dataset('test',t)
                for i,j in PRIMARY:
                    case=(i,j,'parallel');label=key(seed,case)
                    st,tok,rel=merge([host(get_output(m,case,old,slice(x,x+64),dev,tables[seed])) for x in range(0,len(old['a']),64)])
                    older[tid][label]=compact(metrics(old,*st,(i,j),rel))
            # Match inputs and alternate execution order across all on-device timing lanes.
            # Four entire groups (32 graphs) per template, half of them blind.
            groups=np.unique(d['group_id']);rng=np.random.default_rng(18414+ti)
            chosen=np.concatenate((rng.choice(groups[::2],2,replace=False),rng.choice(groups[1::2],2,replace=False)))
            ix=np.concatenate([np.flatnonzero(d['group_id']==i) for i in chosen]);sample=subset(d,ix)
            lanes=[(seed,case) for seed in SEEDS for case in CASES if case[-1]!='zero_history']
            elapsed={lane:[] for lane in lanes};kept={lane:[] for lane in lanes}
            for seed,case in lanes:
                for i in range(3):get_output(models[seed],case,sample,slice(i,i+1),dev,tables[seed]);torch.mps.synchronize()
            for i in range(len(ix)):
                start_at=(i+ti)%len(lanes)
                for lane in lanes[start_at:]+lanes[:start_at]:
                    seed,case=lane
                    start=time.perf_counter_ns();out=get_output(models[seed],case,sample,slice(i,i+1),dev,tables[seed]);torch.mps.synchronize()
                    elapsed[lane].append((time.perf_counter_ns()-start)/1.e6);kept[lane].append(out)
            for lane in lanes:
                seed,case=lane;label=key(seed,case)
                st,tok,rel=merge([host(x) for x in kept[lane]]);check_trace(sample,st,tok)
                stats=metrics(sample,*st,case[:2],rel)['run2']
                timings[tid][label]=dict(indices=ix.tolist(),samples_ms=elapsed[lane],
                    median_ms=statistics.median(elapsed[lane]),complete=stats['nonempty_complete_graphs'],
                    nonempty=stats['nonempty_graphs'],valid_graphs_per_second=1000*stats['nonempty_complete_graphs']/sum(elapsed[lane]))
            print(tid,{k:v['r2']['nonempty_complete_graphs'] for k,v in panels[tid].items() if k.endswith('parallel')},flush=True)
    report=dict(fits=fits,panels=panels,source_hashes=inputs,old_panel=older,paired=comparisons,timings=timings,serial_checks=controls,strata=strata)
    (a.root/'results.json').write_text(json.dumps(report,separators=(',',':'))+'\n')

if __name__=='__main__':main()
