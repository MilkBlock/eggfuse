"""Same 24-wave learned source prefix and same coverage predicate on CPU and MPS."""
import argparse
import ctypes
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from statistics import median
from time import perf_counter_ns

import numpy as np
import torch

from certificate import require
from learned_proposal import BUDGET,Pointer,generate,load_case

HERE=Path(__file__).resolve().parent


class Checker:
    def __init__(self,graph,plan,shader,native,device):
        self.device=device
        self.graph=graph.to(device)
        config=[len(graph),plan.initial_value,plan.increment]
        self.config=torch.tensor(config,device=device,dtype=torch.int64)
        self.flags=torch.empty((len(graph),2),device=device,dtype=torch.int32)
        self.shader=shader
        self.native=native

    def __call__(self,tokens):
        # Moves are charged to the caller for the mixed-device ablations.
        actual=tokens.to(self.device).contiguous()
        if self.device=='cpu':
            self.native(self.graph.data_ptr(),actual.data_ptr(),self.config.data_ptr(),self.flags.data_ptr())
        else:
            self.shader.certify(self.graph,actual,self.config,self.flags,threads=len(self.graph))
        # The public result is a host-visible verdict in all arms.
        return tuple(map(int,self.flags.cpu().numpy().sum(axis=0)))


def native_checker(folder):
    lib=folder/'check.dylib'
    subprocess.run(['clang++','-std=c++17','-O3','-dynamiclib','-DEGGFUSE_CPU_CHECK','-x','c++',
                    str(HERE/'coverage.metal'),'-o',str(lib)],check=True)
    symbol=ctypes.CDLL(str(lib)).certify_cpu
    symbol.argtypes=[ctypes.c_void_p]*4
    symbol.restype=None
    return symbol


def negative_controls(checkers,raw):
    edits={'intact':raw}
    has_child={p for p in raw[:,2]}
    terminal=next(i for i in range(1,len(raw)) if i not in has_child)
    for label,i,k,value in [('missing',terminal,0,0),('wrong-depth',terminal,3,0),
                            ('wrong-value',terminal,4,10001),('invalid-address',terminal,2,len(raw))]:
        edit=raw.copy();edit[i,k]=value;edits[label]=edit
    reports={}
    for name,arr in edits.items():
        values=[c(torch.from_numpy(arr)) for c in checkers.values()]
        assert values[0]==values[1]
        if name=='intact':assert values[0]==(0,0)
        elif name=='missing':assert values[0]==(0,1)
        else:assert values[0]==(1,0)
        reports[name]=values[0]
    return reports


def until_fixed(model,graph,plan):
    # With fixed graph/weights, F(x) == x implies F^k(x) == x. This
    # optimization only shortens the generator; the full coverage check follows.
    scores=model.pointers(graph)
    state=model.initial(graph)
    for wave in range(BUDGET):
        later,_=model.propose(graph,scores,state,plan.initial_value,plan.increment)
        if torch.equal(later,state):return later,wave+1
        state=later
    return state,BUDGET


@torch.inference_mode()
def study(a,native):
    frozen=json.loads((a.weights/'results.json').read_bytes())
    shader=torch.mps.compile_shader((HERE/'coverage.metal').read_text())
    result=dict(architecture='source-closed first attribute saturation',torch_version=str(torch.__version__),
                neural_waves=BUDGET,repeats=a.repeats,samples={})
    for seed in (1703,1709):
        path=a.weights/f'pointer-{seed}.pt'
        require(hashlib.sha256(path.read_bytes()).hexdigest()==frozen['learned'][str(seed)]['weight_sha256'],
                'weights differ from the audited neural run')
        state=torch.load(path,map_location='cpu',weights_only=True)
        models={}
        for device in ('cpu','mps'):
            model=Pointer();model.load_state_dict(state);models[device]=model.eval().to(device)
        for name in a.cases:
            _,plan,domain,*_=load_case(a.ref/f'release-input-{name}/ingress.json')
            graph={k:torch.from_numpy(domain).to(k) for k in models}
            check={d:Checker(graph[d],plan,shader,native,d) for d in models}
            raw=np.array(frozen['learned'][str(seed)]['results'][name]['intact']['raw_tokens'])
            gold={d:torch.from_numpy(raw).to(d) for d in models}
            expected=(0,0)
            trial=dict(controls=negative_controls(check,raw),placements={})
            arms={'cpu1/cpu':('cpu',1,'cpu'),'cpu4/cpu':('cpu',4,'cpu'),'mps/mps':('mps',1,'mps'),
                  'mps/cpu':('mps',1,'cpu'),'cpu1/mps':('cpu',1,'mps'),'cpu1-absorbing/cpu':('cpu',1,'cpu')}
            def evaluate(placement,record):
                gen,threads,verify=arms[placement]
                torch.set_num_threads(threads)
                report=trial['placements'].setdefault(placement,dict(generation_us=[],verification_us=[],both_us=[]))
                def infer():
                    if placement=='cpu1-absorbing/cpu':return until_fixed(models[gen],graph[gen],plan)
                    return generate(models[gen],graph[gen],plan,'intact'),BUDGET
                # Timed separately from the uninterrupted end-to-end lane.
                start=perf_counter_ns()
                tokens,actual_waves=infer()
                if gen=='mps':torch.mps.synchronize()
                generated=(perf_counter_ns()-start)/1000
                np.testing.assert_array_equal(tokens.cpu().numpy(),raw)
                start=perf_counter_ns()
                verdict=check[verify](gold[gen])
                verified=(perf_counter_ns()-start)/1000
                assert verdict==expected
                start=perf_counter_ns()
                tokens,actual_waves=infer()
                verdict=check[verify](tokens)
                together=(perf_counter_ns()-start)/1000
                assert verdict==expected
                np.testing.assert_array_equal(tokens.cpu().numpy(),raw)
                if record:
                    assert report.setdefault('actual_waves',actual_waves)==actual_waves
                    for key,value in [('generation_us',generated),('verification_us',verified),('both_us',together)]:
                        report[key].append(value)
            labels=list(arms)
            for arm in labels:evaluate(arm,False)
            for j in range(a.repeats):
                order=labels[j%len(labels):]+labels[:j%len(labels)]
                for arm in (order if j%2==0 else order[::-1]):evaluate(arm,True)
            for report in trial['placements'].values():
                report['median_us']={k:median(v) for k,v in report.items() if k.endswith('_us')}
            trial.update(raw_token_count=len(raw),all_fields_identical=True,illegal=0,uncovered=0)
            result['samples'][f'{name}/{seed}']=trial
            print(name,seed,{k:int(v['median_us']['both_us']) for k,v in trial['placements'].items()},flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ref',type=Path);parser.add_argument('weights',type=Path);parser.add_argument('out',type=Path)
    parser.add_argument('--cases',nargs='+',default=['sum-bits','dot-product'])
    parser.add_argument('--repeats',type=int,default=20)
    a=parser.parse_args()
    require(torch.backends.mps.is_available() and os.getenv('PYTORCH_ENABLE_MPS_FALLBACK','0')=='0','native MPS required')
    with tempfile.TemporaryDirectory() as tmp:report=study(a,native_checker(Path(tmp)))
    a.out.write_text(json.dumps(report,indent=1)+'\n')
