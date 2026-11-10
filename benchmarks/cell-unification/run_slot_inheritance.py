#!/usr/bin/env python3
"""Verify frozen sum-bits slot layouts, work costs and native contract; no timing."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from check_links import load, sha
from check_alias_routes import same_execution, clean
from check_mixed_outputs import differences


def run(args):
    root=args.root.resolve()
    root.mkdir()
    for name,source in [('runtime-baseline',args.baseline),('runtime-candidate',args.runtime),('bake-state-plan',args.emitter),('compare-work',args.ledger)]:
        shutil.copy2(source,root/name)
    shutil.copy2(args.program,root/'program-old.json')
    for name,mode in [('program.json',[]),('program-materialized.json',['materialize'])]:
        subprocess.run([str(root/'bake-state-plan'),str(root/'program-old.json'),str(root/name),str(root/(name+'.audit')), *mode],check=True)
    records=[]
    programs={ 'baseline':'program-old.json','materialized':'program-materialized.json','candidate':'program.json' }
    for lane,program in programs.items():
        binary=root/('runtime-baseline' if lane=='baseline' else 'runtime-candidate')
        argv=[str(binary),'--program',str(root/program),'--output',str(root/f'run-{lane}'),'--local-congruence']
        with (root/f'{lane}.log').open('w') as log:
            subprocess.run(argv,env=dict(os.environ,CELL_CPU_HASH_BITS='64'),stdout=log,stderr=subprocess.STDOUT,check=True)
        records.append(dict(argv=argv,binary_sha256=sha(binary),program_sha256=sha(root/program)))
    result=same_execution([root/f'run-{v}' for v in programs],[root/p for p in programs.values()])
    parsed=[load(root/p) for p in programs.values()]
    for p in parsed:
        p.pop('sha256')
        p['iterative_bake'].pop('state_plan',None)
    assert parsed[0]==parsed[1]==parsed[2]
    a,b=[load(root/f'run-{v}/report.json') for v in ('materialized','candidate')]
    values=[clean(p) for p in (a,b)]
    for v in values:v.pop('program_sha256')
    changed=differences(*values)
    allowed={'/stage_spine/stats/'+k for k in ('history_capture_reads','history_slots_written','history_heap_frames','history_inheritance_marks','history_inherited_reads','history_inherited_slots')}
    allowed |= {k for k in changed if k.startswith('/stage_spine/published_history_storage/')}
    assert changed.keys()<=allowed,changed
    subprocess.run([str(root/'compare-work'),str(root/'run-materialized/report.json'),str(root/'run-candidate/report.json'),str(root/'credit.json')],check=True)
    credit=load(root/'credit.json')
    assert credit['net_saved_operations']>0
    plan=load(root/'program.json')['iterative_bake']['state_plan']
    layouts=[dict(state=i,rule=c['activation']['rule'],slots=c['slot_layout']) for i,c in enumerate(plan['contracts']) if c.get('exports')]
    assert len(layouts)==13 and sum(any(s['inherit'] for s in c['slots']) for c in layouts)==8
    native=args.native_reference.resolve()
    (root/'semantic').mkdir()
    for name,target in {'native-source.json':native/'native-source.json','native-legacy.json':native/'native-marked.json',
        'native-values.json':native/'native-marked.json','sum-legacy':native/'sum','run-legacy':root/'run-baseline','run-values':root/'run-candidate'}.items():
        (root/'semantic'/name).symlink_to(target)
    subprocess.run(['python3','benchmarks/marker-handoff/choice_diagnosis.py',str(root/'semantic'),str(root/'semantic-acceptance.json')],check=True)
    assert load(root/'semantic-acceptance.json')['status']=='pass'
    result.update(scope='standalone Cell CPU; work and semantic diagnostics, no timing or total allocator measurement',
        materialized_control='same kernel, all state choices materialize; provenance recording disabled',
        changed_work=changed,work_credit=credit,layouts=layouts,runs_manifest=records,
        report_hashes={v:sha(root/f'run-{v}/report.json') for v in programs},
        sources=dict(baseline_binary=sha(args.baseline),candidate_binary=sha(args.runtime),input_program=sha(args.program)),
        resource_costs=dict(result_frame_bytes=b['stage_spine']['history_result_frame_bytes'],
            effect_plan_slot_bytes=b['stage_spine']['effect_plan_slot_bytes'],
            published_history_storage={name:r['stage_spine']['published_history_storage'] for name,r in [('materialized',a),('candidate',b)]}),
        limits='Source witnesses retain all ordinary validation. Old-owner projection changes and widths above 64 materialize affected fields. Parents are leaf owners; no transitive runtime chain or runtime layout allocation. Published storage counts unique reachable owners, retained parents and referenced shared layouts, including array capacities and estimated Rc headers; excludes allocator rounding, pending work, unreferenced compiled layouts and unrelated graph storage. Bitmap arithmetic and byte costs are not calibrated by equal-weight Work. No speed or whole-process memory gain claimed.')
    (root/'check.json').write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('root','baseline','runtime','program','emitter','ledger','native-reference'):
        p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
