"""Train a second Bake round on actual first-round neural executions; compare frozen source-scheduled arms."""
import argparse
from collections import Counter,defaultdict
import gzip
import hashlib
import json
from pathlib import Path
from statistics import median
import subprocess
import sys
from time import perf_counter_ns

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'joint-witness'))
from evaluate import read,rpc,sealed_plans,audit
from prepare import prepare
from types import SimpleNamespace


def paths(a,case):
    if case in ('sum-bits','dot-product'):
        return a.ref/case/'program.json',a.ref/f'release-input-{case}',a.ref/f'events-{case}',a.capture
    return a.corpus/case/'program.json',a.corpus/case/'input',a.corpus/case/'observation',(
        a.train_capture if case in a.catalog['training'] else a.capture)


def make_session(a,case,seed):
    prog,image,old,capture=paths(a,case)
    folder=a.out/f'{case}-{seed}-static'
    prepare(SimpleNamespace(program=prog,image=image,out=folder,policy='certified',seed=seed))
    req=read(folder/'request.json')
    for k in ('single_config','multi_weights','merge_config','root_config'):
        req[k]=str(folder/req[k])
    proc=subprocess.Popen([a.binary,prog,folder/'plans.json'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    return proc,req,read(folder/'plans.json'),old,capture


def describe(run,case,a,plans,capture):
    v=audit(run,case,a.ref,a.corpus,capture,plans,'learned','stackseal3xlearned')
    assert v['aligned'] and not v['uncredited'],v['checks']
    root=run['root_recipe']
    assert len(root['commits'])==v['actual_rhs']
    actual_fresh={id for _,id,*_ in run['cell_ids']}
    roots={row[0] for row in root['fresh']}
    merged={e['allocated'] for e in run['merge_child']['issued'] if e['allocated'] is not None}
    assert not roots.intersection(merged) and (roots|merged)<=actual_fresh
    got=dict(runs=run['runs'],rhs=v['source_rhs'],neural_rhs=v['total_attributed'],direct=len(roots|merged),fresh=len(actual_fresh),
             graph=run['state_sha'],spine_equal=v['checks']['resumes'],unions_equal=v['checks']['unions'],source_exact=True)
    h=run.get('higher')
    if h:
        commits={c[0]:c for c in root['commits']}; examples=[]
        for ordinal,epoch,rid,w,parent,serial,prid,effect,issued,version,ticket,depth,value in h['winners']:
            assert epoch>issued and ordinal>parent>0 and commits[parent][2:4]==[serial,prid]
            binding=commits[ordinal]
            assert binding[3]==rid and binding[5]==epoch and binding[6][0]['row']==w and binding[6][0]['version']==version
            assert rid==(a.catalog['family']['gt'] if value>a.catalog['family']['threshold'] else a.catalog['family']['eq'])
            if len(examples)<5 or depth>max(x[-2] for x in examples):examples.append([parent,issued,prid,effect,ordinal,epoch,rid,depth,value])
        assert len({e[0] for e in h['winners']})==len(h['winners'])==sum(h['counts'][11:13])
        got.update(winners=sum(h['counts'][11:13]),counts=h['counts'],examples=examples,projected=h['projected'],peak_pending=h['peak_pending'],
                   max_chain=h['max_chain'],retired=h.get('retired',0),peak_payload_bytes=h.get('peak_payload_bytes'),
                   peak_hash_capacity=h.get('peak_hash_capacity'),final_pending=h.get('final_pending'),logical_request_bytes=h['request_logical_bytes'],observed=h['observed'],
                   root_wire_bytes=run['root_recipe']['wire_bytes'])
    return got


def config(a,mode,parents,recursive=False,profile=False):
    return dict(family=a.catalog['family'],mode=mode,parents=parents,recursive=recursive,profile=profile)


def growth(a):
    first=a.catalog['first'];training={};stats=defaultdict(lambda:Counter())
    for case in a.catalog['training']:
        proc,req,plans,old,cap=make_session(a,case,1703)
        try:
            data=rpc(proc,dict(req,audit=True,higher_config=config(a,'baked',[first],profile=True)))
            info=describe(data,case,a,plans,cap);training[case]=info
            for rid,e,c in info['observed']:
                if c[1]:stats[(rid,e)][case]+=c[1]
        finally:proc.stdin.close();proc.wait()
    # Every selected upstream interface actually fed the next 138-like consumer of the seed
    # in at least two distinct source families. Reuse the existing conditional as one unit.
    ranked=sorted((k for k,v in stats.items() if len(v)>=2 and list(k)!=first),
                  key=lambda k:(-sum(stats[k].values()),k))
    parents=[first,*[list(k) for k in ranked[:a.growth_budget]]]
    out=dict(first_round=[first],second_round=parents,training=training,
             source='actual R1 native committed neural parents and next source consumer',growth_budget=a.growth_budget)
    (a.out/'growth.json').write_text(json.dumps(out,indent=1)+'\n')
    print('growth',parents,[(k,dict(stats[k])) for k in ranked],flush=True)
    return parents


def main(a):
    a.out.mkdir(parents=True,exist_ok=False);a.catalog=read(a.catalog_path)
    expanded=growth(a) if not a.grown else read(a.grown)['second_round'];result={}
    for case in a.cases:
        for seed in a.seeds:
            proc,req,plans,old,cap=make_session(a,case,seed)
            initial=[a.catalog['first']]
            variants={'base':None,'r1-flat':config(a,'flat',initial),'r1-dispatch':config(a,'dispatch',initial),
                      'r1-baked':config(a,'baked',initial),'grown-flat':config(a,'flat',expanded),
                      'grown-dispatch':config(a,'dispatch',expanded),'grown-baked':config(a,'baked',expanded),
                      'grown-recursive':config(a,'baked',expanded,True),'stale':config(a,'stale',expanded),
                      'shadow':config(a,'shadow',expanded)}
            if a.arms:variants={k:variants[k] for k in a.arms}
            reports={}
            try:
                for mode,cfg in variants.items():
                    audit_cfg=None if cfg is None else dict(cfg,profile=True)
                    r=rpc(proc,dict(req,audit=True,higher_config=audit_cfg))
                    got=describe(r,case,a,plans,cap);got['ms']=[];reports[mode]=got
                    if r.get('higher'):
                        with gzip.open(a.out/f'{case}-{seed}-{mode}-hits.json.gz','wt') as f:json.dump(r['higher']['winners'],f)
                    print(case,seed,mode,got.get('winners'),got.get('projected'),got.get('max_chain'),flush=True)
                for prefix in ['r1','grown']:
                    group=[k for k in reports if k.startswith(prefix+'-')]
                    if len(group)>1:
                        def ords(arm):
                            with gzip.open(a.out/f'{case}-{seed}-{arm}-hits.json.gz','rt') as f:
                                # Serials are proposal-local: emitting a rejected flat branch legitimately
                                # renumbers subsequent tokens. Compare physical witness and actual parent ordinal.
                                return [x[:5]+x[6:11]+x[12:] for x in json.load(f)]
                        for arm in group[1:]:
                            assert ords(arm)==ords(group[0]),(case,seed,arm,'actual child or parent divergence')
                if 'shadow' in reports:assert not reports['shadow']['winners']
                if 'stale' in reports:assert not reports['stale']['winners']
                timing=[n for n in variants if n not in ('stale','shadow')]
                for trial in range(a.repeats+1):
                    shifted=timing[trial%len(timing):]+timing[:trial%len(timing)]
                    for mode in shifted if trial%2==0 else shifted[::-1]:
                        r=rpc(proc,dict(req,audit=False,higher_config=variants[mode]))
                        assert r['state_sha']==reports[mode]['graph'] and r['runs']==reports[mode]['runs']
                        if mode!='base':
                            assert r['higher']['counts'][11:13]==reports[mode]['counts'][11:13],(case,mode)
                        if trial:reports[mode]['ms'].append(r['ms'])
                for mode in timing:
                    if reports[mode]['ms']:reports[mode]['median_ms']=median(reports[mode]['ms'])
            finally:proc.stdin.close();proc.wait()
            result[f'{case}/{seed}']=reports
            (a.out/'results.json').write_text(json.dumps(result,indent=1)+'\n')
            print(case,seed,[(n,round(reports[n].get('median_ms',0),2)) for n in timing],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('binary','ref','corpus','capture','train_capture','catalog_path','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','gemm-bias-relu','stable-argmax'])
    p.add_argument('--seeds',nargs='+',type=int,default=[1703,1709])
    p.add_argument('--arms',nargs='+');p.add_argument('--growth-budget',type=int,default=3)
    p.add_argument('--repeats',type=int,default=8);p.add_argument('--grown',type=Path)
    main(p.parse_args())
