"""Exercise each observed recipe with reference-selected roots; measure learned issuance separately."""
import argparse
from pathlib import Path
from tempfile import TemporaryDirectory
import json

import numpy as np
import torch
from capture import inputs,load_catalog,read,verify,execute
from chain_check import serial_compiler
from compound_model import compiled_actions
from compound_boundaries import boundaries


def main(a):
    torch.set_num_threads(1)
    e=a.exp
    ref=e/'pass3-release-reproduction-20261120'
    donor=ref/'sum-bits/program.json'
    image, program, gold=inputs(e/'repair-bake-families-20261120',ref,a.case)
    policy=read(a.policy)
    joins,tails,wires=compiled_actions(read(donor),policy['three_step'])
    entries=load_catalog(image,program,donor)
    split=read(e/'repair-bake-families-20261120/collection.json')[a.case]['split']
    capture=e/'compound-boundary-capture-v1'/a.case
    with np.load(capture/'neural-inputs.npz') as z:
        witnesses=z['witnesses'];pub=z['publications'];features=z['features']
    target_file=e/'compound-boundary-targets-v1'/split/(a.case+'.npz')
    with np.load(target_file) as z:
        targets=z['targets']
        saved={k:z[k] for k in ('imports','exports','outside_uses')}
    with np.load(gold/'output.npz') as z: rhs=z['rhs']
    a.out.mkdir(parents=True,exist_ok=False)
    boundary=boundaries(targets,pub,witnesses)
    for key,records in boundary.items():
        np.testing.assert_array_equal(records,saved[key])
    np.savez_compressed(a.out/'boundary-targets.npz',targets=targets,publications=pub,**boundary)
    report={}
    for unit in policy['three_step']:
        idx=next(i for i,join in enumerate(joins) if join[0]==unit)
        paths=np.flatnonzero(targets[:,3]==unit)
        if not len(paths):continue
        raw=np.zeros((len(features),4,12),dtype=np.float32)
        issued={}
        for index in paths:
            run,leaf,rank,_,depth,*path=map(int,targets[index])
            address=int(features[run-1,leaf*8+rank,0])
            t=run-1
            if np.any(raw[t,:2,9]==address+1):continue
            lane=int(np.count_nonzero(raw[t,:2,11]))
            if lane==2:continue
            raw[t,lane,8:]=[leaf+1,address+1,rank+1,1]
            raw[t,2+lane,8:]=[joins[idx][3]+1,2*t+lane+1,wires[idx]+1,1]
            issued[t,lane]=int(index)
        cfg=dict(catalog=entries,rows=2,ranks=8,hidden=8,waves=2,capture_boundaries=True,capture_edges=True,weights=policy['roots'],
                 compound=dict(joins=joins,tails=tails,wires=wires,child=policy['child'],batch=True,
                               named_boundary=True,replay=raw))
        with TemporaryDirectory() as tmp:
            dest=Path(tmp)/'run'
            execute(image/'device.json',e/'rotary-axes-20261119/packed-1703/final.pt',
                    ref/'ports-1703.pt',2048,2,dest,neural=cfg,count_work=True,
                    serial_compile=serial_compiler(Path(tmp)))
            verify(dest,gold,image)
            with np.load(dest/'boundary-output.npz') as actual:
                np.testing.assert_array_equal(actual['publications'],pub)
                np.testing.assert_array_equal(actual['witnesses'],witnesses)
            complete=side=outside=0
            corrupt=None
            with np.load(dest/'compound-output.npz') as z:
                for (t,lane),index in issued.items():
                    depth=int(targets[index,4])
                    path=targets[index,5:5+depth]
                    for hop,ordinal in enumerate(path[1:]):
                        bank='claims' if hop==0 else 'tails' if hop==1 else f'hop_{hop+1}'
                        claim=z[bank][t,lane]
                        if not claim[7]:break
                        assert claim[7]==ordinal and claim[2]==path[hop]
                        refs=witnesses[ordinal-1]
                        assert refs[0,0]==claim[3]+1 and refs[0,2]==claim[4]
                        for pos in np.flatnonzero(refs[1:,0])+1:
                            named=z['named_inputs'][hop,t,lane,pos-1]
                            np.testing.assert_array_equal(named,refs[pos,:2])
                            side+=1
                            if corrupt is None and hop==depth-2:
                                corrupt=(t,lane,hop,int(pos),int(ordinal))
                    else:
                        complete+=1
                        outside+=int(np.sum(boundary['outside_uses'][:,0]==index))
            if corrupt is not None:
                t,lane,hop,pos,ordinal=corrupt
                stale_build=Path(tmp)/"stale-build"
                stale_build.mkdir()
                build=serial_compiler(stale_build)
                def stale_version(shader):
                    target="ref[1]=meta[6*row+4];"
                    assert shader.count(target)==1
                    return build(shader.replace(target,target+
                        f"if(id=={hop}*COM_LAYER+{2*t+lane} && pos=={pos})ref[1]--;"))
                fork=Path(tmp)/'stale'
                execute(image/'device.json',e/'rotary-axes-20261119/packed-1703/final.pt',
                        ref/'ports-1703.pt',2048,2,fork,neural=cfg,count_work=True,serial_compile=stale_version)
                verify(fork,gold,image)
                with np.load(dest/'compound-output.npz') as full,np.load(fork/'compound-output.npz') as stale:
                    for key in ('claims','tails',*[k for k in full if k.startswith("hop_")]):
                        expected=full[key][:,:,7].copy()
                        if key==('claims' if hop==0 else 'tails' if hop==1 else f'hop_{hop+1}'):
                            assert expected[t,lane]==ordinal
                            expected[t,lane]=0
                        np.testing.assert_array_equal(expected,stale[key][:,:,7])
                with np.load(fork/'boundary-output.npz') as actual:
                    np.testing.assert_array_equal(actual['witnesses'],witnesses)
                    np.testing.assert_array_equal(actual['publications'],pub)
            report[unit]=dict(paths=len(paths),issued=len(issued),complete=complete,
                              named_side_reads=side,stale_forks=int(corrupt is not None),outside_uses_on_completed=outside)
            if not complete:raise ValueError(f'no complete instance of unit {unit}')
        (a.out/'recipes.json').write_text(json.dumps(report,indent=2)+'\n')
        print(unit,report[unit],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('exp','policy','out'):p.add_argument(name,type=Path)
    p.add_argument('--case',default='affine-twins')
    main(p.parse_args())
