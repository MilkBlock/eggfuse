"""Compile weight tables once, then measure real generation and verification at two Q/K capacities."""
import argparse
from contextlib import ExitStack
import hashlib
import importlib.util
import json
from pathlib import Path
from statistics import median
import subprocess
from time import perf_counter_ns

import numpy as np

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('compact_benchmark',HERE.parent/'compact-recipes/study.py')
bench=importlib.util.module_from_spec(spec);spec.loader.exec_module(bench)


def write(path,data):
    path.write_text(json.dumps(data,separators=(',',':'))+'\n')
    return str(path)


def measure(case,seed,args):
    bundle=args.bundles/f'{case}-{seed}';program=bundle/'program.json'
    base=bench.read(bundle/'request.json')
    assert hashlib.sha256(program.read_bytes()).hexdigest()==base['source_sha256']
    for k in ('single_config','multi_weights','merge_config','root_config'):base[k]=str(bundle/base[k])
    root=bench.read(bundle/'root.json');base['root_config']=write(args.out/'root.json',dict(root,encoding='resident'))
    original=bench.read(bundle/'multi.json')
    w=((np.asarray(original['q'],np.float32)+np.asarray(original['k'],np.float32))*np.float32(.5)).tolist()
    tied=dict(original,q=w,k=w)
    inputs=({'tied3':tied} if args.packed_views==3 else {'tied':tied}) if args.packed else {'three':original,'tied':tied}
    weights={};tables={};offline={}
    for family,value in inputs.items():
        weights[family]=write(args.out/f'{case}-{seed}-{family}.json',value)
        table=args.out/f'{case}-{seed}-{family}.bin';start=perf_counter_ns()
        subprocess.run([args.build/'bake',weights[family],table],check=True)
        offline[family]=dict(compile_ms=(perf_counter_ns()-start)/1e6,bytes=table.stat().st_size,
                             hash=hashlib.sha256(table.read_bytes()).hexdigest())
        tables[family]=str(table)
    variants=[(f'{family}-{impl}',family,impl) for family in inputs for impl in ('weights','table','column')]
    if args.packed:
        variants=[(f'{family}-{impl}',family,impl) for family in inputs for impl in ('weights','table','packed')]
    report={};requests={}
    with bench.session(args.vanilla/'vanilla-audit',program) as run:gold=run(dict(audit=True))
    with ExitStack() as stack:
        infer=stack.enter_context(bench.session(args.build/'session',program,bundle/'plans.json'))
        vanilla=stack.enter_context(bench.session(args.vanilla/'vanilla',program))
        for name,family,impl in variants:
            request=dict(base,multi_weights=weights[family],
                         multi_mode='stackseal3xlearned' if family in ('three','tied3') else 'stackseallearned',
                         radius=2 if family=='three' else 0)
            if impl!='weights':request.update(baked_codes=tables[family],baked_row_index=impl=='column',packed_lookup=impl=='packed')
            output=infer(dict(request,audit=True))
            v=bench.compare(output,gold);report[name]=v
            if not v['aligned']:
                print(case,seed,name,'failed',v.get('error'),flush=True)
                continue
            assert v['neural_rhs']==v['rhs'] and v['direct_cells']>=.98*v['fresh']
            v['multi_work']=output['multi']['counts'];v['ms']=[]
            if impl!='weights':
                reference=report[family+'-weights']
                for field in ('commits','physical','multi','children','cells','neural_rhs','raw','rhs'):
                    assert v[field]==reference[field],(name,field)
            requests[name]=request
            del output
        order=['vanilla',*requests];report['vanilla']=dict(ms=[],rhs=gold['rhs_count'],runs=gold['runs'])
        for t in range(1+2*len(order)):
            position=t%len(order);seq=order[position:]+order[:position]
            for name in seq if (t//len(order))%2==0 else reversed(seq):
                got=vanilla({}) if name=='vanilla' else infer(dict(requests[name],audit=False))
                assert got['state_sha']==gold['state_sha']
                if name!='vanilla':assert got['root_recipe']['allocated']==report[name]['root_allocated']
                if t:report[name]['ms'].append(got['ms'])
        for name in order:report[name]['median_ms']=median(report[name]['ms'])
        # Mutate a weight checksum and a code byte independently. Each fresh reader must reject it.
        if case=='sum-bits' and seed==1703 and not args.packed:
            request=dict(requests['three-table'])
            errors={}
            for index,label in [(8,'weights'),(-1,'table')]:
                corrupt=bytearray(Path(request['baked_codes']).read_bytes());corrupt[index]^=1
                path=args.out/f'bad-{label}.bin';path.write_bytes(corrupt)
                trial=subprocess.run([args.build/'session',program,bundle/'plans.json'],
                   input=json.dumps(dict(request,baked_codes=str(path)))+'\n',text=True,capture_output=True)
                assert trial.returncode and 'incompatible learned port table' in trial.stderr
                errors[label]=True
            report['corruption_rejected']=errors
    report['offline_compile']=offline
    print(case,seed,[(k,round(report[k]['median_ms'],1)) for k in order],flush=True)
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('build','vanilla','bundles','out'):p.add_argument(key,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','jacobi-1d'])
    p.add_argument('--packed',action='store_true')
    p.add_argument('--packed-views',type=int,choices=(1,3),default=1)
    p.add_argument('--seeds',type=int,nargs='+',default=[1703,1709])
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False);result={}
    for case in a.cases:
        for seed in a.seeds:
            result[f'{case}/{seed}']=measure(case,seed,a)
            (a.out/'results.json').write_text(json.dumps(result,indent=1)+'\n')
