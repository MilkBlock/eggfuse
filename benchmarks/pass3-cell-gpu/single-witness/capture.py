"""Produce training labels after an independent full-source Cell execution."""
import argparse,json,os,subprocess
from pathlib import Path

def read(path):return json.loads(Path(path).read_bytes())
def dump(path,x):Path(path).write_text(json.dumps(x,separators=(',',':'))+'\n')
def paths(corpus,ref,name):
    if name in ('sum-bits','dot-product'):return ref/name/'program.json',ref/f'events-{name}'
    return corpus/name/'program.json',corpus/name/'observation'

def launch(binary,program,out,policy=None):
    env=dict(os.environ)
    if policy:env['EGGFUSE_SINGLE_POLICY']=str(policy)
    else:env.pop('EGGFUSE_SINGLE_POLICY',None)
    subprocess.run([str(binary),'--program',str(program),'--output',str(out),'--audit-events'],env=env,check=True,stdout=subprocess.DEVNULL)

def aligned(got,gold):
    for k in ('rhs','writes','resumes','state'):
        p=gold/f'{k}.json'
        if p.is_file():
            a,b=read(got/f'{k}.json'),read(p)
            if a!=b:
                if isinstance(a,list) and isinstance(b,list):
                    first=next((i+1 for i,(x,y) in enumerate(zip(a,b)) if x!=y),min(len(a),len(b))+1)
                    raise ValueError(f'{k}: first differs at {first}, lengths {len(a)} vs {len(b)}')
                raise ValueError(f'{k}: graph mismatch')
    a,b=read(got/'report.json')['steps'],read(gold/'report.json')['steps']
    assert [ (v['ordinal'],v['ruleset'],v['epoch'],v['executed_bindings']) for v in a]==[(v['ordinal'],v['ruleset'],v['epoch'],v['executed_bindings']) for v in b]
    if (gold/'events.json').is_file():
        keep=lambda f:[[e for e in row if e[0] in ('union','resume','write')] for row in read(f)]
        assert keep(got/'events.json')==keep(gold/'events.json')

def capture(a):
    a.out.mkdir(parents=True,exist_ok=False);cfg=a.out/'capture.json';dump(cfg,dict(mode='capture',residual=True))
    for n in a.cases:
        program,gold=paths(a.corpus,a.ref,n);folder=a.out/n
        launch(a.build/'runtime',program,folder,cfg);aligned(folder,gold)
        report=read(folder/'report.json');state=report['single_witness']
        assert state['rhs']==sum(s['executed_bindings'] for s in report['steps'])
        print(n,state['rhs'],len(state['committed']),state['work'],len(state['features']),len(state['events']),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('corpus','ref','build','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','affine-twins','clamped-ramp','segmented-prefix','window-laplacian'])
    capture(p.parse_args())
