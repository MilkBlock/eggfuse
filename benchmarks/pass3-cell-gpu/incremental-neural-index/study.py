"""Replay full source passes, audit distinct tickets and root allocations, and interleave resident timings."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from statistics import median
import subprocess
import sys
from time import perf_counter_ns

HERE=Path(__file__).resolve().parent
base_spec=importlib.util.spec_from_file_location('root_audit',HERE.parent/'joint-root-cells/study.py')
base=importlib.util.module_from_spec(base_spec);base_spec.loader.exec_module(base)
read=base.read


def study(a):
    a.out.mkdir(parents=True,exist_ok=False)
    report={}
    for case in a.cases:
        anchor=case in ('sum-bits','dot-product')
        program=a.ref/case/'program.json' if anchor else a.corpus/case/'program.json'
        image=a.ref/f'release-input-{case}' if anchor else a.corpus/case/'input'
        reference=a.ref/f'events-{case}' if anchor else a.corpus/case/'observation'
        expected_hash=hashlib.sha256((reference/'state.json').read_bytes()).hexdigest()
        plans=base.joint.sealed_plans(image)
        path=a.out/f'{case}-plans.json';path.write_text(json.dumps(plans,separators=(',',':')))
        proc=subprocess.Popen([a.binary,program,path],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            for seed in a.seeds:
                for regime in a.regimes:
                    single=a.out/f'{case}-{seed}-{regime}-single.json'
                    config=read(HERE.parent/'single-witness'/f'{regime}-{seed}.json')
                    config.update(mode='learned',residual=regime!='certified')
                    single.write_text(json.dumps(config))
                    merge=a.out/f'{case}-{seed}-merge.json'
                    weights=read(HERE.parent/'joint-witness/weights'/f'nested-{seed}.json')
                    merge.write_text(json.dumps(dict(program_sha256=read(program)['sha256'],weights=weights['weights'],control='learned')))
                    root=a.out/f'{case}-{seed}-{regime}-root.json';root.write_text(json.dumps(dict(control='use',forbid_fallback=regime=='certified')))
                    options=dict(single_config=str(single),multi_weights=str(HERE.parent/'ordinary-witness'/f'weights-{seed}.json'),
                                 merge_config=str(merge),root_config=str(root),radius=2,cap=1000000,multi_residual=False)
                    scenarios={'exact':dict(baseline=True)}
                    scenarios.update({m:dict(options,multi_mode=m) for m in a.modes})
                    measured={}; prior=None
                    for arm,req in scenarios.items():
                        if arm=='exact':
                            measured[arm]=dict(ms=[],wall_ms=[]);continue
                        r=base.joint.rpc(proc,dict(req,audit=True))
                        observed=base.audit(r,case,a,plans,'use')
                        assert r['state_sha']==expected_hash and observed['neural_rhs']>=.98*observed['rhs']
                        assert observed['direct_distinct']>=.98*observed['fresh']
                        compare={k:observed[k] for k in ('root_proposal_hash','multi_raw_hash','merge_gate_hash','allocation_sha',
                                                         'root_allocations_sha','root_commits_sha','neural_rhs','direct_distinct')}
                        if prior is not None and not a.different_tokens:assert compare==prior,(case,seed,arm,compare,prior)
                        prior=compare
                        measured[arm]=dict(ms=[],wall_ms=[],audit=observed,counters=r['multi']['counts'],
                                           memo=r['multi']['shortlist'],raw_cache=r['multi']['raw_cache'],pair_stats=r['multi'].get('pair_stats',{}),delta=r['multi'].get('delta_stats',{}),signature_stats=r['multi'].get('signature_stats',{}))
                    order=list(scenarios)
                    for i in range(a.repeats+len(order)):
                        seq=order[i%len(order):]+order[:i%len(order)]
                        for arm in seq if i%2==0 else seq[::-1]:
                            start=perf_counter_ns();r=base.joint.rpc(proc,dict(scenarios[arm],audit=False))
                            wall=(perf_counter_ns()-start)/1e6
                            assert r['state_sha']==expected_hash
                            if arm!='exact':
                                obs=measured[arm]['audit'];assert obs['neural_rhs']==len(r['single']['committed'])+r['multi']['neural_committed']
                                assert obs['direct_roots']==r['root_recipe']['allocated'] and obs['direct_children']==r['merge_child']['counts'][5]
                            if i>=len(order):measured[arm]['ms'].append(r['ms']);measured[arm]['wall_ms'].append(wall)
                    for v in measured.values():v.update(median_ms=median(v['ms']),median_wall_ms=median(v['wall_ms']))
                    report[f'{case}/{seed}/{regime}']=measured
                    (a.out/'results.json').write_text(json.dumps(report,indent=1)+'\n')
                    print(case,seed,regime,[(k,round(v['median_ms'],2),v.get('raw_cache',{}).get('cache_hits')) for k,v in measured.items()],flush=True)
        finally:
            proc.stdin.close();proc.wait()
            if proc.returncode:raise RuntimeError(proc.stderr.read().decode()[-2048:])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('binary','ref','corpus','capture','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','gemm-bias-relu','stable-argmax'])
    p.add_argument('--seeds',type=int,nargs='+',default=[1703,1709])
    p.add_argument('--regimes',nargs='+',default=['certified'])
    p.add_argument('--modes',nargs='+',default=['stackseal3xlearned','tuplememostackseal3xlearned'])
    p.add_argument('--repeats',type=int,default=8)
    p.add_argument('--different-tokens',action='store_true')
    study(p.parse_args())
