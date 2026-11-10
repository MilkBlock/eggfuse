#!/usr/bin/env python3
"""Summarize frozen interleaved state-plan samples; runs no workloads."""
import argparse
import json
import hashlib
from pathlib import Path
from collect_sieve import TIMING

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    p.add_argument('output', type=Path)
    args = p.parse_args()
    root = args.root
    data = json.loads((root / 'timing/samples.json').read_text())
    assert data.get('finished_at_utc') and 'failure' not in data
    assert data['repeat'] == 7 and data['warmups'] == 1
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    old, new = [json.loads((root / f'program-{v}.json').read_text()) for v in ('old', 'selected')]
    plan = new['iterative_bake'].pop('state_plan')
    for v in (old, new): v.pop('sha256')
    assert old == new, 'non-state-plan changes would confound the timing'
    rows = {}
    summary = {'scope':'standalone Cell CPU; normal release sum-bits; not native egglog',
        'baseline':'f4fd21cb (same runtime as 14e112c7)', 'candidate':'575faa4d',
        'repeat':7,'warmups':1,'samples_sha256':sha(root/'timing/samples.json'),
        'state_plan_bytes':len(json.dumps(plan,separators=(',',':')).encode()),
        'eligible_inheritance_states':plan['implementations'].count('inherit'),
        'compiler_diagnostic':json.loads((root/'compile.json').read_text()),
        'semantic_reference':data['semantic_reference'],
        'build_features':'runtime built separately with sparse-cells,view-ports,storage-metrics; ordinary release, no allocation audit',
        'lanes':{},'paired_ratios':{},'execution_order':data['execution_order'],
        'limits':'Single short workload. Inheritance container savings already existed before this change; these timings test overhead, not broader Cell performance.'}
    for lane, v in data['lanes'].items():
        binary = root / ('runtime-baseline' if lane == 'baseline' else 'runtime-candidate')
        program = root / ('program-selected.json' if lane == 'selected' else 'program-old.json')
        assert v['runtime_sha256'] == sha(binary) and v['program_file_sha256'] == sha(program)
        rows[lane] = sorted(v['samples'],key=lambda r:r['iteration'])
        assert [r['iteration'] for r in rows[lane]] == list(range(7))
        assert all(all(r[k] == x for k,x in data['semantic_reference'].items()) for r in rows[lane])
        summary['lanes'][lane] = {'binary_sha256':sha(binary),'program_sha256':sha(program),
            'timing':{k:TIMING['distribution']([r[k] for r in rows[lane]]) for k in ('inference_seconds','process_wall_seconds','load_seconds','setup_seconds')},
            'key_lookup_calls':sorted(set(r['key_lookup_calls'] for r in rows[lane])),
            'samples':[{k:r[k] for k in ('iteration','inference_seconds','process_wall_seconds','load_seconds','setup_seconds')} for r in rows[lane]],
            'warmups':[{k:r[k] for k in ('iteration','inference_seconds','process_wall_seconds')} for r in v['warmup_samples']]}
    for before,after in [('baseline','compatible'),('compatible','selected'),('baseline','selected')]:
        summary['paired_ratios'][after+'/'+before] = {k:TIMING['paired_ratio']([r[k] for r in rows[before]],[r[k] for r in rows[after]]) for k in ('inference_seconds','process_wall_seconds')}
    args.output.write_text(json.dumps(summary,indent=2)+'\n')
