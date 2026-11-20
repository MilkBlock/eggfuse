"""Time independent exact and neural Rust executables on unseen programs, with direct path provenance."""
import argparse
from contextlib import ExitStack
import gc
import json
from pathlib import Path
from statistics import median
from time import perf_counter_ns
from pgo_common import ARMS,PROOFS,DONORS,HERE,HOLDOUTS,file_digest,inputs,session,source



def binary(a,arm):
    if arm=='vanilla-release':return a.exp/'compact-vanilla-20261121/vanilla'
    if arm=='learned-release':return a.exp/'composed-cpu-profile-v1/session'
    return a.build/arm



def audit(a,program,plan,request,case):
    with session(a.exp/'compact-vanilla-20261121/vanilla-audit',program) as oracle:
        gold=oracle({'audit':True})
    refs={}
    archive=json.loads((HERE.parent/'composed-cpu'/('large.json' if case in ('3mm','deriche') else 'core.json')).read_bytes())[case]['combined-lazy']
    for arm in ARMS:
        if arm.startswith('vanilla'):
            with session(binary(a,arm),program) as exact:row=exact({})
            assert all(row[k]==gold[k] for k in ('runs','state_sha','rhs_count'))
            refs[arm]=dict(runs=row['runs'],state_sha=row['state_sha'],rhs=row['rhs_count'])
        else:
            with session(binary(a,arm),program,plan) as evaluate:
                data=evaluate(dict(request,audit=True))
                row=source.base.summarize(data,gold)
                assert all(row[k]==archive[k] for k in PROOFS),(case,arm)
                assert data['multi']['counts']['exhausted']==0
                assert data['header_view']['delta_updates']>0 and data['multi']['lazy_eq']['computed']>0
                refs[arm]={k:row[k] for k in PROOFS}
                refs[arm].update(checks=row['checks'],remaining_rhs=row['rhs']-row['neural_rhs'],
                                 root_allocated=row['root_allocated'],multi_tuples=data['multi']['counts']['raw_tuples'],
                                 header_updates=data['header_view']['delta_updates'],arithmetic=data['multi']['lazy_eq']['computed'])
                del data,row
        gc.collect()
    assert refs['learned-release']==refs['learned-plain']==refs['learned-use']
    return refs


def measure(a):
    a.out.mkdir(parents=True,exist_ok=False);results={}
    manifest=json.loads((a.build/'build.json').read_bytes())
    for arm in ARMS:
        if not arm.endswith('-release'):assert file_digest(binary(a,arm))==manifest['binaries'][arm]['sha256']
    for case in a.cases:
        assert case not in DONORS
        p,plan,req=inputs(a,case)
        refs=audit(a,p,plan,req,case)
        gc.collect()
        for v in refs.values():v.update(ms=[],roundtrip_ms=[])
        with ExitStack() as stack:
            native={arm:stack.enter_context(session(binary(a,arm),p,*([plan] if arm.startswith('learned') else []))) for arm in ARMS}
            schedules=[]
            for iteration in range(-1,a.repeats):
                if iteration<0:order=ARMS
                else:
                    shift=iteration%len(ARMS)
                    order=ARMS[shift:]+ARMS[:shift]
                    if (iteration//len(ARMS))%2:order=tuple(reversed(order))
                    schedules.append(order)
                for arm in order:
                    learned=arm.startswith('learned')
                    start=perf_counter_ns()
                    v=native[arm](req if learned else {})
                    elapsed=(perf_counter_ns()-start)/1e6
                    expected=refs[arm]
                    assert v['runs']==refs['vanilla-plain']['runs'] and v['state_sha']==expected['state_sha']
                    if learned:
                        assert v['multi']['total_rhs']==expected['rhs'] and v['root_recipe']['allocated']==expected['root_allocated']
                        assert v['multi']['counts']['raw_tuples']==expected['multi_tuples']
                    else:assert v['rhs_count']==expected['rhs']
                    if iteration>=0:
                        expected['ms'].append(v['ms']);expected['roundtrip_ms'].append(elapsed)
            for v in refs.values():
                v.update(median_ms=median(v['ms']),median_roundtrip_ms=median(v['roundtrip_ms']))
        results[case]=dict(program_sha256=file_digest(p),sealed_sha256=file_digest(plan),orders=schedules,arms=refs,binaries={arm:file_digest(binary(a,arm)) for arm in ARMS})
        (a.out/'results.json').write_text(json.dumps(results,indent=1)+'\n')
        print(case,[(k,round(v['median_ms'],2)) for k,v in refs.items()],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('exp','build','out'):p.add_argument(name,type=Path)
    p.add_argument('--cases',nargs='+',default=list(HOLDOUTS));p.add_argument('--repeats',type=int,default=6)
    a=p.parse_args();a.seed=1703;measure(a)
