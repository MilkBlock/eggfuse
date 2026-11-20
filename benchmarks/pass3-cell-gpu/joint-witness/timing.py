"""Paired full source timings and a graph/state check for each actual learned or unassisted CPU pass."""
import argparse
import hashlib
import json
from pathlib import Path
from statistics import median
import subprocess
from time import perf_counter_ns
from evaluate import read,rpc, sealed_plans


def main(a):
    a.out.mkdir(parents=True,exist_ok=False);results={}
    for case in a.cases:
        anchor=case in ('sum-bits','dot-product')
        prog=a.ref/case/'program.json' if anchor else a.corpus/case/'program.json'
        im=a.ref/f'release-input-{case}' if anchor else a.corpus/case/'input'
        gold=a.ref/f'events-{case}' if anchor else a.corpus/case/'observation'
        digest=hashlib.sha256((gold/'state.json').read_bytes()).hexdigest()
        plan=a.out/f'{case}-plans.json';plan.write_text(json.dumps(sealed_plans(im)))
        proc=subprocess.Popen([a.binary,prog,plan],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            for seed in (1703,1709):
                modes={'exact':dict(baseline=True,audit=False)}
                for cutoff in (('high','certified') if a.primary else ('high','balanced')):
                    config=a.single/f'{seed}-{cutoff}.json'
                    if a.primary:
                        config=a.out/f'{case}-{seed}-{cutoff}-policy.json'
                        ck=read(Path(__file__).resolve().parents[1]/'single-witness'/f'{cutoff}-{seed}.json')
                        ck.update(mode='learned',residual=cutoff!='certified');config.write_text(json.dumps(ck))
                    modes[cutoff]=dict(single_config=str(config),multi_mode='stackseal3xlearned' if a.shortlist else 'seal3xlearned',radius=2,cap=1000000,
                        multi_weights=str(a.multi/str(seed)/'model.json'),multi_residual=False,audit=False)
                    if a.primary:
                        gate=read(Path(__file__).resolve().parents[1]/'merge-result-port'/f'gate-{seed}.json')
                        merge=a.out/f'{case}-{seed}-child.json'
                        merge.write_text(json.dumps(dict(program_sha256=read(prog)['sha256'],weights=gate['weights'],control='learned')))
                        modes[cutoff]['merge_config']=str(merge)
                group={k:dict(ms=[],request_ms=[]) for k in modes}
                order=list(modes)
                for trial in range(8):
                    seq=order[trial%3:]+order[:trial%3]
                    for mode in seq if trial%2==0 else seq[::-1]:
                        start=perf_counter_ns();observed=rpc(proc,modes[mode]);request_ms=(perf_counter_ns()-start)/1e6
                        assert observed['state_sha']==digest
                        if mode!='exact':
                            single=observed['single'];multi=observed['multi'];assert single['rhs']==multi['total_rhs']
                            n=len(single['committed'])+multi['neural_committed']
                            assert n==group[mode].get('learned_rhs',n);group[mode]['learned_rhs']=n
                        if trial>=2:
                            group[mode]['ms'].append(observed['ms']);group[mode]['request_ms'].append(request_ms)
                for v in group.values():v['median_ms']=median(v['ms']);v['median_request_ms']=median(v['request_ms'])
                results[f'{case}/{seed}']=group
                (a.out/'results.json').write_text(json.dumps(results,indent=1)+'\n')
        finally:
            proc.stdin.close();proc.wait()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('binary','ref','corpus','single','multi','out'):p.add_argument(k,type=Path)
    p.add_argument('--primary',action='store_true')
    p.add_argument('--shortlist',action='store_true')
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','gemm-bias-relu','stable-argmax'])
    main(p.parse_args())
