"""Evaluate two causal Bake rounds and the unrestricted depths on held-out full Pass 3 runs."""
import argparse,hashlib,importlib.util,json
from contextlib import ExitStack
from collections import Counter
from pathlib import Path
from statistics import median
from time import perf_counter
HERE=Path(__file__).resolve().parent
sp=importlib.util.spec_from_file_location('bake_integral',HERE/'bake.py');bake=importlib.util.module_from_spec(sp);sp.loader.exec_module(bake)
src=bake.joint['src'];MODES=('full1','full2','baked1','baked2')
FIELDS=('checks','single_winners','multi_winners','root_parents','root_ids','nested_ids','cells','rhs','direct_cells','children','multi','state_sha','scores','singleton_digest','new','visible','physical','commits','birth_ids','end_ids','child_decisions','children_selected')
def routes(c):
    count={(tuple(tuple(e)for e in k)):n for k,n in c['suppressed']}
    ledger=[];top={}
    for p,(ports,offers,winners) in c['routes']:
        key=tuple(tuple(e)for e in p)
        ledger.append((p,ports,offers,winners,count.get(key,0)))
    for depth in (1,2):top[depth]=sorted((x for x in ledger if len(x[0])==depth),key=lambda x:(-x[-1],-x[-2],x[0]))[:12]
    return dict(attributed=[sum(v for k,v in count.items() if len(k)==i) for i in (1,2)],
                admitted=[sum(a[1] for a in ledger if len(a[0])==i) for i in (1,2)],
                shapes=[sum(len(a[0])==i for a in ledger) for i in (1,2)],offers=c['offers'],credited=c['commits'],
                different_owner=c['different_owner'],second_after_internal=c['second_after_internal'],second_after_external=c['second_after_external'],not_in_library=c['not_in_library'],missing_prior=c['missing_parent'],top=top,route_digest=bake.digest(ledger))
def check(r):
    base=r['full1']
    for n in MODES:
        q=r[n];z=q['chain']
        for k in FIELDS:assert q[k]==base[k],(n,k)
        assert all(q['checks'].values()) and q['native_depths']==base['native_depths'] and q['native_singleton_depths']==base['native_singleton_depths']
        assert q['confirmed']+q['uncommitted']==q['internal']
        assert sum(z['attributed'])+z['different_owner']==q['confirmed']
        assert z['second_after_internal']+z['second_after_external']==z['attributed'][1]
        assert all(a<=b<=c<=d for a,b,c,d in zip(z['attributed'],z['credited'],z['offers'],z['admitted']))
        assert q['total_packets']==sum(q['emitted'])+q['children_selected']
        if n.endswith('1'):assert z['attributed'][1]==z['credited'][1]==0
    assert r['control1']['matched'] and r['wrong_parent']['rejected']==bool(r['full2']['chain']['credited'][1])
def study(a):
    a.out.mkdir(parents=True,exist_ok=True);result={};lib=json.loads(a.library.read_bytes())
    l1=lib['rounds']['1']['selected'];l2=lib['rounds']['2']['selected']
    ds={x['program']for v in lib['rounds'].values()for x in v['donors'].values()}
    for case in a.cases:
        prog,plan,req=src.config(a,case);assert hashlib.sha256(prog.read_bytes()).hexdigest() not in ds
        ids,ix=bake.schema_map(prog);one=bake.relink(l1,ix);two=bake.relink(l2,ix)
        specs={'full1':{'depth':1},'full2':{'depth':2},'baked1':{'depth':1,'library':one},'baked2':{'depth':2,'library':one+two}}
        cfg=bake.joint['settings'](req,'filter_mixed')
        opts={n:dict(cfg,chain=s)for n,s in specs.items()}
        vd=a.exp/'compact-vanilla-20261121'
        with src.base.session(vd/'vanilla-audit',prog) as get:gold=get(dict(audit=True))
        r={'vanilla':dict(rhs=gold['rhs_count'],runs=gold['runs'],ms=[],wall_ms=[])}
        for n,request in opts.items():
            with src.base.session(a.native,prog,plan) as get:v=get(dict(request,audit=True,birth_ledger=True))
            assert 'source_error' not in v,(case,n,v.get('source_error'))
            q=src.base.summarize(v,gold);del q['rows'],q['work']
            actual=[e for run in v['events'] for e in run if e[0]=='resume']
            single_rules={e[2] for e in v['single']['committed']}
            multi_rules={e['rule'] for e in v['multi']['tickets']}
            assert single_rules.isdisjoint(multi_rules) and all(e[4] in single_rules|multi_rules for e in actual)
            assert len(actual)==sum(x[0] for x in gold['resumes'])
            depth_count=dict(Counter(str(e[5])for e in actual));singleton_depth=dict(Counter(str(e[5])for e in actual if e[4] in single_rules))
            b=v['constructor_births'];owned={x[0]:x[4] for x in b['rows'] if x[3] and x[7]&1 and x[4]};vis={x[0] for x in b['endpoint'] if x[2]==0}
            children=v['merge_child']['issued'];nc=sum(int(x['selected'])for x in children)
            ext=sum(q['emitted'])+nc;pkt=v['integral_packets'];c=v['integral_root']['counts'];z=routes(v['integral_root']['chain'])
            q.update(native_depths=depth_count,native_singleton_depths=singleton_depth,chain=z,library=[len(one),len(two)],birth_ids=bake.digest(b['rows']),end_ids=bake.digest(b['endpoint']),
                     child_decisions=len(children),children_selected=nc,new=len(owned),visible=len(owned.keys()&vis),total_packets=ext,
                     new_per_packet=len(owned)/ext,fept=len(owned.keys()&vis)/ext,uncommitted=pkt['uncommitted_internal'],
                     internal=pkt['counts']['delivered'],confirmed=pkt['counts']['confirmed'],regular_checks=v['single']['work'][2],
                     anchor_reads=c['anchor_reads'],point_reads=c['point_reads'],primitives=c['primitives'],ms=[],wall_ms=[],
                     scores=v['single']['adaptive_rows']['decision_digest'],singleton_digest=bake.digest(v['single']['committed']))
            r[n]=q; print(case,n,'matched/actual suppressed',z['credited'],z['attributed'],q['emitted'],q['fept'],flush=True);del v
        for depth,key in [(1,'control1'),(2,'wrong_parent')]:
            with src.base.session(a.native,prog,plan) as get:v=get(dict(cfg,chain=dict(depth=depth,wrong_parent=True)))
            r[key]=dict(rejected='integral certificate owner, Run or binding mismatch' in v.get('source_error',''),error=v.get('source_error'),runs=v['runs'],matched=v.get('state_sha')==gold['state_sha'])
        check(r)
        with ExitStack() as stack:
            native=stack.enter_context(src.base.session(a.native,prog,plan));exact=stack.enter_context(src.base.session(vd/'vanilla',prog));names=['vanilla',*MODES]
            for i in range(a.repeats+1):
                order=names[i%5:]+names[:i%5]
                for n in order if i%2 else reversed(order):
                    t=perf_counter();v=exact({})if n=='vanilla' else native(opts[n]);wall=(perf_counter()-t)*1000
                    assert v['state_sha']==gold['state_sha'] and v['runs']==gold['runs']
                    if n!='vanilla':
                        assert v['root_recipe']['emitted']==r[n]['emitted'] and v['root_recipe']['allocated']==r[n]['root_allocated']
                        assert v['integral_packets']['counts']['confirmed']==r[n]['confirmed']
                    if i:r[n]['ms'].append(v['ms']);r[n]['wall_ms'].append(wall)
        for n in names:r[n]['median_ms']=median(r[n]['ms']);r[n]['median_wall_ms']=median(r[n]['wall_ms'])
        result[case]=r;(a.out/'results.json').write_text(json.dumps(result,indent=1)+'\n')
        print(case,[(n,round(r[n]['median_ms'],2))for n in names],flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('exp','native','library','out'):p.add_argument(n,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','3mm']);p.add_argument('--repeats',type=int,default=4)
    study(p.parse_args())
