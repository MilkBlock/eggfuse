"""Execute actor and verifier before each source Run's residual search."""
import argparse,json
from pathlib import Path
import numpy as np
from capture import read,inputs,load_catalog,verify,execute

def run_case(corpus,ref,reader,weights,case,out,variant):
    image,p,gold=inputs(corpus,ref,case);actor=read(weights)
    assert actor['schema']=='eggfuse.recurrent-leaf/v1'
    lib=load_catalog(image,p,ref/'sum-bits/program.json')
    cfg=dict(catalog=lib,weights=actor['weights'],rows=actor['rows'],hidden=actor['hidden'],ranks=actor['ranks'],
             intervention={'zero-latent':1,'swap-latent':2,'all-null':3}.get(variant,0),
             close=variant not in ('positive-only','shadow'),shadow=variant=='shadow')
    execute(image/'device.json',reader,ref/'ports-1703.pt',2048,2,out,neural=cfg)
    verify(out,gold,image)
    report=read(out/'run.json')
    with np.load(out/'neural-output.npz') as packet,np.load(out/'output.npz') as engine:
        status=packet['verdict'][:,:,0];won=packet['committed'];all_rhs=engine['runs'][:,1]
        np.testing.assert_array_equal(packet['raw'][:,:,-1]!=0,status!=0)
        assert np.all((won==0)|(status==1)) and np.all(won.sum(1)<=all_rhs)
        return dict(runs=report['completed'],total_rhs=int(all_rhs.sum()),raw=int((status!=0).sum()),accepted=int((status==1).sum()),
                    rejected=int((status==2).sum()),duplicate=int((status==3).sum()),won=int(won.sum()),fallback=int(all_rhs.sum()-won.sum()),
                    rows_won=won.sum(0).tolist(),both_won_runs=int((won.sum(1)==2).sum()),nonempty=int((all_rhs>0).sum()),
                    whole_nonempty=int(((all_rhs>0)&(all_rhs==won.sum(1))).sum()),inference_ms=report['inference_ms'],
                    exact=True,roles=report['execution_roles'])

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('corpus','ref','reader','weights','case','out'):p.add_argument(k,type=str if k=='case' else Path)
    p.add_argument('--variant',choices=('intact','zero-latent','swap-latent','all-null','positive-only','shadow'),default='intact')
    a=p.parse_args()
    r=run_case(a.corpus,a.ref,a.reader,a.weights,a.case,a.out,a.variant)
    (a.out/'acceptance.json').write_text(json.dumps(r,indent=1)+'\n')
    print(r,flush=True)
