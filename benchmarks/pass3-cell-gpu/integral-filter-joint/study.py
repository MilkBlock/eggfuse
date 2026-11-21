"""Interleave exact scalar omissions and integral lanes under the original native Run schedule."""
import argparse,hashlib,importlib.util,json
from contextlib import ExitStack
from pathlib import Path
from statistics import median
from time import perf_counter
HERE=Path(__file__).resolve().parent
sp=importlib.util.spec_from_file_location('profile_loader',HERE.parent/'pair-source-frontier/profile.py');src=importlib.util.module_from_spec(sp);sp.loader.exec_module(src)
MODES=('raw_external','raw_closed','filter_external','filter_closed','filter_mixed')
IDENTITY=('checks','single_winners','multi_winners','root_parents','root_ids','nested_ids','cells','rhs','direct_cells','children','multi','state_sha','scores','all_single','owned_births','visible','endpoint_ids','constructor_ids','merge_decisions','selected_child')
def settings(req,mode):
    scalar,kind=mode.split('_')
    if scalar not in ('raw','filter') or kind not in ('external','closed','mixed'):raise ValueError(mode)
    return dict(req,header_mode=3,derived_ports=dict(mode=1,cache=True),lazy_equations=4,multi_page_tuples=8192,proposal_wave=65536,integral_root='apply',rows=dict(req['rows'],scalar_certificates=scalar=='filter'),integral_packets=kind!='external',integral_mixed=kind=='mixed')

def digest(x):return hashlib.sha256(json.dumps(x,separators=(',',':'),sort_keys=True).encode()).hexdigest()
def check(rows):
    for mode in MODES:
        q=rows[mode];base=rows[mode.split('_')[0]+'_external']
        assert all(q[k]==rows['raw_external'][k] for k in IDENTITY),mode
        assert all(q['checks'].values()) and q['aligned']
        for k in ('physical','commits','root_births','negatives','audited_negatives'):
            assert q[k]==base[k],(mode,k)
        assert q['negatives']==q['audited_negatives']
        if mode.startswith('filter'):assert q['negatives'] and rows['raw_external']['emitted'][0]-rows['filter_external']['emitted'][0]==q['negatives']
        if mode.endswith('external'):continue
        c=q['internal']['counts']
        assert c['delivered']==c['original_checks']==c['closed_lanes']+c['mixed_lanes']>0
        assert c['delivered']==c['confirmed']+q['internal']['uncommitted_internal']
        assert base['emitted'][0]-q['emitted'][0]==base['regular_verifications']-q['regular_verifications']==c['delivered']
        assert base['emitted'][1]==q['emitted'][1]
        if mode.endswith('mixed'):assert c['mixed_lanes']>0 and c['mixed_banks']==c['ordered_merges']
    assert rows['filter_mixed']['emitted'][0]<rows['filter_closed']['emitted'][0]
    for kind in ('stale','order'):assert rows['faults'][kind]['rejected'],kind

def run(a):
    a.out.mkdir(parents=True,exist_ok=True);report={}
    for case in a.cases:
        prog,plan,req=src.config(a,case)
        modes={k:settings(req,k) for k in MODES};vd=a.exp/'compact-vanilla-20261121'
        with src.base.session(vd/'vanilla-audit',prog) as get:gold=get(dict(audit=True))
        rows={'vanilla':dict(runs=gold['runs'],rhs=gold['rhs_count'],ms=[],wall_ms=[])}
        for mode,request in modes.items():
            with src.base.session(a.native,prog,plan) as get:v=get(dict(request,audit=True,birth_ledger=True))
            assert 'source_error' not in v,(case,mode,v.get('source_error'))
            q=src.base.summarize(v,gold);del q['work'],q['rows']
            b=v['constructor_births'];vis={x[0] for x in b['endpoint'] if x[2]==0};roots=v['root_recipe']
            owned={x[0]:x[4] for x in b['rows'] if x[3] and x[7]&1 and x[4]};rr={x[2] for x in roots['commits']};assert set(owned.values())<=rr
            counts=v['single']['adaptive_rows']['scalar_certificates'];children=v['merge_child']['issued']
            q.update(negatives=sum(x['missing']+x['stale'] for x in counts),audited_negatives=sum(x['audited'] for x in counts),
                     owned_births=len(owned),visible=len(owned.keys()&vis),constructor_ids=digest(sorted(owned)),endpoint_ids=digest(sorted(vis)),
                     root_births=digest(sorted(owned.items())),selected_child=sum(int(x['selected'])for x in children),merge_decisions=len(children),
                     internal=v['integral_packets'],integral=v['integral_root']['counts'],regular_verifications=v['single']['work'][2],
                     scores=v['single']['adaptive_rows']['decision_digest'],all_single=digest(v['single']['committed']),ms=[],wall_ms=[])
            q['packets']=sum(q['emitted'])+q['selected_child']
            q['new_per_packet']=q['owned_births']/q['packets'];q['visible_per_packet']=q['visible']/q['packets']
            rows[mode]=q;print(case,mode,q['emitted'],q['negatives'],q['internal'] and q['internal']['counts'],flush=True);del v
        rows['faults']={}
        for kind,(field,msg) in {'stale':('integral_release_fault','integral release epoch or watermark mismatch'),
                                'order':('mixed_order_fault','integral packet lanes lost their committed source order')}.items():
            with src.base.session(a.native,prog,plan) as infer:v=infer(dict(modes['filter_mixed'],**{field:True}))
            rows['faults'][kind]=dict(rejected=msg in v.get('source_error',''),error=v.get('source_error'),runs=v['runs'])
        check(rows)
        with ExitStack() as ctx:
            infer=ctx.enter_context(src.base.session(a.native,prog,plan));vanilla=ctx.enter_context(src.base.session(vd/'vanilla',prog))
            names=['vanilla',*modes]
            for i in range(1+a.repeats):
                seq=names[i%len(names):]+names[:i%len(names)]
                for mode in seq if i%2 else reversed(seq):
                    start=perf_counter();v=vanilla({}) if mode=='vanilla' else infer(modes[mode]);wall=(perf_counter()-start)*1000
                    assert v['state_sha']==gold['state_sha'] and v['runs']==gold['runs']
                    if mode!='vanilla':
                        assert v['root_recipe']['emitted']==rows[mode]['emitted'] and v['root_recipe']['allocated']==rows[mode]['root_allocated']
                        if mode.endswith(('mixed','closed')):assert v['integral_packets']['counts']['confirmed']==rows[mode]['internal']['counts']['confirmed']
                    if i:rows[mode]['ms'].append(v['ms']);rows[mode]['wall_ms'].append(wall)
        for n in names:rows[n]['median_ms']=median(rows[n]['ms']);rows[n]['median_wall_ms']=median(rows[n]['wall_ms'])
        report[case]=rows;(a.out/'results.json').write_text(json.dumps(report,indent=1)+'\n')
        print(case,[(n,round(rows[n]['median_ms'],2))for n in names],flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','3mm']);p.add_argument('--repeats',type=int,default=4)
    run(p.parse_args())
