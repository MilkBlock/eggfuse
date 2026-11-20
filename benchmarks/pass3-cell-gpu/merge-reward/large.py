"""Transfer a frozen merge gate to a larger actual eggcc Pass 3 with a separate vanilla executable."""
import argparse
from contextlib import ExitStack
from pathlib import Path
import hashlib
import importlib.util
from statistics import median
from native import BASE,digest,higher,save
local_spec=importlib.util.spec_from_file_location('frozen_gate_evaluation',Path(__file__).with_name('evaluate.py'))
local=importlib.util.module_from_spec(local_spec);local_spec.loader.exec_module(local)
summarize=local.summarize

spec=importlib.util.spec_from_file_location('vanilla_comparison', BASE.parent/'compact-recipes/study.py')
reference=importlib.util.module_from_spec(spec);spec.loader.exec_module(reference)
read=reference.read


def measure(a):
    a.out.mkdir(parents=True,exist_ok=False)
    catalog=read(BASE/'catalog.json');grown=read(BASE/'growth.json')['second_round']
    donor=read(a.exp/'pass3-atlas-integration-20261120/sum-bits/program.json')['recipe']
    policies=read(a.policies)['policies'];saved={}
    for case in a.cases:
        b=a.exp/'compact-holdouts-20261121-v1'/f'{case}-{a.seed}'
        program=b/'program.json';target=read(program)['recipe']
        assert target['tables']==donor['tables']
        for rid in {i for i,_ in grown}|{catalog['family'][k] for k in ('eq','gt')}:
            for field in ('query','effects','slots'):
                assert target['rules'][rid][field]==donor['rules'][rid][field]
        req=read(b/'request.json');assert req['source_sha256']==hashlib.sha256(program.read_bytes()).hexdigest()
        for k in ('single_config','multi_weights','merge_config','root_config'):req[k]=str(b/req[k])
        vanilla=a.exp/'compact-vanilla-20261121'
        with reference.session(vanilla/'vanilla-audit',program) as run:gold=run(dict(audit=True))
        names=['leaf','all','real-prior','synthetic-prior','real-settled','real-charged','synthetic-charged']
        trials={'vanilla':{'ms':[]}};configs={}
        with ExitStack() as stack:
            infer=stack.enter_context(reference.session(a.binary,program,b/'plans.json'))
            pure=stack.enter_context(reference.session(vanilla/'vanilla',program))
            for name in names:
                mode=0 if name=='leaf' else 3
                gate=None if name in ('leaf','all') else policies[f'{a.seed}-{name}']['gate']
                cfg=dict(family=catalog['family'],parents=grown,recursive=True,mode='baked',composed=mode,macro_policy=gate)
                configs[name]=cfg
                out=infer(dict(req,higher_config=dict(cfg,profile=True),audit=True))
                v=reference.compare(out,gold);h=out['higher']
                assert v['aligned'] and v['neural_rhs']==v['rhs']==gold['rhs_count'] and v['direct_cells']*100>=98*v['fresh']
                ep=dict(state=out['state_sha'],winner=digest(h['winners']),allocations=digest(out['cell_ids']),
                        rhs=digest(out['rhs']),writes=digest(out['writes']),spine=digest(out['resumes']),unions=digest(gold['unions']))
                item=dict(charges=h['charges'],boundary=h['boundary'],children=len(h['winners']),rhs=v['rhs'],direct=v['direct_cells'],
                          fresh=v['fresh'],endpoints=ep,runs=gold['runs'],chain=h['max_chain'])
                trials[name]=summarize(item,gate)
                assert trials[name]['endpoint_digest']==trials['leaf']['endpoint_digest']
            order=list(trials)
            for lap in range(a.repeats+1):
                k=lap%len(order);seq=order[k:]+order[:k]
                for name in seq if lap%2 else reversed(seq):
                    v=pure({}) if name=='vanilla' else infer(dict(req,higher_config=configs[name],audit=False))
                    assert v['state_sha']==gold['state_sha'] and v['runs']==gold['runs']
                    if lap:trials[name]['ms'].append(v['ms'])
        for arm in trials.values():arm['median_ms']=median(arm['ms'])
        saved[f'{case}/{a.seed}']=trials;save(a.out/'results.json',saved)
        print(case,{k:round(v['median_ms'],2) for k,v in trials.items()},flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','binary','policies','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['jacobi-1d']);p.add_argument('--seed',type=int,default=1703)
    p.add_argument('--repeats',type=int,default=6);measure(p.parse_args())
