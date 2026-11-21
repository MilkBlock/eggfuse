"""Compare unchanged root types, learned tagged producer rights, and all-eligible dispatch."""
import argparse,hashlib,importlib.util,json
from contextlib import ExitStack
from pathlib import Path
from statistics import median
from time import perf_counter
HERE=Path(__file__).resolve().parent
sp=importlib.util.spec_from_file_location('family_train',HERE/'train.py');training=importlib.util.module_from_spec(sp);sp.loader.exec_module(training)
src=training.joint['src']
fields=('checks','single_winners','multi_winners','root_parents','root_ids','nested_ids','cells','rhs','direct_cells','children','multi','state_sha','scores','singleton_digest','new','visible','physical','commits','birth_digest','endpoint_digest','child_decisions','child_packets')

def check(case,rows):
    b=rows['off']
    for mode in ('learned','all'):
        q=rows[mode]
        for k in fields:assert q[k]==b[k],(case,mode,k)
        assert all(q['checks'].values())
        a=q['tags'];s=q['internal']['counts']
        assert sum(a[0] for a in q['costs_by_rule'].values())==q['tagged']<=sum(q['emitted'])
        assert 0<a[7]<=a[6]<=a[5]<=a[3] and 0<a[2]<=a[1]<=a[0]
        assert q['actual_packet_change']==b['packets']-q['packets']
        assert q['regular_checks']+s['delivered']==b['regular_checks']+b['internal']['counts']['delivered']
        assert q['packets']==sum(q['emitted'])+q['child_packets'] and q['visible_per_packet']==q['visible']/q['packets']
    assert rows['fault']['rejected'] and rows['fault']['runs']<rows['vanilla']['runs']

def run(a):
    a.out.mkdir(parents=True,exist_ok=True);paid=json.loads(a.policy.read_bytes());result={}
    donors={v['sha'] for v in paid['donors'].values()}
    for case in a.cases:
        prog,plan,req=src.config(a,case)
        assert hashlib.sha256(prog.read_bytes()).hexdigest() not in donors
        cfg=training.joint['settings'](req,'filter_mixed')
        rules=json.loads(prog.read_bytes())['recipe']['rules'];ids=[i for i,r in enumerate(rules) if training.key(r) in paid['chosen']]
        modes={'off':dict(cfg),'learned':dict(cfg,paid_families=dict(mode='learned',rules=ids)),
               'all':dict(cfg,paid_families=dict(mode='discovery'))}
        vd=a.exp/'compact-vanilla-20261121'
        with src.base.session(vd/'vanilla-audit',prog) as get:gold=get(dict(audit=True))
        rows={'vanilla':dict(runs=gold['runs'],rhs=gold['rhs_count'],ms=[],wall_ms=[])}
        for mode,request in modes.items():
            with src.base.session(a.native,prog,plan) as get:v=get(dict(request,audit=True,birth_ledger=True))
            assert 'source_error' not in v,(case,mode,v.get('source_error'))
            q=src.base.summarize(v,gold);del q['work'],q['rows']
            b=v['constructor_births'];vis={x[0] for x in b['endpoint'] if x[2]==0};owned={x[0]:x[4] for x in b['rows'] if x[3] and x[7]&1 and x[4]}
            assert set(owned.values())<={x[2] for x in v['root_recipe']['commits']}
            family=v['paid_families'] or {};by=family.get('rules',{});totals=[sum(x[i] for x in by.values()) for i in range(8)]
            child=v['merge_child']['issued'];selected=sum(int(c['selected']) for c in child)
            ext=sum(q['emitted'])+selected;inc=v['integral_root']['counts']
            digest=training.joint['digest'];single=v['single']
            q.update(policy_rule_ids=ids if mode=='learned' else [],new=len(owned),visible=len(owned.keys()&vis),tagged=totals[0],tags=totals,
                     costs_by_rule=by,deep_seen=family.get('deep_seen',0),no_right=family.get('unpaid',0),
                     birth_digest=digest(b['rows']),endpoint_digest=digest(b['endpoint']),singleton_digest=digest(single['committed']),
                     scores=single['adaptive_rows']['decision_digest'],regular_checks=single['work'][2],child_decisions=len(child),child_packets=selected,
                     packets=ext,new_per_packet=len(owned)/ext,visible_per_packet=len(owned.keys()&vis)/ext,
                     if_separate_gate_per_tag=len(owned.keys()&vis)/(ext+totals[0]),internal=v['integral_packets'],
                     total_release_points=inc['point_reads'],regular_point_reads=single['work'][3],primitive_calls=inc['primitives'],ms=[],wall_ms=[])
            q['actual_packet_change']=0 if mode=='off' else rows['off']['packets']-ext
            rows[mode]=q;print(case,mode,q['emitted'],q['packets'],q['visible_per_packet'],'tag/link counts',totals,flush=True)
        with src.base.session(a.native,prog,plan) as get:f=get(dict(modes['learned'],paid_families=dict(mode='learned',rules=ids,wrong_prior=True)))
        rows['fault']=dict(rejected='invalid predecessor on paid producer output' in f.get('source_error',''),error=f.get('source_error'),runs=f['runs'])
        check(case,rows)
        with ExitStack() as st:
            infer=st.enter_context(src.base.session(a.native,prog,plan));exact=st.enter_context(src.base.session(vd/'vanilla',prog));names=['vanilla',*modes]
            for i in range(1+a.repeats):
                order=names[i%len(names):]+names[:i%len(names)]
                for n in order if i%2 else reversed(order):
                    start=perf_counter();v=exact({}) if n=='vanilla' else infer(modes[n]);wall=1000*(perf_counter()-start)
                    assert v['state_sha']==gold['state_sha'] and v['runs']==gold['runs']
                    if n!='vanilla':assert v['root_recipe']['emitted']==rows[n]['emitted'] and v['root_recipe']['allocated']==rows[n]['root_allocated']
                    if i:rows[n]['ms'].append(v['ms']);rows[n]['wall_ms'].append(wall)
        for n in names:rows[n]['median_ms']=median(rows[n]['ms']);rows[n]['median_wall_ms']=median(rows[n]['wall_ms'])
        result[case]=rows;(a.out/'results.json').write_text(json.dumps(result,indent=1)+'\n')
        print(case,[(n,round(rows[n]['median_ms'],2)) for n in names],flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('exp','native','policy','out'):p.add_argument(n,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','3mm']);p.add_argument('--repeats',type=int,default=4)
    run(p.parse_args())
