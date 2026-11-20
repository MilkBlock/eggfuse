"""Produce per-window training labels from real, unpruned, ordered device repairs."""
import argparse,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'co-repair'))
from device import execute_case
from collect import read

def policy(budget=32,window=32):
    return dict(budget=budget,window=window,capture=True,weights=[0]*6,bias=0,build_price=1)

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ('corpus','reference','weights','out'):p.add_argument(k,type=Path)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    for n in read(a.corpus/'collection.json'):
        r=execute_case(a.corpus,a.reference,a.weights,n,a.out/n,region=policy())
        print(n,r['completed'],r['state'][55],flush=True)
