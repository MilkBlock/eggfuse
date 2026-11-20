"""Measure actual Graph.decode_fact invocations before exit/export, on the same accepted paths."""
import argparse,json
from pathlib import Path
from measure import HERE, variants, make_session, read, rpc


def run(a):
    a.catalog=read(HERE.parent/'higher-order-bake/catalog.json')
    a.out.mkdir(parents=True,exist_ok=False)
    saved=read(HERE/'incremental.json')
    report={}
    for key,accepted in saved.items():
        case,seed=key.split('/')
        p,req,_,_,_=make_session(a,case,int(seed))
        try:
            observations={}
            for name,prior in accepted.items():
                cfg=variants(a)[name]
                r=rpc(p,dict(req,audit=False,higher_config=cfg))
                assert r['state_sha']==prior['graph'] and r['runs']==prior['runs'] and r['higher']['boundary']==prior['boundary']
                observations[name]=dict(fact_decode_calls=r['inference_fact_decodes'],entry_row_reads_saved=prior['initial_row_decodes_saved'],graph=prior['graph'])
            report[key]=observations
        finally:p.stdin.close();p.wait()
    (a.out/'results.json').write_text(json.dumps(report,indent=1)+'\n')
    print({k:[v[n]['fact_decode_calls'] for n in ('leaf','delta')] for k,v in report.items()},flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for n in ('binary','ref','corpus','capture','train_capture','out'):ap.add_argument(n,type=Path)
    run(ap.parse_args())
