"""On-device recurrent root and pending child generation before ordered Pass 3 publication."""
import argparse
from pathlib import Path
from tempfile import TemporaryDirectory

from capture import execute, inputs, load_catalog, read, verify
from compound_model import compiled_actions


def run(a):
    image,program,gold=inputs(a.corpus,a.ref,a.case)
    donor=a.ref/'sum-bits/program.json';model=read(a.checkpoint)
    entries=load_catalog(image,program,donor)
    joins,tails,wires=compiled_actions(read(donor),model.get("three_step",[]))
    if model['joins']!=list(map(list,joins)) or model.get('tails',tails)!=tails or model.get('wires',wires)!=wires:
        raise ValueError("policy uses different Bake wiring")
    cfg=dict(catalog=entries,rows=2,hidden=8,ranks=8,waves=2,weights=model['roots'],complete_residual=not a.no_exact,
             compound=dict(named_boundary=model.get("named_boundary",False),joins=joins,tails=tails,wires=wires,child=model['child'],batch=a.mode=='batch'))
    from chain_check import serial_compiler
    with TemporaryDirectory() as tmp:
        execute(image/'device.json',a.reader,a.ref/'ports-1703.pt',2048,2,a.out,neural=cfg,count_work=True,
                serial_compile=serial_compiler(Path(tmp)) if a.serial_cpu else None)
    if not a.no_exact:verify(a.out,gold,image)
    print(read(a.out/'run.json')['execution_roles'],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('corpus','ref','reader','checkpoint','out'):p.add_argument(k,type=Path)
    p.add_argument('--case',default='sum-bits');p.add_argument('--mode',choices=('batch','wave'),default='batch')
    p.add_argument('--serial-cpu',action='store_true')
    p.add_argument('--no-exact',action='store_true');run(p.parse_args())
