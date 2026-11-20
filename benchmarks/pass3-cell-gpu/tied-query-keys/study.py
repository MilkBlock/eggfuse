"""Separate what the pointer learns from what the compiler proves about equal-valued ports."""
import argparse
import hashlib
import json
from pathlib import Path
from statistics import median
import subprocess
import sys
import numpy as np

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'joint-witness'))
from evaluate import audit,read,rpc,sealed_plans


def checkpoint(path,arm):
    model=read(path)
    if arm=='original' or arm=='asymmetric-zero':return model
    q=np.array(model['q'],np.float32);k=np.array(model['k'],np.float32)
    if arm in ('tied-one','tied-three'):shared=(q+k)*.5
    elif arm=='fixed-bits':shared=np.eye(*q.shape,dtype=np.float32)
    else:raise ValueError(arm)
    # The two sides read exactly the same bipolar encoding of a canonical typed value.
    # Equal values therefore necessarily agree on every output bit without any radius search.
    model['q']=shared.tolist();model['k']=shared.tolist()
    return model


def main(a):
    a.out.mkdir(parents=True,exist_ok=False);results={}
    for name in ('sum-bits','dot-product','gemm-bias-relu','stable-argmax'):
        anchor=name in ('sum-bits','dot-product')
        prog=a.ref/name/'program.json' if anchor else a.corpus/name/'program.json'
        image=a.ref/f'release-input-{name}' if anchor else a.corpus/name/'input'
        baseline=a.ref/f'events-{name}' if anchor else a.corpus/name/'observation'
        digest=hashlib.sha256((baseline/'state.json').read_bytes()).hexdigest()
        plans=sealed_plans(image);plan=a.out/f'{name}-plans.json';plan.write_text(json.dumps(plans))
        proc=subprocess.Popen([a.binary,prog,plan],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            for seed in (1703,1709):
                single=a.out/f'{name}-{seed}-single.json';config=read(HERE.parent/'single-witness'/f'certified-{seed}.json')
                config.update(residual=False,mode='learned');single.write_text(json.dumps(config))
                merge=a.out/f'{name}-{seed}-merge.json';gate=read(HERE.parent/'merge-result-port'/f'gate-{seed}.json')
                merge.write_text(json.dumps(dict(program_sha256=read(prog)['sha256'],weights=gate['weights'],control='learned')))
                reqs={};report={}
                for arm in ('original','asymmetric-zero','tied-one','tied-three','fixed-bits'):
                    file=a.out/f'{seed}-{arm}-weights.json'
                    file.write_text(json.dumps(checkpoint(HERE.parent/'ordinary-witness'/f'weights-{seed}.json',arm)))
                    mode='stackseal3xlearned' if arm in ('original','tied-three','fixed-bits') else 'stackseallearned'
                    arm_single=single
                    if arm=='asymmetric-zero':
                        arm_single=a.out/f'{name}-{seed}-{arm}-single.json'
                        arm_single.write_text(json.dumps(dict(config,complete_unsupported=True)))
                    req=dict(audit=True,multi_weights=str(file),single_config=str(arm_single),merge_config=str(merge),
                             multi_mode=mode,multi_residual=arm=='asymmetric-zero',radius=2 if arm=='original' else 0,cap=1000000)
                    v=rpc(proc,req)
                    ev=audit(v,name,a.ref,a.corpus,a.capture,plans,'learned',mode)
                    assert ev['aligned']
                    # Fixed projections are a deterministic control despite sharing the same execution code.
                    ev['learned_multi_credit']=0 if arm=='fixed-bits' else ev['neural_multi']
                    ev['deterministic_pointer_rhs']=ev['neural_multi'] if arm=='fixed-bits' else 0
                    if arm=='fixed-bits':
                        ev['joint_credit_includes_deterministic_control']=ev['total_attributed']
                        ev['deterministic_multi_rhs']=ev['neural_multi'];ev['neural_multi']=0
                        ev['neural_rhs_including_single']=ev['neural_single']
                        ev['total_attributed']=ev['neural_single'];ev['uncredited']=ev['source_rhs']-ev['neural_single']
                        ev['verified_source_coverage']=ev['neural_single']/ev['source_rhs'];ev['valid_98']=False
                        ev['pass_without_zero_witness']=False
                    ev['ms']=[];reqs[arm]=dict(req,audit=False);report[arm]=ev
                reqs['exact']=dict(baseline=True,audit=False);report['exact']=dict(ms=[])
                order=list(reqs)
                for i in range(8):
                    seq=order[i%6:]+order[:i%6]
                    for arm in (seq if i%2==0 else seq[::-1]):
                        v=rpc(proc,reqs[arm]);assert v['state_sha']==digest
                        if arm!='exact':assert v['multi']['counts']['committed']==report[arm]['multi_work']['committed']
                        if i>=2:report[arm]['ms'].append(v['ms'])
                for ev in report.values():ev['median_ms']=median(ev['ms'])
                results[f'{name}/{seed}']=report;(a.out/'results.json').write_text(json.dumps(results,indent=1)+'\n')
                print(name,seed,[(k,v.get('multi_work',{}).get('raw_tuples'),round(v['median_ms'])) for k,v in report.items()],flush=True)
        finally:proc.stdin.close();proc.wait()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('binary','ref','corpus','capture','out'):p.add_argument(k,type=Path)
    main(p.parse_args())
