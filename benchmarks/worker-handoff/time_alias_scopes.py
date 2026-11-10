#!/usr/bin/env python3
"""Interleaved short-workload timing of frozen kernels; no compilation/deployment."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import time

TIMING = runpy.run_path(str(Path(__file__).resolve().parents[1]/'raytrace-parallel/collect.py'))
RUN_KEYS = ('ordinal','ruleset','path','iterations','epoch','logical_matches','executed_bindings','changed')
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('baseline','candidate','program','root','output'):
        parser.add_argument('--'+key,type=Path,required=True)
    args=parser.parse_args()
    args.root.mkdir()
    result=dict(scope='standalone Cell CPU sum-bits; paired normal and scoped modes; not native egglog',
                warmups=1,repeat=7,program_sha256=sha(args.program),
                binaries={k:sha(getattr(args,k)) for k in ('baseline','candidate')},modes={})
    for mode, flags in [('normal',[]),('scoped',['--port-scopes'])]:
        rows={k:[] for k in ('baseline','candidate')}
        reference=None
        order=[]
        for iteration in range(-1,7):
            lanes=['baseline','candidate'] if iteration%2==0 else ['candidate','baseline']
            for lane in lanes:
                dest=args.root/f'{mode}-{iteration}-{lane}'
                cmd=[str(getattr(args,lane)), '--program',str(args.program),'--output',str(dest),'--local-congruence',*flags]
                start=time.perf_counter()
                subprocess.run(cmd,env=dict(os.environ,CELL_CPU_HASH_BITS='64'),stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,check=True)
                wall=time.perf_counter()-start
                report=json.loads((dest/'report.json').read_text())
                assert report['status']=='complete'
                semantic=dict(state=sha(dest/'state.json'),runs=[[s[k] for k in RUN_KEYS] for s in report['steps']])
                if reference is None:reference=semantic
                assert semantic==reference
                order.append([iteration,lane])
                rows[lane].append(dict(iteration=iteration,inference_seconds=report['inference_seconds'],
                    process_wall_seconds=wall,load_seconds=report['load_seconds'],setup_seconds=report['setup_seconds']))
        fields=('inference_seconds','process_wall_seconds','load_seconds','setup_seconds')
        result['modes'][mode]=dict(samples=rows,execution_order=order,state_sha256=reference['state'],runs=len(reference['runs']),
            medians={lane:{k:TIMING['distribution']([s[k] for s in samples if s['iteration']>=0]) for k in fields} for lane,samples in rows.items()},
            paired_ratios={k:TIMING['paired_ratio']([s[k] for s in rows['baseline'] if s['iteration']>=0],[s[k] for s in rows['candidate'] if s['iteration']>=0]) for k in fields})
    assert result['binaries']=={k:sha(getattr(args,k)) for k in ('baseline','candidate')}
    result['limits']='One short workload, seven pairs. Wall includes process startup/export/reporting. No repair speedup established from compressed forecast counts.'
    args.output.write_text(json.dumps(result,indent=2)+'\n')
