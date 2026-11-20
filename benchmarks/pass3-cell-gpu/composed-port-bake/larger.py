"""Check the frozen SubTuple boundary on a larger held-out source with independent vanilla."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
from statistics import median
from contextlib import ExitStack
from measure import HERE,variants,fingerprint
from holdout import common


def run(a):
    a.out.mkdir(parents=True,exist_ok=False)
    a.catalog=common.read(HERE.parent/'higher-order-bake/catalog.json')
    configs={k:v for k,v in variants(a).items() if k in ('leaf','inline','delta')}
    rows={}
    for case in a.cases:
        for seed in a.seeds:
            folder=a.bundles/f'{case}-{seed}'
            program=folder/'program.json';req=common.read(folder/'request.json')
            assert req['source_sha256']==hashlib.sha256(program.read_bytes()).hexdigest()
            for k in ('single_config','multi_weights','merge_config','root_config'):req[k]=str(folder/req[k])
            with common.session(a.vanilla/'vanilla-audit',program) as execute:gold=execute(dict(audit=True))
            results={}
            with ExitStack() as stack:
                source=stack.enter_context(common.session(a.vanilla/'vanilla',program))
                neural=stack.enter_context(common.session(a.binary,program,folder/'plans.json'))
                identity=None
                for name,cfg in configs.items():
                    r=neural(dict(req,audit=True,higher_config=dict(cfg,profile=True)))
                    checked=common.compare(r,gold);assert checked['aligned']
                    h=r['higher'];actual=fingerprint([h['winners'],h['transactions']['source_order'],r['root_recipe']['commits'],r['root_recipe']['fresh'],r['single']['committed']])
                    if identity is None:identity=actual
                    assert actual==identity
                    z=h['boundary'];results[name]=dict(rhs=checked['rhs'],neural_rhs=checked['neural_rhs'],
                        direct=checked['direct_cells'],fresh_cells=checked['fresh'],graph=gold['state_sha'],checks=checked['checks'],
                        identity=identity,boundary=z,delta=h['delta'],max_chain=h['max_chain'],wins=sum(h['counts'][11:13]),
                        initial_row_decodes_saved=z[2]-z[5],net_entry_after_rebuild=z[2]-z[3]-z[1],ms=[])
                    assert checked['rhs']==checked['neural_rhs'] and checked['direct_cells']*100>=98*checked['fresh']
                results['vanilla']=dict(rhs=gold['rhs_count'],graph=gold['state_sha'],ms=[])
                arms=list(results)
                for turn in range(a.repeats+1):
                    order=arms[turn%4:]+arms[:turn%4]
                    for name in order if turn%2 else order[::-1]:
                        r=source({}) if name=='vanilla' else neural(dict(req,audit=False,higher_config=configs[name]))
                        assert r['state_sha']==gold['state_sha'] and r['runs']==gold['runs']
                        if turn:results[name]['ms'].append(r['ms'])
            for v in results.values():v['median_ms']=median(v['ms'])
            rows[f'{case}/{seed}']=results
            (a.out/'results.json').write_text(json.dumps(rows,indent=1)+'\n')
            print(case,seed,[(k,round(v['median_ms'],2)) for k,v in results.items()],flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('binary','bundles','vanilla','out'):ap.add_argument(name,type=Path)
    ap.add_argument('--cases',nargs='+',default=['jacobi-1d'])
    ap.add_argument('--seeds',nargs='+',type=int,default=[1703,1709]);ap.add_argument('--repeats',type=int,default=8)
    run(ap.parse_args())
