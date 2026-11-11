#!/usr/bin/env python3
"""Read allocation diagnostics; never run or time a workload."""
import json
from pathlib import Path
import runpy
import sys

h=runpy.run_path(str(Path(__file__).parents[1]/'cell-column-influence/collect.py'))
read,sha,signature=(h[k] for k in ('read','sha','signature'))

def collect(root,output):
    prior=read(Path(__file__).parents[1]/'cell-column-influence/dispatch.json')
    result={'baseline_commit':'5197c099','scope':'standalone Cell CPU; allocation diagnostic, no timing',
        'binary_sha256':[sha(root/n) for n in ['control','runtime']], 'cases':{}}
    for case in ['sum','ray1280']:
        before,after=[root/(case+'-'+m) for m in ['before','after']]
        a,b=[read(p/'report.json') for p in [before,after]]
        assert sha(before/'state.json')==sha(after/'state.json')==prior['cases'][case]['state_sha256']
        assert signature(a)==signature(b)==prior['cases'][case]['ordered_run_sha256']
        for key in ['stats','sieve','free_join','entry_schedule','indexed_columns','publication','key_lookup_calls']:
            assert a[key]==b[key],(case,key)
        result['cases'][case]={'state_sha256':sha(after/'state.json'),'ordered_run_sha256':signature(b),
            'reports_sha256':[sha(p/'report.json') for p in [before,after]],
            'allocations':[r['allocations'] for r in [a,b]], 'remaining_work_and_effects_equal':True}
    assert read(root/'semantic-acceptance.json')['status']=='pass'
    assert sha(root/'semantic/run-values/state.json')==result['cases']['sum']['state_sha256']
    result['native_sum_acceptance_sha256']=sha(root/'semantic-acceptance.json')
    output.write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':
    if not __debug__: raise SystemExit('run without -O')
    collect(*map(Path,sys.argv[1:]))
