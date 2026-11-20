"""Interleave exact and learned deployment arms, including a profile trained on the original issuer."""
import argparse
from contextlib import ExitStack
import gc,json
from pathlib import Path
from statistics import median
from time import perf_counter_ns
from joint_common import HERE,HOLDOUTS,file_digest,routes,session,source

ARMS=('exact-release','plain-original','pgo-union','exact-pgo','plain-union','pgo-original')
PROOFS=('single_winners','multi_winners','root_parents','root_ids','nested_ids','rhs','direct_cells','fresh','cells','state_sha')
STREAM=('raw','multi','commits','physical','children')


def exe(a,arm):
    if arm=='exact-release':return a.exp/'compact-vanilla-20261121/vanilla'
    if arm=='exact-pgo':return a.reference/'vanilla-use'
    return a.build/('learned-use' if arm.startswith('pgo') else 'learned-plain')


def measure(a):
    a.out.mkdir(parents=True,exist_ok=False);results={}
    refbuild=json.loads((a.reference/'build.json').read_bytes())
    assert file_digest(exe(a,'exact-pgo'))==refbuild['binaries']['vanilla-use']['sha256']
    fit=json.loads((a.build/'joint-build.json').read_bytes())
    assert file_digest(exe(a,'pgo-union'))==fit['binaries']['use']['sha256']
    for name in a.cases:
        p,plans,off,union=routes(a,name);arms={}
        # Compare physical provenance to already published production-execution studies too.
        expected=json.loads((HERE.parent/'incremental-request-ports/results.json').read_bytes())[name]
        with session(a.exp/'compact-vanilla-20261121/vanilla-audit',p) as goldfn:gold=goldfn({'audit':True})
        for arm in ARMS:
            union_on=arm.endswith('-union')
            if arm.startswith('exact-'):
                with session(exe(a,arm),p) as inf:out=inf({})
                assert all(out[k]==gold[k] for k in ('runs','rhs_count','state_sha'))
                row=dict(rhs=out['rhs_count'],state_sha=out['state_sha'])
            else:
                with session(exe(a,arm),p,plans) as inf:out=inf(dict(union if union_on else off,audit=True))
                q=source.base.summarize(out,gold);prior=expected['union' if union_on else 'off']
                for k in PROOFS+STREAM:assert q[k]==prior[k],(name,arm,k)
                row={k:q[k] for k in PROOFS+STREAM};m=out['multi']
                assert m['counts']['exhausted']==0
                row.update(checks=q['checks'],remaining_rhs=q['rhs']-q['neural_rhs'],root_allocated=q['root_allocated'],
                    raw_count=m['counts']['raw_tuples'],activation=m.get('wake',{'routed_calls':0}),patch=m.get('patch_ports',{'union_repairs':0}),requests=m.get('bridges',{}).get('requests',0))
                assert (row['patch']['union_repairs']>0)==union_on
                assert (row['activation']['routed_calls']>0)==union_on
            row.update(runs=gold['runs'],ms=[],api_ms=[])
            arms[arm]=row;del out;gc.collect()
        del gold;gc.collect();schedules=[]
        with ExitStack() as stack:
            fun={arm:stack.enter_context(session(exe(a,arm),p,*([] if arm.startswith('exact') else [plans]))) for arm in ARMS}
            for i in range(-1,a.repeats):
                # Move two places and reverse successive rounds to counter time trends.
                k=2*max(i,0)%len(ARMS);order=ARMS[k:]+ARMS[:k]
                if i%2:order=order[::-1]
                if i>=0:schedules.append(order)
                for arm in order:
                    row=arms[arm];exact=arm.startswith('exact')
                    t=perf_counter_ns();out=fun[arm]({} if exact else union if arm.endswith('union') else off);wall=(perf_counter_ns()-t)/1e6
                    assert out['state_sha']==row['state_sha'] and out['runs']==row['runs']
                    if exact:assert out['rhs_count']==row['rhs']
                    else:
                        assert out['multi']['total_rhs']==row['rhs'] and out['root_recipe']['allocated']==row['root_allocated']
                        assert out['multi']['counts']['raw_tuples']==row['raw_count']
                        assert out['multi'].get('patch_ports',{}).get('union_repairs',0)==row['patch']['union_repairs']
                    if i>=0:row['ms'].append(out['ms']);row['api_ms'].append(wall)
        for row in arms.values():row.update(median_ms=median(row['ms']),median_api_ms=median(row['api_ms']))
        results[name]=dict(program=file_digest(p),plans=file_digest(plans),arms=arms,orders=schedules)
        (a.out/'joint-results.json').write_text(json.dumps(results,indent=1)+'\n')
        print(name,[(arm,round(row['median_ms'],2)) for arm,row in arms.items()],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','reference','build','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',choices=HOLDOUTS,default=list(HOLDOUTS))
    p.add_argument('--repeats',type=int,default=4);a=p.parse_args();a.seed=1703;measure(a)
