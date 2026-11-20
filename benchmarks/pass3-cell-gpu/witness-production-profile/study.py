"""Pair production and archived single-winner execution with unmodified and same-build exact controls."""
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
from statistics import median
import sys
import subprocess
from time import perf_counter

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'compact-recipes'))
import study as compact


def winner_checks(v, truth):
    checks=compact.compare(v,truth)
    assert checks['aligned'] and checks['neural_rhs']==truth['rhs_count']
    proof={k:checks[k] for k in ('commits','multi','physical','children','state_sha','cells','neural_rhs','fresh','direct_cells','rhs','raw','wire_hash')}
    proof['single_evidence']=compact.digest(v['single']['committed'])
    proof['multi_evidence']=compact.digest(v['multi']['tickets'])
    return proof


def study(a):
    a.out.mkdir(parents=True,exist_ok=False)
    root=a.out/'root.json'
    root.write_text(json.dumps(dict(control='use',forbid_fallback=True,encoding='resident')))
    report={}
    for case in a.cases:
        b=a.bundles/f'{case}-1703'
        req=compact.read(b/'request.json')
        for k in ('single_config','merge_config'):
            req[k]=str(b/req[k])
        req.update(root_config=str(root),radius=0,packed_lookup=True,baked_row_index=False,
                   multi_weights=str(a.weights/f'{case}-1703-tied.json'),baked_codes=str(a.weights/f'{case}-1703-tied.bin'),
                   multi_mode='rowdeltapairguardstackseallearned')
        with ExitStack() as stack:
            truth_fn=stack.enter_context(compact.session(a.vanilla/'vanilla-audit',b/'program.json'))
            truth=truth_fn({'audit':True})
            source=stack.enter_context(compact.session(a.vanilla/'vanilla',b/'program.json'))
            old=stack.enter_context(compact.session(a.old,b/'program.json',b/'plans.json'))
            new=stack.enter_context(compact.session(a.new,b/'program.json',b/'plans.json'))
            reference=winner_checks(old(dict(req,audit=True)),truth)
            assert winner_checks(new(dict(req,audit=True,archive_single_winners=False)),truth)==reference
            arms={'vanilla':(source,{}),'same_build_exact':(new,{'baseline':True}),
                  'old_tuned':(old,req),'archive':(new,dict(req,archive_single_winners=True)),
                  'production':(new,dict(req,archive_single_winners=False))}
            rows={arm:{'ms':[],'roundtrip_ms':[],'phase_ms':[],'pre_post_ms':[],'cold_ms':[]} for arm in arms}
            counters={}
            for trial in range(a.repeats+1):
                order=list(arms);i=trial%len(order);order=order[i:]+order[:i]
                for arm in reversed(order) if trial%2 else order:
                    fn,request=arms[arm]
                    start=perf_counter()
                    v=fn(request)
                    wall=(perf_counter()-start)*1000.
                    assert (v['runs'],v['state_sha'])==(truth['runs'],truth['state_sha'])
                    if arm in ('archive','production','old_tuned'):
                        single=v['single']; multi=v['multi']; root_summary=v['root_recipe']
                        count=(len(single['committed']),sum(t[3] for t in single['rules'].values()))
                        assert count[1]>0 and count[0]==(0 if arm=='production' else count[1])
                        assert count[1]+multi['neural_committed']==reference['neural_rhs']
                        keys=(single['work'],single['guard_counts'],multi['counts'],root_summary['allocated'])
                        if not counters:counters=keys
                        assert counters==keys
                        rows[arm]['single_winners']=count[1]; rows[arm]['archived_winners']=count[0]
                    if trial:
                        rows[arm]['ms'].append(v['ms']);rows[arm]['roundtrip_ms'].append(wall)
                        if 'phases_ms' in v:
                            rows[arm]['phase_ms'].append(v['phases_ms'])
                            rows[arm]['pre_post_ms'].append(v['pre_post_ms'])
                    del v
            for trial in range(3):
                for arm in (('production','vanilla') if trial%2 else ('vanilla','production')):
                    argv=[a.new,b/'program.json',b/'plans.json'] if arm=='production' else [a.vanilla/'vanilla',b/'program.json']
                    payload=json.dumps(arms[arm][1]).encode()+b'\n'
                    start=perf_counter()
                    v=json.loads(subprocess.run(argv,input=payload,stdout=subprocess.PIPE,check=True).stdout)
                    rows[arm]['cold_ms'].append((perf_counter()-start)*1000.)
                    assert v['state_sha']==truth['state_sha'] and v['runs']==truth['runs']
            for v in rows.values():
                v['median_ms']=median(v['ms']);v['median_roundtrip_ms']=median(v['roundtrip_ms'])
                if v['phase_ms']:
                    v['median_phase_ms']=[median(col) for col in zip(*v['phase_ms'])]
                    v['median_pre_post_ms']=[median(col) for col in zip(*v['pre_post_ms'])]
                if v['cold_ms']:v['median_cold_ms']=median(v['cold_ms'])
            report[case]=dict(audit=reference,runs=truth['runs'],arms=rows)
            (a.out/'results.json').write_text(json.dumps(report,indent=1)+'\n')
            print(case,[(arm,round(v['median_ms'],1)) for arm,v in rows.items()],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('old','new','vanilla','bundles','weights','out'):
        p.add_argument(key,type=Path)
    p.add_argument('--cases',nargs='+',default=['jacobi-1d','conjugate-gradient'])
    p.add_argument('--repeats',type=int,default=6)
    study(p.parse_args())
