"""Attribute full frozen inference time on the larger transfer workloads."""
import argparse
import importlib.util
import json
from pathlib import Path
from statistics import median

HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('integrated_port_source',HERE.parent/'integrated-cpu-policy/measure.py')
base=importlib.util.module_from_spec(s);s.loader.exec_module(base)


def run(a):
    a.out.mkdir(parents=True,exist_ok=False);data={};gold=base.read(a.evidence)
    tables=a.exp/'baked-port-packed-study-v1';admission=base.read(HERE.parent/'single-signature-frontier/admission.json')['parameters']
    for case in ('3mm','deriche'):
        b=a.bundles/(case+'-1703');req=base.read(b/'request.json')
        for k in ('single_config','merge_config'):req[k]=str(b/req[k])
        root=a.out/f'{case}-root.json';root.write_text(json.dumps(dict(control='use',forbid_fallback=True,encoding='checked_slots')))
        req.update(root_config=str(root),multi_weights=str(tables/'sum-bits-1703-tied.json'),baked_codes=str(tables/'sum-bits-1703-tied.bin'),
                   packed_lookup=True,baked_row_index=False,radius=0,multi_generation='complete',
                   multi_mode='profilerowdeltapairguardstackseal2xlearned',early_guards='constants',
                   rows=dict(action=4,max_rows=1,workers=1,batch=True,verify=2,prefilter=2,profile=True))
        req=base.query(req,'all',admission)
        req.update(forward=dict(columns=2,budget=4<<20,existence=True,freshness=True,min_candidates=8),atom_constraints=2,
                   tiered_ports=dict(primary=True,columns=True,evidence_views=1,bytes=1<<20))
        samples=[]
        with base.session(a.native,b/'program.json',b/'plans.json') as native:
            for trial in range(4):
                out=native(req);ref=gold[case]['frozen'];assert out['state_sha']==ref['state_sha'] and out['root_recipe']['allocated']==ref['root_allocated']
                if not trial:continue
                multi=out['multi']['rule_profile']
                vals={'inference':out['ms'],**dict(zip(('search','rhs','repair','publication','delivery'),out['phases_ms'],strict=True)),
                      **{k:sum(row[k] for row in multi) for k in ('frame_ms','issuance_ms','validation_ms')}}
                times=out['single']['adaptive_rows']['phase_ns']
                vals.update({k:v/1e6 for k,v in zip(('single_headers','single_score','single_issue'),times[:3])})
                # These inner clocks overlap search. Never sum them with the phase envelope.
                vals['outside_search']=vals['inference']-vals['search']
                samples.append(vals)
        data[case]={'samples':samples,'median_ms':{k:median(v[k] for v in samples) for k in samples[0]},
                    'vanilla_half_ms':gold[case]['vanilla']['median_ms']/2}
        (a.out/'phases.json').write_text(json.dumps(data,indent=1)+'\n');print(case,data[case]['median_ms'],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','bundles','evidence','out'):p.add_argument(k,type=Path)
    run(p.parse_args())
