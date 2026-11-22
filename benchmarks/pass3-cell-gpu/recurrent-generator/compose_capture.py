"""Record source-visible producer RHS ordinals and their precise effect ports for each committed Spine input."""
import argparse
from tempfile import TemporaryDirectory
from pathlib import Path
import numpy as np
from capture import execute, inputs, load_catalog, read, verify

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('corpus','ref','reader','out'):p.add_argument(k,type=Path)
    p.add_argument('--splits',nargs='+',choices=('train','development','heldout','anchor'),default=['heldout','anchor'])
    p.add_argument('--serial-cpu',action='store_true')
    from chain_check import serial_compiler
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    for case,info in read(a.corpus/'collection.json').items():
        if info['split'] not in a.splits:continue
        image,program,gold=inputs(a.corpus,a.ref,case)
        entries=load_catalog(image,program,a.ref/'sum-bits/program.json')
        dest=a.out/case
        with TemporaryDirectory() as tmp:
            execute(image/'device.json',a.reader,a.ref/'ports-1703.pt',2048,2,dest,
                neural=dict(catalog=entries,rows=2,ranks=8,hidden=8,capture=True,capture_edges=True,capture_boundaries=True),
                serial_compile=serial_compiler(Path(tmp)) if a.serial_cpu else None)
        verify(dest,gold,image)
        with np.load(dest/'neural-inputs.npz') as z,np.load(dest/'output.npz') as g:
            consumed,pub,rhs=z['consumed'],z['publications'],g['rhs']
            children=np.flatnonzero(consumed)
            assert np.array_equal(consumed>0,z['pivot']>0)
            parents=pub[consumed[children]-1,0]-1
            assert (parents>=0).all() and (rhs[parents,0]<rhs[children,0]).all()
            first=np.cumsum(g['runs'][:,1])-g['runs'][:,1]
            for run,offset,_,rid,child,_ in g['resumes']:
                i=first[run-1]+offset-1
                assert consumed[i]>0 and rhs[pub[consumed[i]-1,0]-1,1]==rid and rhs[i,1]==child
            print(case,len(children),'source-visible parent ports checked',flush=True)
