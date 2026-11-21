"""Check each learned Run forecast against the native vector and retain a concrete many-template wave."""
import argparse,importlib.util,json,math
from collections import defaultdict
from pathlib import Path
HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('wave_example',HERE/'study.py');trial=importlib.util.module_from_spec(s);s.loader.exec_module(trial)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','weights','out'):p.add_argument(k,type=Path)
    a=p.parse_args();a.seed=1703;a.policy=json.loads(a.weights.read_bytes());a.out.mkdir(parents=True,exist_ok=False)
    program,plans,req=trial.wave.parent.common.config(a,'3mm');cfg=trial.settings(req,a)['named']
    with trial.wave.parent.base.session(a.exp/'compact-vanilla-20261121/vanilla',program) as ref:gold=ref({})
    with trial.wave.parent.base.session(a.native,program,plans) as infer:
        out=infer(dict(cfg,spec_cells=dict(cfg['spec_cells'],capture=True)))
    assert out['state_sha']==gold['state_sha'] and out['multi']['total_rhs']==gold['rhs_count']
    report=out['spec_cells'];alloc={(v[0],v[1]):v for v in report['grants']};groups=defaultdict(list)
    w=cfg['spec_cells']['weights'];cap=cfg['spec_cells']['cap']
    for ep,rid,t,x,n,wins,fresh in report['samples']:
        grant=alloc[(ep,rid)]
        pred=min(cap,int(math.floor(math.expm1(min(math.log1p(cap),max(0.,sum(i*j for i,j in zip(w,x)))))+.5)))
        assert x[7]==0 and pred==grant[2] and [wins,fresh]==grant[4:]
        groups[ep].append(dict(rule=rid,template=t,requested=pred,granted=grant[3],offers=n,wins=wins,fresh=fresh))
    for block in groups.values():
        need=sum(v['requested'] for v in block);assert sum(v['granted'] for v in block)==min(need,cap)
    ep=max(groups,key=lambda e:sum(r['offers'] for r in groups[e]))
    record=groups[ep]
    result=dict(epoch=ep,active_rules=len(record),granted=sum(v['granted'] for v in record),source_offers=sum(v['offers'] for v in record),
                wins=sum(v['wins'] for v in record),fresh=sum(v['fresh'] for v in record),
                nonempty_grants=sum(v['granted']>0 for v in record),preissued_wave=out['multi']['wave'],
                top_by_requested=sorted(record,key=lambda v:-v['requested'])[:8],checked_vectors=len(groups),checked_rules=len(alloc))
    (a.out/'example.json').write_text(json.dumps(result,indent=1)+'\n');print(result['epoch'],result['granted'],result['source_offers'],result['fresh'],flush=True)
