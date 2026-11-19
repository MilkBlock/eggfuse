"""Back-to-back batch-one timings of identical policies with dense or early-return Metal rows."""
import argparse
import json
from pathlib import Path
import time
import numpy as np
import torch

from evaluate import Lane, make_lanes, models_for, transfer, compact_output, on_host, fingerprints, timed_indices
from gate_data import templates,fresh_panel
from encoder import EClassSchema


def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('parent',type=Path);a=p.parse_args()
    if not torch.backends.mps.is_available():raise RuntimeError('MPS required')
    config=json.loads((a.root/'calibration.json').read_text());ts=templates()
    schema=EClassSchema([t for t in ts if t['split']=='train']);dev=torch.device('mps')
    models,_=models_for(a.root,a.parent,schema,dev)
    lanes=make_lanes(config);pick=('all','none','p0-calibrated','p25-calibrated','p25-default')
    chosen={l.name:l for l in lanes if l.policy in pick and l.backend in ('metal_dense','metal_skip')}
    data={};results={}
    with torch.inference_mode():
        for ordinal,t in enumerate(x for x in ts if x['split']=='heldout'):
            tid=t['id'];d=fresh_panel(t);bank=schema.bank(t,'pairwise',dev)
            tables={n:m.encoder.frozen_bank(bank) for n,m in models.items()}
            # One entire targeted and one entire blind group from the original timing sample.
            idx=timed_indices(d,ordinal);used=[]
            for blind in (False,True):
                candidate=next(i for i in idx if bool(d['blind'][i])==blind)
                used.extend(np.flatnonzero(d['group_id']==d['group_id'][candidate]).tolist())
            def run(l,i):
                out=l.calls(models[l.treatment],transfer(d,slice(i,i+1),dev),tables[l.treatment])
                torch.mps.synchronize()
                return out
            for lane in chosen.values():
                for i in used[:3]:run(lane,i)
            cases=[(policy,seed) for policy in pick for seed in (1703,1709)]
            timings={f'{policy}-{seed}':[] for policy,seed in cases}
            for repeat in range(3):
                for sample,i in enumerate(used):
                    offset=(repeat+sample+ordinal)%len(cases)
                    for j,(policy,seed) in enumerate(cases[offset:]+cases[:offset]):
                        order=('metal_dense','metal_skip') if (repeat+sample+j)%2==0 else ('metal_skip','metal_dense')
                        ms={};outs={}
                        for backend in order:
                            l=chosen[f'{policy}-{backend}-{seed}'];start=time.perf_counter_ns()
                            out=run(l,i);ms[backend]=(time.perf_counter_ns()-start)/1e6;outs[backend]=compact_output(out,full=False)
                        if repeat==0:
                            assert fingerprints(on_host(outs['metal_dense']))==fingerprints(on_host(outs['metal_skip']))
                        timings[f'{policy}-{seed}'].append(dict(index=i,repeat=repeat,first=order[0],**ms))
            data[tid]=timings
    for key in next(iter(data.values())):
        rows=[item for by_policy in data.values() for item in by_policy[key]]
        # Average repeats for the same source before comparing; percentiles are descriptive.
        grouped=[]
        for panel in data.values():
            by_index={}
            for item in panel[key]:
                by_index.setdefault(item['index'],[]).append(item['metal_dense']-item['metal_skip'])
            grouped.extend(float(np.median(x)) for x in by_index.values())
        results[key]=dict(pairs=len(rows),unique_per_policy=len(grouped),
              dense_median_ms=float(np.median([r['metal_dense'] for r in rows])),
              skip_median_ms=float(np.median([r['metal_skip'] for r in rows])),
              median_source_paired_saving_ms=float(np.median(grouped)),
              positive_sources=sum(x>0 for x in grouped),paired_quartiles=np.percentile(grouped,[25,75]).tolist())
    (a.root/'timing-pairs.json').write_text(json.dumps(dict(method='Three back-to-back repeats per input; paired order alternates. Positive difference means early return saved wall time.',summary=results,samples=data),separators=(',',':'))+'\n')
    print(results,flush=True)

if __name__=='__main__':main()
