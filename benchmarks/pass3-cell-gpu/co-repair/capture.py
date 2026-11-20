"""Capture exact dynamic producer ports, source Spine pivot and individual union wakeups."""
import argparse,json
from pathlib import Path
from collect import read
from device import execute_case

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for k in ('corpus','reference','weights','out'):parser.add_argument(k,type=Path)
    a=parser.parse_args();a.out.mkdir(exist_ok=True,parents=True)
    cases=read(a.corpus/'collection.json')
    for case,e in cases.items():
        if 'error' in e:raise ValueError(e)
        dest=a.out/case
        if dest.exists():raise FileExistsError(dest)
        r=execute_case(a.corpus,a.reference,a.weights,case,dest,trace=True)
        print(case,r['completed'],r['co_repair']['counters'][12],flush=True)
