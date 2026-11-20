"""Collect paired single-first-admission interventions, learn a gate, and deploy it."""
import argparse, hashlib, json, subprocess
from collections import Counter
from pathlib import Path

HERE=Path(__file__).resolve().parent
CASES=('dot-product','stable-argmax','gemm-bias-relu','gated-state')
READ=lambda p:json.loads(p.read_bytes())


def references():
    stream=READ(HERE.parent/'prospective-owner-placement/stream.json')
    return {case:{'pooled/keep':dict(source=v['pooled/keep']['source_sha'],graph=v['pooled/keep']['graph'],runs=v['pooled/keep']['runs'])}
            for case,v in stream.items()}


def hashed(x):
    return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def sample(offers,budget):
    # Use distinct features first, balancing occupancy and width. No terminal
    # data or hypothetical physical action determines which states we test.
    bins={}
    seen=set()
    for obs in sorted(offers,key=lambda obs:hashed(obs)):
        x=tuple(obs[4])
        if x in seen:continue
        seen.add(x)
        group=(min(x[0],3),min(x[3]//4,3))
        bins.setdefault(group,[]).append(obs)
    ordered=[]
    while any(bins.values()) and len(ordered)<budget:
        for key in sorted(bins):
            if bins[key] and len(ordered)<budget:
                ordered.append(bins[key].pop())
    return ordered


def run_native(a,case,config):
    ref=a.reference[case]['pooled/keep']
    program=a.exp/('old-pair-catalogs-v1' if case in CASES[:2] else 'owner-action-fresh-v1')/case/'program.json'
    cfg=a.out/'current.json';dest=a.out/'latest.json'
    for f in (dest,Path(str(dest)+'.private')):
        if f.exists():f.unlink()
    cfg.write_text(json.dumps(dict(config,expected_source=ref['source'])))
    subprocess.run([a.engine,program,'prefix',dest,cfg],check=True,stdout=subprocess.DEVNULL)
    files=[dest,Path(str(dest)+'.private')] if config.get('paired') else [dest]
    results=[READ(p) for p in files]
    # Keep the most recent pair for diagnosis; clear any stale child before launch.
    for row in results:
        assert row['source']==ref['source'] and row['graph']==ref['graph'] and row['runs']==ref['runs'],(case,row['source'],ref['source'])
    return results if config.get('paired') else results[0]


def collect(a):
    for name in CASES:
        file=a.out/(name+'-episodes.json')
        if file.exists():continue
        partial=a.out/(name+'-partial.json')
        if partial.exists():
            checkpoint=READ(partial)
        else:
            raw=run_native(a,name,{'capture':True})
            chosen=sample(raw.pop('offers'),a.donors if name in CASES[:2] else a.holdouts)
            assert raw['count'] and raw['selected']==0 and chosen
            sham=run_native(a,name,{'focus':chosen[0][0],'private':False,'paired':True})
            for k in ('terminal_graph_bytes','owner_byte_runs','source','graph','focus','later_ports','physical'):
                assert sham[0][k]==sham[1][k],(name,'neutral fork',k)
            checkpoint=dict(reference=raw,chosen=chosen,episodes=[],sham={k:sham[0][k] for k in
                ('source','graph','terminal_graph_bytes','owner_byte_runs','later_ports')},sham_identical=True)
        raw=checkpoint['reference'];chosen=checkpoint['chosen'];episodes=checkpoint['episodes']
        for ordinal,run,shape,members,x in chosen[len(episodes):]:
            arms=run_native(a,name,{'focus':ordinal,'private':True,'paired':True})
            keep,priv=arms
            census_features=x
            run,shape,members,x=[keep['focus'][k] for k in ('run','shape','members','features')]
            for i,row in enumerate(arms):
                t=row['focus']
                assert [t['ordinal'],t['run'],t['shape'],t['members'],t['features']]==[ordinal,run,shape,members,x]
                assert t['selected']==bool(i) and row['selected']==i and len(row['trace'])==i
                assert all(v is not None for v in t['backings'])
                assert all(r['source']==raw['source'] and r['graph']==raw['graph'] for r in arms)
            assert keep['pre_owner_byte_runs']==priv['pre_owner_byte_runs']
            assert keep['port_runs']==priv['port_runs']==raw['runs']-run+1
            assert keep['focus']['ports']==priv['focus']['ports'] and keep['later_ports']==priv['later_ports']
            assert all(q==priv['focus']['backings'][0] for q in priv['focus']['backings'])
            assert priv['focus']['backings'][0][1]==len(members)
            episodes.append(dict(id=ordinal,run=run,shape=shape,members=members,x=x,census_features=census_features,
                source_ports=keep['focus']['ports'],port_digest=keep['later_ports'],port_runs=keep['port_runs'],
                old_owner=keep['focus']['backings'][0],private_owner=priv['focus']['backings'][0],
                birth_saving=keep['focus']['owner_bytes_at_birth']-priv['focus']['owner_bytes_at_birth'],
                terminal_saving=keep['terminal_graph_bytes']-priv['terminal_graph_bytes'],
                owner_area_saving=keep['owner_byte_runs']-priv['owner_byte_runs'],
                outcomes=[{k:r[k] for k in ('terminal_graph_bytes','owner_byte_runs','pre_owner_byte_runs','owner_peak','terminal_owner_charge','placement','physical')} for r in arms]))
            tmp=partial.with_suffix('.new')
            tmp.write_text(json.dumps(checkpoint,separators=(',',':')))
            tmp.replace(partial)
        del checkpoint['chosen']
        file.write_text(json.dumps(checkpoint,indent=1)+'\n')
        print(name,'offers',raw['count'],'paired',len(episodes),'different backings',sum(s['old_owner']!=s['private_owner'] for s in episodes),flush=True)


def fit(a):
    import torch
    torch.set_num_threads(1)
    donors=[e for case in CASES[:2] for e in READ(a.out/(case+'-episodes.json'))['episodes']]
    x=torch.tensor([e['x'] for e in donors],dtype=torch.float64)
    scale=x.abs().amax(0).clamp(min=1)
    features=x/scale
    policies={}
    for k in ('birth_saving','terminal_saving','owner_area_saving'):
        target=torch.tensor([e[k] for e in donors],dtype=torch.float64)
        unit=target.abs().mean().clamp(min=1)
        design=torch.cat([features,torch.ones((len(features),1),dtype=torch.float64)],dim=1)
        # Closed-form squared-error regression. Fixed regularization, unpenalized bias.
        penalty=torch.eye(9,dtype=torch.float64)*(.01*len(features));penalty[-1,-1]=0
        w=torch.linalg.solve(design.T@design+penalty,design.T@(target/unit))
        weight=[round(v*(2**20))/(2**20) for v in (w[:8]/scale).tolist()+[w[-1].item()]]
        policies[k]=dict(weights=weight,unit=unit.item(),donors=list(CASES[:2]),examples=len(donors))
    (a.out/'policies.json').write_text(json.dumps(policies,indent=1)+'\n')
    return policies


def write_deployment(folder,summary):
    with (folder/'support.jsonl').open('w') as f:
        for case,arms in summary.items():
            for arm,row in arms.items():
                f.write(json.dumps([case,arm,row.pop('feature_support')],separators=(',',':'))+'\n')
    (folder/'deployment.json').write_text(json.dumps(summary,indent=1)+'\n')


def deploy(a,policies):
    summary={}
    for name in CASES[2:]:
        source=READ(a.out/(name+'-episodes.json'));ref=source['reference'];episodes=source['episodes']
        rows={}
        for policy,spec in {'pool':{'weights':[0.]*9},'private':{'weights':[0.]*8+[1.]},'multiple':{'weights':[1.]+[0.]*7+[-1.5]},**policies}.items():
            w=spec['weights'];paired,r=run_native(a,name,{'weights':w,'capture':True,'paired':True})
            assert paired['selected']==0
            def choose(x):return w[-1]+sum(i*j for i,j in zip(w,x))>0
            assert [o for o in r['offers'] if choose(o[4])]==r['trace']
            decisions=[e for e in episodes if choose(e['x'])]
            frequency=Counter(tuple(o[4]) for o in r['offers'])
            rows[policy]=dict(feature_support=[[list(x),n,choose(x)] for x,n in sorted(frequency.items())],offers=r['count'],selected=r['selected'],decision_digest=hashed(r['trace']),
                source=r['source'],graph=r['graph'],runs=r['runs'],terminal_graph_bytes=r['terminal_graph_bytes'],
                owner_byte_runs=r['owner_byte_runs'],owner_peak=r['owner_peak'],
                episode_selected=len(decisions),isolated_graph_delta=sum(e['terminal_saving'] for e in decisions),
                isolated_area_delta=sum(e['owner_area_saving'] for e in decisions),
                terminal_owner_charge=r['terminal_owner_charge'],placement=r['placement'],physical=r['physical'],
                paired_terminal_bytes=paired['terminal_graph_bytes'],paired_byte_runs=paired['owner_byte_runs'],
                graph_saving=paired['terminal_graph_bytes']-r['terminal_graph_bytes'],
                area_saving=paired['owner_byte_runs']-r['owner_byte_runs'])
        summary[name]=rows
        print(name,[(k,v['selected'],v['graph_saving'],v['area_saving']) for k,v in rows.items()],flush=True)
    write_deployment(a.out,summary)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','engine','out'):p.add_argument(k,type=Path)
    p.add_argument('--donors',type=int,default=16);p.add_argument('--holdouts',type=int,default=12)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    a.reference=references()
    collect(a)
    if not (a.out/'deployment.json').exists():
        deploy(a, fit(a))
