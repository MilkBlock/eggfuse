"""Freeze the trained conditional library and transfer its exact interfaces to larger source Pass 3 programs."""
import argparse
from contextlib import ExitStack
import hashlib
import importlib.util
import json
from pathlib import Path
from statistics import median

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('vanilla_contract',HERE.parent/'compact-recipes/study.py')
common=importlib.util.module_from_spec(spec);spec.loader.exec_module(common)
read=common.read


def study(a):
    a.out.mkdir(parents=True,exist_ok=False)
    results={};catalog=read(HERE/'catalog.json');grown=read(HERE/'growth.json')['second_round'];pairs=read(HERE/'pair-catalog.json')['pairs']
    donor=read(a.ref/'sum-bits/program.json')['recipe']
    for case in a.cases:
        for seed in a.seeds:
            bundle=a.bundles/f'{case}-{seed}';program=bundle/'program.json';target=read(program)['recipe']
            assert donor['tables']==target['tables']
            # Freeze the training interfaces and transfer only unchanged source programs at those slots.
            for rule in set([r for r,e in grown]+[r for pair in pairs for r in pair]+[catalog['family'][k] for k in ('eq','gt')]):
                assert all(donor['rules'][rule][k]==target['rules'][rule][k] for k in ('query','effects','slots'))
            request=read(bundle/'request.json')
            assert request['source_sha256']==hashlib.sha256(program.read_bytes()).hexdigest()
            for k in ('single_config','multi_weights','merge_config','root_config'):request[k]=str(bundle/request[k])
            with common.session(a.vanilla/'vanilla-audit',program) as run:gold=run(dict(audit=True))
            plans={'prior':{},'subtuple':dict(higher_config=dict(family=catalog['family'],parents=grown,mode='baked',recursive=True)),
                   'sibling':dict(guarded_pairs=dict(pairs=pairs,sharing='verified'))}
            plans['both']=dict(plans['subtuple'],**plans['sibling'])
            report={'vanilla':dict(rhs=gold['rhs_count'],runs=gold['runs'],state_sha=gold['state_sha'],ms=[])}
            with ExitStack() as stack:
                run=stack.enter_context(common.session(a.binary,program,bundle/'plans.json'))
                vanilla=stack.enter_context(common.session(a.vanilla/'vanilla',program))
                for label,config in plans.items():
                    marked=dict(config)
                    if 'higher_config' in marked:marked['higher_config']=dict(marked['higher_config'],profile=True)
                    full=run(dict(request,**marked,audit=True));v=common.compare(full,gold);assert v['aligned'],(case,seed,label,v)
                    assert v['neural_rhs']==v['rhs']==v['applied']==gold['rhs_count']
                    h=full.get('higher');pa=full.get('guarded_pairs')
                    report[label]=dict(v,ms=[],subtuple_children=sum(h['counts'][11:13]) if h else 0,
                         inherited_requests=h['counts'][13] if h else 0,max_chain=h['max_chain'] if h else 0,
                         skipped_pair_program_calls=pa['reused_sibling_runs'] if pa else 0,
                         skipped_raw_tuples=pa['shared_raw_tuples'] if pa else 0,
                         accepted_shared=pa['committed'] if pa else 0,cross_stage_shared=pa['cross_stage'] if pa else 0)
                names=list(report)
                for turn in range(a.repeats+1):
                    seq=names[turn%len(names):]+names[:turn%len(names)]
                    for label in (seq if turn%2 else seq[::-1]):
                        got=vanilla({}) if label=='vanilla' else run(dict(request,**plans[label],audit=False))
                        assert got['state_sha']==gold['state_sha'] and got['runs']==gold['runs']
                        if turn:report[label]['ms'].append(got['ms'])
            for arm in report.values():arm['median_ms']=median(arm['ms'])
            results[f'{case}/{seed}']=report;(a.out/'results.json').write_text(json.dumps(results,indent=1)+'\n')
            print(case,seed,[(n,round(v['median_ms'],1)) for n,v in report.items()],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('binary','vanilla','ref','bundles','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['jacobi-1d','conjugate-gradient'])
    p.add_argument('--seeds',nargs='+',type=int,default=[1703,1709])
    p.add_argument('--repeats',type=int,default=6)
    study(p.parse_args())
