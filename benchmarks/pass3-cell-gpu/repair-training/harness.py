import gzip
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
from time import perf_counter_ns

import torch

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'native-forest'))
from certificate import Generator

EMPTY=dict(first=[],bias=[],last=[],offset=[])
def read(path):return json.loads(path.read_bytes())

def paths(corpus,ref,name):
    if name in ('sum-bits','dot-product'):
        return ref/name/'program.json',ref/f'release-input-{name}',ref/f'oracle-{name}',corpus/name/'observation'
    case=corpus/name
    return case/'program.json',case/'input',case/'reference',case/'observation'

def family_key(program,template,table):
    # Reserve the whole typed LHS/effects family across all programs; avoid using
    # the schedule-specific numeric template ordinal as a train/test identity.
    if template<len(program['templates']):
        r=program['recipe']['rules'][program['templates'][template]['rule']]
        obj=[r['query'],r['effects']]
    else:obj=['input',program['recipe']['tables'][table]['name']]
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',',':')).encode()).hexdigest()

class Session:
    def __init__(self,binary,program,image,checkpoint,out):
        self.gen=None
        args=[binary,program]
        if checkpoint:
            self.gen=Generator(program,image,torch.load(checkpoint,weights_only=True,map_location='cpu'),'cpu')
            roots,_,_=self.gen.emit()
            layout=out/'layout.json';out.mkdir(parents=True,exist_ok=True)
            layout.write_text(json.dumps(dict(schema='eggfuse.sealed-forest/v1',program_sha256=self.gen.digest,
                                             roots=roots.tolist(),catalog=self.gen.catalog,children=[])))
            args.append(layout)
        self.proc=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE)
    @torch.inference_mode()
    def run(self,mode,weights,tables,audit):
        q=dict(mode=mode,weights=weights,tables=tables,audit=audit)
        pipe=self.proc.stdin;out=self.proc.stdout
        pipe.write((json.dumps(q,separators=(',',':'))+'\n').encode());pipe.flush()
        if out.readline()!=b'ready\n':raise RuntimeError(('session failed before generation',self.proc.poll()))
        start=perf_counter_ns()
        words=self.gen.emit()[1].numpy().astype('<i4',copy=False).tobytes() if self.gen else b''
        emitted=perf_counter_ns()
        pipe.write(struct.pack('<I',len(words))+words);pipe.flush()
        record=json.loads(out.readline())
        end=perf_counter_ns()
        result=json.loads(out.readline())
        result.update(record,whole_ms=(end-start)/1e6,generation_ms=(emitted-start)/1e6)
        return result
    def close(self):
        self.proc.stdin.close();code=self.proc.wait()
        if code:raise RuntimeError(('native build failed',code))

def verify(result,gold,baseline_unions=None):
    assert result['state_sha']==hashlib.sha256((gold/'state.json').read_bytes()).hexdigest()
    for k in ('rhs','writes','resumes'):assert result[k]==read(gold/f'{k}.json'),k
    assert len(result['rhs'])==result['runs']
    if baseline_unions is not None:assert result['ordered_unions']==baseline_unions
    if result['forest'] is not None:
        assert result['forest']['rhs']>0 and result['forest']['assisted']

def capture(a):
    torch.set_num_threads(1);a.out.mkdir(parents=True,exist_ok=False)
    collection=read(a.corpus/'collection.json');report={}
    for name,info in collection.items():
        program,img,gold,ob=paths(a.corpus,a.ref,name);path=a.out/name
        engine=Session(a.binary,program,img,a.weights,path)
        try:r=engine.run('capture',EMPTY,[],True)
        finally:engine.close()
        source_events=read(ob/'events.json')
        unions=[event for run in source_events for event in run if event[0]=='union']
        verify(r,gold,unions)
        parsed=read(program);families={}
        for row in r['trial']['events']:
            idx=(row['template'],row['table'])
            if idx not in families:families[idx]=family_key(parsed,*idx)
            row['family']=families[idx];row['table_name']=parsed['recipe']['tables'][row['table']]['name']
        with gzip.open(path/'events.json.gz','wt') as f:json.dump(r['trial']['events'],f,separators=(',',':'))
        forest=r['forest'];report[name]=dict(split=info['split'],program=parsed['sha256'],runs=r['runs'],unions=r['unions'],
                      source_neural_rhs=len(forest['children']),source_total_rhs=forest['rhs'],events=len(r['trial']['events']),
                      eligible=r['trial']['counts']['fast_eligible'],weighted_eligible=r['trial']['counts']['eligible_port_work'])
        print(name,report[name],flush=True)
        (a.out/'capture.json').write_text(json.dumps(report,indent=1)+'\n')

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser()
    for k in ('corpus','ref','weights','binary','out'):p.add_argument(k,type=Path)
    capture(p.parse_args())
