"""Exact same-cohort Pass 3 audit + timings, with separately instrumented point reads."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
from statistics import median
import subprocess
import sys

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("hybrid_bench",HERE.parent/'hybrid/bench.py')
hybrid=importlib.util.module_from_spec(spec)
spec.loader.exec_module(hybrid)
WEIGHTS=HERE/'weights.json'

def build_report(root,out):
    if not __debug__ or 'EGGFUSE_PARENT_FINE_TIMING' in os.environ:
        raise ValueError("timed arms require ordinary release execution without per-lookup clocks")
    lanes={'cpu':[],'point':['--unique-parent','point'],'model':['--unique-parent','model','--parent-weights',WEIGHTS],
           'metal':['--unique-parent','metal']}
    hybrid.bench(root,out,lanes,{'point':'cell-cpu-unique-point','model':'cell-cpu-resident-parent-model'})
    samples=hybrid.read(out/'results.json')
    report={'weights_sha256':hybrid.sha(WEIGHTS),'samples_per_arm':8,'cases':{}}
    for case,arms in samples.items():
        result={}
        for lane,arm in arms.items():
            data={k:arm[k] for k in ('audit','program_sha256','state_sha256')}
            data['samples']=[{k:v for k,v in s.items() if k in ('cli_ms','inference_ms','setup_ms')} for s in arm['samples']]
            data['median']={k:median(s[k] for s in data['samples']) for k in data['samples'][0]}
            trace=hybrid.read(out/f'{case}-{lane}-audit/report.json')
            data['backend']=trace['backend']
            if lane!='cpu':
                data['admitted_bindings']=trace['gpu_bindings']['admitted_bindings']
                data['spine_routes']=trace['gpu_bindings']['spine_token_routes']
                data['eligible_rules']=trace['gpu_bindings']['eligible_rules']
            if lane=='metal':
                data['gpu_work']={k:trace['gpu_bindings'][k] for k in ('tested_pairs','device_dispatches','input_rows','request_bytes')}
            if lane in ('point','model'):
                metrics=trace['unique_parent']
                assert not metrics['fine_timing']
                data['counts']={k:v for k,v in metrics.items() if not k.endswith('_seconds') and k not in ('fine_timing','audited_parent_addresses','ambiguous_present_keys','absent_parent_keys','wrong_identical_code','wrong_primary_only','wrong_other_score','true_parent_code_mismatch')}
                if lane=='model':
                    assert metrics['audited_parent_addresses']==metrics['proposals']
                    data['audited_parent_addresses']=metrics['audited_parent_addresses']
                data['profile_ms']=[]
                for repeat in range(5):
                    dest=out/f'{case}-{lane}-profile-{repeat}'
                    subprocess.run([out/'gpu-bindings','--program',root/case/'program.json','--output',dest,*lanes[lane]],check=True,
                                   env=dict(os.environ,EGGFUSE_PARENT_FINE_TIMING='1'),stdout=subprocess.DEVNULL)
                    assert hybrid.sha(dest/'state.json')==data['state_sha256']
                    study=hybrid.read(dest/'report.json')['unique_parent']
                    assert study['fine_timing'] and all(study[k]==v for k,v in data['counts'].items())
                    data['profile_ms'].append({k.removesuffix('_seconds'):1000*v for k,v in study.items() if k.endswith('_seconds')})
            result[lane]=data
        for lane in lanes:
            assert result[lane]['audit']==result['cpu']['audit']
            assert result[lane]['state_sha256']==result['cpu']['state_sha256']
        m=result['model']['counts'];p=result['point']['counts']
        assert m['rule_occurrences']==p['rule_occurrences'] and m['anchors']==p['exact_probes']
        assert m['anchors']==m['verified_parent']+m['fallback_probes']==m['proposals']+m['abstentions']
        assert m['wrong_parent']+m['verified_parent']==m['proposals']
        assert m['bindings']==p['bindings']==m['from_proposal']+m['recovered_wrong_parent']+m['missed_by_abstention']
        assert len({(result[a]['admitted_bindings'],result[a]['spine_routes'],result[a]['eligible_rules']) for a in ('point','model','metal')})==1
        report['cases'][case]=result

    # Force every prediction to abstain. All valid matches must now come from
    # the exact completion path, including positive continuations.
    empty=hybrid.read(WEIGHTS)
    empty['null']=2.
    control=out/'all-null.json'
    control.write_text(json.dumps(empty))
    for case in hybrid.CASES:
        dest=out/f'{case}-null-control'
        subprocess.run([out/'gpu-bindings,slot-transfer-audit','--program',root/case/'program.json','--output',dest,
                        '--unique-parent','model','--parent-weights',control],check=True,stdout=subprocess.DEVNULL)
        oracle=root/f'oracle-{case}'
        for file in ('rhs.json','writes.json','resumes.json','state.json'):
            assert hybrid.sha(dest/file)==hybrid.sha(oracle/file)
        counts=hybrid.read(dest/'report.json')['unique_parent']
        assert counts['proposals']==0 and counts['missed_by_abstention']==counts['bindings']>0
        report['cases'][case]['null_control']={'coverage':counts['missed_by_abstention'],'lookups':counts['fallback_probes'],
                                              'ordered_digests_and_final_state_equal':True}

    sem=out/'semantic'
    sem.mkdir()
    src=root/'native-gpu-sum'
    for name in ('native-source.json','native-legacy.json','native-values.json','sum-legacy','run-values'):
        (sem/name).symlink_to((src/name).resolve())
    (sem/'run-legacy').symlink_to(out/'sum-bits-model-audit')
    subprocess.run([sys.executable,HERE.parents[1]/'marker-handoff/choice_diagnosis.py',sem,sem/'sum-check.json'],check=True)
    for name in ('sum-bits','dot-product','native-gpu-dot'):
        (sem/name).symlink_to(root/name)
    (sem/'export-dot-product').symlink_to(out/'dot-product-model-audit')
    subprocess.run([sys.executable,HERE.parent/'native_accept.py',sem,sem/'dot-check.json'],check=True)
    for n,label in [('sum-bits','sum'),('dot-product','dot')]:
        report['cases'][n]['native_status']=hybrid.read(sem/(label+'-check.json'))['status']
        assert report['cases'][n]['native_status']=='pass'
    (out/'unique-parent.json').write_text(json.dumps(report,indent=1)+'\n')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference',type=Path)
    parser.add_argument('new_output',type=Path)
    a=parser.parse_args()
    build_report(a.reference.resolve(),a.new_output.resolve())
