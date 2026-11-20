"""Offline compilation of the checked native action library and learned weights."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

GEN=Path(__file__).resolve().parents[1]/'recurrent-generator'
sys.path.insert(0,str(GEN))
from catalog import load_catalog,read


def compile_plan(program,image,donor,checkpoint):
    model=read(checkpoint)
    entries=load_catalog(image,program,donor)
    assert model['schema']=='eggfuse.one-emission/v1'
    leaf_count=len(read(donor)['spine_blocks']['entries'])
    expected=[[leaf_count+i,j['left'],j['output'],j['right']] for i,j in enumerate(read(donor)['iterative_bake']['joins'])
              if j['left']<leaf_count and j['right']<leaf_count]
    assert model['joins']==expected
    return dict(digest=hashlib.sha256(program.read_bytes()).hexdigest(),entries=[[rid,pivot,table] for rid,pivot,_,table in entries],
        root=model['root'],head=model['head'],sets=read(image/'device.json')['sets'],joins=expected)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ('program','image','donor','checkpoint','out'):p.add_argument(k,type=Path)
    a=p.parse_args()
    a.out.write_text(json.dumps(compile_plan(a.program,a.image,a.donor,a.checkpoint),separators=(',',':')))
