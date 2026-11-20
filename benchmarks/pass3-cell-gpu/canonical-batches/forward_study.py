"""Isolate inline forward subscription lists while retaining native ordered reverse subscriptions."""
import argparse
from contextlib import ExitStack
import hashlib
import importlib.util
import json,re,subprocess
from pathlib import Path
from statistics import median
from time import perf_counter
HERE=Path(__file__).resolve().parent
sp=importlib.util.spec_from_file_location('integrated_forward',HERE.parent/'integrated-cpu-policy/measure.py')
base=importlib.util.module_from_spec(sp);sp.loader.exec_module(base)
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def run(a):
    a.out.mkdir(parents=True,exist_ok=False);result={}
    adm=base.read(HERE.parent/'single-signature-frontier/admission.json')['parameters']
    if not a.tree.is_file():
        paired=a.compact.parent/'control/session'
        if not paired.is_file():raise FileNotFoundError(f'neither supplied nor paired ordinary control exists: {a.tree}, {paired}')
        print('Using the ordinary binary built by the same paired build:',paired,flush=True)
        a.tree=paired
    provenance={}
    for arm,exe in [('tree',a.tree),('compact',a.compact)]:
        tracked=base.read(exe.parent/'build.json')
        provenance[arm]={'binary_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),'base':tracked['base'],
            'small_forward':tracked['small_forward'],'sources':digest(tracked['sources'])}
    assert provenance['tree']['sources']==provenance['compact']['sources'] and not provenance['tree']['small_forward'] and provenance['compact']['small_forward']
    (a.out/'builds.json').write_text(json.dumps(provenance,indent=1)+'\n')
    for case in a.cases:
        b=a.exp/'extra-pass3-transfer-v1'/f'{case}-1703';p=b/'program.json';w=a.exp/'baked-port-packed-study-v1'
        req=base.read(b/'request.json')
        for k in ('single_config','merge_config'):req[k]=str(b/req[k])
        root=a.out/f'{case}-root.json';root.write_text(json.dumps(dict(control='use',encoding='checked_slots',forbid_fallback=True)))
        req.update(root_config=str(root),multi_weights=str(w/'sum-bits-1703-tied.json'),baked_codes=str(w/'sum-bits-1703-tied.bin'),
                   packed_lookup=True,baked_row_index=False,radius=0,multi_generation='complete',multi_mode='rowdeltapairguardstackseal2xlearned',
                   early_guards='constants',rows=dict(action=4,max_rows=1,workers=1,batch=True,verify=2,prefilter=2))
        req=base.query(req,'all',adm);req.update(forward=dict(columns=2,budget=4<<20,existence=True,freshness=True,min_candidates=8),
           atom_constraints=2,tiered_ports=dict(primary=True,columns=True,evidence_views=1,bytes=1<<20))
        modes={'tree':(a.tree,0,0),'sealed_inputs':(a.tree,0,1),'derived':(a.tree,0,2),'derived_direct':(a.tree,2,2),
               'compact':(a.compact,0,0),'compact_frames':(a.compact,0,2),'compact_both':(a.compact,4,2)}
        binaries={name:settings[0] for name,settings in modes.items()}
        vd=a.exp/'compact-vanilla-20261121'
        with base.session(vd/'vanilla-audit',p) as check:gold=check({'audit':True})
        with ExitStack() as s:
            vanilla=s.enter_context(base.session(vd/'vanilla',p))
            tree=s.enter_context(base.session(a.tree,p,b/'plans.json'));small=s.enter_context(base.session(a.compact,p,b/'plans.json'))
            sessions={name:(tree if binary==a.tree else small) for name,(binary,_,_) in modes.items()}
            arms={'vanilla':dict(ms=[],wall=[],state=gold['state_sha'],rhs=gold['rhs_count'])};com=None
            for arm,call in sessions.items():
                q=dict(req,canon_frame=modes[arm][2],canon_mode=modes[arm][1])
                v=call(dict(q,audit=True,canon_check=True,inspect_subscriptions=True));proof=base.summarize(v,gold)
                identity={k:proof[k] for k in ('rhs','fresh','direct_cells','cells','state_sha','root_ids','nested_ids','single_winners','multi_winners','raw','multi','physical','commits','children')}
                identity.update(per_rhs=digest(v['allocations']),new_cells=v['new_cells'])
                if com is None:com=identity
                else:assert com==identity
                arms[arm]=dict(ms=[],wall=[],phases=[],peak_rss_bytes=[],identity=identity,checks=proof['checks'],subscriptions=v['subscriptions'])
                del v
                diag=call(dict(q,canon_audit=True));arms[arm]['parent_root_phase']=diag['canon_work']['phase'];arms[arm]['extra_contains']=diag['canon_contains'];arms[arm]['frame']=diag['canon_frame']
            names=list(arms)
            for lap in range(5):
                shift=lap%len(names);seq=names[shift:]+names[:shift]
                for arm in reversed(seq) if lap%2 else seq:
                    t=perf_counter();v=vanilla({}) if arm=='vanilla' else sessions[arm](dict(req,canon_frame=modes[arm][2],canon_mode=modes[arm][1]))
                    ms=(perf_counter()-t)*1000.
                    assert v['state_sha']==gold['state_sha'] and v['runs']==gold['runs']
                    if lap:
                        arms[arm]['ms'].append(v['ms']);arms[arm]['wall'].append(ms)
                        if arm!='vanilla':arms[arm]['phases'].append(v['phases_ms'])
        for i in range(2):
            for arm in ('tree','compact') if i else ('compact','tree'):
                q=subprocess.run(['/usr/bin/time','-l',binaries[arm],p,b/'plans.json'],input=json.dumps(req)+'\n',text=True,capture_output=True,check=True)
                assert json.loads(q.stdout)['state_sha']==gold['state_sha']
                rss=re.search(r'(\d+)\s+maximum resident set size',q.stderr);assert rss
                arms[arm]['peak_rss_bytes'].append(int(rss.group(1)))
        for arm,v in arms.items():
            v.update(median_ms=median(v['ms']),median_wall=median(v['wall']))
            if arm!='vanilla':v['phase_medians']=list(map(median,zip(*v['phases'])))
        result[case]=arms;(a.out/'results.json').write_text(json.dumps(result,indent=1)+'\n')
        print(case,[(k,round(v['median_ms'],2),v.get('phase_medians',[])[1:3]) for k,v in arms.items()],flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for f in ('tree','compact','exp','out'):p.add_argument(f,type=Path)
    p.add_argument('--cases',nargs='+',default=['3mm','deriche']);run(p.parse_args())
